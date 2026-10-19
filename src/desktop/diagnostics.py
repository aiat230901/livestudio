"""Explicit offline self-check for packaged runtime, media tools and spawn."""

import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import tempfile


def media_worker(directory, results):
    try:
        import ffmpeg
        from desktop.worker import run_job  # noqa: F401

        sample = Path(directory) / "sample.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=160x120:rate=10",
                "-t",
                "0.5",
                "-c:v",
                "libx264",
                "-y",
                str(sample),
            ],
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        probe = ffmpeg.probe(str(sample))
        results.put(
            dict(
                video=any(s["codec_type"] == "video" for s in probe["streams"]),
                duration=float(probe["format"]["duration"]),
            )
        )
    except Exception as error:
        results.put(dict(error=type(error).__name__))


def self_check(output):
    from PySide6.QtWidgets import QApplication
    from desktop.theme import apply_theme
    from desktop.license_dialog import LicenseDialog  # noqa: F401
    from desktop.licensing import load_config, protect_data
    from desktop.updates import bundled_config

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    config = load_config()
    sealed = protect_data(b"runtime-check")
    assert protect_data(sealed, decrypt=True) == b"runtime-check"
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory() as temporary:
        results = context.Queue()
        process = context.Process(target=media_worker, args=(temporary, results))
        process.start()
        process.join(45)
        if process.is_alive():
            process.terminate()
            process.join()
            raise ValueError("Media subprocess timed out")
        assert process.exitcode == 0
        result = results.get(timeout=3)
        assert result.get("video") and result["duration"] > 0
        process.close()
        results.close()
        results.join_thread()
    Path(output).write_text(
        json.dumps(
            dict(
                status="ok",
                version=bundled_config()["version"],
                server_url=config["server_url"],
                qt=True,
                dpapi=True,
                spawned_media=result,
                pid=os.getpid(),
            )
        ),
        encoding="utf-8",
    )
    return 0
