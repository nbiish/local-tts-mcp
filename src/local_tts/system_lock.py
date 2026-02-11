"""
System-wide cross-process coordination for Local TTS MCP servers.

Ensures only one TTS inference runs at a time across ALL MCP server instances
on the system, regardless of which AI tool (VS Code Copilot, Claude Desktop,
Cursor, Windsurf, etc.) spawned them.

Uses:
- File-based FIFO ticket queue for fair ordering
- fcntl.flock() for mutual exclusion (auto-released on process crash)
- PID liveness checks for stale ticket/registry cleanup
- Parent process detection to identify the spawning AI tool
"""

from __future__ import annotations

import atexit
import fcntl
import json
import logging
import os
import signal
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger("local-tts")

# ── Shared filesystem paths ──────────────────────────────────────────
SYSTEM_TTS_DIR = Path("/tmp/local-tts-mcp")
SYSTEM_TTS_LOCK_FILE = SYSTEM_TTS_DIR / "inference.lock"
SYSTEM_TTS_REGISTRY = SYSTEM_TTS_DIR / "registry"
SYSTEM_TTS_QUEUE = SYSTEM_TTS_DIR / "queue"

# ── Constants ────────────────────────────────────────────────────────
LOCK_TIMEOUT_S = 120          # Max time to wait for the system lock
QUEUE_POLL_INTERVAL_S = 0.25  # How often to check queue position
STALE_TICKET_AGE_S = 300      # Remove tickets older than 5 min (safety net)

# Known parent process → AI tool mapping
_TOOL_MAP: dict[str, str] = {
    "code":      "VS Code / GitHub Copilot",
    "code-insi": "VS Code Insiders / GitHub Copilot",
    "cursor":    "Cursor",
    "claude":    "Claude Desktop",
    "windsurf":  "Windsurf",
    "zed":       "Zed",
    "warp":      "Warp Terminal",
    "terminal":  "Terminal (manual)",
    "iterm":     "iTerm2 (manual)",
    "kitty":     "Kitty (manual)",
    "alacritty": "Alacritty (manual)",
}


def _pid_alive(pid: int) -> bool:
    """Check whether *pid* is still running (POSIX)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, but we lack permission to signal it
    except OSError:
        return False


def _detect_parent_tool() -> str:
    """Walk up the process tree to identify the AI tool that spawned us."""
    try:
        # Get the full process ancestry via ps
        result = subprocess.run(
            ["ps", "-o", "ppid=,comm=", "-p", str(os.getpid())],
            capture_output=True, text=True, timeout=5,
        )
        ppid_str = result.stdout.strip().split()[0] if result.stdout.strip() else ""
        ppid = int(ppid_str) if ppid_str.isdigit() else os.getppid()

        # Walk up to 8 levels
        visited: set[int] = set()
        current_pid = ppid
        for _ in range(8):
            if current_pid <= 1 or current_pid in visited:
                break
            visited.add(current_pid)

            res = subprocess.run(
                ["ps", "-p", str(current_pid), "-o", "ppid=,comm="],
                capture_output=True, text=True, timeout=5,
            )
            parts = res.stdout.strip().split(None, 1)
            if len(parts) < 2:
                break

            next_ppid_str, comm = parts
            comm_lower = comm.strip().lower()

            for key, tool_name in _TOOL_MAP.items():
                if key in comm_lower:
                    return tool_name

            current_pid = int(next_ppid_str) if next_ppid_str.strip().isdigit() else 1

    except Exception as exc:
        logger.debug(f"[SystemLock] Parent tool detection failed: {exc}")

    return "Unknown"


class SystemTTSCoordinator:
    """
    Cross-process coordinator that guarantees only one TTS model load /
    inference happens at any given time across the entire system.

    Lifecycle:
        coordinator = SystemTTSCoordinator()   # registers PID
        with coordinator.inference_lock():     # blocks until our turn
            model = load_model()
            audio = model.generate(...)
        # lock released, next process proceeds
        coordinator.shutdown()                 # deregisters PID
    """

    def __init__(self) -> None:
        self.pid: int = os.getpid()
        self.instance_id: str = f"{self.pid}-{time.time_ns()}"
        self.parent_tool: str = _detect_parent_tool()
        self._lock_fd: Any | None = None
        self._ticket_path: Path | None = None

        # Ensure coordination directories exist (race-safe with exist_ok)
        for d in (SYSTEM_TTS_DIR, SYSTEM_TTS_REGISTRY, SYSTEM_TTS_QUEUE):
            d.mkdir(parents=True, exist_ok=True)

        self._register()
        atexit.register(self.shutdown)

        logger.info(
            f"[SystemLock] Registered instance {self.instance_id} "
            f"(PID {self.pid}, Tool: {self.parent_tool})"
        )

    # ── Registry management ──────────────────────────────────────────

    def _register(self) -> None:
        """Write our instance info to the shared registry."""
        reg_file = SYSTEM_TTS_REGISTRY / f"{self.instance_id}.json"
        info = {
            "pid": self.pid,
            "instance_id": self.instance_id,
            "parent_tool": self.parent_tool,
            "start_time": time.time(),
            "start_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        reg_file.write_text(json.dumps(info, indent=2))

    def _deregister(self) -> None:
        """Remove our registry entry."""
        reg_file = SYSTEM_TTS_REGISTRY / f"{self.instance_id}.json"
        try:
            reg_file.unlink(missing_ok=True)
        except Exception:
            pass

    def _cleanup_stale_registry(self) -> None:
        """Purge registry entries whose PIDs are no longer running."""
        if not SYSTEM_TTS_REGISTRY.exists():
            return
        for entry in SYSTEM_TTS_REGISTRY.iterdir():
            if entry.suffix != ".json":
                continue
            try:
                info = json.loads(entry.read_text())
                pid = info.get("pid", 0)
                if not _pid_alive(pid):
                    entry.unlink(missing_ok=True)
                    logger.info(
                        f"[SystemLock] Cleaned stale registry: PID {pid} "
                        f"({info.get('parent_tool', '?')})"
                    )
            except Exception:
                entry.unlink(missing_ok=True)

    # ── Queue / ticket management ────────────────────────────────────

    def _create_ticket(self) -> Path:
        """Create a numbered ticket file in the shared queue."""
        # Nanosecond timestamp ensures ordering + PID for uniqueness
        ticket_name = f"{time.time_ns():020d}-{self.pid}.ticket"
        ticket_path = SYSTEM_TTS_QUEUE / ticket_name
        info = {
            "pid": self.pid,
            "instance_id": self.instance_id,
            "parent_tool": self.parent_tool,
            "enqueue_time": time.time(),
            "enqueue_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        ticket_path.write_text(json.dumps(info, indent=2))
        return ticket_path

    def _remove_ticket(self, ticket_path: Path) -> None:
        """Remove our ticket from the queue."""
        try:
            ticket_path.unlink(missing_ok=True)
        except Exception:
            pass

    def _cleanup_stale_tickets(self) -> None:
        """Remove tickets belonging to dead processes or past the age limit."""
        if not SYSTEM_TTS_QUEUE.exists():
            return
        now = time.time()
        for entry in SYSTEM_TTS_QUEUE.iterdir():
            if not entry.name.endswith(".ticket"):
                continue
            try:
                info = json.loads(entry.read_text())
                pid = info.get("pid", 0)
                enqueue_time = info.get("enqueue_time", 0)

                is_dead = not _pid_alive(pid)
                is_stale = (now - enqueue_time) > STALE_TICKET_AGE_S

                if is_dead or is_stale:
                    entry.unlink(missing_ok=True)
                    reason = "dead PID" if is_dead else "stale (age limit)"
                    logger.info(
                        f"[SystemLock] Cleaned {reason} ticket: PID {pid} "
                        f"({info.get('parent_tool', '?')})"
                    )
            except Exception:
                entry.unlink(missing_ok=True)

    def _sorted_tickets(self) -> list[str]:
        """Return ticket file names sorted by creation order (name sort)."""
        if not SYSTEM_TTS_QUEUE.exists():
            return []
        return sorted(
            f.name for f in SYSTEM_TTS_QUEUE.iterdir()
            if f.name.endswith(".ticket")
        )

    def _our_position(self, ticket_name: str) -> tuple[int, int]:
        """Return (our 1-based position, total tickets) in the queue."""
        tickets = self._sorted_tickets()
        total = len(tickets)
        try:
            pos = tickets.index(ticket_name) + 1
        except ValueError:
            pos = 0
        return pos, total

    def _who_is_first(self) -> dict[str, Any] | None:
        """Read info about the first ticket holder."""
        tickets = self._sorted_tickets()
        if not tickets:
            return None
        try:
            path = SYSTEM_TTS_QUEUE / tickets[0]
            return json.loads(path.read_text())
        except Exception:
            return None

    # ── Lock acquisition / release ───────────────────────────────────

    def _acquire_flock(self) -> None:
        """Acquire the POSIX file lock (blocking)."""
        self._lock_fd = open(SYSTEM_TTS_LOCK_FILE, "w")
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
        # Write current holder info for external inspection
        holder = {
            "pid": self.pid,
            "instance_id": self.instance_id,
            "parent_tool": self.parent_tool,
            "acquired_at": time.time(),
            "acquired_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        self._lock_fd.write(json.dumps(holder, indent=2))
        self._lock_fd.flush()

    def _release_flock(self) -> None:
        """Release the POSIX file lock."""
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                self._lock_fd.close()
            except Exception:
                pass
            self._lock_fd = None

    @contextmanager
    def inference_lock(self, timeout: float = LOCK_TIMEOUT_S):
        """
        Context manager that ensures exclusive system-wide TTS inference.

        Workflow:
        1. Create a ticket in the shared FIFO queue
        2. Wait until our ticket is first (poll + stale cleanup)
        3. Acquire ``fcntl.flock`` for hard mutual exclusion
        4. Yield to caller (model load + inference happens here)
        5. Release lock + remove ticket on exit

        Raises ``TimeoutError`` if we cannot acquire within *timeout* seconds.
        """
        ticket_path = self._create_ticket()
        ticket_name = ticket_path.name
        start = time.time()
        acquired = False

        try:
            # ── Phase 1: Wait for our ticket to be first ─────────
            logged_positions: set[int] = set()
            while True:
                self._cleanup_stale_tickets()
                tickets = self._sorted_tickets()

                if not tickets or tickets[0] == ticket_name:
                    break  # we are first

                elapsed = time.time() - start
                if elapsed > timeout:
                    raise TimeoutError(
                        f"[SystemLock] Timed out after {timeout:.0f}s waiting "
                        f"for inference lock"
                    )

                pos, total = self._our_position(ticket_name)
                if pos not in logged_positions:
                    logged_positions.add(pos)
                    first = self._who_is_first()
                    first_desc = (
                        f"PID {first['pid']} ({first['parent_tool']})"
                        if first else "unknown"
                    )
                    logger.info(
                        f"[SystemLock] Waiting — position {pos}/{total}. "
                        f"Current holder: {first_desc}. "
                        f"Elapsed: {elapsed:.1f}s"
                    )

                time.sleep(QUEUE_POLL_INTERVAL_S)

            # ── Phase 2: Acquire the hard file lock ──────────────
            self._acquire_flock()
            acquired = True
            elapsed = time.time() - start
            logger.info(
                f"[SystemLock] ✓ Acquired inference lock "
                f"(PID {self.pid}, Tool: {self.parent_tool}, "
                f"waited {elapsed:.2f}s)"
            )

            yield  # caller does model load + inference here

        finally:
            if acquired:
                self._release_flock()
                logger.info(
                    f"[SystemLock] Released inference lock "
                    f"(PID {self.pid}, Tool: {self.parent_tool})"
                )
            self._remove_ticket(ticket_path)

    # ── Observability ────────────────────────────────────────────────

    def get_active_instances(self) -> list[dict[str, Any]]:
        """Return info dicts for all currently registered TTS instances."""
        self._cleanup_stale_registry()
        instances: list[dict[str, Any]] = []
        if not SYSTEM_TTS_REGISTRY.exists():
            return instances
        for entry in SYSTEM_TTS_REGISTRY.iterdir():
            if entry.suffix != ".json":
                continue
            try:
                instances.append(json.loads(entry.read_text()))
            except Exception:
                pass
        return sorted(instances, key=lambda i: i.get("start_time", 0))

    def get_queue_status(self) -> list[dict[str, Any]]:
        """Return info dicts for all tickets currently in the queue."""
        self._cleanup_stale_tickets()
        status: list[dict[str, Any]] = []
        for name in self._sorted_tickets():
            try:
                path = SYSTEM_TTS_QUEUE / name
                info = json.loads(path.read_text())
                info["ticket"] = name
                status.append(info)
            except Exception:
                pass
        return status

    def get_current_holder(self) -> dict[str, Any] | None:
        """Read info about whoever currently holds the inference lock."""
        try:
            if SYSTEM_TTS_LOCK_FILE.exists():
                content = SYSTEM_TTS_LOCK_FILE.read_text().strip()
                if content:
                    return json.loads(content)
        except Exception:
            pass
        return None

    # ── Lifecycle ────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Clean up on exit — release lock, remove ticket, deregister."""
        self._release_flock()
        if self._ticket_path is not None:
            self._remove_ticket(self._ticket_path)
            self._ticket_path = None
        self._deregister()
        logger.info(
            f"[SystemLock] Shutdown complete "
            f"(PID {self.pid}, Tool: {self.parent_tool})"
        )
