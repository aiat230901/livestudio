from dataclasses import dataclass


@dataclass
class RecordingResult:
    path: str | None
    reason: str
    bytes_written: int
    error: str | None = None
