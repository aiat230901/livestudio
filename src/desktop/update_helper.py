"""Runs from an independent onefile EXE after the recorder has closed safely."""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import time
from pathlib import Path

from desktop.updates import bundled_config, install_package


def wait_for_exit(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if kernel.WaitForSingleObject(handle, 120000) != 0:
            raise ValueError("Ứng dụng cũ chưa thoát; chưa thay đổi tệp chương trình.")
    finally:
        kernel.CloseHandle(handle)


def launch(directory, arguments=()):
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return subprocess.Popen(
        [str(directory / "LiveStudio.exe"), *arguments],
        cwd=directory.parent,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    args = parser.parse_args()
    work, target = args.apply.resolve(), args.target.resolve()
    waited = False
    try:
        wait_for_exit(args.pid)
        waited = True
        envelope = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
        ack = work / "started.json"
        ack.unlink(missing_ok=True)

        def start(directory):
            process = launch(directory, ["--update-ack", str(ack)])
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if ack.exists():
                    try:
                        result = json.loads(ack.read_text(encoding="utf-8"))
                        if result == dict(
                            pid=process.pid, version=envelope["payload"]["version"]
                        ):
                            return True
                    except (OSError, ValueError):
                        pass
                if process.poll() is not None:
                    return False
                time.sleep(0.2)
            process.terminate()
            process.wait(timeout=10)
            return False

        backup = install_package(
            work / "release.zip",
            envelope,
            bundled_config()["update_public_key"],
            target,
            start,
        )
        (work / "result.txt").write_text(
            "Updated successfully. Previous installation: " + str(backup),
            encoding="utf-8",
        )
    except Exception as error:
        (work / "result.txt").write_text(
            f"Update failed: {type(error).__name__}: {error}", encoding="utf-8"
        )
        ctypes.windll.user32.MessageBoxW(
            None, str(error), "Live Studio — Cập nhật chưa hoàn tất", 0x10
        )
        if waited and (target / "LiveStudio.exe").exists():
            launch(target)


if __name__ == "__main__":
    main()
