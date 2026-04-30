"""
Python SDK host-tool callback registration example shipped with the wheel.
随 wheel 分发的 Python SDK 宿主工具 callback 注册示例。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from luaskills import HostToolJsonRequest, LuaSkillsClient, LuaSkillsJsonFfi


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


# Mock host tool metadata exposed through vulcan.host.list().
# 通过 vulcan.host.list() 暴露的 mock 宿主工具元数据。
HOST_TOOLS = [
    {
        "name": "model.embed",
        "description": "Mock embedding tool for SDK examples",
    },
]


def host_tool_callback(request: HostToolJsonRequest) -> dict[str, Any] | list[dict[str, str]] | bool:
    """
    Handle list, has, and call actions from Lua.
    处理来自 Lua 的 list、has 与 call 动作。
    """

    if request["action"] == "list":
        return HOST_TOOLS
    if request["action"] == "has":
        return any(tool["name"] == request["tool_name"] for tool in HOST_TOOLS)
    if request["action"] == "call" and request["tool_name"] == "model.embed":
        args = request["args"] if isinstance(request["args"], dict) else {}
        return {
            "ok": True,
            "value": {
                "model": args.get("model", "mock-embedding"),
                "input": args.get("input", ""),
                "embedding": [0.1, 0.2, 0.3],
            },
        }
    return {
        "ok": False,
        "error": {
            "code": "tool_not_found",
            "message": f"Unknown host tool: {request['tool_name'] or '<missing>'}",
        },
    }


def main() -> None:
    """
    Register one host-tool callback and exercise vulcan.host from inline Lua.
    注册单个宿主工具 callback，并从内联 Lua 调用 vulcan.host。
    """

    runtime_root = resolve_runtime_root()
    library_path = resolve_library_path()
    ffi = LuaSkillsJsonFfi(library_path=library_path, runtime_root=runtime_root)
    ffi.set_host_tool_json_callback(host_tool_callback)
    try:
        with LuaSkillsClient(library_path=library_path, runtime_root=runtime_root) as client:
            lua_result = client.run_lua(
                """
local tools = vulcan.host.list()
local result = vulcan.host.call("model.embed", {
  model = "mock-embedding",
  input = args.input,
})

return {
  tool_count = #tools,
  has_embed = vulcan.host.has("model.embed"),
  has_missing = vulcan.host.has_tool("missing.tool"),
  result = result,
}
""",
                {"input": "hello from Python"},
            )
            print(json.dumps(lua_result, ensure_ascii=False, indent=2))
    finally:
        ffi.clear_host_tool_json_callback()


if __name__ == "__main__":
    main()
