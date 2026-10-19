import pytest

from desktop.store import DesktopStore, normalize_username


@pytest.mark.parametrize(
    "value",
    ["@Example.Name", "example.name", "https://www.tiktok.com/@example.name/live?x=1"],
)
def test_normalize(value):
    assert normalize_username(value) == "example.name"


@pytest.mark.parametrize("value", ["", "../bad", "https://evil.com/@name", "a/b", "@"])
def test_reject_bad_user(value):
    with pytest.raises(ValueError):
        normalize_username(value)


def test_persistence_and_unique_channel(tmp_path):
    path = tmp_path / "dữ liệu.db"
    store = DesktopStore(path)
    store.save_channel("@name", 3600, "D:/Video có dấu", True)
    store.save_channel("name", None, None, False)
    assert len(store.list_channels()) == 1
    store.set_setting("interval", 120)
    store.save_session("name", "room1", 100, 1000, "completed")
    store.close()
    store = DesktopStore(path)
    assert store.get_session("name", "room1")["deadline_utc"] == 1000
    assert store.get_session("name", "room1")["state"] == "completed"
    assert store.get_setting("interval") == 120
    for invalid in [0, -1, 1.5, True]:
        with pytest.raises(ValueError):
            store.save_channel("name", invalid, None, True)
    assert store.list_channels()[0]["duration_seconds"] is None
    store.close()


def test_phase3_database_migrates_without_losing_data(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE channels(username TEXT PRIMARY KEY, duration_seconds INTEGER, output TEXT, enabled INTEGER NOT NULL)"
    )
    db.execute("INSERT INTO channels VALUES (?, ?, ?, ?)", ("old", 1800, "D:/Video", 1))
    db.commit()
    db.close()
    store = DesktopStore(path)
    channel = store.list_channels()[0]
    assert channel["mode"] == "continuous" and channel["schedules"] == []
    assert channel["duration_seconds"] == 1800 and channel["output"] == "D:/Video"
    rule = dict(kind="weekly", days=[0, 2], start_minute=540, end_minute=600)
    store.save_channel(
        "old", 1800, "D:/Video", True, mode="scheduled", schedules=[rule]
    )
    store.save_channel("old", 1800, "D:/Video", False)
    store.close()
    store = DesktopStore(path)
    channel = store.list_channels()[0]
    assert channel["mode"] == "scheduled" and channel["schedules"] == [rule]
    with pytest.raises(ValueError):
        store.save_channel("old", mode="scheduled", schedules=[dict(kind="weekly")])
    assert store.list_channels()[0] == channel
    store.close()
