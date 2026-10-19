"""Short end-to-end check through the desktop coordinator, with isolated data."""

import argparse
import json
import multiprocessing
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from desktop.manager import RecordingManager  # noqa: E402
from desktop.store import DesktopStore  # noqa: E402
from desktop.worker import run_job  # noqa: E402


class FileAPI:
    def __init__(self, media):
        self.media = media
        self.ended = False
        self.http_client = type("Client", (), {})()

    def get_room_id_from_user(self, user):
        return "controlled-room"

    def is_room_alive(self, room):
        return not self.ended

    def get_live_url_candidates(self, *args, **kwargs):
        return ["controlled"]

    def download_live_stream(self, url):
        yield Path(self.media).read_bytes()
        self.ended = True


def controlled_job(job, events, stop):
    media = str(ROOT / "diagnostics" / "phase3-sample.flv")
    with (
        patch("desktop.worker.TikTokAPI", lambda **kw: FileAPI(media)),
        patch("core.tiktok_recorder.TikTokAPI", lambda **kw: FileAPI(media)),
    ):
        run_job(job, events, stop)


def controlled_process(*, target, args):
    return multiprocessing.get_context("spawn").Process(
        target=controlled_job, args=args
    )


def verify(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    data = json.loads(result.stdout)
    assert {"video", "audio"} <= {s["codec_type"] for s in data["streams"]}
    decode = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-i",
            path,
            "-fps_mode",
            "passthrough",
            "-enc_time_base",
            "demux",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    assert not decode.stderr, decode.stderr.decode(errors="replace")
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return dict(
        duration=float(data["format"]["duration"]),
        bytes=Path(path).stat().st_size,
        resolution=f"{video['width']}x{video['height']}",
        strict_decode=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    options = parser.parse_args()
    mode = "live" if options.live else "controlled"
    folder = ROOT / "diagnostics" / f"phase3-{mode}-{time.strftime('%Y%m%d-%H%M%S')}"
    folder.mkdir()
    if not options.live:
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
                str(ROOT / "diagnostics" / "phase3-sample.flv"),
            ],
            check=True,
            timeout=30,
        )
    store = DesktopStore(folder / "state.db")
    users = ("sacngockhang_official", "ungthaimenuochoa")
    for user in users:
        store.save_channel(user, 15, str(folder / "videos" / user), True)
    manager = RecordingManager(
        store, process_factory=None if options.live else controlled_process
    )
    deadline = time.monotonic() + 110
    peak = 0
    while time.monotonic() < deadline:
        manager.tick()
        peak = max(
            peak, sum(j["spec"]["kind"] == "record" for j in manager.jobs.values())
        )
        if len(store.list_recordings()) >= 2:
            break
        if not manager.jobs and len(manager.next_poll) == len(users):
            break
        time.sleep(0.1)
    manager.shutdown()
    deadline = time.monotonic() + 45
    while manager.jobs and time.monotonic() < deadline:
        manager.tick()
        time.sleep(0.1)
    # Emergency cleanup is for a failed diagnostic only; never a normal UI stop.
    hung = bool(manager.jobs)
    for job in manager.jobs.values():
        job["process"].terminate()
        job["process"].join(timeout=5)
    records = store.list_recordings()
    output = dict(
        mode=mode,
        peak_parallel_recordings=peak,
        hung=hung,
        states=manager.snapshot(),
        recordings=records,
        verified=[],
    )
    for record in records:
        if record.get("path") and record["reason"] != "conversion_error":
            output["verified"].append(
                dict(
                    username=record["username"],
                    path=record["path"],
                    **verify(record["path"]),
                )
            )
    (folder / "report.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            dict(
                report=str(folder / "report.json"),
                peak=peak,
                verified=len(output["verified"]),
                hung=hung,
            ),
            ensure_ascii=False,
        )
    )
    store.close()
    return 0 if len(output["verified"]) == 2 and not hung and peak == 2 else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
