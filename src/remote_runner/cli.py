# src/remote_runner/cli.py
import argparse
import fcntl
import posixpath
import sys
import time
from pathlib import Path

from remote_runner import __version__
from remote_runner.config import load_config
from remote_runner.sync import (
    rsync_to,
    atomic_swap,
    chmod_executables,
    cleanup_remote,
    ensure_remote_dir,
    expand_remote_path,
    fetch_artifacts,
    SyncError,
)
from remote_runner.build import run_remote, BuildError

EXIT_OK = 0
EXIT_BUILD = 1
EXIT_SYNC = 2
EXIT_CONN = 3
EXIT_LOCK = 4

LOCK_PATH = Path("~/.cache/remote-runner/lock")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="remote-runner",
        description="用远程工具链编译本地项目",
        epilog="子命令: init  生成 remote-build.toml 模板（remote-runner init --help）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "source",
        nargs="?",
        default=".",
        help="要同步的本地目录，或要执行的脚本；默认当前目录",
    )
    p.add_argument("--config", default="remote-build.toml", help="配置文件路径")
    p.add_argument("--cmd", help="覆盖配置里的 build.command（位置参数是脚本时忽略）")
    p.add_argument("--no-fetch", action="store_true", help="不回传产物")
    p.add_argument("--quiet", action="store_true", help="不实时输出构建日志")
    p.add_argument(
        "--nosync",
        action="store_true",
        help="不同步本地到远端，直接在远端已有目录上执行命令",
    )
    p.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="分配 tty，直接连远端终端（用于 REPL 等交互命令）",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args(argv)


def _cmd_init(argv):
    from remote_runner.init import init_config
    p = argparse.ArgumentParser(
        prog="remote-runner init",
        description="生成 remote-build.toml 模板",
    )
    p.add_argument("--host", default="user@server", help="SSH 目标")
    p.add_argument("--port", type=int, default=22, help="SSH 端口")
    p.add_argument("--force", action="store_true", help="覆盖已有文件")
    p.add_argument("--config", default="remote-build.toml", help="输出路径")
    args = p.parse_args(argv)
    return init_config(Path(args.config), args.host, args.port, args.force)


def acquire_lock():
    path = LOCK_PATH.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


def _run(
    cfg,
    source_dir: Path,
    ts: str,
    no_fetch: bool,
    quiet: bool,
    nosync: bool,
    interactive: bool,
) -> int:
    try:
        workdir = expand_remote_path(cfg.host, cfg.workdir, cfg.port)
    except SyncError as e:
        print(f"解析远端路径失败: {e}", file=sys.stderr)
        return EXIT_CONN

    log_file = Path(cfg.log_dir).expanduser() / f"build-{ts}.log"

    if nosync:
        try:
            run_remote(
                cfg.host, workdir, cfg.build_command, log_file, cfg.port,
                stream=not quiet, interactive=interactive,
            )
        except BuildError as e:
            print(f"编译失败，日志: {e.log_file}", file=sys.stderr)
            return EXIT_BUILD
    else:
        remote_tmp = f"{workdir}.tmp-{ts}"
        remote_parent = posixpath.dirname(workdir)
        try:
            try:
                ensure_remote_dir(cfg.host, remote_parent, cfg.port)
                rsync_to(cfg.host, str(source_dir), remote_tmp, cfg.exclude, cfg.port)
            except SyncError as e:
                print(f"同步失败: {e}", file=sys.stderr)
                return EXIT_SYNC

            try:
                atomic_swap(cfg.host, remote_tmp, workdir, cfg.port)
            except SyncError as e:
                print(f"原子替换失败: {e}", file=sys.stderr)
                return EXIT_SYNC

            try:
                chmod_executables(cfg.host, workdir, cfg.executables, cfg.port)
            except SyncError as e:
                print(f"设置执行权限失败: {e}", file=sys.stderr)
                return EXIT_SYNC

            try:
                run_remote(
                    cfg.host, workdir, cfg.build_command, log_file, cfg.port,
                    stream=not quiet, interactive=interactive,
                )
            except BuildError as e:
                print(f"编译失败，日志: {e.log_file}", file=sys.stderr)
                return EXIT_BUILD
        finally:
            cleanup_remote(cfg.host, remote_tmp, cfg.port)

    if not no_fetch and cfg.artifacts:
        try:
            fetch_artifacts(cfg.host, workdir, str(source_dir), cfg.artifacts, cfg.port)
        except SyncError as e:
            print(f"产物回传失败: {e}", file=sys.stderr)
            return EXIT_SYNC

    print(f"构建成功，日志: {log_file}")
    return EXIT_OK


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and Path(argv[0]).name.startswith("remote-runner"):
        argv = argv[1:]
    if argv and argv[0] == "init":
        return _cmd_init(argv[1:])

    args = parse_args(argv)

    try:
        cfg = load_config(args.config)
    except FileNotFoundError:
        print(f"配置错误: 找不到 {args.config}（可运行 remote-runner init 生成模板）", file=sys.stderr)
        return EXIT_CONN
    except ValueError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        return EXIT_CONN

    source_arg = Path(args.source)
    if source_arg.is_file():
        if args.cmd:
            print(
                f'警告: 位置参数是脚本，忽略 --cmd "{args.cmd}"',
                file=sys.stderr,
            )
        source_dir = source_arg.resolve().parent
        script = source_arg.name
        args.cmd = f"./{script}"
        if script not in cfg.executables:
            cfg.executables = cfg.executables + [script]
    else:
        source_dir = source_arg.resolve()
        if not source_dir.is_dir():
            print(f"源目录不存在: {source_dir}", file=sys.stderr)
            return EXIT_CONN

    if args.cmd:
        cfg.build_command = args.cmd

    if not cfg.build_command:
        print("配置错误: 缺少 build.command，且未提供 --cmd", file=sys.stderr)
        return EXIT_CONN

    if args.interactive and args.quiet:
        print(
            "提示: --interactive 与 --quiet 同时存在，交互模式忽略 --quiet",
            file=sys.stderr,
        )

    lock = acquire_lock()
    if lock is None:
        print("已有构建在运行", file=sys.stderr)
        return EXIT_LOCK

    try:
        ts = time.strftime("%Y%m%d-%H%M%S")
        return _run(
            cfg, source_dir, ts,
            args.no_fetch, args.quiet, args.nosync, args.interactive,
        )
    finally:
        lock.close()


if __name__ == "__main__":
    sys.exit(main())