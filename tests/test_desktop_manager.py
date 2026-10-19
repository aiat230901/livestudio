from queue import Queue
import pytest

from desktop.manager import RecordingManager
from desktop.store import DesktopStore


class Process:
    def __init__(self, **kwargs):
        self.job = kwargs["args"][0]
        self.alive = True
        self.exitcode = None

    def start(self):
        pass

    def is_alive(self):
        return self.alive

    def join(self, timeout=0):
        pass

    def close(self):
        pass


def setup(tmp_path):
    store = DesktopStore(tmp_path / "state.db")
    for user in ("one", "two"):
        store.save_channel(user, 60, str(tmp_path), True)
    manager = RecordingManager(store, process_factory=Process, clock=lambda: 100)
    manager.events = Queue()
    return store, manager


def deliver(manager, user, kind, **payload):
    job = manager.jobs[user]
    manager.events.put(
        dict(job_id=job["spec"]["job_id"], username=user, kind=kind, payload=payload)
    )
    job["process"].alive = False
    job["process"].exitcode = 0
    manager.tick()


def test_parallel_and_no_duplicate(tmp_path):
    store, manager = setup(tmp_path)
    manager.tick()
    ids = [j["spec"]["job_id"] for j in manager.jobs.values()]
    manager.enable("one", True)
    manager.tick()
    assert ids == [j["spec"]["job_id"] for j in manager.jobs.values()]
    deliver(manager, "one", "probe_done", room_id="room1")
    assert manager.jobs["one"]["spec"]["kind"] == "record"
    assert store.get_session("one", "room1")["deadline_utc"] == 160
    deliver(
        manager, "one", "record_done", path=None, reason="duration", bytes_written=10
    )
    manager.record_now("one")
    deliver(manager, "one", "probe_done", room_id="room1")
    assert "one" not in manager.jobs
    manager.record_now("one")
    deliver(manager, "one", "probe_done", room_id="room2")
    assert manager.jobs["one"]["spec"]["kind"] == "record"


def test_stop_during_probe_and_ignore_stale(tmp_path):
    store, manager = setup(tmp_path)
    manager.tick()
    manager.enable("one", False)
    deliver(manager, "one", "probe_done", room_id="room")
    assert "one" not in manager.jobs
    assert store.get_session("one", "room") is None
    manager.events.put(
        dict(
            job_id="old", username="two", kind="probe_done", payload={"room_id": "bad"}
        )
    )
    manager.tick()
    assert manager.jobs["two"]["spec"]["kind"] == "probe"


def test_crash_and_shutdown(tmp_path):
    _, manager = setup(tmp_path)
    manager.tick()
    manager.jobs["one"]["process"].alive = False
    manager.jobs["one"]["process"].exitcode = 1
    manager.tick()
    assert "one" not in manager.jobs
    assert manager.snapshot()["one"]["status"] == "Lỗi kết nối"
    manager.shutdown()
    assert manager.jobs["two"]["stop"].is_set()


def test_license_blocks_manual_and_scheduled_launch_and_finalizes_running_job(tmp_path):
    store, manager = setup(tmp_path)
    permitted = [False]
    manager.license_guard = lambda: permitted[0]
    manager.tick()
    manager.record_now("one")
    assert not manager.jobs
    permitted[0] = True
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    job = manager.jobs["one"]
    permitted[0] = False
    manager.tick()
    assert job["stop"].is_set() and job["stop_reason"] == "license_denied"
    assert manager.jobs["two"]["stop"].is_set()
    deliver(
        manager,
        "one",
        "record_done",
        path="saved.mp4",
        reason="user_stop",
        bytes_written=1000,
    )
    assert store.list_recordings()[0]["reason"] == "license_denied"
    assert store.list_recordings()[0]["path"] == "saved.mp4"
    assert store.get_session("one", "room")["state"] == "active"
    deliver(manager, "two", "probe_done", room_id="other")
    assert not manager.jobs
    permitted[0] = True
    manager.tick()
    assert manager.jobs["one"]["spec"]["kind"] == "probe"
    deliver(manager, "one", "probe_done", room_id="room")
    assert manager.jobs["one"]["spec"]["deadline_utc"] == 160


def test_license_denial_at_probe_completion_never_starts_recording(tmp_path):
    _, manager = setup(tmp_path)
    manager.tick()
    manager.license_guard = lambda: False
    deliver(manager, "one", "probe_done", room_id="room")
    assert "one" not in manager.jobs


def test_restart_preserves_deadline_and_completed_room(tmp_path):
    store, manager = setup(tmp_path)
    store.save_session("one", "room", 1, 50, "active")
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    assert "one" not in manager.jobs
    assert store.get_session("one", "room")["deadline_utc"] == 50
    # A new room gets its own limit, stored before the process is started.
    manager.record_now("one")
    deliver(manager, "one", "probe_done", room_id="new")
    assert manager.jobs["one"]["spec"]["deadline_utc"] == 160
    manager.stop_recording("one")
    deliver(
        manager, "one", "record_done", path=None, reason="user_stop", bytes_written=0
    )
    assert store.get_session("one", "new")["state"] == "stopped"
    manager.next_poll["one"] = 0
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="new")
    assert "one" not in manager.jobs
    manager.record_now("one")
    deliver(manager, "one", "probe_done", room_id="new")
    assert manager.jobs["one"]["spec"]["deadline_utc"] == 160


def test_network_retry_and_shutdown_do_not_reset_session(tmp_path):
    store, manager = setup(tmp_path)
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    deliver(
        manager,
        "one",
        "record_done",
        path="part.mp4",
        reason="network_error",
        bytes_written=8000,
    )
    assert store.get_session("one", "room")["state"] == "active"
    manager.record_now("one")
    deliver(manager, "one", "probe_done", room_id="room")
    assert manager.jobs["one"]["spec"]["deadline_utc"] == 160
    manager.shutdown()
    deliver(
        manager,
        "one",
        "record_done",
        path="part2.mp4",
        reason="user_stop",
        bytes_written=8000,
    )
    assert store.get_session("one", "room")["state"] == "active"
    assert len(store.list_recordings()) == 2


def scheduled_setup(tmp_path, rules, duration=60):
    store = DesktopStore(tmp_path / "scheduled.db")
    store.save_channel(
        "one", duration, str(tmp_path), True, mode="scheduled", schedules=rules
    )
    clock = [100]
    manager = RecordingManager(store, process_factory=Process, clock=lambda: clock[0])
    manager.events = Queue()
    return store, manager, clock


@pytest.mark.parametrize("duration", [None, 60])
def test_wait_start_stop_then_resume_same_room_with_original_deadline(
    tmp_path, duration
):
    rules = [
        dict(kind="once", start=110, end=120),
        dict(kind="once", start=130, end=150),
    ]
    store, manager, clock = scheduled_setup(tmp_path, rules, duration=duration)
    manager.tick()
    assert not manager.jobs
    assert manager.snapshot()["one"]["status"] == "Chờ lịch"
    clock[0] = 110
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    assert manager.jobs["one"]["spec"]["window_end_utc"] == 120
    expected_deadline = 170 if duration else None
    assert store.get_session("one", "room")["deadline_utc"] == expected_deadline
    clock[0] = 120
    manager.tick()
    assert manager.jobs["one"]["stop"].is_set()
    deliver(
        manager,
        "one",
        "record_done",
        path="first.mp4",
        reason="user_stop",
        bytes_written=8000,
    )
    assert not manager.jobs
    assert store.list_recordings()[0]["reason"] == "schedule_end"
    assert store.get_session("one", "room")["state"] == "active"
    clock[0] = 130
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    assert manager.jobs["one"]["spec"]["deadline_utc"] == expected_deadline
    assert manager.jobs["one"]["spec"]["window_end_utc"] == 150


def test_overlap_and_adjacent_rules_do_not_restart_or_duplicate(tmp_path):
    rules = [
        dict(kind="once", start=100, end=120),
        dict(kind="once", start=115, end=130),
        dict(kind="once", start=130, end=150),
    ]
    _, manager, clock = scheduled_setup(tmp_path, rules)
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    job = manager.jobs["one"]
    assert job["spec"]["window_end_utc"] == 150
    for tick in (115, 120, 130, 149):
        clock[0] = tick
        manager.tick()
        assert manager.jobs["one"] is job
        assert not job["stop"].is_set()


def test_manual_bypasses_schedule_but_not_room_budget(tmp_path):
    store, manager, clock = scheduled_setup(
        tmp_path, [dict(kind="once", start=200, end=250)]
    )
    manager.enable("one", False)
    manager.record_now("one")
    deliver(manager, "one", "probe_done", room_id="room")
    assert manager.jobs["one"]["spec"]["window_end_utc"] is None
    clock[0] = 110
    manager.tick()
    assert not manager.jobs["one"]["stop"].is_set()
    deliver(
        manager,
        "one",
        "record_done",
        path="part.mp4",
        reason="network_error",
        bytes_written=8000,
    )
    clock[0] = 120
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    assert manager.jobs["one"]["spec"]["deadline_utc"] == 160
    manager.stop_recording("one")
    deliver(
        manager,
        "one",
        "record_done",
        path="part2.mp4",
        reason="user_stop",
        bytes_written=8000,
    )
    clock[0] = 210
    manager.enable("one", True)
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    assert "one" not in manager.jobs
    assert store.get_session("one", "room")["state"] == "stopped"


def test_probe_finishing_after_window_cannot_start_recording(tmp_path):
    store, manager, clock = scheduled_setup(
        tmp_path, [dict(kind="once", start=100, end=105)]
    )
    manager.tick()
    clock[0] = 106
    deliver(manager, "one", "probe_done", room_id="room")
    assert not manager.jobs
    assert store.get_session("one", "room") is None


def test_restart_in_active_or_expired_window_preserves_completed_session(tmp_path):
    rule = dict(kind="once", start=100, end=200)
    store, manager, clock = scheduled_setup(tmp_path, [rule], duration=10)
    store.save_session("one", "room", 80, 90, "completed")
    clock[0] = 150
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    assert not manager.jobs
    store.close()
    store = DesktopStore(tmp_path / "scheduled.db")
    restarted = RecordingManager(store, process_factory=Process, clock=lambda: 201)
    restarted.tick()
    assert not restarted.jobs
    assert store.get_session("one", "room")["deadline_utc"] == 90


def test_stop_racing_network_error_keeps_manual_stop_persistent(tmp_path):
    store, manager, _ = scheduled_setup(
        tmp_path, [dict(kind="once", start=100, end=200)]
    )
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    manager.stop_recording("one")
    deliver(
        manager,
        "one",
        "record_done",
        path="saved.mp4",
        reason="network_error",
        bytes_written=8000,
    )
    assert store.get_session("one", "room")["state"] == "stopped"
    assert store.list_recordings()[0]["reason"] == "user_stop"


def test_reopen_inside_window_resumes_original_budget(tmp_path):
    store, _, _ = scheduled_setup(tmp_path, [dict(kind="once", start=100, end=300)])
    store.save_session("one", "room", 80, 200, "active")
    store.close()
    reopened = DesktopStore(tmp_path / "scheduled.db")
    manager = RecordingManager(reopened, process_factory=Process, clock=lambda: 150)
    manager.events = Queue()
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    assert manager.jobs["one"]["spec"]["deadline_utc"] == 200
    assert manager.jobs["one"]["spec"]["window_end_utc"] == 300


def test_missed_gap_stops_old_job_before_starting_next_window(tmp_path):
    rules = [
        dict(kind="once", start=100, end=110),
        dict(kind="once", start=120, end=140),
    ]
    _, manager, clock = scheduled_setup(tmp_path, rules)
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room")
    old = manager.jobs["one"]
    clock[0] = 125  # No coordinator ticks occurred during the gap.
    manager.tick()
    assert old["stop"].is_set()
    assert manager.jobs["one"] is old
    deliver(
        manager,
        "one",
        "record_done",
        path="old.mp4",
        reason="user_stop",
        bytes_written=8000,
    )
    assert manager.jobs["one"]["spec"]["kind"] == "probe"
    deliver(manager, "one", "probe_done", room_id="room")
    assert manager.jobs["one"]["spec"]["window_end_utc"] == 140
