"""Verify host SQLite and captured callback generations against the selected native core.
使用选定原生核心验证宿主 SQLite 及捕获的回调代次。
"""
import gc
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from luaskills import LuaSkillsClient, LuaSkillsJsonFfi, RuntimeRoots
from luaskills.examples.sqlite_demo import MANIFEST, LUA, main, sqlite_provider


@unittest.skipUnless(os.environ.get("LUASKILLS_LIB"), "requires an explicit native core library")
class SQLiteHostNativeTests(unittest.TestCase):
    """Exercise actual Lua/FFI/SQLite, including replacement and clear while engines remain live.
    验证真实 Lua、FFI、SQLite，并覆盖引擎存活期间的替换与清空。
    """

    def test_packaged_demo(self):
        """Run the packaged demo's write, rollback and reopen assertions; return nothing.
        运行包内示例的写入、回滚及重开断言；无返回值。
        """
        main()

    def test_existing_engines_keep_distinct_providers(self):
        """Keep A/B providers alive after replacement, clear and collection; return nothing.
        在替换、清空及垃圾回收后保持 A、B 提供方存活；无返回值。
        """
        with TemporaryDirectory() as temporary:
            # Only this fixture owns its generated package and database directory.
            # 仅此夹具拥有生成的包及数据库目录。
            root = Path(temporary)
            skill = root / "user_skills" / "sqlite-demo"
            (skill / "runtime").mkdir(parents=True)
            (skill / "skill.yaml").write_text(MANIFEST, encoding="utf-8")
            (skill / "runtime/run.lua").write_text(LUA, encoding="utf-8")
            ffi = LuaSkillsJsonFfi(library_path=os.environ["LUASKILLS_LIB"])
            # Windows path aliases must identify the same process-global registration slot.
            # Windows 路径别名必须标识同一个进程全局注册槽位。
            replacement = LuaSkillsJsonFfi(library_path=str(ffi.library_path).upper() if os.name == "nt" else ffi.library_path)
            calls = [0, 0]

            def provider(index):
                """Capture index and return a real SQLite adapter that counts its generation.
                捕获 index 并返回统计当前代次的真实 SQLite 适配器。
                """
                def execute(request):
                    """Execute request and return SQLite data while recording the captured owner.
                    执行 request 并返回 SQLite 数据，同时记录捕获的所有者。
                    """
                    calls[index] += 1
                    return sqlite_provider(request)
                return execute

            try:
                ffi.set_sqlite_provider_json_callback(provider(0))
                with LuaSkillsClient(library_path=ffi.library_path, runtime_root=root, host_options={"sqlite_callback_mode": "json"}) as first:
                    replacement.set_sqlite_provider_json_callback(provider(1))
                    ffi.clear_sqlite_provider_json_callback()
                    with LuaSkillsClient(library_path=ffi.library_path, runtime_root=root, host_options={"sqlite_callback_mode": "json"}) as second:
                        replacement.clear_sqlite_provider_json_callback()
                        gc.collect()
                        first.load_from_roots(RuntimeRoots.standard(root))
                        second.load_from_roots(RuntimeRoots.standard(root))
                        first.call_skill("sqlite-demo-run", {"write": True, "text": "captured A/B"})
                        self.assertGreater(calls[0], 0)
                        self.assertEqual(calls[1], 0)
                        second.call_skill("sqlite-demo-run", {"write": False, "text": "captured A/B"})
                        self.assertGreater(calls[1], 0)
                    # Releasing the later engine cannot release the earlier engine's callback.
                    # 释放较新引擎不能释放较早引擎的回调。
                    first.call_skill("sqlite-demo-run", {"write": False, "text": "captured A/B"})
            finally:
                replacement.clear_sqlite_provider_json_callback()
                ffi.clear_sqlite_provider_json_callback()
