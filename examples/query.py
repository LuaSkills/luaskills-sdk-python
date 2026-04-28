"""
Python SDK query-surface example using the bundled USER-layer fixture skill.
使用内置 USER 层夹具 skill 的 Python SDK 查询面示例。
"""

from __future__ import annotations

import os
from pathlib import Path

from luaskills import Authority, LuaSkillsClient, RuntimeRoots


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
    Load the fixture skill and print common delegated-query results.
    加载夹具 skill 并输出常见委托查询结果。
    """

    runtime_root = resolve_runtime_root()
    skill_roots = RuntimeRoots.standard(runtime_root)
    tool_name = "demo-standard-ffi-skill-ping"

    with LuaSkillsClient(library_path=resolve_library_path(), runtime_root=runtime_root) as client:
        client.load_from_roots(skill_roots)
        entries = client.list_entries(Authority.DELEGATED_TOOL)
        print("Entry count:", len(entries))
        print("Is delegated-visible skill:", client.is_skill(tool_name, Authority.DELEGATED_TOOL))
        print("Owning skill id:", client.skill_name_for_tool(tool_name, Authority.DELEGATED_TOOL))
        completions = client.prompt_argument_completions(tool_name, "note", Authority.DELEGATED_TOOL) or []
        print("Prompt completion count:", len(completions))
        print("Help tree count:", len(client.list_skill_help(Authority.DELEGATED_TOOL)))


if __name__ == "__main__":
    main()
