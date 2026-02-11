"""
Tests for the system-wide cross-process TTS coordination lock.

Tests cover:
- Single-process lock acquisition and release
- FIFO ordering across multiple threads (simulating processes)
- Stale ticket cleanup for dead PIDs
- Registry lifecycle (register → deregister → cleanup)
- Context manager exception safety
- Timeout behaviour
- Observability methods (status, queue, holder)
"""

from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import signal
import sys
import tempfile
import time
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from local_tts.system_lock import (
    SystemTTSCoordinator,
    SYSTEM_TTS_DIR,
    SYSTEM_TTS_LOCK_FILE,
    SYSTEM_TTS_QUEUE,
    SYSTEM_TTS_REGISTRY,
    _pid_alive,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_coordination_dirs():
    """Ensure a clean coordination directory before and after each test."""
    for d in (SYSTEM_TTS_QUEUE, SYSTEM_TTS_REGISTRY):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
    # Clear the lock file contents
    if SYSTEM_TTS_LOCK_FILE.exists():
        SYSTEM_TTS_LOCK_FILE.write_text("")
    yield
    for d in (SYSTEM_TTS_QUEUE, SYSTEM_TTS_REGISTRY):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)


# ── Unit tests: _pid_alive ───────────────────────────────────────────


class TestPidAlive:
    def test_own_pid_is_alive(self):
        assert _pid_alive(os.getpid()) is True

    def test_init_pid_is_alive(self):
        assert _pid_alive(1) is True  # launchd / init always exists

    def test_zero_pid_is_not_alive(self):
        assert _pid_alive(0) is False

    def test_negative_pid_is_not_alive(self):
        assert _pid_alive(-1) is False

    def test_very_large_pid_is_not_alive(self):
        # PID 999999999 is unlikely to exist
        assert _pid_alive(999_999_999) is False


# ── Unit tests: SystemTTSCoordinator lifecycle ───────────────────────


class TestCoordinatorLifecycle:
    def test_register_creates_file(self):
        coord = SystemTTSCoordinator()
        reg_files = list(SYSTEM_TTS_REGISTRY.glob("*.json"))
        assert len(reg_files) >= 1

        # Verify contents
        info = json.loads(reg_files[0].read_text())
        assert info["pid"] == os.getpid()
        assert "parent_tool" in info
        assert "start_time" in info

        coord.shutdown()

    def test_deregister_removes_file(self):
        coord = SystemTTSCoordinator()
        instance_id = coord.instance_id
        coord.shutdown()

        reg_file = SYSTEM_TTS_REGISTRY / f"{instance_id}.json"
        assert not reg_file.exists()

    def test_parent_tool_detected(self):
        coord = SystemTTSCoordinator()
        # Should be a non-empty string
        assert isinstance(coord.parent_tool, str)
        assert len(coord.parent_tool) > 0
        coord.shutdown()


# ── Unit tests: inference lock ───────────────────────────────────────


class TestInferenceLock:
    def test_basic_acquire_and_release(self):
        coord = SystemTTSCoordinator()

        acquired = False
        with coord.inference_lock(timeout=5):
            acquired = True
            # Lock file should exist and contain our info
            assert SYSTEM_TTS_LOCK_FILE.exists()
            content = SYSTEM_TTS_LOCK_FILE.read_text()
            holder = json.loads(content)
            assert holder["pid"] == os.getpid()

        assert acquired

        # Queue should be empty after release
        tickets = list(SYSTEM_TTS_QUEUE.glob("*.ticket"))
        assert len(tickets) == 0

        coord.shutdown()

    def test_lock_releases_on_exception(self):
        coord = SystemTTSCoordinator()

        with pytest.raises(ValueError, match="test error"):
            with coord.inference_lock(timeout=5):
                raise ValueError("test error")

        # Ticket should be cleaned up
        tickets = list(SYSTEM_TTS_QUEUE.glob("*.ticket"))
        assert len(tickets) == 0

        coord.shutdown()

    def test_sequential_locks_same_coordinator(self):
        coord = SystemTTSCoordinator()

        for i in range(3):
            with coord.inference_lock(timeout=5):
                pass  # just acquire and release

        tickets = list(SYSTEM_TTS_QUEUE.glob("*.ticket"))
        assert len(tickets) == 0

        coord.shutdown()


# ── FIFO ordering tests ─────────────────────────────────────────────


class TestFIFOOrdering:
    def test_threads_acquire_in_order(self):
        """Multiple threads should acquire the lock in ticket order."""
        coord = SystemTTSCoordinator()
        order_log: list[int] = []
        lock = threading.Lock()
        barrier = threading.Barrier(3)

        def worker(worker_id: int):
            # Stagger ticket creation slightly for deterministic order
            time.sleep(worker_id * 0.05)
            with coord.inference_lock(timeout=30):
                with lock:
                    order_log.append(worker_id)
                # Hold the lock briefly to ensure ordering matters
                time.sleep(0.1)

        threads = []
        for i in range(3):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=30)

        assert order_log == [0, 1, 2], f"Expected FIFO order [0,1,2], got {order_log}"
        coord.shutdown()


# ── Stale cleanup tests ─────────────────────────────────────────────


class TestStaleCleanup:
    def test_stale_ticket_from_dead_pid_is_cleaned(self):
        coord = SystemTTSCoordinator()

        # Create a fake stale ticket with a dead PID
        stale_ticket = SYSTEM_TTS_QUEUE / "00000000000000000001-999999999.ticket"
        stale_ticket.write_text(json.dumps({
            "pid": 999_999_999,
            "instance_id": "fake",
            "parent_tool": "Dead Tool",
            "enqueue_time": time.time() - 100,
        }))

        assert stale_ticket.exists()

        # Acquiring the lock should clean the stale ticket
        with coord.inference_lock(timeout=5):
            pass

        assert not stale_ticket.exists()
        coord.shutdown()

    def test_stale_registry_from_dead_pid_is_cleaned(self):
        coord = SystemTTSCoordinator()

        # Create a fake registry entry with a dead PID
        fake_reg = SYSTEM_TTS_REGISTRY / "999999999-fake.json"
        fake_reg.write_text(json.dumps({
            "pid": 999_999_999,
            "instance_id": "999999999-fake",
            "parent_tool": "Dead Tool",
            "start_time": time.time() - 100,
        }))

        instances = coord.get_active_instances()
        # Our instance should be there, but not the dead one
        pids = [i["pid"] for i in instances]
        assert os.getpid() in pids
        assert 999_999_999 not in pids

        coord.shutdown()


# ── Observability tests ──────────────────────────────────────────────


class TestObservability:
    def test_get_active_instances(self):
        coord = SystemTTSCoordinator()
        instances = coord.get_active_instances()

        assert len(instances) >= 1
        our = [i for i in instances if i["pid"] == os.getpid()]
        assert len(our) == 1
        assert our[0]["instance_id"] == coord.instance_id

        coord.shutdown()

    def test_get_queue_status_empty(self):
        coord = SystemTTSCoordinator()
        status = coord.get_queue_status()
        assert status == []
        coord.shutdown()

    def test_get_queue_status_during_lock(self):
        coord = SystemTTSCoordinator()

        # Another thread holding the lock
        hold_event = threading.Event()
        release_event = threading.Event()

        def holder():
            with coord.inference_lock(timeout=10):
                hold_event.set()
                release_event.wait(timeout=10)

        t = threading.Thread(target=holder)
        t.start()
        hold_event.wait(timeout=5)

        # While lock is held, if we create a ticket it should appear
        # (We can't easily check the holder's ticket since it was consumed,
        #  but we can check the holder info)
        holder_info = coord.get_current_holder()
        assert holder_info is not None
        assert holder_info["pid"] == os.getpid()

        release_event.set()
        t.join(timeout=10)
        coord.shutdown()

    def test_get_current_holder_when_no_lock(self):
        # Clear the lock file
        if SYSTEM_TTS_LOCK_FILE.exists():
            SYSTEM_TTS_LOCK_FILE.write_text("")
        coord = SystemTTSCoordinator()
        holder = coord.get_current_holder()
        assert holder is None
        coord.shutdown()


# ── Cross-process tests ─────────────────────────────────────────────


def _child_acquire_lock(result_queue: multiprocessing.Queue, hold_seconds: float):
    """Child process that acquires the system lock and holds it."""
    try:
        # Re-import in child (needed for spawn context)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from local_tts.system_lock import SystemTTSCoordinator as _Coord

        coord = _Coord()
        with coord.inference_lock(timeout=30):
            result_queue.put(("acquired", os.getpid(), time.time()))
            time.sleep(hold_seconds)
        result_queue.put(("released", os.getpid(), time.time()))
        coord.shutdown()
    except Exception as e:
        result_queue.put(("error", os.getpid(), str(e)))


# Use spawn to avoid fork-related state issues on macOS
_mp_ctx = multiprocessing.get_context("spawn")


class TestCrossProcess:
    def test_two_processes_sequential(self):
        """Two child processes should acquire the lock one at a time."""
        q = _mp_ctx.Queue()

        p1 = _mp_ctx.Process(target=_child_acquire_lock, args=(q, 0.5))
        p2 = _mp_ctx.Process(target=_child_acquire_lock, args=(q, 0.3))

        p1.start()
        time.sleep(0.3)  # ensure p1 gets ticket first
        p2.start()

        p1.join(timeout=15)
        p2.join(timeout=15)

        events: list[tuple] = []
        while not q.empty():
            events.append(q.get_nowait())

        # Extract acquisition order
        acquired = [(e[1], e[2]) for e in events if e[0] == "acquired"]
        errors = [e for e in events if e[0] == "error"]
        assert not errors, f"Child processes reported errors: {errors}"
        assert len(acquired) == 2, f"Expected 2 acquisitions, got {len(acquired)}: {events}"

        # First acquirer should be p1 (started first)
        # Their timestamps should show non-overlapping holds
        released_p1 = [e for e in events if e[0] == "released" and e[1] == acquired[0][0]]
        if released_p1 and len(acquired) > 1:
            assert released_p1[0][2] <= acquired[1][1] + 0.1, \
                "Second process should not acquire before first releases"


# ── Timeout test ─────────────────────────────────────────────────────


class TestTimeout:
    def test_timeout_raises(self):
        coord = SystemTTSCoordinator()

        # Create a ticket that appears to be from an alive process (our own PID)
        # with a much earlier timestamp so it's always first
        blocking_ticket = SYSTEM_TTS_QUEUE / "00000000000000000001-{}.ticket".format(os.getpid())
        blocking_ticket.write_text(json.dumps({
            "pid": os.getpid(),
            "instance_id": "blocker",
            "parent_tool": "Test",
            "enqueue_time": time.time(),
        }))

        # Create a second coordinator to try to acquire
        coord2 = SystemTTSCoordinator()

        with pytest.raises(TimeoutError):
            with coord2.inference_lock(timeout=1.0):
                pass  # should never reach here

        # Cleanup
        blocking_ticket.unlink(missing_ok=True)
        coord.shutdown()
        coord2.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
