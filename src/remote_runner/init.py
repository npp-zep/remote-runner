# src/remote_runner/init.py
from pathlib import Path

TEMPLATE = """\
[remote]
host = "{host}"
port = {port}
# workdir = "~/tmp/remote-build/myproj"

[sync]
exclude = [".git", "node_modules", "__pycache__", "*.log"]
executables = ["*.sh", "scripts/*.sh"]

[build]
command = "make"
# artifacts = ["build/"]

[local]
log_dir = "~/.remote-build-logs"
"""


def render_template(host: str = "user@server", port: int = 22) -> str:
    return TEMPLATE.format(host=host, port=port)


def init_config(path: Path, host: str, port: int, force: bool) -> int:
    if path.exists() and not force:
        print(f"配置文件已存在: {path}（用 --force 覆盖）")
        return 1
    path.write_text(render_template(host, port), encoding="utf-8")
    print(f"已生成: {path}")
    print("下一步：")
    print(f"  1. 编辑 {path.name}，把 host 改成真实的 SSH 目标")
    print(f"  2. 验证连通：ssh -p {port} {host} true && echo ok")
    print("  3. 运行：remote-runner")
    return 0