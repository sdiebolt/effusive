"""Python-side motor controller for manual stack jogging."""

from __future__ import annotations

import struct
import threading
import os
import time

import serial
from serial.tools import list_ports


class MotorController:
    """Manual motor controller used by the napari widget.

    Parameters
    ----------
    kind : str
        Backend kind identifier. Supported values are `"dummy"` and
        `"real"`.
    port_name : str | None, optional
        Serial port backing the real controller. Dummy controllers leave this
        as `None`.
    """

    MM_PER_STEP = 0.047625e-3
    BAUD_RATE = 9600

    def __init__(
        self,
        kind: str,
        port_name: str | None = None,
        min_position_mm: float = float("-inf"),
        max_position_mm: float = float("inf"),
    ) -> None:
        self.kind = kind
        self.port_name = port_name
        self.min_position_mm = min_position_mm
        self.max_position_mm = max_position_mm
        self.current_position_mm = 0.0
        self._lock = threading.Lock()
        self._transport = None

        if self.kind != "real":
            return

        if not self.port_name:
            raise RuntimeError("Motor port name cannot be empty.")

        self._transport = serial.Serial(
            self.port_name,
            baudrate=self.BAUD_RATE,
            timeout=15,
            write_timeout=15,
        )
        self.current_position_mm = self._read_current_position_mm()

    def move_to(self, target_position_mm: float) -> None:
        """Move to an absolute target position in millimeters.

        Parameters
        ----------
        target_position_mm : float
            Absolute target motor position in millimeters.
        """

        if (
            target_position_mm < self.min_position_mm
            or target_position_mm > self.max_position_mm
        ):
            raise RuntimeError(
                "Requested motor position "
                f"{target_position_mm:.6f} mm outside configured limits "
                f"[{self.min_position_mm:.6f}, {self.max_position_mm:.6f}] mm."
            )

        with self._lock:
            if self.kind == "real":
                self._write_command(1, 20, self._mm_to_steps(target_position_mm))
            self.current_position_mm = target_position_mm

    def jog_relative(self, delta_mm: float) -> float:
        """Move by a relative offset and return the new position.

        Parameters
        ----------
        delta_mm : float
            Relative move size in millimeters.

        Returns
        -------
        float
            New absolute motor position in millimeters.
        """

        target_position_mm = self.current_position_mm + delta_mm
        self.move_to(target_position_mm)
        return self.current_position_mm

    def home(self) -> float:
        """Home the motor and return the post-home position.

        Returns
        -------
        float
            Absolute motor position in millimeters after homing.

        Raises
        ------
        RuntimeError
            If homing fails or reports an invalid response.
        """

        with self._lock:
            if self.kind == "real":
                self._write_command(1, 1, 0)
                self._wait_for_motion_settle()
                self._write_command(1, 45, 0)
                self.current_position_mm = self._read_current_position_mm()
            else:
                self.current_position_mm = 0.0
        return self.current_position_mm

    def close(self) -> None:
        """Release the underlying transport if present."""

        with self._lock:
            if self._transport is None:
                return
            try:
                self._transport.close()
            finally:
                self._transport = None

    def _write_command(self, device_id: int, command_id: int, payload: int) -> None:
        if self._transport is None:
            return
        command = struct.pack("<BBi", device_id, command_id, int(payload))
        self._transport.write(command)
        self._transport.flush()

    def _flush_input(self) -> None:
        """Discard any stale bytes waiting in the serial input buffer.

        Returns
        -------
        None
            This helper clears unread serial input data in place.
        """

        if self._transport is None:
            return
        self._transport.reset_input_buffer()

    def _mm_to_steps(self, position_mm: float) -> int:
        return int(round(position_mm / self.MM_PER_STEP))

    def _read_current_position_mm(self) -> float:
        """Read and return the current motor position in millimeters.

        Returns
        -------
        float
            Current motor position in millimeters.

        Raises
        ------
        RuntimeError
            If the motor response is malformed.
        """

        if self._transport is None:
            return 0.0
        self._flush_input()
        self._write_command(1, 60, 0)

        deadline = time.monotonic() + 5.0
        last_command_id = None
        while time.monotonic() < deadline:
            reply = self._transport.read(6)
            if len(reply) != 6:
                continue
            device_id, command_id, steps = struct.unpack("<BBi", reply)
            if device_id != 1:
                continue
            if command_id == 255:
                raise RuntimeError(
                    "Motor reported out-of-range command while reading position."
                )
            last_command_id = command_id
            if command_id == 60:
                return float(steps) * self.MM_PER_STEP

        if last_command_id is None:
            raise RuntimeError(
                "Timed out while reading motor position: no valid 6-byte reply received."
            )
        raise RuntimeError(
            "Timed out while reading motor position: "
            f"last command id was {last_command_id}."
        )

    def _wait_for_motion_settle(self) -> None:
        """Wait until successive position reads indicate settled motion.

        Returns
        -------
        None
            This helper blocks until motion appears settled.

        Raises
        ------
        RuntimeError
            If a stable reading is not observed within the timeout window.
        """

        if self._transport is None:
            return

        deadline = time.monotonic() + 20.0
        stable_count = 0
        last_position_mm = None
        while time.monotonic() < deadline:
            position_mm = self._read_current_position_mm()
            if (
                last_position_mm is not None
                and abs(position_mm - last_position_mm) <= 0.002
            ):
                stable_count += 1
                if stable_count >= 3:
                    return
            else:
                stable_count = 0
            last_position_mm = position_mm
            time.sleep(0.05)

        raise RuntimeError("Timed out waiting for motor motion to settle after home.")


def create_motor_controller(
    *,
    use_dummy_motor: bool,
    motor_port: str | None = None,
    min_position_mm: float | None = None,
    max_position_mm: float | None = None,
) -> MotorController:
    """Create the requested Python motor controller.

    Parameters
    ----------
    use_dummy_motor : bool
        Whether to create the dummy backend instead of the real hardware
        backend.
    motor_port : str | None, optional
        Configured serial port for the real backend. If omitted, the function
        auto-selects the port when exactly one serial device is available.

    Returns
    -------
    MotorController
        Newly created controller instance.

    Raises
    ------
    RuntimeError
        If the real backend is requested but the serial dependency or port
        configuration is unavailable.
    """

    if min_position_mm is None:
        min_position_mm = _parse_optional_limit("EFFUSIVE_STACK_MOTOR_MIN_MM", False)
    if max_position_mm is None:
        max_position_mm = _parse_optional_limit("EFFUSIVE_STACK_MOTOR_MAX_MM", True)
    if min_position_mm > max_position_mm:
        raise RuntimeError(
            "Invalid stack motor limits: "
            f"min {min_position_mm:.6f} mm is greater than max {max_position_mm:.6f} mm."
        )

    if use_dummy_motor:
        return MotorController(
            "dummy",
            min_position_mm=min_position_mm,
            max_position_mm=max_position_mm,
        )

    port_name = (motor_port or "").strip()
    if not port_name:
        port_name = _auto_detect_motor_port()
    return MotorController(
        "real",
        port_name=port_name,
        min_position_mm=min_position_mm,
        max_position_mm=max_position_mm,
    )


def _parse_optional_limit(variable_name: str, upper: bool) -> float:
    """Parse an optional motor boundary from the environment.

    Parameters
    ----------
    variable_name : str
        Environment variable name to parse.
    upper : bool
        Whether the limit is an upper boundary. Lower boundaries default to
        `-inf`; upper boundaries default to `inf`.

    Returns
    -------
    float
        Parsed boundary value in millimeters.

    Raises
    ------
    RuntimeError
        If the environment variable is set to a non-float value.
    """

    raw_value = os.getenv(variable_name, "").strip()
    if not raw_value:
        return float("inf") if upper else float("-inf")
    try:
        return float(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid motor limit for {variable_name}: expected a float in millimeters."
        ) from exc


def _auto_detect_motor_port() -> str:
    available_ports = [port.device for port in list_ports.comports()]
    if len(available_ports) == 1:
        return available_ports[0]
    if len(available_ports) > 1:
        raise RuntimeError(
            "Real motor backend requested, but no motor port was configured. "
            "Multiple serial ports are available ("
            + ", ".join(available_ports)
            + "). Set stackMotorPort or EFFUSIVE_STACK_MOTOR_PORT."
        )
    raise RuntimeError(
        "Real motor backend requested, but no motor port was configured. "
        "Set stackMotorPort or EFFUSIVE_STACK_MOTOR_PORT."
    )
