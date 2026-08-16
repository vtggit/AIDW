import app.worker.loop as loop


def test_issue448_surgical(monkeypatch):
    calls = {"fire_due_sequences_once": 0, "execute_scheduled_run_once": 0}

    def fire_recorder(*args, **kwargs):
        calls["fire_due_sequences_once"] += 1
        return []

    def execute_recorder(*args, **kwargs):
        calls["execute_scheduled_run_once"] += 1
        return None

    monkeypatch.setattr(loop, "fire_due_sequences_once", fire_recorder)
    monkeypatch.setattr(loop, "execute_scheduled_run_once", execute_recorder)
    monkeypatch.setattr(loop, "reap_stale_running", lambda *a, **k: 0)
    monkeypatch.setattr(loop, "reap_stale_executing", lambda *a, **k: 0)
    monkeypatch.setattr(loop, "run_once", lambda *a, **k: None)
    monkeypatch.setattr(loop, "deletions_once", lambda *a, **k: False)

    loop.main_loop(poll_seconds=0.01, max_iterations=1)

    assert calls["fire_due_sequences_once"] == 1
    assert calls["execute_scheduled_run_once"] == 1
