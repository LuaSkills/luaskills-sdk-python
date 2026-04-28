"""
Python SDK lifecycle example using the bundled USER-layer fixture skill.
使用内置 USER 层夹具 skill 的 Python SDK 生命周期示例。
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
    Demonstrate disable and enable through the ordinary Skills plane.
    演示通过普通 Skills plane 执行 disable 与 enable。
    """

    runtime_root = resolve_runtime_root()
    skill_roots = RuntimeRoots.standard(runtime_root)
    tool_name = "demo-standard-ffi-skill-ping"
    skill_id = "demo-standard-ffi-skill"

    with LuaSkillsClient(library_path=resolve_library_path(), runtime_root=runtime_root) as client:
        client.load_from_roots(skill_roots)
        before = client.call_skill(tool_name, {"note": "before-disable"})
        print("Call before disable:", before["content"])

        client.skills.disable(skill_roots, skill_id, "example maintenance window")
        print("Skill disabled:", skill_id)
        print("Visible after disable:", client.is_skill(tool_name, Authority.DELEGATED_TOOL))

        try:
            client.call_skill(tool_name, {"note": "after-disable"})
            raise RuntimeError("call_skill unexpectedly succeeded while the skill was disabled")
        except Exception as error:
            print("Call after disable failed as expected:", error)

        client.skills.enable(skill_roots, skill_id)
        print("Skill enabled:", skill_id)
        after = client.call_skill(tool_name, {"note": "after-enable"})
        print("Call after enable:", after["content"])


if __name__ == "__main__":
    main()
