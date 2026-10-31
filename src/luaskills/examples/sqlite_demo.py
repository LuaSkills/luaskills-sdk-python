"""Run a real host-owned SQLite round trip through LuaSkills 0.7.4.
通过 LuaSkills 0.7.4 执行真实宿主 SQLite 往返验证。
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from luaskills import LuaSkillsClient, LuaSkillsJsonFfi, RuntimeRoots

# The demo declares SQLite access but never chooses a database implementation.
# 示例声明 SQLite 访问权限，但不选择数据库实现。
MANIFEST = """name: sqlite-demo
version: 0.1.0
enable: true
sqlite:
  enable: true
entries:
  - name: run
    lua_entry: runtime/run.lua
    lua_module: sqlite_demo_run
"""

# SQL parameters cross Lua and FFI unchanged; a failing batch must roll back completely.
# SQL 参数原样经过 Lua 和 FFI；失败批次必须完整回滚。
LUA = """-- Verify host SQLite persistence, parameter binding, and atomic rollback.
-- 验证宿主 SQLite 持久化、参数绑定及原子回滚。
return function(args)
  if args.write then
    vulcan.sqlite.execute_script({sql = 'CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL);'})
    vulcan.sqlite.execute_batch({statements = {{sql = 'INSERT INTO notes VALUES (?, ?)', params = {1, args.text}}}})
    -- A duplicate key after a valid insert must leave neither change committed.
    -- 有效插入后发生重复键错误，必须保证整个批次均不提交。
    local ok = pcall(function()
      vulcan.sqlite.execute_batch({statements = {
        {sql = 'INSERT INTO notes VALUES (?, ?)', params = {2, 'rolled back'}},
        {sql = 'INSERT INTO notes VALUES (?, ?)', params = {1, 'duplicate'}}
      }})
    end)
    assert(not ok, 'invalid batch unexpectedly succeeded')
  end
  -- The second invocation uses a new engine and freshly opened host connections.
  -- 第二次调用使用新引擎及宿主重新打开的连接。
  local result = vulcan.sqlite.query_json({sql = 'SELECT body FROM notes WHERE id = ?', params = {1}})
  assert(#result.rows == 1 and result.rows[1].body == args.text, 'parameter or persistence mismatch')
  local count = vulcan.sqlite.query_json({sql = 'SELECT COUNT(*) AS total FROM notes', params = {}})
  assert(count.rows[1].total == 1, 'batch was not rolled back')
  return 'sqlite-demo:ok:' .. result.database_path
end
"""


def sqlite_provider(request: Any) -> dict[str, Any]:
    """Execute the action/binding/input request using a host-owned connection; return JSON rows or changes.
    使用宿主连接执行 action/binding/input 请求；返回 JSON 行或变更数。
    Only the core binding chooses the database path; SQL uses positional parameters and errors propagate.
    仅由核心绑定指定数据库路径；SQL 使用位置参数，错误直接传播。
    """
    # The binding is authoritative; skill input cannot redirect the connection.
    # 绑定是唯一可信路径来源；技能输入不能重定向连接。
    database_path = Path(request["binding"]["default_database_path"])
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # Every request opens and closes its own connection, proving file persistence between requests.
    # 每次请求均打开并关闭独立连接，验证请求之间的文件持久化。
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        # The input shape is the demo's explicit SQL protocol, not a core-owned SQL dialect.
        # 输入结构是示例显式定义的 SQL 协议，不是核心管理的 SQL 方言。
        sql_input = request["input"]
        if request["action"] == "execute_script":
            connection.executescript(sql_input["sql"])
            return {"changes": connection.total_changes}
        if request["action"] == "execute_batch":
            with connection:
                for statement in sql_input["statements"]:
                    connection.execute(statement["sql"], statement["params"])
            return {"changes": connection.total_changes}
        if request["action"] == "query_json":
            # Lua represents an empty table as an object; this protocol accepts it as zero parameters.
            # Lua 将空表表示为对象；本协议将其解释为零个参数。
            parameters = sql_input["params"]
            if parameters == {}:
                parameters = []
            return {"rows": [dict(row) for row in connection.execute(sql_input["sql"], parameters)], "database_path": str(database_path)}
        raise ValueError(f"unsupported SQLite demo action: {request['action']}")


def main() -> None:
    """Create an isolated skill, run write/read engines, and retain the database for inspection; return nothing.
    创建隔离技能，运行写入及读取引擎，并保留数据库供检查；无返回值。
    LUASKILLS_LIB or LUASKILLS_RUNTIME_ROOT selects the installed core, never an existing demo database.
    LUASKILLS_LIB 或 LUASKILLS_RUNTIME_ROOT 选择已安装核心，不复用既有示例数据库。
    """
    # Library discovery uses the installed runtime, while generated data lives in a fresh directory.
    # 动态库发现使用已安装运行时，而生成数据存放于全新目录。
    ffi = LuaSkillsJsonFfi(library_path=os.environ.get("LUASKILLS_LIB"), runtime_root=os.environ.get("LUASKILLS_RUNTIME_ROOT", "luaskills-runtime"))
    runtime_root = Path(mkdtemp(prefix="luaskills-sqlite-python-"))
    skill = runtime_root / "user_skills" / "sqlite-demo"
    (skill / "runtime").mkdir(parents=True)
    (skill / "skill.yaml").write_text(MANIFEST, encoding="utf-8")
    (skill / "runtime" / "run.lua").write_text(LUA, encoding="utf-8")
    # Quotes, SQL syntax, and Unicode remain data instead of executable SQL.
    # 引号、SQL 语法及 Unicode 始终是数据，而非可执行 SQL。
    note = "宿主 SQLite: '); DROP TABLE notes; --"
    try:
        for write in (True, False):
            ffi.set_sqlite_provider_json_callback(sqlite_provider)
            with LuaSkillsClient(library_path=ffi.library_path, runtime_root=runtime_root, host_options={"host_mode": "desktop", "sqlite_callback_mode": "json"}) as client:
                # Existing engines retain their captured provider after the process default is cleared.
                # 清空进程默认值后，既有引擎仍保留已捕获的提供方。
                ffi.clear_sqlite_provider_json_callback()
                client.load_from_roots(RuntimeRoots.standard(runtime_root))
                result = client.call_skill("sqlite-demo-run", {"write": write, "text": note})
                if not result["content"].startswith("sqlite-demo:ok:"):
                    raise AssertionError(result)
                print(result["content"])
    finally:
        ffi.clear_sqlite_provider_json_callback()


if __name__ == "__main__":
    main()
