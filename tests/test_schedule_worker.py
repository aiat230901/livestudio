from queue import Queue
from threading import Event
from types import SimpleNamespace

import pytest

from desktop.worker import run_job
from utils.recording_result import RecordingResult


@pytest.mark.parametrize(
    "session_end,window_end,expected_duration,reason",
    [
        (160, 120, 20, "schedule_end"),
        (120, 160, 20, "duration"),
        (120, 120, 20, "duration"),
        (None, 120, 20, "schedule_end"),
        (160, None, 60, "duration"),
    ],
)
def test_worker_enforces_earliest_limit_without_resetting_budget(
    monkeypatch, session_end, window_end, expected_duration, reason
):
    captured = []

    class Recorder:
        def __init__(self, config, **kwargs):
            captured.append(config.duration)
            self.tiktok = SimpleNamespace(http_client=SimpleNamespace())

        def start_recording(self, *args):
            return RecordingResult(None, "duration", 0)

    monkeypatch.setattr("desktop.worker.TikTokRecorder", Recorder)
    monkeypatch.setattr("desktop.worker.time.time", lambda: 100)
    events = Queue()
    run_job(
        dict(
            kind="record",
            job_id="job",
            username="user",
            room_id="room",
            output="unused",
            deadline_utc=session_end,
            window_end_utc=window_end,
        ),
        events,
        Event(),
    )
    assert captured == [expected_duration]
    assert events.get_nowait()["payload"]["reason"] == reason
