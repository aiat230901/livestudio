import time
from contextlib import closing
from http.client import HTTPException
from pathlib import Path
from threading import Thread, Event
from uuid import uuid4

from requests import RequestException
from curl_cffi import CurlError

from core.tiktok_api import TikTokAPI
from utils.logger_manager import logger
from utils.recorder_config import RecorderConfig
from utils.recording_result import RecordingResult
from utils.video_management import VideoManagement
from utils.custom_exceptions import LiveNotFound, UserLiveError, TikTokRecorderError
from utils.enums import Mode, Error, TimeOut, TikTokError


class TikTokRecorder:
    def __init__(self, config: RecorderConfig, stop_event=None, on_event=None):
        self.stop_event = stop_event if stop_event is not None else Event()
        self.on_event = on_event or (lambda kind, payload: None)
        self.tiktok = TikTokAPI(proxy=config.proxy, cookies=config.cookies)

        self.url = config.url
        self.user = config.user
        self.room_id = config.room_id
        self.mode = config.mode
        self.automatic_interval = config.automatic_interval
        self.duration = config.duration
        self.output = config.output
        self.bitrate = config.bitrate
        self.ffmpeg_path = config.ffmpeg_path
        self.use_telegram = config.use_telegram
        self._proxy = config.proxy
        self._cookies = config.cookies

    def _setup(self):
        """Resolve user/room data and validate prerequisites via network calls."""
        if self.mode == Mode.FOLLOWERS:
            self.check_country_blacklisted()

            self.sec_uid = self.tiktok.get_sec_uid()
            if self.sec_uid is None:
                raise TikTokRecorderError("Failed to retrieve sec_uid.")

            logger.info("Followers mode activated\n")
        else:
            if self.url:
                self.user, self.room_id = self.tiktok.get_room_and_user_from_url(
                    self.url
                )

            if not self.user:
                self.user = self.tiktok.get_user_from_room_id(self.room_id)

            if not self.room_id:
                self.room_id = self.tiktok.get_room_id_from_user(self.user)

            self.check_country_blacklisted()

            logger.info(f"USERNAME: {self.user}" + ("\n" if not self.room_id else ""))
            if self.room_id:
                logger.info(
                    f"ROOM_ID:  {self.room_id}"
                    + ("\n" if not self.tiktok.is_room_alive(self.room_id) else "")
                )

        # If proxy was used for the initial checks, switch to a direct connection
        # for the actual stream download to avoid proxy bottlenecks
        if self._proxy:
            self.tiktok = TikTokAPI(proxy=None, cookies=self._cookies)

    def run(self):
        """
        Resolves prerequisites and runs the recorder in the selected mode.

        If the mode is MANUAL, it checks if the user is currently live and
        if so, starts recording.

        If the mode is AUTOMATIC, it continuously checks if the user is live
        and if not, waits for the specified timeout before rechecking.
        If the user is live, it starts recording.

        if the mode is FOLLOWERS, it continuously checks the followers of
        the authenticated user. If any follower is live, it starts recording
        their live stream in a separate process.
        """
        self._setup()

        if self.mode == Mode.MANUAL:
            self.manual_mode()

        elif self.mode == Mode.AUTOMATIC:
            self.automatic_mode()

        elif self.mode == Mode.FOLLOWERS:
            self.followers_mode()

    def manual_mode(self):
        if not self.tiktok.is_room_alive(self.room_id):
            raise UserLiveError(f"@{self.user}: {TikTokError.USER_NOT_CURRENTLY_LIVE}")

        self.start_recording(self.user, self.room_id)

    def automatic_mode(self):
        while True:
            try:
                self.room_id = self.tiktok.get_room_id_from_user(self.user)
                self.manual_mode()

            except (UserLiveError, LiveNotFound) as ex:
                logger.info(ex)
                logger.info(
                    f"Waiting {self.automatic_interval} minutes before recheck\n"
                )
                time.sleep(self.automatic_interval * TimeOut.ONE_MINUTE)

            except (ConnectionError, RequestException, HTTPException):
                logger.error(Error.CONNECTION_CLOSED_AUTOMATIC)
                time.sleep(TimeOut.CONNECTION_CLOSED * TimeOut.ONE_MINUTE)

    def followers_mode(self):
        active_recordings = {}  # follower -> Thread

        while True:
            try:
                followers = self.tiktok.get_followers_list(self.sec_uid)

                for follower in followers:
                    if follower in active_recordings:
                        if not active_recordings[follower].is_alive():
                            logger.info(f"Recording of @{follower} finished.")
                            del active_recordings[follower]
                        else:
                            continue

                    try:
                        room_id = self.tiktok.get_room_id_from_user(follower)

                        if not room_id or not self.tiktok.is_room_alive(room_id):
                            continue

                        logger.info(f"@{follower} is live. Starting recording...")

                        thread = Thread(
                            target=self.start_recording,
                            args=(follower, room_id),
                            daemon=True,
                        )
                        thread.start()
                        active_recordings[follower] = thread

                        time.sleep(2.5)

                    except TikTokRecorderError as e:
                        logger.error(f"Error while processing @{follower}: {e}")
                        continue

                    except Exception as e:
                        logger.error(
                            f"Unexpected error processing @{follower}: {e}",
                            exc_info=True,
                        )
                        continue

                print()
                logger.info(
                    f"Waiting {self.automatic_interval} minutes for the next check..."
                )
                time.sleep(self.automatic_interval * TimeOut.ONE_MINUTE)

            except (UserLiveError, LiveNotFound) as ex:
                logger.info(ex)
                logger.info(
                    f"Waiting {self.automatic_interval} minutes before recheck\n"
                )
                time.sleep(self.automatic_interval * TimeOut.ONE_MINUTE)

            except (ConnectionError, RequestException, HTTPException):
                logger.error(Error.CONNECTION_CLOSED_AUTOMATIC)
                time.sleep(TimeOut.CONNECTION_CLOSED * TimeOut.ONE_MINUTE)

    def _build_output_path(self, user: str) -> str:
        folder = Path(self.output or ".")
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y.%m.%d_%H-%M-%S", time.localtime())
        return str(folder / f"TK_{user}_{stamp}_{uuid4().hex[:10]}_flv.mp4")

    def start_recording(self, user, room_id):
        deadline = time.monotonic() + self.duration if self.duration else None
        reason, error = "network_error", None
        live_urls = self.tiktok.get_live_url_candidates(room_id, user=user)
        if not live_urls:
            raise LiveNotFound(TikTokError.RETRIEVE_LIVE_URL)
        for candidate_index, live_url in enumerate(live_urls):
            if candidate_index:
                self.on_event(
                    "source_fallback",
                    {
                        "message": "Nguồn trước không dùng được; đang thử nguồn tiếp theo."
                    },
                )
            if self.stop_event.is_set():
                return RecordingResult(None, "user_stop", 0)
            if deadline is not None and time.monotonic() >= deadline:
                return RecordingResult(None, "duration", 0)
            output = self._build_output_path(user)
            reason, error = "network_error", None
            bytes_written = 0
            last_progress = 0
            try:
                if not self.tiktok.is_room_alive(room_id):
                    return RecordingResult(None, "live_ended", 0)
                logger.info(f"Started recording @{user}")
                # Each transport attempt owns a new file: never append two FLV headers.
                with open(output, "xb") as out_file:
                    with closing(self.tiktok.download_live_stream(live_url)) as chunks:
                        for chunk in chunks:
                            if bytes_written == 0 and (
                                (
                                    chunk.startswith(b"FLV")
                                    and len(chunk) > 4
                                    and not chunk[4] & 1
                                )
                                or chunk.startswith(b"#EXTM3U")
                            ):
                                error = "Nguồn này không có video tải trực tiếp được."
                                break
                            out_file.write(chunk)
                            bytes_written += len(chunk)
                            now = time.monotonic()
                            if now - last_progress >= 1:
                                self.on_event(
                                    "progress", {"bytes_written": bytes_written}
                                )
                                last_progress = now
                            if self.stop_event.is_set():
                                reason = "user_stop"
                                break
                            if deadline is not None and now >= deadline:
                                reason = "duration"
                                break
                        else:
                            if not self.tiktok.is_room_alive(room_id):
                                logger.info(
                                    "User is no longer live. Stopping recording."
                                )
                                reason = "live_ended"
                            else:
                                reason = "network_error"
            except KeyboardInterrupt:
                reason = "user_stop"
            except (RequestException, CurlError, HTTPException, ConnectionError) as ex:
                reason, error = "network_error", type(ex).__name__
            except OSError as ex:
                reason, error = (
                    "storage_error",
                    f"Không ghi được video: {type(ex).__name__}. Hãy kiểm tra quyền ghi và dung lượng ổ đĩa.",
                )
            except Exception as ex:
                reason, error = "network_error", type(ex).__name__
                logger.warning(f"Stream interrupted: {type(ex).__name__}")
            if self.stop_event.is_set():
                reason = "user_stop"
            elif deadline is not None and time.monotonic() >= deadline:
                reason = "duration"
            if bytes_written < 4096:
                Path(output).unlink(missing_ok=True)
                if reason in ("duration", "user_stop", "live_ended"):
                    return RecordingResult(None, reason, bytes_written, error)
                continue
            self.on_event("finalizing", {"bytes_written": bytes_written})
            converted = VideoManagement.convert_flv_to_mp4(
                output, self.bitrate, self.ffmpeg_path
            )
            if converted:
                return RecordingResult(converted, reason, bytes_written, error)
            # Keep the source if conversion fails; try a lower candidate if it
            # was audio-only or invalid, while retaining the original deadline.
            if reason in ("duration", "user_stop"):
                return RecordingResult(
                    output,
                    "conversion_error",
                    bytes_written,
                    "Không xuất được MP4; đã giữ tệp nguồn.",
                )
        return RecordingResult(
            output if bytes_written >= 4096 else None,
            "conversion_error" if bytes_written >= 4096 else reason,
            bytes_written,
            error or "Không nhận được video hợp lệ.",
        )

    def check_country_blacklisted(self):
        is_blacklisted = self.tiktok.is_country_blacklisted()
        if not is_blacklisted:
            return False

        if self.room_id is None:
            raise TikTokRecorderError(TikTokError.COUNTRY_BLACKLISTED)

        if self.mode == Mode.AUTOMATIC:
            raise TikTokRecorderError(TikTokError.COUNTRY_BLACKLISTED_AUTO_MODE)

        elif self.mode == Mode.FOLLOWERS:
            raise TikTokRecorderError(TikTokError.COUNTRY_BLACKLISTED_FOLLOWERS_MODE)

        return is_blacklisted
