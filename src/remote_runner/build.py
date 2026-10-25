# src/remote_runner/build.py
import shlex
import subprocess
import sys
from pathlib import Path


class BuildError(Exception):
    def __init__(self, returncode: int, log_file: Path):
        super().__init__(f"构建失败，退出码 {returncode}")
        self.returncode = returncode
        self.log_file = log_file


def _ssh_cmd(host: str, port: int, remote_cmd: str, tty: bool) -> list[str]:
    cmd = ["ssh"]
    if tty:
        cmd.append("-t")
    if port != 22:
        cmd += ["-p", str(port)]
    cmd += [host, remote_cmd]
    return cmd


def run_remote(
    host: str,
    remote_dir: str,
    command: str,
    log_file: Path,
    port: int = 22,
    stream: bool = True,
    interactive: bool = False,
) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    remote_cmd = f"cd {shlex.quote(remote_dir)} && {command}"
    cmd = _ssh_cmd(host, port, remote_cmd, tty=interactive)

    if interactive:
        # 继承终端，不捕获，不写日志（pty 控制字符会污染日志）
        try:
            rc = subprocess.call(cmd)
        except FileNotFoundError:
            raise BuildError(-1, log_file)
        if rc != 0:
            raise BuildError(rc, log_file)
        return

    try:
        proc = subprocess.Popen(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
    except FileNotFoundError:
        raise BuildError(-1, log_file)

    with log_file.open("w", encoding="utf-8") as lf:
        assert proc.stdout is not None
        for line in proc.stdout:
            lf.write(line)
            lf.flush()
            if stream:
                sys.stdout.write(line)
                sys.stdout.flush()
        proc.wait()

    if proc.returncode != 0:
        raise BuildError(proc.returncode, log_file)