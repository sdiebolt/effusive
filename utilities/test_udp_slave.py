"""Send a mock mpep session to the Effusive UDP slave.

Run this script while Effusive is already running (VSX active) to verify that
UDP experiment and block control works end-to-end.
"""

from __future__ import annotations

import argparse
import socket
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionConfig:
    """Runtime configuration for a UDP test session.

    Parameters
    ----------
    host : str
        UDP control server host address.
    port : int
        UDP control server port.
    subject : str
        Subject label used in mpep-style messages.
    series : str
        Session/series label used in mpep-style messages.
    experiment : str
        Experiment/run identifier used in mpep-style messages.
    record_seconds : float
        Delay between `BlockStart` and `BlockEnd`.
    timeout_seconds : float
        Timeout for each expected echo.
    """

    host: str
    port: int
    subject: str
    series: str
    experiment: str
    record_seconds: float
    timeout_seconds: float


def parse_args() -> SessionConfig:
    """Parse command-line arguments.

    Returns
    -------
    SessionConfig
        Parsed runtime configuration.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="UDP control host.")
    parser.add_argument(
        "--port",
        type=int,
        default=1025,
        help="UDP control port (must match viewer UDP control port).",
    )
    parser.add_argument("--subject", default="TestSubject", help="Subject label.")
    parser.add_argument(
        "--series", default=time.strftime("%Y%m%d"), help="Series label."
    )
    parser.add_argument("--exp", default="1", help="Experiment id.")
    parser.add_argument(
        "--record-seconds",
        type=float,
        default=30.0,
        help="Seconds to wait between BlockStart and BlockEnd.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=12.0,
        help="Timeout for each echo.",
    )
    args = parser.parse_args()
    return SessionConfig(
        host=args.host,
        port=args.port,
        subject=args.subject,
        series=args.series,
        experiment=args.exp,
        record_seconds=args.record_seconds,
        timeout_seconds=args.timeout_seconds,
    )


def send_and_wait(sock: socket.socket, message: str, cfg: SessionConfig) -> None:
    """Send one message and wait for one echo.

    Parameters
    ----------
    sock : socket.socket
        Bound UDP socket used to send and receive datagrams.
    message : str
        Message payload to send.
    cfg : SessionConfig
        Session configuration containing host/port and timeout.

    Returns
    -------
    None
        Prints send/receive progress to stdout.
    """

    print(f"[test] --> {message}")
    sock.sendto(message.encode("utf-8"), (cfg.host, cfg.port))
    sock.settimeout(cfg.timeout_seconds)
    try:
        data, _ = sock.recvfrom(4096)
    except TimeoutError:
        print(
            f"[test] WARNING: no echo received for '{message}' "
            f"within {cfg.timeout_seconds:.1f}s"
        )
        return
    print(f"[test] <-- {data.decode('utf-8', errors='replace')}")


def main() -> int:
    """Run the UDP mock session.

    Returns
    -------
    int
        Process exit code.
    """

    cfg = parse_args()
    print(f"[test] Sending to {cfg.host}:{cfg.port}")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        send_and_wait(sock, "hello", cfg)
        send_and_wait(
            sock,
            f"ExpStart {cfg.subject} {cfg.series} {cfg.experiment}",
            cfg,
        )
        send_and_wait(
            sock, f"BlockStart {cfg.subject} {cfg.series} {cfg.experiment} 1", cfg
        )
        print(f"[test] Recording for {cfg.record_seconds:.1f} seconds...")
        time.sleep(cfg.record_seconds)
        send_and_wait(
            sock, f"BlockEnd {cfg.subject} {cfg.series} {cfg.experiment} 1", cfg
        )
        send_and_wait(sock, f"ExpEnd {cfg.subject} {cfg.series} {cfg.experiment}", cfg)
    print("[test] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
