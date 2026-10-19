"""Real Windows spawn + FFmpeg check with a controlled source and short windows."""

import json
import multiprocessing
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from desktop.manager import RecordingManager  # noqa: E402
from desktop.store import DesktopStore  # noqa: E402
from desktop.worker import run_job  # noqa: E402
from diagnostics.phase3_check import verify  # noqa: E402


class ControlledAPI:
    def __init__(self, media):
        self.media = media
        self.http_client = SimpleNamespace()

    def get_room_id_from_user(self, user):
        return "same-controlled-room"

    def is_room_alive(self, room):
        return True

    def get_live_url_candidates(self, *args, **kwargs):
        return ["controlled"]

    def download_live_stream(self, url):
        yield Path(self.media).read_bytes()
        # Keep transport open without appending another FLV header.
        while True:
            time.sleep(0.03)
            yield b""


def controlled_job(job, events, stop):
    media = str(Path(job["output"]).parent / "sample.flv")
    with (
        patch("desktop.worker.TikTokAPI", lambda **kwargs: ControlledAPI(media)),
        patch("core.tiktok_recorder.TikTokAPI", lambda **kwargs: ControlledAPI(media)),
    ):
        run_job(job, events, stop)


def controlled_process(*, target, args):
    return multiprocessing.get_context("spawn").Process(
        target=controlled_job, args=args
    )


def run_check(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    media = folder / "sample.flv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-f",
            "flv",
            str(media),
        ],
        check=True,
        timeout=30,
    )
    store = DesktopStore(folder / "state.db")
    now = time.time()
    first = [
        dict(kind="once", start=now + 1, end=now + 2.8),
        dict(kind="once", start=now + 2.4, end=now + 3.6),
        dict(kind="once", start=now + 4.5, end=now + 6),
    ]
    store.save_channel(
        "scheduled_one",
        20,
        str(folder / "one"),
        True,
        mode="scheduled",
        schedules=first,
    )
    store.save_channel(
        "scheduled_two",
        1,
        str(folder / "two"),
        True,
        mode="scheduled",
        schedules=[dict(kind="once", start=now + 1.4, end=now + 6)],
    )
    manager = RecordingManager(store, process_factory=controlled_process)
    peak = 0
    job_ids = {user: set() for user in ("scheduled_one", "scheduled_two")}
    original_deadline = None
    failures = []
    try:
        manager.tick()
        assert not manager.jobs, "Probed a channel outside its window"
        while time.time() < now + 18:
            manager.tick()
            peak = max(
                peak, sum(j["spec"]["kind"] == "record" for j in manager.jobs.values())
            )
            for user, job in manager.jobs.items():
                if job["spec"]["kind"] == "record":
                    job_ids[user].add(job["spec"]["job_id"])
                    if user == "scheduled_one":
                        if original_deadline is None:
                            original_deadline = job["spec"]["deadline_utc"]
                        assert original_deadline == job["spec"]["deadline_utc"], (
                            "Room budget was reset"
                        )
            if len(store.list_recordings()) >= 3 and not manager.jobs:
                break
            time.sleep(0.04)
        records = store.list_recordings()
        one = [r for r in records if r["username"] == "scheduled_one"]
        two = [r for r in records if r["username"] == "scheduled_two"]
        assert len(one) == 2 and all(r["reason"] == "schedule_end" for r in one)
        assert len(two) == 1 and two[0]["reason"] == "duration"
        assert peak == 2, "Did not record concurrently"
        assert len(job_ids["scheduled_one"]) == 2 and len(job_ids["scheduled_two"]) == 1
        verified = [dict(path=r["path"], **verify(r["path"])) for r in records]
        assert (
            store.get_session("scheduled_one", "same-controlled-room")["deadline_utc"]
            == original_deadline
        )
    finally:
        manager.shutdown()
        deadline = time.monotonic() + 15
        while manager.jobs and time.monotonic() < deadline:
            manager.tick()
            time.sleep(0.04)
        for job in manager.jobs.values():
            # Emergency cleanup is restricted to this controlled diagnostic.
            job["process"].terminate()
            job["process"].join(timeout=5)
            failures.append("Hung test worker")
        store.close()
    store = DesktopStore(folder / "state.db")
    restarted = RecordingManager(store, process_factory=controlled_process)
    restarted.tick()
    assert not restarted.jobs, "Restart replayed an expired schedule"
    assert (
        store.get_session("scheduled_one", "same-controlled-room")["deadline_utc"]
        == original_deadline
    )
    report = dict(
        peak_parallel_recordings=peak,
        recordings=records,
        verified=verified,
        record_jobs={user: len(ids) for user, ids in job_ids.items()},
        deadline_preserved=True,
        expired_restart_no_jobs=True,
        failures=failures,
    )
    store.close()
    (folder / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    assert not failures
    return report


def main():
    folder = (
        ROOT / "diagnostics" / f"phase4-controlled-{time.strftime('%Y%m%d-%H%M%S')}"
    )
    report = run_check(folder)
    print(
        json.dumps(
            dict(
                report=str(folder / "report.json"),
                verified=len(report["verified"]),
                peak=report["peak_parallel_recordings"],
            )
        )
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
