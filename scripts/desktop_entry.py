import multiprocessing
import os
from pathlib import Path
import sys
import traceback

if __name__ == "__main__":
    multiprocessing.freeze_support()
    directory = Path(
        os.environ.get(
            "TIKTOK_RECORDER_DATA",
            str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TikTokLiveStudio"),
        )
    )
    directory.mkdir(parents=True, exist_ok=True)
    log = (directory / "application.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    os.environ["PATH"] = (
        str(Path(sys.executable).parent / "bin")
        + os.pathsep
        + os.environ.get("PATH", "")
    )
    try:
        if "--self-test" in sys.argv:
            from desktop.diagnostics import self_check

            raise SystemExit(self_check(sys.argv[sys.argv.index("--self-test") + 1]))
        from desktop.app import main

        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "Không mở được Live Studio. Chi tiết được lưu tại "
            + str(directory / "application.log"),
            "Live Studio",
            0x10,
        )
        raise SystemExit(1)
