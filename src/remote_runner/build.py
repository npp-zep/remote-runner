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


def run_remote(
    host: str,
    remote_dir: str,
    command: str,
    log_file: Path,
    port: int = 22,
    stream: bool = True,
) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ssh"]
    if port != 22:
        cmd += ["-p", str(port)]
    cmd += [host, f"cd {shlex.quote(remote_dir)} && {command}"]

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