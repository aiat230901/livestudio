from diagnostics.phase4_check import run_check


def test_schedules_record_real_mp4s_and_restore_room_budget(tmp_path):
    result = run_check(tmp_path)
    assert result["deadline_preserved"]
    assert result["expired_restart_no_jobs"]
    assert len(result["verified"]) == 3
