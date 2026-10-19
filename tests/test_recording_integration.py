"""Controlled checks, separate from evidence of a real TikTok recording.

Run: .venv/Scripts/python -m pytest tests/test_recording_integration.py -v
"""

import json
import io
import multiprocessing
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.tiktok_recorder import TikTokRecorder  # noqa: E402
from utils.enums import Mode  # noqa: E402
from utils.recorder_config import RecorderConfig  # noqa: E402
from utils.video_management import VideoManagement  # noqa: E402


class FileStreamAPI:
    """Only TikTok discovery/transport is replaced; file writes and FFmpeg are real."""

    def __init__(self, media):
        self.media = Path(media)
        self.ended = False

    def get_room_id_from_user(self, user):
        return "controlled-room"

    def is_country_blacklisted(self):
        return False

    def is_room_alive(self, room_id):
        return not self.ended

    def get_live_url_candidates(self, room_id, user=None):
        return ["controlled://sample.flv"]

    def download_live_stream(self, url):
        with self.media.open("rb") as stream:
            while chunk := stream.read(4096):
                yield chunk
        self.ended = True


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    folder = tmp_path_factory.mktemp("media")
    output = folder / "sample.flv"
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
            "sine=frequency=440:sample_rate=44100",
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
            str(output),
        ],
        check=True,
        timeout=30,
    )
    assert output.stat().st_size > 4096
    return output


def verify_media(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    data = json.loads(result.stdout)
    assert {s["codec_type"] for s in data["streams"]} >= {"audio", "video"}
    assert 1.8 <= float(data["format"]["duration"]) <= 2.5
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )


def test_record_and_finalize_real_audio_video(media, tmp_path):
    recorder = TikTokRecorder(
        RecorderConfig(
            mode=Mode.MANUAL,
            user="controlled_one",
            output=str(tmp_path),
            cookies={},
        )
    )
    recorder.tiktok = FileStreamAPI(media)
    recorder.start_recording(recorder.user, "controlled-room")
    outputs = list(tmp_path.glob("*.mp4"))
    assert len(outputs) == 1
    assert not outputs[0].name.endswith("_flv.mp4")
    verify_media(outputs[0])


def record_worker(media, output, user, ready):
    from main import record_user

    with patch("core.tiktok_recorder.TikTokAPI", return_value=FileStreamAPI(media)):
        ready.wait(timeout=15)
        record_user(
            RecorderConfig(
                mode=Mode.MANUAL,
                user=user,
                output=output,
                cookies={},
            )
        )


def test_two_windows_processes_record_independent_files(media, tmp_path):
    context = multiprocessing.get_context("spawn")
    ready = context.Barrier(2)
    workers = [
        context.Process(
            target=record_worker,
            args=(str(media), str(tmp_path), user, ready),
        )
        for user in ("controlled_a", "controlled_b")
    ]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=30)
            assert not worker.is_alive(), "Recording worker hung"
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
    outputs = list(tmp_path.glob("*.mp4"))
    assert len(outputs) == 2
    for output in outputs:
        assert not output.name.endswith("_flv.mp4")
        verify_media(output)


def test_automatic_mode_waits_then_records_when_live(media, monkeypatch, tmp_path):
    import core.tiktok_recorder as module

    class PollingAPI(FileStreamAPI):
        polls = 0

        def get_room_id_from_user(self, user):
            self.polls += 1
            if self.polls > 2:
                raise StopIteration("Controlled diagnostic complete")
            return "controlled-room"

        def is_room_alive(self, room_id):
            return self.polls > 1 and not self.ended

    recorder = TikTokRecorder(
        RecorderConfig(
            mode=Mode.AUTOMATIC,
            user="automatic_check",
            automatic_interval=2,
            output=str(tmp_path),
            cookies={},
        )
    )
    recorder.tiktok = PollingAPI(media)
    waits = []
    monkeypatch.setattr(module.time, "sleep", waits.append)
    with pytest.raises(StopIteration, match="Controlled diagnostic complete"):
        recorder.automatic_mode()
    assert waits == [120]
    outputs = list(tmp_path.glob("*.mp4"))
    assert len(outputs) == 1
    verify_media(outputs[0])


def test_timed_stop_produces_fully_decodable_file(media, monkeypatch, tmp_path):
    import core.tiktok_recorder as module

    packets = json.loads(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_packets",
                "-of",
                "json",
                str(media),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    )["packets"]
    video_packet = [p for p in packets if p["codec_type"] == "video"][-1]
    cutoff = int(video_packet["pos"]) + int(video_packet["size"]) // 2
    clock = {"seconds": 0}

    class TimedAPI(FileStreamAPI):
        def download_live_stream(self, url):
            clock["seconds"] = 6
            yield self.media.read_bytes()[:cutoff]
            yield self.media.read_bytes()[cutoff:]

    recorder = TikTokRecorder(
        RecorderConfig(
            mode=Mode.MANUAL,
            user="timed_stop",
            duration=5,
            output=str(tmp_path),
            cookies={},
        )
    )
    recorder.tiktok = TimedAPI(media)
    monkeypatch.setattr(module.time, "time", lambda: clock["seconds"])
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["seconds"])
    recorder.start_recording(recorder.user, "controlled-room")
    output = next(p for p in tmp_path.glob("*.mp4") if "_flv" not in p.name)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(output),
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )


def test_duration_is_total_across_stream_reconnections(monkeypatch, tmp_path):
    import core.tiktok_recorder as module

    clock = {"seconds": 0}

    class ReconnectingAPI:
        attempts = 0

        def get_live_url_candidates(self, room_id, user=None):
            return ["controlled://reconnect"]

        def is_room_alive(self, room_id):
            return self.attempts < 3

        def download_live_stream(self, url):
            self.attempts += 1
            clock["seconds"] += 4
            yield b"x" * 8192

    recorder = TikTokRecorder(
        RecorderConfig(
            mode=Mode.MANUAL,
            user="duration_check",
            duration=5,
            output=str(tmp_path),
            cookies={},
        )
    )
    recorder.tiktok = ReconnectingAPI()
    monkeypatch.setattr(module.time, "time", lambda: clock["seconds"])
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["seconds"])
    monkeypatch.setattr(VideoManagement, "convert_flv_to_mp4", lambda *args: None)
    recorder.start_recording(recorder.user, "controlled-room")
    assert recorder.tiktok.attempts <= 2, "5s limit allowed 12s across 3 connections"


def test_stream_download_rejects_http_error_response(monkeypatch):
    import requests
    from core.tiktok_api import TikTokAPI

    response = requests.Response()
    response.status_code = 403
    response._content = b"access denied" * 1024
    response._content_consumed = False
    response.raw = io.BytesIO(response._content)
    api = TikTokAPI.__new__(TikTokAPI)
    api._http_client_stream = requests.Session()
    monkeypatch.setattr(api._http_client_stream, "get", lambda *a, **kw: response)
    with pytest.raises(requests.HTTPError):
        list(api.download_live_stream("https://controlled.invalid/denied.flv"))
    assert response.raw.closed


def test_stream_download_closes_connection_when_recording_stops(monkeypatch):
    import requests
    from core.tiktok_api import TikTokAPI

    response = requests.Response()
    response.status_code = 200
    response.raw = io.BytesIO(b"video-data" * 2000)
    api = TikTokAPI.__new__(TikTokAPI)
    api._http_client_stream = requests.Session()
    monkeypatch.setattr(api._http_client_stream, "get", lambda *a, **kw: response)
    chunks = api.download_live_stream("https://controlled.invalid/live.flv")
    assert next(chunks) == (b"video-data" * 2000)[:4096]
    chunks.close()
    assert response.raw.closed


def test_http_failure_falls_back_to_valid_candidate(media, monkeypatch, tmp_path):
    import requests
    from core.tiktok_api import TikTokAPI

    class CandidateAPI(FileStreamAPI):
        def __init__(self, media):
            super().__init__(media)
            self._http_client_stream = requests.Session()

        def get_live_url_candidates(self, room_id, user=None):
            return [
                "https://controlled.invalid/denied",
                "https://controlled.invalid/good",
            ]

        def download_live_stream(self, url):
            yield from TikTokAPI.download_live_stream(self, url)
            self.ended = True

    denied = requests.Response()
    denied.status_code = 403
    denied.raw = io.BytesIO(b"access denied" * 1024)
    good = requests.Response()
    good.status_code = 200
    good.raw = io.BytesIO(media.read_bytes())
    api = CandidateAPI(media)
    responses = iter([denied, good])
    monkeypatch.setattr(
        api._http_client_stream, "get", lambda *a, **kw: next(responses)
    )
    recorder = TikTokRecorder(
        RecorderConfig(
            mode=Mode.MANUAL,
            user="fallback",
            output=str(tmp_path),
            cookies={},
        )
    )
    recorder.tiktok = api
    recorder.start_recording(recorder.user, "controlled-room")
    verify_media(next(tmp_path.glob("*.mp4")))
    assert denied.raw.closed


@pytest.mark.parametrize("tail", [b"", b"\x09", b"\x09\x00\x00\x10" + b"\0" * 8])
def test_flv_tail_trimming_preserves_complete_tags(tmp_path, tail):
    header = b"FLV\x01\x05\x00\x00\x00\x09" + b"\0" * 4
    tag = b"\x08\x00\x00\x02" + b"\0" * 7 + b"ab" + (13).to_bytes(4, "big")
    complete = header + tag
    output = tmp_path / "tail.flv"
    output.write_bytes(complete + tail)
    VideoManagement.trim_incomplete_flv_tag(output)
    assert output.read_bytes() == complete


def test_flv_trimming_leaves_other_formats_untouched(tmp_path):
    output = tmp_path / "other.mp4"
    content = b"\x00\x00\x00\x18ftypisom" + b"\0" * 30
    output.write_bytes(content)
    VideoManagement.trim_incomplete_flv_tag(output)
    assert output.read_bytes() == content


def test_early_live_end_saves_short_video_under_one_hour_limit(media, tmp_path, caplog):
    recorder = TikTokRecorder(
        RecorderConfig(
            mode=Mode.MANUAL,
            user="early_end",
            duration=3600,
            output=str(tmp_path),
            cookies={},
        )
    )
    recorder.tiktok = FileStreamAPI(media)
    recorder.start_recording(recorder.user, "controlled-room")
    output = next(tmp_path.glob("*.mp4"))
    verify_media(output)
    assert "User is no longer live" in caplog.text


def test_conversion_failure_keeps_original_file(tmp_path):
    output = tmp_path / "invalid_flv.mp4"
    output.write_bytes(b"invalid-media" * 1024)
    VideoManagement.convert_flv_to_mp4(str(output))
    assert output.exists()
    assert not (tmp_path / "invalid.mp4").exists()
