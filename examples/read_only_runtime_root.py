"""
Python SDK example that keeps the runtime root read-only by moving the writable directories elsewhere.
将可写目录移到别处、使运行时根保持只读的 Python SDK 示例。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from luaskills import LuaSkillsClient


def resolve_runtime_root() -> Path:
    """
    Resolve the runtime root used by this example; it is only read.
    解析当前示例使用的 runtime root；示例只读取它。
    """

    return Path(os.environ.get("LUASKILLS_EXAMPLE_RUNTIME_ROOT") or Path(__file__).resolve().parent / "fixture_runtime").resolve()


def resolve_library_path() -> Path | None:
    """
    Resolve an optional explicit LuaSkills dynamic library path.
    解析可选的显式 LuaSkills 动态库路径。
    """

    value = os.environ.get("LUASKILLS_LIB")
    return Path(value).resolve() if value else None


def main() -> None:
    """
    Run inline Lua with host-owned temp and download cache directories outside the runtime root.
    使用位于运行时根之外、由宿主拥有的临时目录及下载缓存目录执行内联 Lua。
    """

    runtime_root = resolve_runtime_root()
    with tempfile.TemporaryDirectory(prefix="luaskills-writable-") as writable_text:
        writable = Path(writable_text)
        # The host creates temp_dir; the engine creates the download cache when it first needs it.
        # 宿主创建 temp_dir；引擎在首次需要时创建下载缓存。
        temp_dir = writable / "temp"
        temp_dir.mkdir()
        host_options = {
            "preserve_host_writable_dirs": True,
            "temp_dir": temp_dir.as_posix(),
            "download_cache_root": (writable / "downloads").as_posix(),
            # Managed-runtime environments are writable too; keep them beside the other host-owned directories.
            # 受管运行时环境同样可写；与其他宿主拥有的目录放在一起。
            "managed_runtime_environment_root": (writable / "envs").as_posix(),
        }
        # The runtime root is already installed, so the client must not create its default layout either.
        # 运行时根已安装完毕，因此客户端也不得创建其默认目录布局。
        with LuaSkillsClient(library_path=resolve_library_path(), runtime_root=runtime_root, host_options=host_options,
                             ensure_runtime_layout=False) as client:
            result = client.run_lua("return { temp_dir = vulcan.runtime.temp_dir }", {})
        print("Runtime root (read only):", runtime_root)
        print("Lua temp_dir:", result)


if __name__ == "__main__":
    main()
