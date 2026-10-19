"""Real HTTP + DPAPI + spawned workers: revoking a key finalizes both MP4s."""

import json
import multiprocessing
from pathlib import Path
import subprocess
import sys
from threading import Thread
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from werkzeug.serving import make_server  # noqa: E402
from desktop.licensing import LicenseClient  # noqa: E402
from desktop.manager import RecordingManager  # noqa: E402
from desktop.store import DesktopStore  # noqa: E402
from diagnostics.phase3_check import verify  # noqa: E402
from diagnostics.phase4_check import controlled_process  # noqa: E402
from license_server.app import create_app  # noqa: E402


def run_check(folder):
    folder = Path(folder)
    folder.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-f",
            "flv",
            str(folder / "sample.flv"),
        ],
        check=True,
        timeout=30,
    )
    app = create_app(folder / "server", testing=True)
    service = app.extensions["license_service"]
    key = service.create_keys(1, 1, "isolated recording QA", "qa")[0]
    server = make_server("127.0.0.1", 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = DesktopStore(folder / "desktop.db")
    config = dict(
        version=1,
        server_url=f"http://127.0.0.1:{server.server_port}",
        public_key=app.extensions["license_signer"].public_key,
    )
    client = LicenseClient(folder / "client", config)
    manager = RecordingManager(
        store, process_factory=controlled_process, license_guard=client.allowed
    )
    failures = []
    try:
        assert client.activate(key["key"])
        cached = client.path.read_bytes()
        assert key["key"].encode() not in cached
        assert client.state["activation_token"].encode() not in cached
        for name in ("licensed_one", "licensed_two"):
            store.save_channel(name, None, str(folder / name), True)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            manager.tick()
            if len(manager.jobs) == 2 and all(
                job["spec"]["kind"] == "record"
                and manager.states[user].get("bytes_written", 0) > 0
                for user, job in manager.jobs.items()
            ):
                break
            time.sleep(0.04)
        else:
            raise AssertionError("Both controlled streams did not start")
        service.set_blocked(key["id"], True, "qa")
        assert not client.refresh()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            manager.tick()
            if not manager.jobs:
                break
            time.sleep(0.04)
        assert not manager.jobs
        records = store.list_recordings()
        assert len(records) == 2 and all(
            row["reason"] == "license_denied" for row in records
        )
        verified = [verify(row["path"]) for row in records]
        manager.record_now("licensed_one")
        assert not manager.jobs
        restarted = LicenseClient(folder / "client", config)
        assert not restarted.refresh()
        service.set_blocked(key["id"], False, "qa")
        assert restarted.refresh()
        result = dict(
            parallel_recordings=2,
            block_finalized_both=True,
            mp4_verified=verified,
            encrypted_windows_cache=True,
            denied_restart=True,
            unblock_restored=True,
            source="controlled FLV; no external TikTok request",
        )
    finally:
        manager.shutdown()
        deadline = time.monotonic() + 15
        while manager.jobs and time.monotonic() < deadline:
            manager.tick()
            time.sleep(0.04)
        for job in manager.jobs.values():
            job["process"].terminate()
            job["process"].join(timeout=5)
            failures.append("Hung isolated QA worker")
        store.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert not failures, failures
    return result


if __name__ == "__main__":
    multiprocessing.freeze_support()
    result = run_check(
        ROOT / "diagnostics" / ("license-private-" + time.strftime("%Y%m%d-%H%M%S"))
    )
    (ROOT / "diagnostics" / "license-recording-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
