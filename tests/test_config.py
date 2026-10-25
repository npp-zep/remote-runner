# tests/test_config.py
import pytest
from pathlib import Path
from remote_runner.config import load_config, Config


def write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "remote-build.toml"
    p.write_text(content, encoding="utf-8")
    return p


VALID = """
[remote]
host = "user@example.com"
workdir = "/tmp/rb"

[build]
command = "make -j4"
artifacts = ["out/"]

[sync]
exclude = [".git", "build"]

[local]
log_dir = "~/.logs"
"""


def test_load_valid_config(tmp_path):
    cfg = load_config(write_toml(tmp_path, VALID))
    assert cfg.host == "user@example.com"
    assert cfg.workdir == "/tmp/rb"
    assert cfg.build_command == "make -j4"
    assert cfg.exclude == [".git", "build"]
    assert cfg.artifacts == ["out/"]
    assert cfg.log_dir == "~/.logs"


def test_minimal_config_uses_defaults(tmp_path):
    minimal = """
[remote]
host = "h"

[build]
command = "true"
"""
    cfg = load_config(write_toml(tmp_path, minimal))
    assert cfg.workdir == "~/tmp/remote-build"
    assert ".git" in cfg.exclude
    assert cfg.artifacts == []
    assert cfg.log_dir == "~/.remote-build-logs"


def test_missing_remote_raises(tmp_path):
    content = '[build]\ncommand = "true"\n'
    with pytest.raises(ValueError, match="配置缺少必填字段"):
        load_config(write_toml(tmp_path, content))


def test_missing_host_raises(tmp_path):
    content = """
[remote]
workdir = "/w"

[build]
command = "true"
"""
    with pytest.raises(ValueError, match="配置缺少必填字段"):
        load_config(write_toml(tmp_path, content))


def test_build_section_optional(tmp_path):
    content = """
[remote]
host = "h"
workdir = "/w"
"""
    cfg = load_config(write_toml(tmp_path, content))
    assert cfg.build_command == ""
    assert cfg.artifacts == []


def test_port_parsed(tmp_path):
    content = """
[remote]
host = "h"
workdir = "/w"
port = 2222

[build]
command = "true"
"""
    cfg = load_config(write_toml(tmp_path, content))
    assert cfg.port == 2222


def test_port_defaults_to_22(tmp_path):
    cfg = load_config(write_toml(tmp_path, VALID))
    assert cfg.port == 22