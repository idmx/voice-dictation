"""Cross-platform single-instance guard for Voice Dictation.

Uses a PID file with advisory file locking to ensure only one instance of the
application runs at a time. On Unix (macOS/Linux) ``fcntl.flock`` is used; on
Windows ``msvcrt.locking`` is used as a best-effort advisory lock.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

from loguru import logger

IS_WINDOWS = sys.platform == "win32"

DEFAULT_LOCK_DIR = "~/.voice-dictation"
LOCK_FILE_NAME = "voice-dictation.lock"


class AlreadyRunningError(Exception):
    """Raised when another instance of the application is already running."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        super().__init__(f"Voice Dictation is already running (PID {pid})")


class SingleInstance:
    """Ensure only one instance of Voice Dictation runs at a time."""

    def __init__(self, lock_dir: str | None = None) -> None:
        self._lock_dir = Path(lock_dir or DEFAULT_LOCK_DIR).expanduser()
        self._lock_file = self._lock_dir / LOCK_FILE_NAME
        self._fh: object | None = None
        self._locked = False

    @property
    def lock_file(self) -> Path:
        """Path to the PID lock file."""
        return self._lock_file

    @property
    def is_locked(self) -> bool:
        """Check if the lock is currently held."""
        return self._locked

    def acquire(self) -> None:
        """Try to acquire the single-instance lock.

        Raises AlreadyRunningError if another instance is running.
        Safe to call multiple times — subsequent calls are no-ops.
        """
        if self._locked:
            logger.debug("Single-instance lock already held, skipping acquire")
            return

        self._lock_dir.mkdir(parents=True, exist_ok=True)

        # Read any existing PID for stale-lock detection / error reporting.
        existing_pid = self._read_pid()

        if existing_pid is not None and self._is_process_running(existing_pid):
            logger.warning(f"Another instance is running (PID {existing_pid})")
            raise AlreadyRunningError(existing_pid)

        if existing_pid is not None:
            logger.info(f"Removing stale lock from PID {existing_pid}")

        # Open / create the lock file. We keep the handle open for the
        # lifetime of the lock (the OS releases the flock on close).
        # SIM115 — open is intentional here; the handle must outlive
        # any single with-block because the file lock is tied to it.
        self._fh = open(self._lock_file, "a+b")  # noqa: SIM115

        try:
            self._try_lock()
        except OSError:
            # Lock contention: another live process holds it. Try to read its
            # PID for a meaningful error; fall back to -1 if unreadable.
            self._fh.close()
            self._fh = None
            live_pid = self._read_pid() or -1
            raise AlreadyRunningError(live_pid) from None

        # We hold the lock — write our PID into the file.
        self._write_pid(os.getpid())
        self._locked = True
        logger.debug(f"Single-instance lock acquired (PID {os.getpid()})")

    def release(self) -> None:
        """Release the single-instance lock and remove the PID file."""
        if not self._locked and self._fh is None:
            return

        logger.debug("Releasing single-instance lock")

        if self._fh is not None:
            try:
                self._release_lock()
            except OSError as e:
                logger.warning(f"Failed to release file lock: {e}")
            try:
                self._fh.close()
            except OSError as e:
                logger.warning(f"Failed to close lock file: {e}")
            self._fh = None

        try:
            self._lock_file.unlink(missing_ok=True)
        except OSError as e:
            logger.warning(f"Failed to remove lock file {self._lock_file}: {e}")

        self._locked = False

    def __enter__(self) -> SingleInstance:
        self.acquire()
        return self

    def __exit__(self, *args) -> None:
        self.release()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_pid(self) -> int | None:
        """Read and parse the PID from the lock file, if valid."""
        if not self._lock_file.exists():
            return None
        try:
            raw = self._lock_file.read_bytes().strip()
        except OSError as e:
            logger.warning(f"Failed to read lock file {self._lock_file}: {e}")
            return None
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            logger.warning(f"Invalid PID content in lock file: {raw!r}")
            return None

    def _write_pid(self, pid: int) -> None:
        """Write the current PID into the lock file."""
        assert self._fh is not None
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(f"{pid}\n".encode("ascii"))
        self._fh.flush()
        # fsync may fail on some platforms/filesystems; not fatal.
        with contextlib.suppress(OSError):
            os.fsync(self._fh.fileno())

    @staticmethod
    def _is_process_running(pid: int) -> bool:
        """Check whether a process with the given PID is alive."""
        if IS_WINDOWS:
            return _is_process_running_windows(pid)
        return _is_process_running_unix(pid)

    # ------------------------------------------------------------------
    # Platform locking
    # ------------------------------------------------------------------

    def _try_lock(self) -> None:
        """Attempt a non-blocking exclusive lock on the open file handle."""
        assert self._fh is not None
        if IS_WINDOWS:
            _lock_windows(self._fh)
        else:
            _lock_unix(self._fh)

    def _release_lock(self) -> None:
        """Release the platform-specific file lock."""
        assert self._fh is not None
        if IS_WINDOWS:
            _unlock_windows(self._fh)
        else:
            _unlock_unix(self._fh)


# ======================================================================
# Platform-specific lock helpers (module-level for testability)
# ======================================================================


def _is_process_running_unix(pid: int) -> bool:
    """Return True if a Unix process with *pid* is alive."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we may not signal it — treat as running.
        return True
    except OSError:
        return False
    return True


def _is_process_running_windows(pid: int) -> bool:
    """Return True if a Windows process with *pid* is alive."""
    if pid <= 0:
        return False
    try:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000  # noqa: N806
        STILL_ACTIVE = 259  # noqa: N806
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception as e:
        logger.warning(f"Windows process check failed for PID {pid}: {e}")
        return False


def _lock_unix(fh: object) -> None:
    """Acquire a non-blocking exclusive lock on Unix."""
    import fcntl

    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_unix(fh: object) -> None:
    """Release the exclusive lock on Unix."""
    import fcntl

    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _lock_windows(fh: object) -> None:
    """Acquire a non-blocking exclusive lock on Windows via msvcrt."""
    import msvcrt

    try:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise


def _unlock_windows(fh: object) -> None:
    """Release the exclusive lock on Windows via msvcrt."""
    import msvcrt

    try:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        raise
