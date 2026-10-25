# tests/test_build.py
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from remote_runner.build import run_remote, BuildError


def fake_popen(lines, returncode=0):
    proc = MagicMock()
    proc.stdout = iter(lines)
    proc.returncode = returncode
    proc.wait = MagicMock()
    return proc


def test_run_remote_builds_ssh_command(tmp_path):
    log = tmp_path / "build.log"
    with patch(
        "remote_runner.build.subprocess.Popen",
        return_value=fake_popen([]),
    ) as p:
        run_remote("user@host", "/tmp/rb", "make -j4", log)
    args = p.call_args[0][0]
    assert args[0] == "ssh"
    assert args[1] == "user@host"
    assert args[2] == "cd /tmp/rb && make -j4"


def test_run_remote_streams_and_logs(tmp_path, capsys):
    log = tmp_path / "b.log"
    with patch(
        "remote_runner.build.subprocess.Popen",
        return_value=fake_popen(["line1\n", "line2\n"]),
    ):
        run_remote("h", "/w", "make", log)
    captured = capsys.readouterr()
    assert "line1" in captured.out
    assert "line2" in captured.out
    assert log.read_text() == "line1\nline2\n"


def test_run_remote_quiet_no_stdout(tmp_path, capsys):
    log = tmp_path / "b.log"
    with patch(
        "remote_runner.build.subprocess.Popen",
        return_value=fake_popen(["x\n"]),
    ):
        run_remote("h", "/w", "make", log, stream=False)
    assert capsys.readouterr().out == ""
    assert log.read_text() == "x\n"


def test_run_remote_raises_on_failure(tmp_path):
    log = tmp_path / "b.log"
    with patch(
        "remote_runner.build.subprocess.Popen",
        return_value=fake_popen(["err\n"], returncode=2),
    ):
        with pytest.raises(BuildError) as exc:
            run_remote("h", "/w", "make", log)
    assert exc.value.returncode == 2
    assert exc.value.log_file == log


def test_run_remote_uses_custom_port(tmp_path):
    log = tmp_path / "b.log"
    with patch(
        "remote_runner.build.subprocess.Popen",
        return_value=fake_popen([]),
    ) as p:
        run_remote("user@host", "/tmp/rb", "make", log, port=2222)
    args = p.call_args[0][0]
    assert args[:4] == ["ssh", "-p", "2222", "user@host"]


def test_run_remote_omits_port_for_22(tmp_path):
    log = tmp_path / "b.log"
    with patch(
        "remote_runner.build.subprocess.Popen",
        return_value=fake_popen([]),
    ) as p:
        run_remote("user@host", "/tmp/rb", "make", log)
    args = p.call_args[0][0]
    assert args[0] == "ssh"
    assert args[1] == "user@host"


def test_run_remote_popen_missing_raises_build_error(tmp_path):
    log = tmp_path / "b.log"
    with patch(
        "remote_runner.build.subprocess.Popen",
        side_effect=FileNotFoundError,
    ):
        with pytest.raises(BuildError):
            run_remote("h", "/w", "make", log)


def test_run_remote_creates_log_dir(tmp_path):
    log = tmp_path / "sub" / "b.log"
    with patch(
        "remote_runner.build.subprocess.Popen",
        return_value=fake_popen([]),
    ):
        run_remote("h", "/w", "true", log)
    assert log.parent.exists()
    assert log.exists()