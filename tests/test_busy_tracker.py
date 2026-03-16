from __future__ import annotations

from openclaw_skins.models import BusyRunTracker


def test_busy_tracker_handles_overlapping_runs() -> None:
    tracker = BusyRunTracker()
    assert tracker.busy is False

    tracker.apply_agent_event("run-1", "lifecycle", {"phase": "start"})
    tracker.apply_agent_event("run-2", "lifecycle", {"phase": "start"})
    assert tracker.busy is True
    assert tracker.active_run_ids == {"run-1", "run-2"}

    tracker.apply_agent_event("run-1", "lifecycle", {"phase": "end"})
    assert tracker.busy is True
    assert tracker.active_run_ids == {"run-2"}

    tracker.apply_agent_event("run-2", "lifecycle", {"phase": "error"})
    assert tracker.busy is False
    assert tracker.active_run_ids == set()


def test_busy_tracker_starts_when_midstream_activity_arrives() -> None:
    tracker = BusyRunTracker()

    tracker.apply_agent_event("run-9", "assistant", {"text": "hello"})
    assert tracker.busy is True
    assert tracker.active_run_ids == {"run-9"}

    tracker.apply_agent_event("run-9", "lifecycle", {"phase": "end"})
    assert tracker.busy is False
