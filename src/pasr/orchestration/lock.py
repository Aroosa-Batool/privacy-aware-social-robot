from __future__ import annotations

from pathlib import Path

from filelock import FileLock, Timeout

LOCK_FILENAME = ".runtime.lock"


class RuntimeBusyError(RuntimeError):
    def __init__(self, data_dir: Path) -> None:
        super().__init__(
            f"another pasr runtime is already running on {data_dir} (the robot, camera, "
            "microphone and watch can only have one owner). Stop it first."
        )


class RuntimeLock:
    """One running runtime per data directory: it owns the hardware and runs the scheduler.
    Device checks hold it too (``with RuntimeLock(...)``) so they never fight a running robot."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._lock = FileLock(str(data_dir / LOCK_FILENAME))

    def acquire(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire(timeout=0)
        except Timeout as exc:
            raise RuntimeBusyError(self.data_dir) from exc

    def release(self) -> None:
        if self._lock.is_locked:
            self._lock.release()

    def __enter__(self) -> RuntimeLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    def is_held_elsewhere(self) -> bool:
        if self._lock.is_locked:
            return False
        try:
            self.acquire()
        except RuntimeBusyError:
            return True
        self.release()
        return False
