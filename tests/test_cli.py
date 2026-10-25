# tests/test_cli.py
from pathlib import Path

import fcntl
import pytest

from remote_runner.cli import (
    main,
    EXIT_OK,
    EXIT_BUILD,
    EXIT_SYNC,
    EXIT_CONN,
    EXIT_LOCK,
)
from remote_runner.sync import SyncError
from remote_runner.build import BuildError


def write_cfg(
    tmp_path: Path,
    log_dir: Path | None = None,
    artifacts: list[str] | None = None,
    command: str | None = "make",
) -> Path:
    log = log_dir or tmp_path
    art = ""
    if artifacts:
        art = "artifacts = [" + ", ".join(f'"{a}"' for a in artifacts) + "]\n"
    cmd_line = f'command="{command}"\n' if command is not None else ""
    p = tmp_path / "c.toml"
    p.write_text(
        f'[remote]\nhost="h"\nworkdir="/w"\n'
        f'[build]\n{cmd_line}{art}'
        f'[local]\nlog_dir="{log}"\n',
        encoding="utf-8",
    )
    return p


def _raise(exc):
    def _f(*a, **kw):
        raise exc
    return _f


@pytest.fixture
def isolated_lock(tmp_path, monkeypatch):
    lock = tmp_path / "lock"
    monkeypatch.setattr("remote_runner.cli.LOCK_PATH", lock)
    monkeypatch.setattr(
        "remote_runner.cli.expand_remote_path",
        lambda host, path, port=22: path,
    )
    monkeypatch.setattr(
        "remote_runner.cli.ensure_remote_dir",
        lambda *a, **kw: None,
    )
    return lock


def test_version_exits_zero(isolated_lock):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_missing_config_returns_conn_error(isolated_lock):
    assert main(["--config", "/nonexistent.toml"]) == EXIT_CONN


def test_invalid_config_returns_conn_error(tmp_path, isolated_lock):
    p = tmp_path / "bad.toml"
    p.write_text("[remote]\n", encoding="utf-8")
    assert main(["--config", str(p)]) == EXIT_CONN


def test_expand_path_failure_returns_conn_error(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "remote_runner.cli.expand_remote_path",
            _raise(SyncError("no home")),
        )
        assert main(["--config", str(cfg)]) == EXIT_CONN


def test_missing_cmd_and_command_returns_conn_error(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path, command=None)
    assert main(["--config", str(cfg)]) == EXIT_CONN


def test_nonexistent_source_returns_conn_error(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    assert main(["/nonexistent/dir", "--config", str(cfg)]) == EXIT_CONN


def test_cmd_overrides_config(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    captured = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr(
            "remote_runner.cli.run_remote",
            lambda host, rdir, command, log, port, stream=True: captured.update(
                command=command
            ),
        )
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        assert main(["--config", str(cfg), "--cmd", "echo hi"]) == EXIT_OK
    assert captured["command"] == "echo hi"


def test_source_dir_used_for_sync(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    src = tmp_path / "proj"
    src.mkdir()
    captured = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "remote_runner.cli.rsync_to",
            lambda host, local, rtmp, exc, port: captured.update(local=local),
        )
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.run_remote", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        assert main([str(src), "--config", str(cfg)]) == EXIT_OK
    assert captured["local"] == str(src.resolve())


def test_quiet_passes_stream_false(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    captured = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr(
            "remote_runner.cli.run_remote",
            lambda host, rdir, command, log, port, stream=True: captured.update(
                stream=stream
            ),
        )
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        assert main(["--config", str(cfg), "--quiet"]) == EXIT_OK
    assert captured["stream"] is False


def test_sync_failure_returns_sync_error(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", _raise(SyncError("boom")))
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        assert main(["--config", str(cfg)]) == EXIT_SYNC


def test_swap_failure_returns_sync_error(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", _raise(SyncError("swap failed")))
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        assert main(["--config", str(cfg)]) == EXIT_SYNC


def test_build_failure_returns_build_error(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr(
            "remote_runner.cli.run_remote",
            _raise(BuildError(2, tmp_path / "log")),
        )
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        assert main(["--config", str(cfg)]) == EXIT_BUILD


def test_success_returns_ok(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.run_remote", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        assert main(["--config", str(cfg)]) == EXIT_OK


def test_lock_prevents_concurrent_run(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    holder = open(isolated_lock, "w")
    try:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main(["--config", str(cfg)]) == EXIT_LOCK
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        holder.close()


def test_lock_released_after_run(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.run_remote", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        assert main(["--config", str(cfg)]) == EXIT_OK
        assert main(["--config", str(cfg)]) == EXIT_OK


def test_cleanup_called_on_success(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    cleaned = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.run_remote", lambda *a, **kw: None)
        mp.setattr(
            "remote_runner.cli.cleanup_remote",
            lambda host, path, port: cleaned.append(path),
        )
        assert main(["--config", str(cfg)]) == EXIT_OK
    assert len(cleaned) == 1
    assert cleaned[0].startswith("/w.tmp-")


def test_cleanup_called_on_sync_failure(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    cleaned = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", _raise(SyncError("boom")))
        mp.setattr(
            "remote_runner.cli.cleanup_remote",
            lambda host, path, port: cleaned.append(path),
        )
        assert main(["--config", str(cfg)]) == EXIT_SYNC
    assert len(cleaned) == 1


def test_artifacts_fetched_from_final_dir(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path, artifacts=["out"])
    calls = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.run_remote", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        mp.setattr(
            "remote_runner.cli.fetch_artifacts",
            lambda host, rdir, ldir, arts, port: calls.append((host, rdir, ldir, arts)),
        )
        assert main(["--config", str(cfg)]) == EXIT_OK
    assert calls == [("h", "/w", str(Path.cwd()), ["out"])]


def test_fetch_skipped_with_no_fetch_flag(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path, artifacts=["out"])
    calls = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.run_remote", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.fetch_artifacts", lambda *a, **kw: calls.append(a))
        assert main(["--config", str(cfg), "--no-fetch"]) == EXIT_OK
    assert calls == []


def test_fetch_skipped_when_no_artifacts(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path)
    calls = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.run_remote", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.fetch_artifacts", lambda *a, **kw: calls.append(a))
        assert main(["--config", str(cfg)]) == EXIT_OK
    assert calls == []


def test_fetch_failure_returns_sync_error(tmp_path, isolated_lock):
    cfg = write_cfg(tmp_path, artifacts=["out"])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("remote_runner.cli.rsync_to", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.atomic_swap", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.run_remote", lambda *a, **kw: None)
        mp.setattr("remote_runner.cli.cleanup_remote", lambda *a, **kw: None)
        mp.setattr(
            "remote_runner.cli.fetch_artifacts",
            _raise(SyncError("pull failed")),
        )
        assert main(["--config", str(cfg)]) == EXIT_SYNC