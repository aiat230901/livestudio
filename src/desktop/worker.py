import time
from dataclasses import asdict
from pathlib import Path

import ffmpeg
from curl_cffi import CurlError
from requests import RequestException

from core.tiktok_api import TikTokAPI
from core.tiktok_recorder import TikTokRecorder
from utils.enums import Mode
from utils.recorder_config import RecorderConfig
from utils.utils import read_cookies
from utils.video_management import VideoManagement


def run_job(job, events, stop_event):
    def emit(kind, payload):
        events.put(
            dict(
                job_id=job["job_id"],
                username=job["username"],
                kind=kind,
                payload=payload,
            )
        )

    try:
        try:
            cookies = read_cookies()
        except FileNotFoundError:
            cookies = {}
        if job["kind"] == "probe":
            if job.get("recover"):
                for source in Path(job["output"]).glob(
                    f"TK_{job['username']}_*_flv.mp4"
                ):
                    if stop_event.is_set():
                        break
                    size = source.stat().st_size
                    path = VideoManagement.convert_flv_to_mp4(str(source))
                    if path:
                        emit(
                            "recovered",
                            dict(path=path, reason="recovered", bytes_written=size),
                        )
            if stop_event.is_set():
                emit("probe_done", {"room_id": None})
                return
            api = TikTokAPI(proxy=None, cookies=cookies)
            api.http_client.timeout = 10
            room = api.get_room_id_from_user(job["username"])
            live = bool(room and not stop_event.is_set() and api.is_room_alive(room))
            emit("probe_done", {"room_id": str(room) if live else None})
        else:
            remaining = None
            session_end = job["deadline_utc"]
            window_end = job.get("window_end_utc")
            schedule_first = window_end is not None and (
                session_end is None or window_end < session_end
            )
            effective_end = window_end if schedule_first else session_end
            if effective_end is not None:
                remaining = effective_end - time.time()
                if remaining <= 0:
                    emit(
                        "record_done",
                        dict(
                            path=None,
                            reason="schedule_end" if schedule_first else "duration",
                            bytes_written=0,
                        ),
                    )
                    return
            recorder = TikTokRecorder(
                RecorderConfig(
                    mode=Mode.MANUAL,
                    user=job["username"],
                    room_id=job["room_id"],
                    duration=remaining,
                    output=job["output"],
                    cookies=cookies,
                ),
                stop_event=stop_event,
                on_event=emit,
            )
            recorder.tiktok.http_client.timeout = 10
            result = asdict(recorder.start_recording(job["username"], job["room_id"]))
            if result["reason"] == "duration" and schedule_first:
                result["reason"] = "schedule_end"
            if result["path"] and result["reason"] != "conversion_error":
                probe = ffmpeg.probe(result["path"])
                result["media_duration"] = float(probe["format"].get("duration", 0))
                video = next(s for s in probe["streams"] if s["codec_type"] == "video")
                result["resolution"] = f"{video['width']} × {video['height']}"
            emit("record_done", result)
    except (RequestException, CurlError, ConnectionError) as ex:
        emit("error", {"error": type(ex).__name__})
    except OSError as ex:
        payload = dict(
            error=f"Không truy cập được thư mục/video: {type(ex).__name__}.",
            reason="storage_error",
        )
        if job["kind"] == "record":
            emit("record_done", dict(path=None, bytes_written=0, **payload))
        else:
            emit("error", payload)
    except Exception as ex:
        # Exception text from HTTP clients may include a signed CDN URL.
        emit("error", {"error": type(ex).__name__})
