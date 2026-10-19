import multiprocessing
import time
from pathlib import Path
from queue import Empty
from uuid import uuid4

from desktop.worker import run_job
from desktop.scheduling import channel_window, format_time, is_active


REASONS = {
    "duration": "Đủ thời lượng",
    "live_ended": "Live đã kết thúc",
    "user_stop": "Đã dừng",
    "network_error": "Lỗi kết nối",
    "conversion_error": "Lỗi xuất MP4",
    "storage_error": "Lỗi ghi ổ đĩa",
    "recovered": "Đã phục hồi video",
    "schedule_end": "Hết khung giờ ghi",
    "license_denied": "Dừng do giấy phép",
}


class RecordingManager:
    def __init__(self, store, process_factory=None, clock=None, license_guard=None):
        self.store = store
        self.context = multiprocessing.get_context("spawn")
        self.process_factory = process_factory or self.context.Process
        self.clock = clock or time.time
        self.events = self.context.Queue()
        self.jobs = {}
        self.states = {}
        self.next_poll = {}
        self.manual = set()
        self.closing = False
        self.recovery_started = set()
        self.was_allowed = {}
        self.license_guard = license_guard or (lambda: True)

    def output_for(self, channel):
        if channel["output"]:
            return channel["output"]
        return str(
            Path(
                self.store.get_setting(
                    "output", str(Path.home() / "Videos" / "TikTok Live")
                )
            )
            / channel["username"]
        )

    def _launch(self, channel, kind, **extra):
        if not self.license_guard():
            return
        user = channel["username"]
        spec = dict(
            job_id=uuid4().hex,
            username=user,
            kind=kind,
            output=self.output_for(channel),
            **extra,
        )
        spec["manual"] = user in self.manual
        if kind == "probe":
            window = channel_window(channel, self.clock())
            spec["window_end_utc"] = (
                window[1] if window and not spec["manual"] else None
            )
        if kind == "probe":
            spec["recover"] = user not in self.recovery_started
            self.recovery_started.add(user)
        stop = self.context.Event()
        process = self.process_factory(target=run_job, args=(spec, self.events, stop))
        self.jobs[user] = dict(
            spec=spec, stop=stop, process=process, result=None, launched=self.clock()
        )
        self.states[user] = dict(
            status="Đang kiểm tra" if kind == "probe" else "Đang ghi",
            bytes_written=0,
            started_utc=self.clock(),
        )
        try:
            process.start()
        except Exception:
            self.jobs.pop(user)
            self.states[user]["status"] = "Không khởi chạy được"
            self.next_poll[user] = self.clock() + 120

    def _channel(self, user):
        return next(
            (c for c in self.store.list_channels() if c["username"] == user), None
        )

    def enable(self, user, enabled):
        channel = self._channel(user)
        if channel is None:
            return
        self.store.save_channel(
            user, channel["duration_seconds"], channel["output"], enabled
        )
        if not enabled:
            self.stop_recording(user)
        else:
            self.next_poll[user] = 0

    def record_now(self, user):
        if (
            self.license_guard()
            and not self.closing
            and user not in self.jobs
            and self._channel(user)
        ):
            self.manual.add(user)
            self.next_poll[user] = 0
            self.tick()

    def stop_recording(self, user):
        self.manual.discard(user)
        job = self.jobs.get(user)
        if job:
            if job["spec"]["kind"] == "record":
                session = self.store.get_session(user, job["spec"]["room_id"])
                self.store.save_session(
                    user,
                    session["room_id"],
                    session["started_utc"],
                    session["deadline_utc"],
                    "stopped",
                )
            job["stop"].set()
            job["stop_reason"] = "user_stop"
            self.states[user]["status"] = "Đang dừng…"

    def _finish(self, user, job, kind, payload):
        channel = self._channel(user)
        self.next_poll[user] = self.clock() + self.store.get_setting("interval", 120)
        if kind == "probe_done":
            manual = user in self.manual and job["spec"]["manual"]
            now = self.clock()
            window = channel_window(channel, now) if channel else None
            if (
                not channel
                or self.closing
                or not self.license_guard()
                or job["stop"].is_set()
                or not (channel["enabled"] or manual)
                or (not manual and not is_active(window, now))
            ):
                self.states[user] = {"status": "Đã tắt"}
                self.next_poll[user] = 0
                return
            room = payload.get("room_id")
            if not room:
                self.manual.discard(user)
                self.states[user] = {"status": "Chưa live · đang chờ"}
                return
            session = self.store.get_session(user, room)
            now = self.clock()
            if session and (
                session["state"] == "completed"
                or (
                    session["deadline_utc"] is not None
                    and now >= session["deadline_utc"]
                )
                or (session["state"] == "stopped" and not manual)
            ):
                self.states[user] = {"status": "Đã dừng phiên này · chờ live mới"}
                self.manual.discard(user)
                return
            if not session:
                session = dict(
                    started_utc=now,
                    deadline_utc=now + channel["duration_seconds"]
                    if channel["duration_seconds"]
                    else None,
                )
            self.store.save_session(
                user, room, session["started_utc"], session["deadline_utc"], "active"
            )
            self._launch(
                channel,
                "record",
                room_id=room,
                deadline_utc=session["deadline_utc"],
                window_end_utc=window[1] if not manual else None,
            )
        elif kind == "record_done":
            payload = dict(payload)
            # A schedule stop preserves the room's session budget for later windows.
            if job.get("stop_reason") == "user_stop" and payload["reason"] not in (
                "conversion_error",
                "storage_error",
            ):
                payload["reason"] = "user_stop"
            elif payload["reason"] == "user_stop" and job.get("stop_reason"):
                payload["reason"] = job["stop_reason"]
            elif (
                job.get("stop_reason") == "license_denied"
                and payload["reason"] == "network_error"
            ):
                payload["reason"] = "license_denied"
            reason = payload["reason"]
            self.states[user] = dict(status=REASONS.get(reason, reason), **payload)
            spec = job["spec"]
            session = self.store.get_session(user, spec["room_id"])
            state = (
                "completed"
                if reason in ("duration", "live_ended")
                else "stopped"
                if reason in ("user_stop", "conversion_error", "storage_error")
                and not self.closing
                else "active"
            )
            self.store.save_session(
                user,
                spec["room_id"],
                session["started_utc"],
                session["deadline_utc"],
                state,
            )
            self.store.add_recording(
                dict(
                    username=user,
                    room_id=spec["room_id"],
                    started_utc=job["launched"],
                    ended_utc=self.clock(),
                    **payload,
                )
            )
            if reason == "network_error":
                self.next_poll[user] = self.clock() + 10
            else:
                self.manual.discard(user)
            if reason == "schedule_end":
                self.next_poll[user] = 0
        else:
            self.states[user] = {
                "status": REASONS.get(payload.get("reason"), "Lỗi kết nối"),
                "error": payload.get("error", "Worker không trả kết quả"),
            }
            self.manual.discard(user)

    def tick(self):
        while True:
            try:
                event = self.events.get_nowait()
            except Empty:
                break
            user = event["username"]
            job = self.jobs.get(user)
            if not job or event["job_id"] != job["spec"]["job_id"]:
                continue
            kind, payload = event["kind"], event["payload"]
            if kind in ("probe_done", "record_done", "error"):
                job["result"] = (kind, payload)
            elif kind == "recovered":
                self.store.add_recording(
                    dict(
                        username=user,
                        room_id=None,
                        started_utc=job["launched"],
                        ended_utc=self.clock(),
                        **payload,
                    )
                )
            else:
                self.states[user].update(payload)
                if kind == "finalizing":
                    self.states[user]["status"] = "Đang xuất MP4"
        for user, job in list(self.jobs.items()):
            process = job["process"]
            if process.is_alive():
                continue
            # A multiprocessing Queue flushes before a normally exiting worker.
            if job["result"] is None and process.exitcode == 0:
                job.setdefault("exit_seen", self.clock())
                if self.clock() - job["exit_seen"] < 1:
                    continue
            process.join(timeout=0)
            process.close()
            del self.jobs[user]
            self._finish(user, job, *(job["result"] or ("error", {})))
        if not self.closing:
            licensed = self.license_guard()
            if not licensed:
                self.manual.clear()
            for channel in self.store.list_channels():
                user = channel["username"]
                now = self.clock()
                manual = user in self.manual
                window = channel_window(channel, now)
                allowed = licensed and (
                    (bool(channel["enabled"]) and is_active(window, now)) or manual
                )
                if allowed and not self.was_allowed.get(user, False):
                    self.next_poll[user] = 0
                self.was_allowed[user] = allowed
                job = self.jobs.get(user)
                if job:
                    end = job["spec"].get("window_end_utc")
                    if (
                        not manual
                        and (not allowed or (end is not None and now >= end))
                        and not job["stop"].is_set()
                    ):
                        job["stop_reason"] = (
                            "schedule_end" if licensed else "license_denied"
                        )
                        job["stop"].set()
                        self.states[user]["status"] = (
                            "Đang dừng theo lịch…"
                            if licensed
                            else "Đang dừng do giấy phép…"
                        )
                    continue
                if (
                    user not in self.jobs
                    and allowed
                    and self.clock() >= self.next_poll.get(user, 0)
                ):
                    self._launch(channel, "probe")

    def snapshot(self):
        snapshot = {
            c["username"]: dict(
                c,
                **self.states.get(
                    c["username"], {"status": "Đang chờ" if c["enabled"] else "Đã tắt"}
                ),
            )
            for c in self.store.list_channels()
        }
        now = self.clock()
        for user, channel in snapshot.items():
            window = channel_window(channel, now)
            active = is_active(window, now)
            if channel["mode"] == "continuous":
                channel["schedule_text"] = "Liên tục"
            elif window is None:
                channel["schedule_text"] = "Không còn lịch"
            elif active:
                channel["schedule_text"] = (
                    "Theo lịch · cả tuần"
                    if window[1] is None
                    else "Đến " + format_time(window[1])
                )
            else:
                channel["schedule_text"] = "Từ " + format_time(window[0])
            if (
                channel["enabled"]
                and channel["mode"] == "scheduled"
                and not active
                and user not in self.jobs
                and user not in self.manual
            ):
                channel["status"] = "Chờ lịch" if window else "Chưa có lịch sắp tới"
            if user in self.manual:
                channel["schedule_text"] = "Ghi ngay · bỏ qua lịch"
        return snapshot

    def shutdown(self):
        self.closing = True
        for job in self.jobs.values():
            job["stop"].set()
