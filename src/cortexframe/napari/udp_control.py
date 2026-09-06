"""UDP control server for mpep-compatible experiment commands."""

from __future__ import annotations

import datetime
import socket
import struct
import threading
import time
from pathlib import Path
from dataclasses import dataclass
from typing import TYPE_CHECKING

from qtpy.QtCore import QTimer

from cortexframe import bids, shared_memory
from cortexframe.napari import controls

if TYPE_CHECKING:
    from cortexframe.napari.widget import CortexFrameWidget


@dataclass
class UdpControlServer:
    """Threaded UDP server state.

    Attributes
    ----------
    thread : threading.Thread
        Background thread that processes UDP datagrams.
    stop_event : threading.Event
        Event used to request clean server shutdown.
    socket_handle : socket.socket
        Bound UDP socket used for receive and echo responses.
    """

    thread: threading.Thread
    stop_event: threading.Event
    socket_handle: socket.socket


def start_udp_control_server(widget: "CortexFrameWidget") -> None:
    """Start the napari-side UDP control server for one acquisition run.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning runtime state and shared-memory command access.

    Returns
    -------
    None
        This helper starts a background thread and stores it on the widget.
    """

    if not widget._config.system.udp_control_enabled:
        return
    if widget._udp_server is not None:
        return

    host = "0.0.0.0"
    port = int(widget._config.system.udp_control_port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(0.25)

    stop_event = threading.Event()
    thread = threading.Thread(
        target=_udp_server_loop,
        args=(widget, sock, stop_event),
        daemon=True,
    )
    widget._udp_server = UdpControlServer(
        thread=thread, stop_event=stop_event, socket_handle=sock
    )
    thread.start()
    _log(widget, f"[viewer] UDP control server listening on {host}:{port}.")


def stop_udp_control_server(widget: "CortexFrameWidget") -> None:
    """Stop the napari-side UDP control server.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning runtime state and UDP server handle.

    Returns
    -------
    None
        This helper requests shutdown and closes socket resources.
    """

    server = widget._udp_server
    widget._udp_server = None
    if server is None:
        return
    server.stop_event.set()
    try:
        server.socket_handle.close()
    except OSError:
        pass
    server.thread.join(timeout=1.0)
    QTimer.singleShot(0, lambda: controls.refresh_control_locks(widget))
    _log(widget, "[viewer] UDP control server stopped.")


def _udp_server_loop(
    widget: "CortexFrameWidget", sock: socket.socket, stop_event: threading.Event
) -> None:
    """Serve UDP datagrams and translate mpep commands into save commands.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning runtime state and shared-memory command access.
    sock : socket.socket
        Bound UDP socket used for receive/send.
    stop_event : threading.Event
        Event used to request loop termination.

    Returns
    -------
    None
        This helper runs until stop is requested.
    """

    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(4096)
        except TimeoutError:
            continue
        except OSError:
            break

        message = data.decode("utf-8", errors="replace").strip()
        instruction = (message.split(maxsplit=1)[0] if message else "").lower()
        if instruction != "hello":
            _log(widget, f"[viewer] UDP recv '{message}' from {addr[0]}:{addr[1]}.")
        try:
            if instruction == "hello":
                _echo(widget, sock, data, addr, log_echo=False)
            elif instruction == "blockstart":
                _handle_block_start(widget, sock, data, addr)
            elif instruction in {"expend", "expinterrupt"}:
                _handle_exp_end(widget, sock, data, addr)
            else:
                _echo(widget, sock, data, addr)
        except Exception as exc:  # noqa: BLE001
            _log(widget, f"[viewer] UDP handler error for '{message}': {exc}")


def _handle_block_start(
    widget: "CortexFrameWidget", sock: socket.socket, data: bytes, addr: tuple[str, int]
) -> None:
    """Handle `BlockStart` by starting save if not already active.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning runtime state and command channel.
    sock : socket.socket
        UDP socket used to send echoes.
    data : bytes
        Original datagram bytes to echo.
    addr : tuple[str, int]
        Sender address tuple.

    Returns
    -------
    None
        Starts save on first block and echoes.
    """

    if _save_command_enabled(widget):
        _log(widget, "[viewer] BlockStart ignored: recording already enabled; echoing.")
        _echo(widget, sock, data, addr)
        return

    try:
        subject, session, run_index = _parse_blockstart_message(
            data.decode("utf-8", errors="replace")
        )
    except Exception as exc:  # noqa: BLE001
        widget._pending_udp_error = f"UDP BlockStart rejected: {exc}"
        _log(widget, f"[viewer] BlockStart rejected: {exc}")
        _send(widget, sock, b"ExpRejected malformed_blockstart", addr)
        return

    collision_message = _check_udp_run_collision(widget, subject, session, run_index)
    if collision_message is not None:
        widget._pending_udp_error = collision_message
        _log(widget, f"[viewer] BlockStart rejected: {collision_message}")
        _send(
            widget,
            sock,
            f"ExpRejected {subject} {session} {run_index}".encode("utf-8"),
            addr,
        )
        return

    _apply_udp_metadata(widget, subject, session, run_index)

    req_id = widget.next_command_request_id("save")
    widget.write_shared_memory_command(save_to_disk=1, save_req_id=req_id)
    if not _wait_for_save_ack(widget, req_id, timeout_s=2.0):
        widget._pending_udp_error = (
            "UDP BlockStart rejected: MATLAB save ack timed out."
        )
        _log(widget, "[viewer] BlockStart rejected: MATLAB save ack timeout.")
        _send(
            widget,
            sock,
            f"ExpRejected {subject} {session} {run_index}".encode("utf-8"),
            addr,
        )
        return

    QTimer.singleShot(0, lambda: controls.refresh_control_locks(widget))
    _echo(widget, sock, data, addr)
    _log(widget, "[viewer] First BlockStart acknowledged; recording started.")


def _handle_exp_end(
    widget: "CortexFrameWidget", sock: socket.socket, data: bytes, addr: tuple[str, int]
) -> None:
    """Handle `ExpEnd`/`ExpInterrupt` by disabling save and echoing.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning runtime state and command channel.
    sock : socket.socket
        UDP socket used to send echoes.
    data : bytes
        Original datagram bytes to echo.
    addr : tuple[str, int]
        Sender address tuple.

    Returns
    -------
    None
        Writes save-off command and sends echo response.
    """

    req_id = widget.next_command_request_id("save")
    widget.write_shared_memory_command(save_to_disk=0, save_req_id=req_id)
    QTimer.singleShot(0, lambda: controls.refresh_control_locks(widget))
    _echo(widget, sock, data, addr)


def _parse_blockstart_message(message: str) -> tuple[str, str, int]:
    """Parse subject/session/run fields from a `BlockStart` message.

    Parameters
    ----------
    message : str
        Raw mpep `BlockStart` UDP message.

    Returns
    -------
    tuple[str, str, int]
        Parsed `(subject, session, run_index)` values.
    """

    parts = message.strip().split()
    if len(parts) < 4:
        raise ValueError("BlockStart message must have at least 4 tokens.")
    subject = parts[1].strip()
    session = parts[2].strip()
    run_index = int(parts[3])
    if run_index < 1:
        raise ValueError("BlockStart run index must be >= 1.")
    return subject, session, run_index


def _apply_udp_metadata(
    widget: "CortexFrameWidget", subject: str, session: str, run_index: int
) -> None:
    """Apply BlockStart metadata to napari fields and shared metadata sidecar.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns metadata controls.
    subject : str
        Subject label from `BlockStart`.
    session : str
        Session label from `BlockStart`.
    run_index : int
        Run index from `BlockStart`.

    Returns
    -------
    None
        Updates UI controls and writes sidecar metadata.
    """

    safe_subject = bids.validate_bids_label(subject, "Subject", required=True)
    safe_session = bids.validate_bids_label(
        "".join(ch for ch in session if ch.isalnum()),
        "Session",
        required=True,
    )

    mp = widget._metadata_panel
    bids.write_bids_meta_sidecar(
        task=mp._task_edit.text().strip(),
        acq=mp._acq_edit.text().strip(),
        proc=mp._proc_edit.text().strip(),
        run=int(run_index),
        subject=safe_subject,
        session=safe_session,
    )

    widget._pending_udp_metadata = (safe_subject, safe_session, int(run_index))


def _check_udp_run_collision(
    widget: "CortexFrameWidget", subject: str, session: str, run_index: int
) -> str | None:
    """Return a user-facing collision message for an incoming BlockStart.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning metadata fields.
    subject : str
        Subject label from UDP.
    session : str
        Session label from UDP.
    run_index : int
        Run index from UDP.

    Returns
    -------
    str or None
        Error message when the target storage metadata already exists, otherwise `None`.
    """
    mp = widget._metadata_panel
    storage_root = mp._storage_edit.text().strip()
    if not storage_root:
        return "Storage root is empty. Cannot start UDP recording."

    safe_subject = bids.validate_bids_label(subject, "Subject", required=True)
    safe_session = bids.validate_bids_label(
        "".join(ch for ch in session if ch.isalnum()),
        "Session",
        required=True,
    )
    collision = bids.check_bids_run_collision(
        Path(storage_root),
        datatype=bids.FUSI_DATATYPE,
        subject=safe_subject,
        session=safe_session,
        task=mp._task_edit.text().strip(),
        acq=mp._acq_edit.text().strip(),
        run=int(run_index),
        proc=mp._proc_edit.text().strip(),
    )
    if collision:
        return (
            "UDP BlockStart rejected: Path already exists for this entity set. "
            "Change the storage metadata."
        )
    return None


def _save_command_enabled(widget: "CortexFrameWidget") -> bool:
    """Return whether `save_to_disk` is currently requested in `cf_cmd`.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning command shared-memory segments.

    Returns
    -------
    bool
        `True` when `save_to_disk` is non-zero in the command segment.
    """
    if len(widget._shared_memory_segments) < 4:
        return bool(widget._save_active)
    shm_cmd = widget._shared_memory_segments[3]
    values = struct.unpack_from(shared_memory.CMD_FORMAT, shm_cmd.buf, 0)
    return bool(values[shared_memory.CMD_FIELD_INDEX["save_to_disk"]])


def _wait_for_save_ack(
    widget: "CortexFrameWidget", request_id: int, timeout_s: float
) -> bool:
    """Wait until MATLAB acknowledges a save request id.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning the shared-memory reader.
    request_id : int
        Save request id written to `save_req_id`.
    timeout_s : float
        Maximum wait duration in seconds.

    Returns
    -------
    bool
        `True` when the matching ack is observed before timeout.
    """
    deadline = time.monotonic() + timeout_s
    ack_index = shared_memory.ACK_FIELD_INDEX["save_ack_id"]
    while time.monotonic() < deadline:
        reader = widget._shared_memory_reader
        if reader is None:
            return False
        try:
            ack_tuple = reader.read_ack()
        except Exception:
            time.sleep(0.01)
            continue
        if int(ack_tuple[ack_index]) == int(request_id):
            return True
        time.sleep(0.01)
    return False


def _send(
    widget: "CortexFrameWidget",
    sock: socket.socket,
    data: bytes,
    addr: tuple[str, int],
    kind: str = "send",
    log_send: bool = True,
) -> None:
    """Send one UDP datagram payload and log it.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning the log queue.
    sock : socket.socket
        UDP socket used for sending.
    data : bytes
        Raw datagram payload to send.
    addr : tuple[str, int]
        Destination address tuple.
    kind : str, default: "send"
        Log label describing the outbound packet kind.
    log_send : bool, default: True
        Whether to emit an outbound log line for this send.

    Returns
    -------
    None
        Sends one datagram.
    """

    sock.sendto(data, addr)
    if log_send:
        message = data.decode("utf-8", errors="replace").strip()
        _log(widget, f"[viewer] UDP {kind} '{message}' to {addr[0]}:{addr[1]}.")


def _echo(
    widget: "CortexFrameWidget",
    sock: socket.socket,
    data: bytes,
    addr: tuple[str, int],
    log_echo: bool = True,
) -> None:
    """Echo one datagram payload back to sender and log it.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning the log queue.
    sock : socket.socket
        UDP socket used for sending.
    data : bytes
        Raw datagram payload to echo.
    addr : tuple[str, int]
        Sender address tuple.
    log_echo : bool, default: True
        Whether to emit an outbound log line for this echo.

    Returns
    -------
    None
        Sends one datagram.
    """

    _send(widget, sock, data, addr, kind="echo", log_send=log_echo)


def _log(widget: "CortexFrameWidget", message: str) -> None:
    """Append one timestamped line to the viewer log queue.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance owning the log queue.
    message : str
        Message body to append.

    Returns
    -------
    None
        Pushes one line onto the log queue.
    """

    tagged = message if message.startswith("[") else f"[viewer] {message}"
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(f"[{ts}] {tagged}\n")
