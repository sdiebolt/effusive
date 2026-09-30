"""MATLAB worker lifecycle helpers for the Effusive napari widget."""

from __future__ import annotations

import datetime
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qtpy.QtCore import QTimer

from effusive import shared_memory
from effusive.napari import controls, udp_control
from effusive.napari import crop as crop_helpers
from effusive.napari import runtime as runtime_polling
from effusive.napari import stack as stack_helpers

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget


def build_worker_config(widget: "EffusiveWidget") -> dict:
    """Build the effective MATLAB worker configuration from widget state.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance providing the current UI state.

    Returns
    -------
    dict
        Configuration dictionary passed to the MATLAB worker subprocess.
    """
    tgc_points = widget._processing_panel.get_current_tgc_points()
    sp = widget._sequence_panel
    pp = widget._processing_panel
    config = dict(widget._worker_cfg)
    config["probeName"] = widget._sequence_panel._probe_combo.currentText()
    config["transmitFrequency"] = sp._freq_slider.value() / 1000.0
    config["voltage"] = pp._voltage_slider.value() / 10.0
    config["transmitAperturePercentage"] = pp._tx_aperture_slider.value()
    config["receiveAperturePercentage"] = pp._rx_aperture_slider.value()
    config["txrxFrameRate"] = sp._fps_slider.value()
    config["transmitPulseLength"] = sp._pulse_slider.value()
    config["nTransmissions"] = sp._tx_count_slider.value()
    config["nRepeats"] = sp._ensemble_slider.value()
    config["planewaveOpeningAngle"] = sp._angle_slider.value()
    config["desiredEndDepthMm"] = sp._depth_slider.value() / 10.0
    config["beamformerType"] = widget._config.system.beamformer
    config["tgcGain"] = tgc_points[0]
    config["tgcControlPoints"] = tgc_points
    config["storagePath"] = widget._metadata_panel._storage_edit.text()
    mp = widget._metadata_panel
    config["bidsSubject"] = mp._subject_edit.text().strip()
    config["bidsSession"] = mp._session_edit.text().strip()
    config["bidsTask"] = mp._task_edit.text().strip()
    config["bidsAcq"] = mp._acq_edit.text().strip()
    config["bidsProc"] = mp._proc_edit.text().strip()
    config["bidsRun"] = int(mp._run_spinbox.value())
    matlab_root = widget._config.system.matlab_root.strip() or os.environ.get(
        "MATLAB_ROOT", ""
    )
    if matlab_root:
        config["matlabRoot"] = matlab_root

    vantage_root = widget._config.system.vantage_root.strip() or os.environ.get(
        "VERASONICS_VPF_ROOT", ""
    )
    if vantage_root:
        config["vantageRoot"] = vantage_root

    echoframe_mex_root = (
        widget._config.system.echoframe_mex_root.strip()
        or os.environ.get("ECHOFRAME_MEX_ROOT", "")
    )
    if echoframe_mex_root:
        config["echoFrameMexRoot"] = echoframe_mex_root
    config["stackMotorPort"] = widget._worker_cfg.get(
        "stackMotorPort"
    ) or os.environ.get("EFFUSIVE_STACK_MOTOR_PORT", "")
    config["stackMotorMinMm"] = float(widget._config.stack.motor_min_mm)
    config["stackMotorMaxMm"] = float(widget._config.stack.motor_max_mm)
    if "simulateMode" not in config:
        config["simulateMode"] = 1 if widget._config.system.simulate_mode else 0
    return config


def start_acquisition(
    widget: "EffusiveWidget", worker_script: str, timer_ms: int
) -> None:
    """Start the MATLAB worker, shared memory, and polling timer.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance whose runtime state should be initialized.
    worker_script : str
        Absolute path to the MATLAB worker entry-point script.
    timer_ms : int
        Polling interval for the frame-refresh timer in milliseconds.

    Returns
    -------
    None
        This helper mutates widget state in place.
    """
    run_ready, run_reason = controls.bids_startup_ready(widget)
    if not run_ready:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(f"[{ts}] [viewer] Start rejected: {run_reason}\n")
        widget._set_viewer_status_overlay("cf_status_error")
        controls.refresh_control_locks(widget)
        return

    stack_helpers.reset_stack_preview(widget)
    controls.set_config_controls_locked(widget, True)
    controls.set_runtime_controls_enabled(widget, True)
    controls.set_run_button_state(widget, "running")
    widget._set_viewer_status_overlay("cf_status_starting")
    widget._frame_display_offset = 0
    widget._pending_display_frame_reset = False
    widget._pending_stack_resume_frame_reset = False
    widget._stack_completion_freeze_seen = False

    config = build_worker_config(widget)
    session_id = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_token = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    config["sessionId"] = session_id
    shm_names = {
        "meta": f"cf_meta_{run_token}",
        "bmode": f"cf_bmode_{run_token}",
        "pdi": f"cf_pdi_{run_token}",
        "cmd": f"cf_cmd_{run_token}",
        "rf": f"cf_rf_{run_token}",
        "stack": f"cf_stack_{run_token}",
        "ack": f"cf_ack_{run_token}",
    }
    config["sharedMemoryNameMeta"] = shm_names["meta"]
    config["sharedMemoryNameBmode"] = shm_names["bmode"]
    config["sharedMemoryNamePdi"] = shm_names["pdi"]
    config["sharedMemoryNameCmd"] = shm_names["cmd"]
    config["sharedMemoryNameRf"] = shm_names["rf"]
    config["sharedMemoryNameStack"] = shm_names["stack"]
    config["sharedMemoryNameAck"] = shm_names["ack"]

    session_path = Path(config["storagePath"]) / "effusive_runtime" / session_id

    log_path = session_path / f"effusive_{session_id}.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        widget._log_file = open(log_path, "w")
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_text.appendPlainText(f"[{ts}] [viewer] Log: {log_path}")
    except Exception as error:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_text.appendPlainText(
            f"[{ts}] [viewer] Could not open log file: {error}"
        )
        widget._log_file = None

    widget._shared_memory_segments = shared_memory.create_segments(shm_names)
    widget._shared_memory_reader = shared_memory.ShmReader(shm_names)
    dp = widget._data_panel
    widget.write_shared_memory_command(
        freeze=1 if widget._pause_button.isChecked() else 0,
        save_to_disk=1 if dp._save_button.isChecked() else 0,
        save_rf=1 if dp._save_rf_checkbox.isChecked() else 0,
        save_rf_time_tag=1 if dp._save_rf_time_tag_checkbox.isChecked() else 0,
        save_bf=1 if dp._save_bf_checkbox.isChecked() else 0,
        save_pdi=1 if dp._save_pdi_checkbox.isChecked() else 0,
        svd_threshold=widget._processing_panel._svd_slider.value(),
        freeze_req_id=widget.next_command_request_id("freeze"),
        save_req_id=widget.next_command_request_id("save"),
        svd_req_id=widget.next_command_request_id("svd"),
    )

    try:
        udp_control.start_udp_control_server(widget)
    except Exception as error:  # noqa: BLE001
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(f"[{ts}] [viewer] UDP server start failed: {error}\n")
        if widget._shared_memory_reader is not None:
            widget._shared_memory_reader.close()
            widget._shared_memory_reader = None
        if widget._shared_memory_segments:
            shared_memory.close_segments(*widget._shared_memory_segments, unlink=True)
            widget._shared_memory_segments = ()
        if widget._log_file is not None:
            widget._log_file.close()
            widget._log_file = None
        widget._set_viewer_status_overlay("cf_status_error")
        controls.set_config_controls_locked(widget, False)
        controls.set_runtime_controls_enabled(widget, False)
        controls.set_run_button_state(widget, "ready")
        return

    start_worker_process(widget, worker_script, config)

    widget._timer = QTimer()
    widget._timer.setInterval(timer_ms)
    widget._timer.timeout.connect(lambda: runtime_polling.handle_timer_tick(widget))
    widget._timer.start()


def stop_acquisition(widget: "EffusiveWidget", from_close: bool = False) -> None:
    """Stop the MATLAB worker and clean up shared runtime resources.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance whose runtime state should be torn down.
    from_close : bool, default: False
        Whether cleanup is happening during widget close, which requires the
        cleanup path to run synchronously.

    Returns
    -------
    None
        This helper mutates widget state in place.
    """
    if not from_close:
        controls.set_runtime_controls_enabled(widget, False)
        controls.set_run_button_state(widget, "stopping")
        widget._set_viewer_status_overlay("cf_status_stopping")

    udp_control.stop_udp_control_server(widget)

    if widget._timer is not None:
        try:
            widget._timer.stop()
        except RuntimeError:
            pass
        widget._timer = None

    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(f"[{ts}] [viewer] Sending vsExit to MATLAB...\n")
    if not from_close:
        runtime_polling.drain_log(widget)
    widget.write_shared_memory_command(vsExit=1)

    worker = widget._worker
    widget._worker = None
    reader = widget._shared_memory_reader
    widget._shared_memory_reader = None
    shared_memory_segments = widget._shared_memory_segments
    widget._shared_memory_segments = ()
    log_file_handle = widget._log_file
    widget._log_file = None

    if from_close:
        if worker is not None and worker.poll() is None:
            try:
                worker.wait(timeout=30)
            except subprocess.TimeoutExpired:
                kill_worker_tree(worker)
        if reader:
            reader.close()
        if shared_memory_segments:
            shared_memory.close_segments(*shared_memory_segments, unlink=True)
        if log_file_handle:
            log_file_handle.close()
        return

    def _bg_cleanup() -> None:
        if worker is not None and worker.poll() is None:
            try:
                worker.wait(timeout=30)
            except subprocess.TimeoutExpired:
                kill_worker_tree(worker)
                ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
                widget._log_queue.put(
                    f"[{ts}] [viewer] Worker killed (stop timed out).\n"
                )
        if reader:
            reader.close()
        if shared_memory_segments:
            shared_memory.close_segments(*shared_memory_segments, unlink=False)
        if log_file_handle:
            log_file_handle.close()
        QTimer.singleShot(0, widget._finish_stop)

    threading.Thread(target=_bg_cleanup, daemon=True).start()


def kill_worker_tree(worker: subprocess.Popen[str]) -> None:
    """Force-kill the worker process and its process group if needed.

    Parameters
    ----------
    worker : subprocess.Popen[str]
        Running worker subprocess to terminate.

    Returns
    -------
    None
        This helper attempts best-effort termination in place.
    """
    if worker.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(worker.pid, signal.SIGKILL)
        else:
            worker.kill()
    except ProcessLookupError:
        return
    except Exception:
        try:
            worker.kill()
        except Exception:
            return
    try:
        worker.wait(timeout=5)
    except Exception:
        pass


def finish_stop(widget: "EffusiveWidget") -> None:
    """Reset widget runtime state after the worker has fully stopped.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance whose runtime state should be reset.

    Returns
    -------
    None
        This helper mutates widget state in place.
    """
    sp = widget._stack_panel
    runtime_polling.drain_log(widget)
    widget._save_active = False
    widget._pending_save_target = None
    widget._pending_save_deadline_s = 0.0
    widget._freeze_active = False
    sp._stack_active = False
    sp._stack_error = False
    sp._stack_status_code = shared_memory.STACK_STATUS_IDLE
    sp._stack_current_slice = -1
    sp._stack_total_slices = 0
    sp._stack_target_position_um = 0
    sp._manual_motor_position_um = None
    sp._stack_motor_homed = False
    sp._last_stack_status = None
    stack_helpers.close_motor_controller(widget)
    widget._set_viewer_status_overlay("cf_status_ready")
    controls.set_config_controls_locked(widget, False)
    controls.set_runtime_controls_enabled(widget, False)
    controls.set_save_checkbox_state(widget, False)
    controls.sync_save_controls(widget)
    controls.set_run_button_state(widget, "ready")
    widget._image_depth_pixels = 0
    widget._image_width_pixels = 0
    widget._scale_set = False
    widget._last_frame = -1
    widget._frame_display_offset = 0
    widget._pending_display_frame_reset = False
    widget._pending_stack_resume_frame_reset = False
    widget._stack_completion_freeze_seen = False
    widget._set_viewer_info_overlay("")
    widget._crop_roi = None
    widget._last_rf_counter = 0
    widget._waiting_for_snapshot = False
    widget._last_timing_warning_monotonic = None
    widget._pending_resets.clear()
    stack_helpers.reset_stack_preview(widget)
    sp._stack_target_label.setText("Motor position: -")
    crop_helpers.set_crop_layer_editable(widget, True)
    controls.set_crop_button_state(widget, False)
    stack_helpers.refresh_stack_controls(widget)


def start_worker_process(
    widget: "EffusiveWidget", worker_script: str, config: dict
) -> None:
    """Launch the MATLAB worker subprocess and start stdout forwarding.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that will own the subprocess handle.
    worker_script : str
        Absolute path to the MATLAB worker entry-point script.
    config : dict
        Worker configuration dictionary serialized onto the command line.

    Returns
    -------
    None
        This helper mutates widget state in place.
    """
    config_json = json.dumps(config)
    popen_kwargs: dict[str, Any] = {}
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    elif os.name == "nt":
        popen_kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    widget._worker = subprocess.Popen(
        [sys.executable, worker_script, config_json],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=os.environ,
        **popen_kwargs,
    )
    threading.Thread(target=lambda: forward_output(widget), daemon=True).start()


def classify_worker_line(line: str) -> str:
    """Normalize worker stdout lines into viewer log source tags.

    Parameters
    ----------
    line : str
        One raw line emitted by the MATLAB worker or its child processes.

    Returns
    -------
    str
        Tagged log line body such as `[viewer] ...`, `[worker] ...`, or `[matlab] ...`.
    """
    stripped = line.lstrip()
    if stripped.startswith(("[worker]", "[viewer]", "[matlab]")):
        return line

    return f"[worker] {stripped}"


def forward_output(widget: "EffusiveWidget") -> None:
    """Forward worker stdout into the in-widget console and log file.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the worker subprocess and log sinks.

    Returns
    -------
    None
        This helper streams output until the worker pipe closes.
    """
    if widget._worker is None or widget._worker.stdout is None:
        return
    for line in widget._worker.stdout:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        tagged_line = classify_worker_line(line.rstrip("\n"))
        tagged = f"[{ts}] {tagged_line}\n"
        widget._log_queue.put(tagged)
        if "timetonextacq" in line.lower():
            widget._last_timing_warning_monotonic = time.monotonic()
        if widget._log_file is not None:
            try:
                widget._log_file.write(tagged)
                widget._log_file.flush()
            except Exception:
                pass
