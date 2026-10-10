"""Manifest: one JSON-lines record per object/unit of work, implementing the
state machine from plan.md Section 1A.6:

    LISTED -> PLANNED -> FETCHING -> FETCHED -> VERIFIED -> PROCESSED
              -> ARCHIVED -> EVICTED
                 (any state) -> FAILED(reason, retries, last_error)
                 FAILED -> PLANNED (retry)

Atomic writes (temp file + os.replace) and a cross-process file lock mean a
Studio crash or two processes touching the manifest at once never corrupts
it — the next run resumes from the last fully-written state, no duplicated
or lost work.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator


class ManifestState(str, Enum):
    LISTED = "LISTED"
    PLANNED = "PLANNED"
    FETCHING = "FETCHING"
    FETCHED = "FETCHED"
    VERIFIED = "VERIFIED"
    PROCESSED = "PROCESSED"
    ARCHIVED = "ARCHIVED"
    EVICTED = "EVICTED"
    FAILED = "FAILED"


_VALID_TRANSITIONS: dict[ManifestState, set[ManifestState]] = {
    ManifestState.LISTED: {ManifestState.PLANNED, ManifestState.FAILED},
    ManifestState.PLANNED: {ManifestState.FETCHING, ManifestState.FAILED},
    ManifestState.FETCHING: {ManifestState.FETCHED, ManifestState.FAILED},
    ManifestState.FETCHED: {ManifestState.VERIFIED, ManifestState.FAILED},
    ManifestState.VERIFIED: {ManifestState.PROCESSED, ManifestState.FAILED},
    ManifestState.PROCESSED: {ManifestState.ARCHIVED, ManifestState.FAILED},
    ManifestState.ARCHIVED: {ManifestState.EVICTED, ManifestState.FAILED},
    ManifestState.EVICTED: set(),
    ManifestState.FAILED: {ManifestState.PLANNED},  # explicit retry
}


class ManifestError(Exception):
    """Base class for manifest failures."""


class ManifestLockError(ManifestError):
    """Could not acquire the manifest's exclusive lock in time."""


class InvalidTransitionError(ManifestError):
    """A record's state change isn't allowed by the state machine."""


@dataclass
class ManifestRecord:
    object_key: str
    state: ManifestState
    size_bytes: int | None = None
    checksum: str | None = None
    source: str | None = None
    tile: str | None = None
    sensing_date: str | None = None
    epoch: str | None = None
    processing_baseline: str | None = None
    derivative_paths: list[str] = field(default_factory=list)
    retries: int = 0
    last_error: str | None = None
    updated_at: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> "ManifestRecord":
        d = dict(d)
        d["state"] = ManifestState(d["state"])
        return cls(**d)


@contextmanager
def _file_lock(lock_path: Path, timeout_s: float = 10.0, poll_s: float = 0.02) -> Iterator[None]:
    """A portable exclusive lock via atomic file creation (O_CREAT|O_EXCL) —
    works across processes and threads without an fcntl dependency.
    """
    deadline = time.monotonic() + timeout_s
    fd = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() > deadline:
                raise ManifestLockError(
                    f"Could not acquire manifest lock {lock_path} within {timeout_s}s — "
                    "another process may be holding it."
                )
            time.sleep(poll_s)
    try:
        yield
    finally:
        os.close(fd)
        lock_path.unlink(missing_ok=True)


class Manifest:
    """A JSON-lines manifest at `path`, one line per object, keyed by
    object_key. A snapshot manifest (not append-only) — the file always
    holds exactly the current state of every known object.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _read_all(self) -> dict[str, ManifestRecord]:
        if not self.path.exists():
            return {}
        records: dict[str, ManifestRecord] = {}
        with self.path.open("r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                records[d["object_key"]] = ManifestRecord.from_json_dict(d)
        return records

    def _write_all_atomic(self, records: dict[str, ManifestRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".part")
        with tmp_path.open("w") as f:
            for record in records.values():
                f.write(json.dumps(record.to_json_dict()) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.path)  # atomic on POSIX: fully happens or not at all

    def get(self, object_key: str) -> ManifestRecord | None:
        with _file_lock(self._lock_path):
            return self._read_all().get(object_key)

    def upsert(self, record: ManifestRecord, *, enforce_transition: bool = True) -> None:
        """Insert a new record, or transition an existing one's state.

        Raises InvalidTransitionError if `enforce_transition` and the state
        change isn't allowed by the state machine — never silently allows
        an illegal jump (e.g. LISTED straight to ARCHIVED).
        """
        with _file_lock(self._lock_path):
            records = self._read_all()
            existing = records.get(record.object_key)
            if existing is not None and enforce_transition and existing.state != record.state:
                allowed = _VALID_TRANSITIONS.get(existing.state, set())
                if record.state not in allowed:
                    raise InvalidTransitionError(
                        f"{record.object_key}: cannot transition {existing.state.value} -> {record.state.value}"
                    )
            records[record.object_key] = record
            self._write_all_atomic(records)

    def all_records(self) -> list[ManifestRecord]:
        with _file_lock(self._lock_path):
            return list(self._read_all().values())

    def pending(
        self, terminal_states: "set[ManifestState] | None" = None
    ) -> list[ManifestRecord]:
        """Returns records NOT yet in a terminal state — the resumable
        worklist. A caller processing this list after a crash/restart
        never redoes a record that already reached a terminal state,
        which is what "resume with zero duplicate transfers" means in
        practice (plan.md Phase 2 Part 2.6's resume drill).
        """
        terminal = terminal_states if terminal_states is not None else {ManifestState.VERIFIED, ManifestState.ARCHIVED, ManifestState.EVICTED}
        with _file_lock(self._lock_path):
            return [r for r in self._read_all().values() if r.state not in terminal]

    def cleanup_stale_part_files(self) -> list[Path]:
        """Remove any leftover *.part temp files in the manifest's directory
        left over from a crash mid-write. A .part file is never treated as
        a valid completed write — only a fully `os.replace()`'d file is.
        """
        removed: list[Path] = []
        if not self.path.parent.is_dir():
            return removed
        for p in self.path.parent.glob("*.part"):
            p.unlink()
            removed.append(p)
        return removed
