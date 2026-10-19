"""Build and sign a portable Windows release; private keys never enter the ZIP."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import struct
import zipfile

import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from license_server.leases import decode, encode  # noqa: E402
from license_server.releases import (  # noqa: E402
    DOMAIN,
    manifest_bytes,
    verify_manifest,
    version_tuple,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--server", default="https://livestudio.n2.tinhgon.xyz")
    parser.add_argument(
        "--notes",
        default="Bản Windows đầu tiên: ghi nhiều kênh, đặt lịch, kích hoạt và cập nhật trong tool.",
    )
    parser.add_argument("--ffmpeg-dir", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    version_tuple(args.version)
    if sys.platform != "win32" or not args.server.startswith("https://"):
        parser.error("Build on Windows with an HTTPS server.")
    release_dir = args.output_root.resolve() / ("LiveStudio-" + args.version)
    if release_dir.exists():
        parser.error(
            "Release directory exists; use a new version or an empty output location."
        )
    secrets = json.loads(
        (ROOT / ".license-server/secrets.json").read_text(encoding="utf-8")
    )
    license_key = encode(
        Ed25519PrivateKey.from_private_bytes(decode(secrets["signing_key"]))
        .public_key()
        .public_bytes_raw()
    )
    response = requests.get(
        args.server.rstrip("/") + "/api/license/public-key", timeout=15
    )
    response.raise_for_status()
    if response.json()["public_key"] != license_key:
        raise ValueError(
            "Hosted license signing key differs from the owner's local key."
        )
    private_dir = ROOT / ".release-signing"
    private_dir.mkdir(exist_ok=True)
    key_path = private_dir / "update-signing.key"
    if not key_path.exists():
        key_path.write_text(
            encode(Ed25519PrivateKey.generate().private_bytes_raw()), encoding="ascii"
        )
        key_path.chmod(0o600)
    signer = Ed25519PrivateKey.from_private_bytes(
        decode(key_path.read_text(encoding="ascii"))
    )
    public_key = encode(signer.public_key().public_bytes_raw())
    (private_dir / "update-public-key.txt").write_text(public_key, encoding="ascii")
    work = ROOT / "build" / ("release-" + args.version)
    work.mkdir(parents=True, exist_ok=True)
    config_path = work / "release-config.json"
    config_path.write_text(
        json.dumps(
            dict(
                version=args.version,
                server_url=args.server.rstrip("/"),
                license_public_key=license_key,
                update_public_key=public_key,
            )
        ),
        encoding="utf-8",
    )
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice
    from desktop.theme import app_icon

    application = QApplication.instance() or QApplication([])
    assert application
    png = QByteArray()
    buffer = QBuffer(png)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert app_icon().pixmap(256, 256).save(buffer, "PNG")
    buffer.close()
    image = bytes(png)
    icon_path = work / "LiveStudio.ico"
    icon_path.write_bytes(
        struct.pack("<HHH", 0, 1, 1)
        + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(image), 22)
        + image
    )
    common = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(work / "frozen"),
        "--workpath",
        str(work / "work"),
        "--specpath",
        str(work),
        "--paths",
        str(ROOT / "src"),
        "--windowed",
        "--icon",
        str(icon_path),
        "--add-data",
        str(config_path) + ";desktop",
        "--exclude-module",
        "flask",
        "--exclude-module",
        "waitress",
        "--exclude-module",
        "pytest",
    ]
    subprocess.run(
        [
            *common,
            "--name",
            "LiveStudioUpdater",
            "--onefile",
            "--exclude-module",
            "PySide6",
            str(ROOT / "src/desktop/update_helper.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [
            *common,
            "--name",
            "LiveStudio",
            "--onedir",
            "--add-data",
            str(ROOT / "src/desktop/assets") + ";desktop/assets",
            "--hidden-import",
            "desktop.diagnostics",
            "--hidden-import",
            "desktop.worker",
            "--exclude-module",
            "PySide6.QtWebEngineCore",
            "--exclude-module",
            "PySide6.QtQml",
            "--exclude-module",
            "PySide6.QtQuick",
            str(ROOT / "scripts/desktop_entry.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    release_dir.mkdir(parents=True)
    app = release_dir / "LiveStudio"
    shutil.copytree(work / "frozen/LiveStudio", app)
    shutil.copyfile(
        work / "frozen/LiveStudioUpdater.exe", app / "LiveStudioUpdater.exe"
    )
    binaries = app / "bin"
    binaries.mkdir()
    media = args.ffmpeg_dir or Path(shutil.which("ffmpeg") or "missing").parent
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        source = media / name
        if not source.is_file():
            raise ValueError(
                "FFmpeg and FFprobe are required to build the portable package."
            )
        shutil.copyfile(source, binaries / name)
    (app / ".livestudio-package.json").write_text(
        json.dumps(dict(product="LiveStudio", version=args.version)), encoding="utf-8"
    )
    shutil.copyfile(ROOT / "LICENSE", app / "LICENSE-MIT.txt")
    shutil.copyfile(ROOT / "docs/HUONG_DAN_BAN_WINDOWS.txt", app / "HUONG_DAN.txt")
    notices = app / "THIRD-PARTY-LICENSES"
    notices.mkdir()
    for name in ("LICENSE", "README.txt"):
        if (media.parent / name).is_file():
            shutil.copyfile(media.parent / name, notices / ("FFmpeg-" + name))
    (notices / "FFmpeg-build.txt").write_text(
        subprocess.check_output(
            [str(binaries / "ffmpeg.exe"), "-version"], text=True, encoding="utf-8"
        )
        + "\nBinary provider and corresponding source links: https://www.gyan.dev/ffmpeg/builds/\nFFmpeg source repository: https://git.ffmpeg.org/ffmpeg.git\n",
        encoding="utf-8",
    )
    for distribution in importlib.metadata.distributions():
        for item in distribution.files or []:
            text = str(item).replace("\\", "/")
            if ".dist-info/licenses/" in text:
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    destination = notices / text
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
    (app / ".livestudio-package.json").write_text(
        json.dumps(
            dict(
                product="LiveStudio",
                version=args.version,
                files=sorted(
                    path.relative_to(app).as_posix()
                    for path in app.rglob("*")
                    if path.is_file() and path.name != ".livestudio-package.json"
                ),
            )
        ),
        encoding="utf-8",
    )
    archive = release_dir / ("LiveStudio-" + args.version + "-Windows-x64.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(release_dir).as_posix())
    digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
    payload = dict(
        format=1,
        platform="windows-x64",
        version=args.version,
        sha256=digest,
        size=archive.stat().st_size,
        notes=args.notes,
    )
    envelope = dict(
        payload=payload, signature=encode(signer.sign(DOMAIN + manifest_bytes(payload)))
    )
    verify_manifest(envelope, public_key)
    (release_dir / ("LiveStudio-" + args.version + ".json")).write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Release ready:", archive)
    print("Update public key (safe to put on hosting):", public_key)


if __name__ == "__main__":
    main()
