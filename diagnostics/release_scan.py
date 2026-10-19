"""Check a signed ZIP for private owner material before sharing it."""

import argparse
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from desktop.updates import check_archive  # noqa: E402
from license_server.releases import verify_manifest  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    envelope = json.loads(args.manifest.read_text(encoding="utf-8"))
    public = (ROOT / ".release-signing/update-public-key.txt").read_text()
    payload = verify_manifest(envelope, public)
    check_archive(args.archive, payload)
    forbidden = {
        "secrets.json",
        "license.sqlite3",
        "license.dat",
        "cookies.json",
        "telegram.json",
        "update-signing.key",
        "hosting-bootstrap.txt",
        ".env",
    }
    private = json.loads((ROOT / ".license-server/secrets.json").read_text())
    needles = [
        private["session_secret"].encode(),
        private["signing_key"].encode(),
        (ROOT / ".release-signing/update-signing.key").read_bytes(),
    ]
    with zipfile.ZipFile(args.archive) as bundle:
        names = bundle.namelist()
        assert all(Path(name).name not in forbidden for name in names), (
            "Private filename in ZIP"
        )
        assert any(name.endswith("/platforms/qwindows.dll") for name in names), (
            "Windows Qt platform missing"
        )
        marker = json.loads(bundle.read("LiveStudio/.livestudio-package.json"))
        assert marker["version"] == payload["version"] and marker.get("files")
        assert set(marker["files"]) == {
            name.removeprefix("LiveStudio/")
            for name in names
            if name != "LiveStudio/.livestudio-package.json"
        }
        for name in names:
            with bundle.open(name) as stream:
                tail = b""
                while chunk := stream.read(1024 * 1024):
                    content = tail + chunk
                    assert all(needle not in content for needle in needles), (
                        "Owner private secret in package"
                    )
                    assert not re.search(
                        rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})",
                        content,
                    ), "GitHub token in package"
                    tail = content[-256:]
    report = dict(
        version=payload["version"],
        bytes=payload["size"],
        files=len(names),
        signature="valid",
        hash="valid",
        windows_qt_platform=True,
        owner_secret_scan="passed",
    )
    (ROOT / "diagnostics/windows-release-scan.json").write_text(
        json.dumps(report, indent=2)
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
