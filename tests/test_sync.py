# tests/test_sync.py
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from remote_runner.sync import (
    rsync_to,
    atomic_swap,
    cleanup_remote,
    ensure_remote_dir,
    expand_remote_path,
    resolve_remote_home,
    fetch_artifacts,
    SyncError,
)


def fake_run(returncode=0, stderr="", stdout=""):
    m = MagicMock()
    m.returncode = returncode
    m.stderr = stderr
    m.stdout = stdout
    return m


def test_rsync_builds_correct_command():
    with patch("remote_runner.sync.subprocess.run", return_value=fake_run()) as p:
        rsync_to("user@host", "/local", "/tmp/rb", [".git", "build"])
    args = p.call_args[0][0]
    assert args[0] == "rsync"
    assert "--exclude=.git" in args
    assert "--exclude=build" in args
    assert args[-2] == "/local/"
    assert args[-1] == "user@host:/tmp/rb/"


def test_rsync_raises_on_failure():
    with patch(
        "remote_runner.sync.subprocess.run",
        return_value=fake_run(returncode=23, stderr="some error"),
    ):
        with pytest.raises(SyncError, match="some error"):
            rsync_to("user@host", "/local", "/tmp/rb", [])


def test_rsync_uses_custom_port():
    with patch("remote_runner.sync.subprocess.run", return_value=fake_run()) as p:
        rsync_to("user@host", "/local", "/tmp/rb", [], port=2222)
    args = p.call_args[0][0]
    assert "-e" in args
    assert "ssh -p 2222" in args


def test_rsync_omits_port_for_22():
    with patch("remote_runner.sync.subprocess.run", return_value=fake_run()) as p:
        rsync_to("user@host", "/local", "/tmp/rb", [], port=22)
    args = p.call_args[0][0]
    assert "-e" not in args


def test_resolve_remote_home_returns_stdout():
    with patch(
        "remote_runner.sync.subprocess.run",
        return_value=fake_run(stdout="/home/user\n"),
    ):
        assert resolve_remote_home("h") == "/home/user"


def test_resolve_remote_home_raises_on_failure():
    with patch(
        "remote_runner.sync.subprocess.run",
        return_value=fake_run(returncode=1, stderr="no home", stdout=""),
    ):
        with pytest.raises(SyncError, match="no home"):
            resolve_remote_home("h")


def test_expand_remote_path_no_tilde():
    assert expand_remote_path("h", "/abs/path") == "/abs/path"


def test_expand_remote_path_tilde_only():
    with patch("remote_runner.sync.resolve_remote_home", return_value="/home/u"):
        assert expand_remote_path("h", "~") == "/home/u"


def test_expand_remote_path_tilde_slash():
    with patch("remote_runner.sync.resolve_remote_home", return_value="/home/u"):
        assert expand_remote_path("h", "~/tmp/x") == "/home/u/tmp/x"


def test_ensure_remote_dir_builds_mkdir():
    with patch("remote_runner.sync.subprocess.run", return_value=fake_run()) as p:
        ensure_remote_dir("user@host", "/tmp/rb")
    args = p.call_args[0][0]
    assert args[0] == "ssh"
    assert args[1] == "user@host"
    assert args[2] == 'mkdir -p "/tmp/rb"'


def test_ensure_remote_dir_raises_on_failure():
    with patch(
        "remote_runner.sync.subprocess.run",
        return_value=fake_run(returncode=1, stderr="permission denied"),
    ):
        with pytest.raises(SyncError, match="permission denied"):
            ensure_remote_dir("h", "/root/x")


def test_atomic_swap_builds_remote_script():
    with patch("remote_runner.sync.subprocess.run", return_value=fake_run()) as p:
        atomic_swap("user@host", "/tmp/rb.tmp-1", "/tmp/rb")
    args = p.call_args[0][0]
    assert args[0] == "ssh"
    assert args[1] == "user@host"
    script = args[2]
    assert 'mv "/tmp/rb.tmp-1" "/tmp/rb"' in script
    assert 'rm -rf "/tmp/rb.old"' in script


def test_atomic_swap_uses_custom_port():
    with patch("remote_runner.sync.subprocess.run", return_value=fake_run()) as p:
        atomic_swap("h", "/w.tmp", "/w", port=2222)
    args = p.call_args[0][0]
    assert args[0] == "ssh"
    assert args[1] == "-p"
    assert args[2] == "2222"
    assert args[3] == "h"


def test_atomic_swap_raises_on_failure():
    with patch(
        "remote_runner.sync.subprocess.run",
        return_value=fake_run(returncode=1, stderr="mv failed"),
    ):
        with pytest.raises(SyncError, match="mv failed"):
            atomic_swap("h", "/w.tmp", "/w")


def test_cleanup_remote_does_not_raise():
    with patch(
        "remote_runner.sync.subprocess.run",
        return_value=fake_run(returncode=1, stderr="no such dir"),
    ):
        cleanup_remote("h", "/w.tmp")


def test_fetch_artifacts_builds_command(tmp_path):
    with patch("remote_runner.sync.subprocess.run", return_value=fake_run()) as p:
        fetch_artifacts("user@host", "/tmp/rb", str(tmp_path), ["out/", "bin/app"])
    calls = p.call_args_list
    assert len(calls) == 2
    cmd1 = calls[0][0][0]
    assert cmd1 == ["rsync", "-az", "user@host:/tmp/rb/out", str(tmp_path / "out")]
    cmd2 = calls[1][0][0]
    assert cmd2 == ["rsync", "-az", "user@host:/tmp/rb/bin/app", str(tmp_path / "bin/app")]


def test_fetch_artifacts_raises_on_failure(tmp_path):
    with patch(
        "remote_runner.sync.subprocess.run",
        return_value=fake_run(returncode=23, stderr="denied"),
    ):
        with pytest.raises(SyncError, match="denied"):
            fetch_artifacts("h", "/w", str(tmp_path), ["out"])