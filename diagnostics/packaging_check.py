"""Exercise the actual frozen updater using isolated portable copies and data."""

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from license_server.leases import decode, encode  # noqa: E402
from license_server.releases import DOMAIN, manifest_bytes  # noqa: E402
from desktop.store import DesktopStore  # noqa: E402


def stop_owned_process(pid, expected):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000 | 1 | 0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        assert kernel.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(length)
        )
        assert Path(buffer.value).resolve() == expected.resolve(), (
            "Refusing to stop an unrelated process"
        )
        assert kernel.TerminateProcess(handle, 0)
        assert kernel.WaitForSingleObject(handle, 10000) == 0
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.app_dir.resolve()
    config = json.loads((source / "_internal/desktop/release-config.json").read_text())
    signer = Ed25519PrivateKey.from_private_bytes(
        decode((ROOT / ".release-signing/update-signing.key").read_text())
    )
    assert encode(signer.public_key().public_bytes_raw()) == config["update_public_key"]
    report = {}
    with tempfile.TemporaryDirectory(
        prefix="release-qa-", dir=ROOT / "build"
    ) as temporary:
        home = Path(temporary)
        data = home / "customer-data"
        data.mkdir()
        store = DesktopStore(data / "state.db")
        store.save_channel("qa_channel", enabled=False)
        store.set_setting("interval", 300)
        store.close()
        target = home / "Portable app with spaces"
        shutil.copytree(source, target)
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["TIKTOK_RECORDER_DATA"] = str(data)
        environment["PATH"] = str(Path(environment["WINDIR"]) / "System32")
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        environment.pop("PYTHONPATH", None)
        smoke = home / "self-test.json"
        subprocess.run(
            [str(target / "LiveStudio.exe"), "--self-test", str(smoke)],
            env=environment,
            timeout=60,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        report["frozen_runtime"] = json.loads(smoke.read_text())
        work = home / "update"
        work.mkdir()
        archive = work / "release.zip"
        new_version = "1.0.1"
        with zipfile.ZipFile(
            archive, "w", zipfile.ZIP_DEFLATED, compresslevel=1
        ) as bundle:
            for path in sorted(source.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(source).as_posix()
                if relative == ".livestudio-package.json":
                    bundle.writestr(
                        "LiveStudio/" + relative,
                        json.dumps(
                            dict(json.loads(path.read_text()), version=new_version)
                        ),
                    )
                elif relative == "_internal/desktop/release-config.json":
                    bundle.writestr(
                        "LiveStudio/" + relative,
                        json.dumps(dict(config, version=new_version)),
                    )
                else:
                    bundle.write(path, "LiveStudio/" + relative)
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        payload = dict(
            format=1,
            platform="windows-x64",
            version=new_version,
            sha256=digest,
            size=archive.stat().st_size,
            notes="Isolated QA only; never publish this fixture.",
        )
        envelope = dict(
            payload=payload,
            signature=encode(signer.sign(DOMAIN + manifest_bytes(payload))),
        )
        (work / "manifest.json").write_text(json.dumps(envelope))
        shutil.copyfile(
            source / "LiveStudioUpdater.exe", work / "LiveStudioUpdater.exe"
        )
        dummy = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(0.5)"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        helper = subprocess.Popen(
            [
                str(work / "LiveStudioUpdater.exe"),
                "--apply",
                str(work),
                "--target",
                str(target),
                "--pid",
                str(dummy.pid),
            ],
            env=environment,
            cwd=work,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        started_pid = None
        try:
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline and not (work / "result.txt").exists():
                time.sleep(0.25)
            assert (work / "result.txt").exists(), "Updater did not finish"
            status = (work / "result.txt").read_text(encoding="utf-8")
            assert status.startswith("Updated successfully"), status
            ack = json.loads((work / "started.json").read_text())
            started_pid = ack["pid"]
            assert ack["version"] == new_version
            helper.wait(timeout=30)
            assert (
                json.loads((target / ".livestudio-package.json").read_text())["version"]
                == new_version
            )
            assert list(home.glob("Portable app with spaces.previous-*"))
            store = DesktopStore(data / "state.db")
            assert store.list_channels()[0]["username"] == "qa_channel"
            assert store.get_setting("interval") == 300
            store.close()
            report["actual_updater"] = dict(
                status="ok",
                from_version=config["version"],
                to_version=new_version,
                settings_preserved=True,
                previous_install_retained=True,
            )
        finally:
            if started_pid:
                stop_owned_process(started_pid, target / "LiveStudio.exe")
            if helper.poll() is None:
                helper.terminate()
                helper.wait(timeout=10)
            dummy.wait(timeout=5)
    (ROOT / "diagnostics/windows-package-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
