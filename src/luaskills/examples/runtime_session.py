"""
Python SDK persistent runtime-session example shipped with the wheel.
随 wheel 分发的 Python SDK 持久运行时会话示例。
"""

from __future__ import annotations

import os
from pathlib import Path

from luaskills import LuaSkillsClient


RUNTIME_SESSION_SID = "python-wheel-runtime-session-demo"


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
    Demonstrate one persistent runtime lease without requiring fixture skills.
    演示一个不依赖夹具 skill 的持久运行时租约。
    """

    runtime_root = resolve_runtime_root()
    library_path = resolve_library_path()

    with LuaSkillsClient(library_path=library_path, runtime_root=runtime_root) as client:
        sessions = client.runtime_sessions()
        session = sessions.create_handle(RUNTIME_SESSION_SID, ttl_sec=600, replace=True)
        identity = session.identity_payload()
        print("Lease created:", identity["lease_id"])

        first = session.eval(
            """
counter = (counter or 0) + 1
return {
  counter = counter,
  persisted = true,
}
"""
        )
        print("First eval result:", first["result"])

        second = session.eval(
            """
counter = (counter or 0) + 1
return {
  counter = counter,
  persisted = true,
}
"""
        )
        print("Second eval result:", second["result"])
        print("Lease status result:", session.status())
        print("Lease close result:", session.close())

        post_close = sessions.call_raw(
            "eval",
            {
                "lease_id": identity["lease_id"],
                "sid": identity["sid"],
                "generation": identity["generation"],
                "timeout_ms": 60_000,
                "args": {},
                "code": "return 1",
            },
        )
        print("Post-close eval result:", post_close)


if __name__ == "__main__":
    main()
