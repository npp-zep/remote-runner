# src/remote_runner/config.py
import tomllib
from pathlib import Path
from dataclasses import dataclass, field

DEFAULT_EXCLUDE = [".git", "node_modules", "__pycache__", "build"]


@dataclass
class Config:
    host: str
    workdir: str
    build_command: str
    port: int = 22
    exclude: list[str] = field(default_factory=lambda: DEFAULT_EXCLUDE.copy())
    artifacts: list[str] = field(default_factory=list)
    log_dir: str = "~/.remote-build-logs"


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    try:
        remote = raw["remote"]
        build_section = raw.get("build", {})
        return Config(
            host=remote["host"],
            workdir=remote.get("workdir", "~/tmp/remote-build"),
            build_command=build_section.get("command", ""),
            port=int(remote.get("port", 22)),
            exclude=raw.get("sync", {}).get("exclude", DEFAULT_EXCLUDE.copy()),
            artifacts=build_section.get("artifacts", []),
            log_dir=raw.get("local", {}).get("log_dir", "~/.remote-build-logs"),
        )
    except KeyError as e:
        raise ValueError(f"配置缺少必填字段: {e}") from e