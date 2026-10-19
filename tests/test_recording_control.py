from threading import Event
from pathlib import Path
import subprocess

from requests import ConnectionError

from core.tiktok_recorder import TikTokRecorder
from utils.enums import Mode
from utils.recorder_config import RecorderConfig
from tests import test_recording_integration as integration

FileStreamAPI = integration.FileStreamAPI
media = integration.media
verify_media = integration.verify_media


def test_cooperative_stop_saves_media(media, tmp_path):
    stop = Event()

    class API(FileStreamAPI):
        def download_live_stream(self, url):
            yield self.media.read_bytes()
            stop.set()
            yield b""

    recorder = TikTokRecorder(
        RecorderConfig(mode=Mode.MANUAL, output=str(tmp_path), cookies={}),
        stop_event=stop,
    )
    recorder.tiktok = API(media)
    result = recorder.start_recording("stop_test", "room")
    assert result.reason == "user_stop"
    verify_media(result.path)


def test_unique_output_and_conversion_error(tmp_path):
    recorder = TikTokRecorder(
        RecorderConfig(mode=Mode.MANUAL, output=str(tmp_path), cookies={})
    )
    first = recorder._build_output_path("same")
    second = recorder._build_output_path("same")
    assert first != second


def test_network_failure_keeps_valid_segment_and_closes_stream(media, tmp_path):
    closed = []

    class API(FileStreamAPI):
        def download_live_stream(self, url):
            try:
                yield self.media.read_bytes()
                raise ConnectionError("signed-secret-url")
            finally:
                closed.append(True)

    events = []
    recorder = TikTokRecorder(
        RecorderConfig(mode=Mode.MANUAL, output=str(tmp_path / "có dấu"), cookies={}),
        on_event=lambda *a: events.append(a),
    )
    recorder.tiktok = API(media)
    result = recorder.start_recording("network", "room")
    assert result.reason == "network_error"
    assert result.error == "ConnectionError"
    assert closed
    assert "secret" not in repr(events)
    verify_media(result.path)


def test_failed_conversion_is_not_success_and_preserves_source(tmp_path):
    class API:
        def get_live_url_candidates(self, *a, **kw):
            return ["fake"]

        def is_room_alive(self, room):
            return True

        def download_live_stream(self, url):
            yield b"x" * 8192

    recorder = TikTokRecorder(
        RecorderConfig(mode=Mode.MANUAL, output=str(tmp_path), cookies={})
    )
    recorder.tiktok = API()
    assert recorder.start_recording("invalid", "room").reason == "conversion_error"
    assert next(tmp_path.glob("*_flv.mp4")).exists()


def test_audio_only_is_not_video_success(tmp_path):
    from utils.video_management import VideoManagement

    source = tmp_path / "audio_flv.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "1",
            "-c:a",
            "aac",
            "-f",
            "flv",
            str(source),
        ],
        check=True,
        timeout=15,
    )
    assert VideoManagement.convert_flv_to_mp4(str(source)) is None
    assert source.exists()


def test_skip_audio_header_and_record_video_candidate(media, tmp_path):
    class API(FileStreamAPI):
        def get_live_url_candidates(self, *args, **kwargs):
            return ["audio", "video"]

        def download_live_stream(self, url):
            if url == "audio":
                yield b"FLV\x01\x04" + b"\0" * 4091
            else:
                yield from super().download_live_stream(url)

    recorder = TikTokRecorder(
        RecorderConfig(mode=Mode.MANUAL, output=str(tmp_path), cookies={})
    )
    recorder.tiktok = API(media)
    result = recorder.start_recording("fallback", "room")
    assert result.reason == "live_ended"
    verify_media(result.path)


def test_worker_recovers_interrupted_source_before_probe(media, tmp_path, monkeypatch):
    from queue import Queue
    from types import SimpleNamespace
    from desktop.worker import run_job

    source = tmp_path / "TK_recover_old_flv.mp4"
    source.write_bytes(media.read_bytes())
    api = SimpleNamespace(
        http_client=SimpleNamespace(), get_room_id_from_user=lambda user: None
    )
    monkeypatch.setattr("desktop.worker.TikTokAPI", lambda **kwargs: api)
    events = Queue()
    run_job(
        dict(
            job_id="recover",
            username="recover",
            kind="probe",
            output=str(tmp_path),
            recover=True,
        ),
        events,
        Event(),
    )
    result = events.get_nowait()
    assert result["kind"] == "recovered"
    assert not source.exists()
    verify_media(result["payload"]["path"])
    assert events.get_nowait()["kind"] == "probe_done"


def test_conversion_never_overwrites_existing_mp4(media, tmp_path):
    from utils.video_management import VideoManagement

    folder = tmp_path / "folder_flv.mp4"
    folder.mkdir()
    source = folder / "saved_flv.mp4"
    source.write_bytes(media.read_bytes())
    existing = folder / "saved.mp4"
    existing.write_bytes(b"keep existing video")
    result = VideoManagement.convert_flv_to_mp4(str(source))
    assert result != str(existing)
    assert existing.read_bytes() == b"keep existing video"
    assert Path(result).parent == folder
    verify_media(result)
