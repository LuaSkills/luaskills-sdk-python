"""
Python SDK runtime-lease example using one persistent lease and one interactive child process.
使用持久租约与交互式子进程的 Python SDK runtime-lease 示例。
"""

from __future__ import annotations

import os
from pathlib import Path

from luaskills import Authority, LuaSkillsClient, RuntimeRoots


RUNTIME_SESSION_SID = "python-sdk-runtime-lease-demo"


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
    Run one persistent runtime-lease smoke flow through the high-level SDK surface.
    通过高级 SDK 接口执行一条持久运行时租约烟测链路。
    """

    runtime_root = resolve_runtime_root()
    skill_roots = RuntimeRoots.standard(runtime_root)

    with LuaSkillsClient(library_path=resolve_library_path(), runtime_root=runtime_root) as client:
        client.load_from_roots(skill_roots)

        system = client.system(Authority.SYSTEM)
        print("Visible entry count:", len(system.list_entries()))
        print(
            "Visible skill ownership:",
            system.skill_name_for_tool("demo-standard-ffi-skill-ping"),
        )

        sessions = system.runtime_leases()
        print(
            "Uses dedicated system runtime-lease endpoints:",
            sessions.uses_system_runtime_lease_endpoints(),
        )

        session = sessions.create_handle(
            RUNTIME_SESSION_SID,
            ttl_sec=600,
            replace=True,
            cwd=str(runtime_root / "system_lua_lib"),
            mounts={"example": "python-runtime-lease"},
        )
        identity = session.identity_payload()
        print("Lease created:", identity["lease_id"])
        print("Lease handle count:", len(sessions.list_handles(RUNTIME_SESSION_SID)))

        opened = session.eval(
            """
local info = vulcan.os.info()
if not proc then
  local spec
  if info.os == "windows" then
    spec = {
      program = "cmd",
      args = { "/V:ON", "/C", "set /P line=&echo session:!line!" },
      encoding = "utf-8",
    }
  else
    spec = {
      program = "sh",
      args = { "-c", "read line; echo session:$line" },
      encoding = "utf-8",
    }
  end
  proc = vulcan.process.session.open(spec)
end
counter = (counter or 0) + 1
proc:write((args.input or "runtime-lease-demo") .. "\\n")
return {
  opened = true,
  counter = counter,
  input = args.input,
}
""",
            args={"input": "runtime-lease-demo"},
        )
        print("Open eval result:", opened["result"])

        read_output = session.eval(
            """
counter = (counter or 0) + 1
local output = proc:read({ timeout_ms = 2000, max_bytes = 8192 })
return {
  counter = counter,
  stdout = output.stdout,
  stderr = output.stderr,
  timed_out = output.timed_out,
}
""",
        )
        print("Read eval result:", read_output["result"])

        print("Lease status result:", session.status())

        closed_process = session.eval(
            """
counter = (counter or 0) + 1
local status = proc:close({ timeout_ms = 3000 })
proc = nil
return {
  counter = counter,
  exited = status.exited,
  success = status.success,
}
""",
        )
        print("Close process eval result:", closed_process["result"])

        print("Lease close result:", session.close())
        print(
            "Post-close eval result:",
            sessions.call_raw(
                "eval",
                {
                    "lease_id": identity["lease_id"],
                    "sid": identity["sid"],
                    "generation": identity["generation"],
                    "timeout_ms": 60_000,
                    "args": {},
                    "code": "return 1",
                },
            ),
        )


if __name__ == "__main__":
    main()
