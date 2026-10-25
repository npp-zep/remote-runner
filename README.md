remote-runner
=============

用远程工具链编译本地项目的命令行工具。

在本地编辑代码，通过 rsync 同步到远端服务器，在远端用它的编译器/工具链执行
构建命令，实时看输出，构建成功后把产物拉回本地。

适用于：手机/平板上的 Acode、Termux 等环境，本地缺 JDK、GCC、Node 等工具链，
但有一台能 SSH 的远程机器（或同一台设备的 Termux sshd）可用。


依赖
----

两端都需要：

  本地（运行 remote-runner 的机器）
    - Python >= 3.11
    - rsync
    - ssh（openssh-client）
    例：apk add rsync openssh-client

  远端（执行构建的服务器）
    - rsync
    - sshd（正在运行，且能从本地免密登录）
    例：pkg install rsync openssh        （Termux）
        apt install rsync openssh-server （Debian/Ubuntu）

本地和远端都要能直接执行 rsync 和 ssh。远端缺 rsync 时，同步会报
"rsync: command not found"。

远端还需要装好你要用的工具链（make、gcc、node、java 等），且 PATH 包含这些命令。
非交互 ssh 不读 .bashrc，必要时在 command 里显式 export PATH 或用绝对路径。


安装
----

方式 A：从源码用 uv（推荐）

  git clone <repo> && cd remote-runner
  UV_LINK_MODE=copy uv sync
  uv run remote-runner --help

  想全局使用（任意目录直接敲 remote-runner）：

    UV_LINK_MODE=copy uv tool install . --force
    uv tool update-shell          # 或手动把 ~/.local/bin 加进 PATH
    remote-runner --version

  如果 uv tool install 报 "Operation not permitted" 硬链接错误，说明文件系统
  不支持硬链接，必须设置 UV_LINK_MODE=copy。建议写进 ~/.bashrc：

    echo 'export UV_LINK_MODE=copy' >> ~/.bashrc
    source ~/.bashrc

  安装后命令在 ~/.local/bin（或 $XDG_BIN_HOME），确保该目录在 PATH 里：

    export PATH="$HOME/.local/bin:$PATH"

  卸载：uv tool uninstall remote-runner

方式 B：pip

  pip install .
  remote-runner --version


快速开始
--------

1. 在项目根目录生成配置模板

     remote-runner init --host user@server --port 22

   不带参数则生成占位值（user@server、22），之后手动编辑。

2. 编辑 remote-build.toml，把 host 改成真实的 SSH 目标

3. 验证连通

     ssh -p 22 user@server true && echo ok

4. 运行

     remote-runner


子命令
------

  remote-runner init   生成 remote-build.toml 模板（详见下一节）

主命令的帮助末尾也会提示这一点：remote-runner --help


配置
----

在项目根目录创建 remote-build.toml。最简单的配置只需要 host：

  [remote]
  host = "user@server"

完整字段：

  [remote]
  host = "user@server"              # 必填，SSH 目标，支持 ~/.ssh/config 别名
  port = 22                         # 可选，默认 22
  workdir = "~/tmp/remote-build"    # 可选，远端工作目录，默认 ~/tmp/remote-build
                                    # 支持 ~ 开头，会自动解析为远端 HOME

  [sync]
  exclude = [".git", "node_modules", "__pycache__", "build"]
                                    # 可选，rsync 排除列表
  executables = ["*.sh", "configure"]
                                    # 可选，同步后 chmod +x 的模式

  [build]
  command = "make -j4"              # 可选，构建命令；可用 --cmd 覆盖
  artifacts = ["build/", "bin/app"] # 可选，构建后回传到本地的相对路径

  [local]
  log_dir = "~/.remote-build-logs"  # 可选，本地日志目录

注意：
  - workdir 会被原子替换（旧的挪到 .old 再删），不要指向手动维护的目录。
  - workdir 的父目录会自动创建。
  - exclude 里的 "build" 会匹配任意层级的 build 目录；只想排除根目录用 "/build"。
  - artifacts 是相对 workdir 的路径，回传到本地 source 目录的同名位置。
  - artifacts 里的路径在远端不存在时会跳过并提示，不视为失败。
  - executables 里的通配符（* ? [）由远端 shell 展开；chmod 失败被静默忽略。


用法
----

1. 纯配置模式（同步当前目录，执行配置里的 command）

     cd myproj
     remote-runner

2. 临时覆盖命令

     remote-runner . --cmd "make -j8"
     remote-runner . --cmd "npm run build"

3. 指定源目录

     remote-runner /path/to/proj --cmd "cargo build"

4. 脚本作为位置参数（同步脚本所在目录，自动 chmod +x，远端执行 ./脚本）

     remote-runner ./luaj.sh
     remote-runner ./tools/run.sh

   位置参数是文件时，--cmd 会被忽略并打印警告。

5. 不同步，直接在远端已有目录上执行（只回传产物）

     remote-runner . --cmd "make" --nosync

   适用于远端目录已由你自己维护（比如手动 git clone 过）的场景。
   注意：--nosync 下远端内容不是本次本地状态，可能和本地不一致。

6. 交互模式（REPL、需要输入的命令）

     remote-runner ./luaj.sh --interactive
     remote-runner ./luaj.sh -i --nosync

   分配 tty，直接连远端终端，不写日志（pty 控制字符会污染日志）。
   与非交互模式互斥，--quiet 在交互模式下被忽略。
   如果报 "Pseudo-terminal will not be allocated"，说明本地终端不是真 tty；
   可把 build.py 里的 "-t" 改成 "-tt" 强制分配（输入可能有回显重复）。

7. 静默模式

     remote-runner . --cmd "make" --quiet

   构建输出只写日志，不刷终端。失败时仍会提示日志路径。

8. 不回传产物

     remote-runner . --cmd "make" --no-fetch


init 子命令
-----------

生成 remote-build.toml 模板。

  remote-runner init                          # 当前目录，占位值
  remote-runner init --host user@server --port 2222
  remote-runner init --force                  # 覆盖已有文件
  remote-runner init --config /path/to/x.toml # 输出到指定路径

已有文件时默认拒绝覆盖，提示用 --force。


参数一览
--------

  source                要同步的本地目录，或要执行的脚本；默认当前目录
  --config PATH         配置文件路径，默认 remote-build.toml
  --cmd CMD             覆盖配置里的 build.command
  --no-fetch            不回传产物
  --quiet               不实时输出构建日志
  --nosync              不同步本地到远端，直接在远端已有目录上执行
  -i, --interactive     分配 tty，直接连远端终端
  --version             显示版本
  -h, --help            显示帮助（末尾提示 init 子命令）


退出码
------

  0   成功
  1   编译失败（远端命令返回非零）
  2   同步失败 / 原子替换失败 / chmod 失败 / 产物回传失败
  3   配置错误 / 源目录不存在 / 无法解析远端 HOME
  4   已有构建在运行（本地锁被占用）


执行流程
--------

非 --nosync 模式：

  1. 解析 workdir 里的 ~ 为远端 HOME 绝对路径
  2. 在远端 mkdir -p workdir 的父目录
  3. rsync 本地 source 到 {workdir}.tmp-{时间戳}
  4. 原子替换：workdir 挪到 workdir.old，tmp 挪到 workdir，删 old
  5. 按 executables 在 workdir 里 chmod +x
  6. 在 workdir 里执行 command，输出实时打印并写日志
  7. 按 artifacts 从 workdir 回传到本地 source
  8. 无论成功失败，删除本次的 {workdir}.tmp-{时间戳}

--nosync 模式跳过 2-5 和 8，直接在远端已有 workdir 上执行 6-7。


日志
----

每次运行写一份日志到 log_dir（默认 ~/.remote-build-logs），文件名
build-YYYYMMDD-HHMMSS.log。非交互模式下，日志内容和终端输出一致。
交互模式不写日志。


常见问题
--------

Q: 报 "rsync: command not found"
A: 远端没装 rsync。在远端执行 pkg install rsync（Termux）或
   apt install rsync（Debian/Ubuntu）。

Q: 报 "mkdir ... No such file or directory"
A: 远端 workdir 的父目录不存在。工具会自动创建，如果仍报错，检查
   路径权限，或手动 ssh 上去 mkdir -p。

Q: 报 "Permission denied" 但文件在
A: 脚本没有执行位。把脚本加到 [sync].executables，或用位置参数
   直接传脚本路径（会自动加进 executables）。

Q: 编译成功但本地没有产物
A: 配置里没写 [build].artifacts，或用了 --no-fetch。加上
   artifacts = ["build/"] 之类的路径。如果远端确实没有该路径，
   会打印"远端不存在 ... 跳过回传"，属于正常跳过而非失败。

Q: REPL 里打不了字 / 立刻退出
A: 需要 --interactive 分配 tty。如果仍报 "Pseudo-terminal will not
   be allocated"，说明本地终端不是真 tty，换一个终端模拟器，或把
   build.py 里的 "-t" 改成 "-tt" 强制分配。

Q: 远端 java/gcc/node 找不到
A: 工具只负责把代码送过去执行，工具链要在远端装好，且 PATH 包含
   这些命令。非交互 ssh 不读 .bashrc，必要时在 command 里显式
   export PATH 或写绝对路径。

Q: 同一台设备上连自己的 Termux sshd
A: host 写 user@localhost，port 写 Termux sshd 的端口（默认 8022）。
   先在本地 ssh -p 8022 user@localhost true 确认免密能通。

Q: uv 报 "Operation not permitted" 硬链接错误
A: 设置 UV_LINK_MODE=copy 环境变量，或写进 ~/.bashrc。详见"安装"一节。

Q: uv tool install 后 remote-runner 找不到
A: 安装目录（通常 ~/.local/bin）不在 PATH。执行 uv tool update-shell，
   或手动 export PATH="$HOME/.local/bin:$PATH"。

Q: --nosync 跑完本地没变化
A: 预期行为。--nosync 不同步本地到远端，只在远端已有目录上执行命令，
   再把 artifacts 拉回本地。远端目录内容由你之前某次同步或手动维护决定。

Q: 改了源码但 remote-runner 行为没变
A: uv tool install 装的是 wheel 快照，不是 editable。改源码后需重装：
   UV_LINK_MODE=copy uv tool install . --force。若仍无效，清理缓存：
   uv cache clean，或临时升 pyproject.toml 的 version 强制重建。


退出码速查
----------

  0 OK
  1 编译失败
  2 同步/回传失败
  3 配置/连接错误
  4 并发锁占用