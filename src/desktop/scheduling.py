"""Calendar windows in Vietnam time, independent of the Windows timezone."""

import math
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7), "UTC+7")
WEEK = 7 * 24 * 3600
DAY_NAMES = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")


def normalize_schedule(rule):
    if not isinstance(rule, dict):
        raise ValueError("Lịch không hợp lệ.")
    if rule.get("kind") == "once":
        start, end = rule.get("start"), rule.get("end")
        for value in (start, end):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Ngày giờ không hợp lệ.")
            try:
                datetime.fromtimestamp(value, VN_TZ)
            except (ValueError, OSError, OverflowError) as ex:
                raise ValueError("Ngày giờ nằm ngoài khoảng hỗ trợ.") from ex
        if end <= start:
            raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
        return dict(kind="once", start=float(start), end=float(end))
    if rule.get("kind") == "weekly":
        days = rule.get("days")
        if (
            not isinstance(days, list)
            or not days
            or any(type(day) is not int or not 0 <= day <= 6 for day in days)
        ):
            raise ValueError("Hãy chọn ít nhất một ngày trong tuần.")
        start, end = rule.get("start_minute"), rule.get("end_minute")
        if any(
            type(value) is not int or not 0 <= value < 1440 for value in (start, end)
        ):
            raise ValueError("Giờ trong ngày không hợp lệ.")
        if start == end:
            raise ValueError(
                "Giờ bắt đầu và kết thúc phải khác nhau. Muốn theo dõi cả ngày, chọn Liên tục."
            )
        return dict(
            kind="weekly", days=sorted(set(days)), start_minute=start, end_minute=end
        )
    raise ValueError("Hãy chọn lịch một lần hoặc lịch lặp hằng tuần.")


def _merge(intervals):
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def next_window(schedules, now):
    """Return the current or next merged (start, end); end=None means all week.

    Boundaries are [start, end). Weekly occurrences are expanded near the
    current window's endpoints, so a years-long one-off stays cheap to evaluate.
    """
    once, weekly = [], []
    for rule in schedules:
        if rule["kind"] == "once":
            once.append((rule["start"], rule["end"]))
        else:
            for day in rule["days"]:
                start = day * 86400 + rule["start_minute"] * 60
                end = day * 86400 + rule["end_minute"] * 60
                if end <= start:
                    end += 86400
                weekly.append((start, end))
    if weekly:
        circular = [(start, min(end, WEEK)) for start, end in weekly]
        circular.extend((0, end - WEEK) for _, end in weekly if end > WEEK)
        if _merge(circular) == [(0, WEEK)]:
            return now, None

    def occurrences(anchor):
        local = datetime.fromtimestamp(anchor, VN_TZ)
        monday = (
            (local - timedelta(days=local.weekday()))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        return [
            (monday + shift * WEEK + start, monday + shift * WEEK + end)
            for shift in (-1, 0, 1)
            for start, end in weekly
        ]

    intervals = _merge(once + (occurrences(now) if weekly else []))
    window = next((item for item in intervals if item[1] > now), None)
    while window and weekly:
        expanded = _merge(intervals + occurrences(window[1]))
        updated = next(item for item in expanded if item[1] > now)
        if updated == window:
            break
        intervals, window = expanded, updated
    return window


def channel_window(channel, now):
    if channel.get("mode", "continuous") == "continuous":
        return now, None
    return next_window(channel.get("schedules", []), now)


def is_active(window, now):
    return (
        window is not None
        and window[0] <= now
        and (window[1] is None or now < window[1])
    )


def format_time(timestamp):
    return datetime.fromtimestamp(timestamp, VN_TZ).strftime("%d/%m/%Y %H:%M")


def describe_schedule(rule):
    if rule["kind"] == "once":
        return f"{format_time(rule['start'])} → {format_time(rule['end'])}"
    days = (
        "Mỗi ngày"
        if len(rule["days"]) == 7
        else ", ".join(DAY_NAMES[day] for day in rule["days"])
    )
    start, end = rule["start_minute"], rule["end_minute"]
    overnight = " (qua đêm)" if end < start else ""
    return f"{days} · {start // 60:02d}:{start % 60:02d}–{end // 60:02d}:{end % 60:02d}{overnight}"
