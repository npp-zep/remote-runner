# tests/test_init.py
from remote_runner.init import render_template, init_config


def test_render_template_contains_host_and_port():
    s = render_template("u@h", 2222)
    assert 'host = "u@h"' in s
    assert "port = 2222" in s
    assert "[build]" in s
    assert "[sync]" in s


def test_init_creates_file(tmp_path):
    p = tmp_path / "remote-build.toml"
    assert init_config(p, "u@h", 2222, force=False) == 0
    text = p.read_text()
    assert 'host = "u@h"' in text
    assert "port = 2222" in text


def test_init_refuses_overwrite_without_force(tmp_path, capsys):
    p = tmp_path / "remote-build.toml"
    p.write_text("old")
    assert init_config(p, "u@h", 22, force=False) == 1
    assert p.read_text() == "old"
    assert "已存在" in capsys.readouterr().out


def test_init_overwrites_with_force(tmp_path):
    p = tmp_path / "remote-build.toml"
    p.write_text("old")
    assert init_config(p, "u@h", 22, force=True) == 0
    assert 'host = "u@h"' in p.read_text()


def test_init_defaults():
    s = render_template()
    assert 'host = "user@server"' in s
    assert "port = 22" in s