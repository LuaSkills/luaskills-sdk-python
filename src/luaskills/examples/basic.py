"""
Basic Python SDK version query example shipped with the wheel.
随 wheel 分发的 Python SDK 基础版本查询示例。
"""

from __future__ import annotations

import os
from pathlib import Path

from luaskills import LuaSkillsClient


def resolve_runtime_root() -> Path:
    """
    Resolve the runtime root used by installed examples.
    解析已安装示例使用的 runtime root。
    """

    return Path(os.environ.get("LUASKILLS_RUNTIME_ROOT") or Path.cwd() / "luaskills-runtime").resolve()


def resolve_library_path() -> Path | None:
    """
    Resolve an optional explicit LuaSkills dynamic library path.
    解析可选的显式 LuaSkills 动态库路径。
    """

    value = os.environ.get("LUASKILLS_LIB")
    return Path(value).resolve() if value else None


def main() -> None:
    """
    Print the LuaSkills JSON FFI version through the Python SDK.
    通过 Python SDK 输出 LuaSkills JSON FFI 版本。
    """

    print(LuaSkillsClient.version(library_path=resolve_library_path(), runtime_root=resolve_runtime_root()))


if __name__ == "__main__":
    main()
