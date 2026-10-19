"""Download verified releases and replace only a marked portable installation."""

import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4

import requests

from license_server.releases import verify_manifest, version_tuple

MARKER = ".livestudio-package.json"


def package_info(directory):
    try:
        info = json.loads((Path(directory) / MARKER).read_text(encoding="utf-8"))
        if info.get("product") != "LiveStudio":
            raise ValueError()
        version_tuple(info["version"])
        return info
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError("Thư mục không phải bản Live Studio được đóng gói.") from error


def bundled_config():
    path = Path(__file__).with_name("release-config.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return dict(version="1.0.0", server_url="", update_public_key="")


def check_update(config):
    with requests.get(
        config["server_url"] + "/api/releases/latest",
        timeout=(5, 15),
        allow_redirects=False,
        stream=True,
    ) as response:
        if response.status_code == 404:
            return None
        response.raise_for_status()
        raw = response.raw.read(32769, decode_content=True)
        if len(raw) > 32768:
            raise ValueError("Thông tin cập nhật quá lớn.")
        envelope = json.loads(raw)
    payload = verify_manifest(envelope, config["update_public_key"])
    return (
        envelope
        if version_tuple(payload["version"]) > version_tuple(config["version"])
        else None
    )


def check_archive(archive, payload):
    if Path(archive).stat().st_size != payload["size"]:
        raise ValueError("Dung lượng bản cập nhật không đúng.")
    digest = hashlib.sha256()
    with Path(archive).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != payload["sha256"]:
        raise ValueError("Mã kiểm tra bản cập nhật không đúng.")


def download_update(config, envelope, data, progress=lambda percent: None, cancel=None):
    payload = verify_manifest(envelope, config["update_public_key"])
    if version_tuple(payload["version"]) <= version_tuple(config["version"]):
        raise ValueError("Bản cập nhật phải mới hơn phiên bản hiện tại.")
    work = Path(data) / "updates" / uuid4().hex
    work.mkdir(parents=True)
    path = work / "release.zip"
    digest = payload["sha256"]
    try:
        with requests.get(
            config["server_url"] + f"/api/releases/download/{digest}.zip",
            stream=True,
            timeout=(5, 30),
            allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise ValueError("Không tải được bản cập nhật.")
            total = 0
            with path.open("xb") as output:
                for chunk in response.iter_content(64 * 1024):
                    if cancel is not None and cancel.is_set():
                        raise ValueError("Đã hủy tải bản cập nhật.")
                    total += len(chunk)
                    if total > payload["size"]:
                        raise ValueError("Gói tải xuống vượt dung lượng công bố.")
                    output.write(chunk)
                    progress(int(total * 100 / payload["size"]))
        check_archive(path, payload)
        (work / "manifest.json").write_text(json.dumps(envelope), encoding="utf-8")
        return work
    except Exception:
        path.unlink(missing_ok=True)
        raise


def unpack(archive, destination):
    seen = set()
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if (
            len(entries) > 20000
            or sum(item.file_size for item in entries) > 2 * 1024**3
        ):
            raise ValueError("ZIP có quá nhiều tệp hoặc dung lượng giải nén quá lớn.")
        for item in entries:
            raw = item.orig_filename
            parts = tuple(raw.rstrip("/").split("/"))
            if (
                not parts
                or parts[0] != "LiveStudio"
                or "\\" in raw
                or stat.S_ISLNK(item.external_attr >> 16)
                or any(
                    part in ("", ".", "..")
                    or part.endswith((".", " "))
                    or re.search(r'[<>:"|?*\x00-\x1f]', part)
                    or re.fullmatch(
                        r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part
                    )
                    for part in parts
                )
            ):
                raise ValueError("ZIP chứa đường dẫn không an toàn.")
            relative = Path(*parts[1:])
            normalized = str(relative).casefold()
            if normalized in seen:
                raise ValueError("ZIP có tên tệp trùng nhau.")
            seen.add(normalized)
            output = destination / relative
            if item.is_dir():
                output.mkdir(parents=True, exist_ok=True)
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(item) as source, output.open("xb") as target:
                    shutil.copyfileobj(source, target)


def install_package(archive, envelope, public_key, target, start):
    target = Path(target).resolve()
    current = package_info(target)
    if "files" in current:
        allowed = set(current["files"]) | {MARKER}
        if any(
            path.is_file() and path.relative_to(target).as_posix() not in allowed
            for path in target.rglob("*")
        ):
            raise ValueError(
                "Thư mục tool có thêm tệp riêng hoặc video. Hãy chuyển chúng ra ngoài thư mục chương trình trước khi cập nhật."
            )
    payload = verify_manifest(envelope, public_key)
    if version_tuple(payload["version"]) <= version_tuple(current["version"]):
        raise ValueError("Không được cài lùi phiên bản.")
    check_archive(archive, payload)
    if shutil.disk_usage(target.parent).free < 3 * 1024**3:
        raise ValueError("Cần ít nhất 3 GB trống để cập nhật an toàn.")
    temporary = Path(tempfile.mkdtemp(prefix=".livestudio-stage-", dir=target.parent))
    backup = target.with_name(target.name + ".previous-" + uuid4().hex[:8])
    try:
        unpack(archive, temporary)
        if package_info(temporary)["version"] != payload["version"] or not all(
            (temporary / file).is_file()
            for file in ("LiveStudio.exe", "LiveStudioUpdater.exe")
        ):
            raise ValueError("ZIP không đúng cấu trúc bản phát hành.")
        target.rename(backup)
        try:
            temporary.rename(target)
            if not start(target):
                raise ValueError("Ứng dụng mới không khởi động được.")
        except Exception as error:
            if target.exists():
                target.rename(
                    target.with_name(target.name + ".failed-" + uuid4().hex[:8])
                )
            backup.rename(target)
            raise ValueError("Cập nhật lỗi; đã khôi phục bản trước.") from error
        return backup
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
