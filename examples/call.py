"""
Python SDK call and run_lua example using the bundled USER-layer fixture skill.
使用内置 USER 层夹具 skill 的 Python SDK call 与 run_lua 示例。
"""

from __future__ import annotations

import os
from pathlib import Path

from luaskills import LuaSkillsClient, RuntimeRoots


def resolve_runtime_root() -> Path:
    """
    Resolve the fixture runtime root used by this example.
    解析当前示例使用的夹具 runtime root。
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
    Call the fixture skill and execute one inline Lua snippet.
    调用夹具 skill 并执行一个内联 Lua 片段。
    """

    runtime_root = resolve_runtime_root()
    skill_roots = RuntimeRoots.standard(runtime_root)
    tool_name = "demo-standard-ffi-skill-ping"
    invocation_context = {
        "request_context": {"transport_name": "python-sdk-example"},
        "client_budget": {"budget": 1},
        "tool_config": {"mode": "call-demo"},
    }

    with LuaSkillsClient(library_path=resolve_library_path(), runtime_root=runtime_root) as client:
        client.load_from_roots(skill_roots)
        call_result = client.call_skill(tool_name, {"note": "python-call"}, invocation_context)
        print("Call content:", call_result["content"])
        lua_result = client.run_lua(
            "return { note = args.note, transport = vulcan.context.request.transport_name, budget = vulcan.context.client_budget.budget, mode = vulcan.context.tool_config.mode }",
            {"note": "python-lua"},
            invocation_context,
        )
        print("Run Lua result:", lua_result)


if __name__ == "__main__":
    main()
