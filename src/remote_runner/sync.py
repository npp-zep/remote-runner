# src/remote_runner/sync.py
import shlex
import subprocess
from pathlib import Path


class SyncError(Exception):
    pass


def _ssh_args(host: str, port: int) -> list[str]:
    args = ["ssh"]
    if port != 22:
        args += ["-p", str(port)]
    args.append(host)
    return args


def _run_ssh(host: str, port: int, remote_cmd: str) -> subprocess.CompletedProcess:
    cmd = _ssh_args(host, port) + [remote_cmd]
    try:
        return subprocess.run(cmd, text=True, capture_output=True)
    except FileNotFoundError:
        raise SyncError("找不到 ssh，请先安装：apk add openssh-client")


def resolve_remote_home(host: str, port: int = 22) -> str:
    r = _run_ssh(host, port, 'printf %s "$HOME"')
    if r.returncode != 0 or not r.stdout.strip():
        raise SyncError(r.stderr.strip() or "无法获取远端 HOME")
    return r.stdout.strip()


def expand_remote_path(host: str, path: str, port: int = 22) -> str:
    if path == "~":
        return resolve_remote_home(host, port)
    if path.startswith("~/"):
        return resolve_remote_home(host, port) + path[1:]
    return path


def ensure_remote_dir(host: str, remote_dir: str, port: int = 22) -> None:
    r = _run_ssh(host, port, f'mkdir -p "{remote_dir}"')
    if r.returncode != 0:
        raise SyncError(r.stderr.strip() or f"创建远端目录失败: {remote_dir}")


def rsync_to(
    host: str, local: str, remote_tmp: str, excludes: list[str], port: int = 22
) -> None:
    ex_args = [f"--exclude={e}" for e in excludes]
    cmd = ["rsync", "-az", "--delete", "--partial", *ex_args]
    if port != 22:
        cmd += ["-e", f"ssh -p {port}"]
    cmd += [f"{local}/", f"{host}:{remote_tmp}/"]
    try:
        r = subprocess.run(cmd, text=True, capture_output=True)
    except FileNotFoundError:
        raise SyncError("找不到 rsync，请先安装：apk add rsync")
    if r.returncode != 0:
        raise SyncError(r.stderr.strip() or f"rsync 退出码 {r.returncode}")


def atomic_swap(
    host: str, remote_tmp: str, remote_final: str, port: int = 22
) -> None:
    script = (
        f"set -e; "
        f'rm -rf "{remote_final}.old"; '
        f'if [ -d "{remote_final}" ]; then mv "{remote_final}" "{remote_final}.old"; fi; '
        f'mv "{remote_tmp}" "{remote_final}"; '
        f'rm -rf "{remote_final}.old"'
    )
    r = _run_ssh(host, port, script)
    if r.returncode != 0:
        raise SyncError(r.stderr.strip() or f"原子替换失败（退出码 {r.returncode}）")


def cleanup_remote(host: str, path: str, port: int = 22) -> None:
    _run_ssh(host, port, f'rm -rf "{path}"')


def _quote_pattern(p: str) -> str:
    """通配符模式不加引号，让远端 shell 展开；普通路径用 shlex.quote。"""
    if any(ch in p for ch in "*?["):
        return p
    return shlex.quote(p)


def chmod_executables(
    host: str, remote_dir: str, patterns: list[str], port: int = 22
) -> None:
    """在远端 workdir 里给匹配的文件加执行权限。未匹配到文件时不报错。"""
    if not patterns:
        return
    quoted = " ".join(_quote_pattern(p) for p in patterns)
    script = (
        f"cd {shlex.quote(remote_dir)} && "
        f"(chmod +x {quoted} 2>/dev/null || true)"
    )
    r = _run_ssh(host, port, script)
    # 2>/dev/null || true 让 chmod 失败不暴露，但 cd 失败仍会返回非零
    if r.returncode != 0:
        raise SyncError(r.stderr.strip() or f"chmod +x 失败（退出码 {r.returncode}）")


def fetch_artifacts(
    host: str, remote_dir: str, local_dir: str, artifacts: list[str], port: int = 22
) -> None:
    for rel in artifacts:
        rel = rel.rstrip("/")
        remote_src = f"{host}:{remote_dir}/{rel}"
        local_dst = Path(local_dir) / rel
        local_dst.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["rsync", "-az"]
        if port != 22:
            cmd += ["-e", f"ssh -p {port}"]
        cmd += [remote_src, str(local_dst)]
        try:
            r = subprocess.run(cmd, text=True, capture_output=True)
        except FileNotFoundError:
            raise SyncError("找不到 rsync，请先安装：apk add rsync")
        if r.returncode != 0:
            raise SyncError(
                r.stderr.strip() or f"回传 {rel} 失败（退出码 {r.returncode}）"
            )