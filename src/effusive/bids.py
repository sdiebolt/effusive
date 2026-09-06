"""Helpers for Effusive's BIDS-like storage mode.

This module centralises validation and filename construction for the planned
fUSI-BIDS layout so the napari UI and later MATLAB runtime code can share the
same naming rules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import platformdirs

FUSI_DATATYPE = "fusi"
"""Datatype folder for regular recordings."""

ANGIO_DATATYPE = "angio"
"""Datatype folder for z-stack exports."""

FUSI_RECORDING_SUFFIXES = ("iq", "pwd", "rf", "rftimestamps", "seq.mat")
"""Basename suffixes reserved by one fUSI recording stem."""

VALID_BIDS_LABEL_RE = re.compile(r"^[A-Za-z0-9]+$")
"""Allowed entity-label pattern for the v1 BIDS-like mode."""

BIDS_META_SIDECAR_PATH = (
    Path(platformdirs.user_cache_dir("effusive")) / "cf_bids_meta.json"
)
"""Per-recording metadata sidecar for live updates to the MATLAB worker.

Written by Python at record-start; read by `cfPrepareStorageSpecForSave` to pick up
subject/session/task/acq/proc/run values that may have changed since VSX launched.
"""


def write_bids_meta_sidecar(
    task: str,
    acq: str,
    proc: str,
    run: int,
    subject: str = "",
    session: str = "",
) -> None:
    """Write per-recording BIDS metadata to the shared sidecar file.

    Parameters
    ----------
    task : str
        Task label without the `task-` prefix.
    acq : str
        Acquisition label without the `acq-` prefix.
    proc : str
        Processing label without the `proc-` prefix.
    run : int
        Exact run index to use for the next recording.
    subject : str, optional
        Subject label without the `sub-` prefix.
    session : str, optional
        Session label without the `ses-` prefix.
    """
    BIDS_META_SIDECAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    BIDS_META_SIDECAR_PATH.write_text(
        json.dumps(
            {
                "task": task,
                "acq": acq,
                "proc": proc,
                "run": int(run),
                "subject": subject,
                "session": session,
            }
        )
    )


def validate_bids_label(value: str, field_name: str, required: bool = False) -> str:
    """Validate one BIDS entity label.

    Parameters
    ----------
    value : str
        Raw entity-label text.
    field_name : str
        Human-readable field name used in error messages.
    required : bool, default: False
        Whether an empty value should be rejected.

    Returns
    -------
    str
        Stripped label text when valid.

    Raises
    ------
    ValueError
        Raised when the value is empty for a required field or contains
        characters outside `[A-Za-z0-9]+`.
    """
    cleaned = value.strip()
    if not cleaned:
        if required:
            raise ValueError(f"{field_name} is required.")
        return ""
    if VALID_BIDS_LABEL_RE.fullmatch(cleaned) is None:
        raise ValueError(f"{field_name} must match [A-Za-z0-9]+.")
    return cleaned


def required_bids_fields(datatype: str) -> tuple[str, ...]:
    """Return the required entity names for a datatype.

    Parameters
    ----------
    datatype : str
        Recording datatype, typically `fusi` or `angio`.

    Returns
    -------
    tuple of str
        Required entity names for the requested datatype.
    """
    if datatype == FUSI_DATATYPE:
        return ("subject", "session", "task")
    if datatype == ANGIO_DATATYPE:
        return ("subject", "session")
    raise ValueError(f"Unsupported BIDS datatype: {datatype}.")


def validate_bids_entities(
    *,
    datatype: str,
    subject: str,
    session: str,
    task: str = "",
    acq: str = "",
    proc: str = "",
) -> dict[str, str]:
    """Validate a set of entity values for one datatype.

    Parameters
    ----------
    datatype : str
        Recording datatype, typically `fusi` or `angio`.
    subject : str
        Subject label without the `sub-` prefix.
    session : str
        Session label without the `ses-` prefix.
    task : str, optional
        Task label without the `task-` prefix.
    acq : str, optional
        Acquisition label without the `acq-` prefix.
    proc : str, optional
        Processing label without the `proc-` prefix.

    Returns
    -------
    dict of str to str
        Validated entity values keyed by entity name.

    Raises
    ------
    ValueError
        Raised when any required or optional label is invalid.
    """
    required = set(required_bids_fields(datatype))
    return {
        "subject": validate_bids_label(subject, "Subject", "subject" in required),
        "session": validate_bids_label(session, "Session", "session" in required),
        "task": validate_bids_label(task, "Task", "task" in required),
        "acq": validate_bids_label(acq, "Acq", False),
        "proc": validate_bids_label(proc, "Proc", False),
    }


def format_run(run: int) -> str:
    """Format a run index for the BIDS-like entity string.

    Parameters
    ----------
    run : int
        Positive run index.

    Returns
    -------
    str
        Zero-padded run label body such as `01`.

    Raises
    ------
    ValueError
        Raised when `run` is not positive.
    """
    if run < 1:
        raise ValueError("Run must be >= 1.")
    return f"{run:02d}"


def build_bids_dir(root: Path, subject: str, session: str, datatype: str) -> Path:
    """Build the datatype directory for one BIDS-like recording.

    Parameters
    ----------
    root : Path
        Storage root directory.
    subject : str
        Subject label without the `sub-` prefix.
    session : str
        Session label without the `ses-` prefix.
    datatype : str
        Datatype folder name, typically `fusi` or `angio`.

    Returns
    -------
    Path
        Datatype directory path below `root`.
    """
    subject_label = validate_bids_label(subject, "Subject", required=True)
    session_label = validate_bids_label(session, "Session", required=True)
    return Path(root) / f"sub-{subject_label}" / f"ses-{session_label}" / datatype


def build_bids_stem(
    *,
    subject: str,
    session: str,
    task: str = "",
    acq: str = "",
    run: int | None = None,
    proc: str = "",
    datatype: str = FUSI_DATATYPE,
) -> str:
    """Build a BIDS-like filename stem without suffix or extension.

    Parameters
    ----------
    subject : str
        Subject label without the `sub-` prefix.
    session : str
        Session label without the `ses-` prefix.
    task : str, optional
        Task label without the `task-` prefix.
    acq : str, optional
        Acquisition label without the `acq-` prefix.
    run : int, optional
        Run index. When omitted, the stem is built without a `run-` entity.
    proc : str, optional
        Processing label without the `proc-` prefix.
    datatype : str, default: `fusi`
        Recording datatype, used only to validate required fields.

    Returns
    -------
    str
        Filename stem up to, but not including, the suffix.
    """
    entities = validate_bids_entities(
        datatype=datatype,
        subject=subject,
        session=session,
        task=task,
        acq=acq,
        proc=proc,
    )
    parts = [f"sub-{entities['subject']}", f"ses-{entities['session']}"]
    if entities["task"]:
        parts.append(f"task-{entities['task']}")
    if entities["acq"]:
        parts.append(f"acq-{entities['acq']}")
    if entities["proc"]:
        parts.append(f"proc-{entities['proc']}")
    if run is not None:
        parts.append(f"run-{format_run(run)}")
    return "_".join(parts)


def check_bids_run_collision(
    root: Path,
    *,
    datatype: str,
    subject: str,
    session: str,
    task: str = "",
    acq: str = "",
    run: int,
    proc: str = "",
) -> bool:
    """Return True if any file with the expected BIDS stem already exists.

    Parameters
    ----------
    root : Path
        Storage root directory.
    datatype : str
        Datatype folder name, typically `fusi` or `angio`.
    subject : str
        Subject label without the `sub-` prefix.
    session : str
        Session label without the `ses-` prefix.
    task : str, optional
        Task label without the `task-` prefix.
    acq : str, optional
        Acquisition label without the `acq-` prefix.
    run : int
        Manual run index to check for collision.
    proc : str, optional
        Processing label without the `proc-` prefix.

    Returns
    -------
    bool
        True when at least one file matching `<stem>_*` exists.
    """
    bids_dir = build_bids_dir(root, subject, session, datatype)
    stem = build_bids_stem(
        subject=subject,
        session=session,
        task=task,
        acq=acq,
        run=run,
        proc=proc,
        datatype=datatype,
    )
    if not bids_dir.is_dir():
        return False

    if datatype == FUSI_DATATYPE:
        return any((bids_dir / f"{stem}_{suffix}").exists() for suffix in FUSI_RECORDING_SUFFIXES)

    return any(bids_dir.glob(f"{stem}_*"))


def build_bids_preview_path(
    root: Path,
    *,
    datatype: str,
    subject: str,
    session: str,
    task: str = "",
    acq: str = "",
    run: int | None = None,
    proc: str = "",
    suffix: str = "pwd",
    extension: str = ".ext",
) -> Path:
    """Build a full preview path for UI display.

    Parameters
    ----------
    root : Path
        Storage root directory.
    datatype : str
        Datatype folder name, typically `fusi` or `angio`.
    subject : str
        Subject label without the `sub-` prefix.
    session : str
        Session label without the `ses-` prefix.
    task : str, optional
        Task label without the `task-` prefix.
    acq : str, optional
        Acquisition label without the `acq-` prefix.
    run : int, optional
        Run index for the preview stem.
    proc : str, optional
        Processing label without the `proc-` prefix.
    suffix : str, default: `pwd`
        Output suffix token without the leading underscore.
    extension : str, default: `.ext`
        Filename extension shown in the preview.

    Returns
    -------
    Path
        Full preview path including one representative filename.
    """
    bids_dir = build_bids_dir(root, subject, session, datatype)
    stem = build_bids_stem(
        subject=subject,
        session=session,
        task=task,
        acq=acq,
        run=run,
        proc=proc,
        datatype=datatype,
    )
    return bids_dir / f"{stem}_{suffix}{extension}"
