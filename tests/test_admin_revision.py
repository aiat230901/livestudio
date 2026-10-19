import io
import json
import shutil
import subprocess

import pytest

from license_server import API_REVISION
from license_server import __main__ as launcher
from license_server.app import create_app


@pytest.mark.parametrize("revision,expected", [(None, 1), (API_REVISION, 0)])
def test_launcher_rejects_stale_server_without_touching_data(
    monkeypatch, capsys, revision, expected
):
    monkeypatch.setattr("sys.argv", ["license_server"])
    monkeypatch.setattr(
        launcher.urllib.request,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(
            json.dumps(
                dict(service="live-studio-license", api_revision=revision)
            ).encode()
        ),
    )
    monkeypatch.setattr(
        launcher,
        "create_app",
        lambda *args: pytest.fail(
            "Must not create/migrate a database while another server is running"
        ),
    )
    assert launcher.main() == expected
    output = capsys.readouterr().out
    assert ("Ctrl+C" in output) == (expected == 1)


def test_health_exposes_current_api_revision(tmp_path):
    app = create_app(tmp_path, testing=True)
    assert app.test_client().get("/health").json["api_revision"] == API_REVISION


def test_admin_feedback_stays_visible_in_confirmation():
    from pathlib import Path

    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node is needed for the frontend logic check")
    subprocess.run(
        [executable, str(Path(__file__).with_name("admin_feedback_check.cjs"))],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
