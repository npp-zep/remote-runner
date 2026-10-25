"""remote-runner: 用远程工具链编译本地项目。"""

from importlib.metadata import version , PackageNotFoundError

try:
    __version__ =version("remote-runner")
except PackageNotFoundError:
    __version__="0.0.0"