"""
Verify the generated SDK contract, offline synchronization and wire typing boundaries without a native library.
无需原生库，验证生成 SDK 契约、离线同步及线类型边界。
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import typing
import unittest

from luaskills import EffectState, EmbeddedNativeStatus
from luaskills import embedded_contract as contract


# Load the actual repository generator so malformed schema cases exercise production generation.
# 加载仓库实际生成器，使无效 Schema 用例执行正式生成逻辑。
ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "scripts/generate_embedded_contract.py"
SPEC = importlib.util.spec_from_file_location("embedded_contract_generator", GENERATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class EmbeddedContractTests(unittest.TestCase):
    """
    Exercise SDK artifact reproducibility and type fidelity against the actual packaged Rust schemas.
    针对实际包内 Rust Schema 验证 SDK 产物可复现性及类型保真度。
    """

    def setUp(self) -> None:
        """
        Read and verify the exact packaged contract before each isolated mutation case.
        每个隔离变更用例开始前读取并验证精确包内契约。
        Return nothing and retain independent parsed objects for the test instance.
        无返回值，并为测试实例保留独立解析对象。
        """
        # No native fixture or sibling checkout participates in these offline checks.
        # 这些离线检查不使用原生夹具或相邻检出。
        self.document, self.encoded, self.digest = GENERATOR.verified_contract(GENERATOR.CONTRACT)

    def test_generated_artifact_and_all_references_are_current(self) -> None:
        """
        Check exact source bytes and resolve every public TypedDict reference, including recursive JSON values.
        检查精确源码字节并解析每个公开 TypedDict 引用，包含递归 JSON 值。
        Return nothing; stale source or an unresolved generated field fails the test.
        无返回值；过期源码或未解析的生成字段使测试失败。
        """
        subprocess.run([sys.executable, str(GENERATOR_PATH), "--check"], check=True)
        self.assertEqual(contract.EMBEDDED_CONTRACT_SHA256, hashlib.sha256(self.encoded).hexdigest())
        self.assertEqual(contract.EMBEDDED_PROTOCOL_VERSION, self.document["protocol_version"])
        self.assertEqual(contract.EMBEDDED_CORE_VERSION, self.document["core_version"])
        self.assertEqual(dict((item.name.lower(), item.value) for item in EmbeddedNativeStatus), self.document["native_status"])
        self.assertEqual(set(typing.get_args(EffectState)), {
            variant["const"] for variant in self.document["request"]["$defs"]["EffectState"]["oneOf"]
        })
        for name in contract.__all__:
            with self.subTest(name=name):
                # Resolving imported annotations checks reference spelling beyond mere compileall success.
                # 解析导入注解可在单纯 compileall 成功之外检查引用拼写。
                declaration = getattr(contract, name)
                if typing.is_typeddict(declaration):
                    self.assertEqual(set(typing.get_type_hints(declaration)), declaration.__required_keys__ | declaration.__optional_keys__)

    def test_commands_and_response_types_cover_the_actual_protocol(self) -> None:
        """
        Compare tagged request unions and named response declarations with the Rust command inventory.
        将带标记请求联合及命名响应声明与 Rust 命令清单比较。
        Return nothing; added commands require a generated branch and corresponding response type.
        无返回值；新增命令必须具有生成分支及对应响应类型。
        """
        for name, expected in (("InputCommand", self.document["commands"]), ("InputRuntimeCommand", self.document["runtime_commands"])):
            # Locate branches by their discriminators; assertions never depend on evolving alternative positions.
            # 按判别字段定位分支；断言不依赖会演进的备选项位置。
            actual = set()
            for reference in typing.get_args(getattr(contract, name)):
                declaration = getattr(contract, reference.__forward_arg__)
                actual.update(typing.get_args(typing.get_type_hints(declaration)["type"]))
            self.assertEqual(actual, set(expected))
        for name in self.document["root_responses"]:
            self.assertTrue(typing.is_typeddict(getattr(contract, "OutputRoot" + GENERATOR.identifier(name) + "Response")))
        for name in self.document["runtime_responses"]:
            self.assertTrue(typing.is_typeddict(getattr(contract, "OutputRuntime" + GENERATOR.identifier(name) + "Response")))

    def test_required_optional_null_and_direction_are_preserved(self) -> None:
        """
        Compare every named object against its direction-specific schema and verify null/absence boundaries.
        将每个命名对象与其方向专属 Schema 比较，并验证空值／缺失边界。
        Return nothing; optional input fields must not weaken required output fields.
        无返回值；可省略输入字段不得削弱必需输出字段。
        """
        # Each output root stays independently rooted even when equal definitions share generated declarations.
        # 即使相等定义共享生成声明，各输出根也保持独立。
        roots = [("Input", self.document["request"])] + [
            ("Output", root) for root in [self.document["error_response"], *self.document["root_responses"].values(), *self.document["runtime_responses"].values()]
        ]
        for prefix, root in roots:
            for name, schema in root.get("$defs", {}).items():
                if schema.get("type") == "object" and "properties" in schema:
                    with self.subTest(direction=prefix, name=name):
                        declaration = getattr(contract, prefix + GENERATOR.identifier(name))
                        self.assertEqual(declaration.__required_keys__, set(schema.get("required", [])))
                        self.assertEqual(declaration.__optional_keys__, schema["properties"].keys() - set(schema.get("required", [])))
        self.assertIn("value", contract.OutputOperationSnapshot.__optional_keys__)
        self.assertIn("result", contract.OutputRuntimeOperationWaitResponse.__required_keys__)
        self.assertIs(typing.get_type_hints(contract.OutputRuntimeOperationWaitResponse)["result"], contract.OutputOperationSnapshot)
        self.assertEqual(set(typing.get_args(typing.get_type_hints(contract.InputPluginPoolConfig)["max_uses"])), {int, type(None)})
        # Two synthetic directions exercise schema evolution without mutating the actual upstream copy.
        # 两个合成方向验证 Schema 演进，不修改实际上游副本。
        input_types = GENERATOR.PythonTypes("Input", {})
        output_types = GENERATOR.PythonTypes("Output", {})
        input_types.declare({"type": "object", "properties": {"limit": {"type": "integer"}}}, "InputFutureConfig")
        output_types.declare({"type": "object", "properties": {"limit": {"type": "integer"}}, "required": ["limit"]}, "OutputFutureConfig")
        namespace = {"TypedDict": typing.TypedDict}
        exec("\n".join(input_types.lines + output_types.lines), namespace)
        self.assertIn("limit", namespace["InputFutureConfig"].__optional_keys__)
        self.assertIn("limit", namespace["OutputFutureConfig"].__required_keys__)

    def test_unknown_shapes_and_invalid_root_references_fail_explicitly(self) -> None:
        """
        Reject unknown validation constructs and references satisfied only by a different response root.
        拒绝未知校验构造及只能由其他响应根满足的引用。
        Return nothing; no unsupported shape may silently turn into an arbitrary JSON type.
        无返回值；不支持的形状不得静默变为任意 JSON 类型。
        """
        for schema in ({"type": "string", "pattern": "secret"}, {"allOf": [{"type": "string"}]}, {"$ref": "https://example.invalid/schema"}, {"type": "integer", "format": "new-format"}, {"type": "array"}, False):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                GENERATOR.PythonTypes("Test", {}).declare(schema, "TestShape")
        # EmbeddedError exists in other outputs, which must not repair a broken local error root.
        # EmbeddedError 存在于其他输出中，但不得修补已损坏的局部错误根。
        broken = copy.deepcopy(self.document)
        del broken["error_response"]["$defs"]["EmbeddedError"]
        with self.assertRaisesRegex(ValueError, "independent root"):
            GENERATOR.generate(broken, self.encoded)

    def test_conflicting_definitions_and_generated_names_are_rejected(self) -> None:
        """
        Reject divergent output definitions and normalized-name collisions before producing source files.
        在产出源码文件前拒绝不一致输出定义及规范名称冲突。
        Return nothing; equal names cannot silently acquire another wire meaning.
        无返回值；相同名称不得静默获得另一种线含义。
        """
        broken = copy.deepcopy(self.document)
        broken["error_response"]["$defs"]["EmbeddedError"]["required"] = ["code"]
        with self.assertRaisesRegex(ValueError, "conflicting output definition"):
            GENERATOR.generate(broken, self.encoded)
        with self.assertRaisesRegex(ValueError, "colliding normalized"):
            GENERATOR.PythonTypes("Input", {"some_type": {}, "SomeType": {}})
        # Anonymous names derive from shape, preserving them when alternative ordering changes.
        # 匿名名称从形状派生，在备选项顺序变化时保留。
        left = GENERATOR.PythonTypes("Input", {})
        right = GENERATOR.PythonTypes("Input", {})
        variants = [{"type": "object", "properties": {"value": {}}}, {"type": "object", "properties": {"error": {"type": "string"}}}]
        left.declare({"anyOf": variants}, "InputResult")
        right.declare({"anyOf": list(reversed(variants))}, "InputResult")
        self.assertEqual(set(left.owners), set(right.owners))

    def test_digest_and_duplicate_members_are_verified_before_generation(self) -> None:
        """
        Detect changed line endings, corruption and duplicate JSON keys even when a new digest is supplied.
        即使提供新摘要，也检测换行变化、损坏及重复 JSON 键。
        Return nothing; source bytes remain untouched after rejected verification.
        无返回值；验证拒绝后源字节保持不变。
        """
        with tempfile.TemporaryDirectory() as temporary:
            # The isolated contract uses exactly the documented adjacent digest filename.
            # 隔离契约精确使用文档规定的相邻摘要文件名。
            source = Path(temporary) / "contract.json"
            checksum = source.with_name("contract.sha256")
            source.write_bytes(self.encoded.replace(b"\n", b"\r\n"))
            checksum.write_bytes(self.digest)
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                GENERATOR.verified_contract(source)
            duplicate = b'{"contract_version":1,"contract_version":1}\n'
            source.write_bytes(duplicate)
            checksum.write_bytes((hashlib.sha256(duplicate).hexdigest() + "  contract.json\n").encode("ascii"))
            with self.assertRaisesRegex(ValueError, "duplicate contract member"):
                GENERATOR.verified_contract(source)
            self.assertEqual(source.read_bytes(), duplicate)

    def test_offline_source_copy_checks_without_rewriting_stale_artifacts(self) -> None:
        """
        Run the generator in an isolated source-layout copy with no adjacent core or SDK checkout.
        在独立源码布局副本中运行生成器，不依赖相邻核心或 SDK 检出。
        Return nothing; a stale artifact must fail check mode and keep its original bytes.
        无返回值；过期产物必须使检查模式失败并保留其原始字节。
        """
        with tempfile.TemporaryDirectory() as temporary:
            # Copy only explicit inputs and the standalone generator, proving there is no machine-path dependency.
            # 仅复制显式输入及独立生成器，证明不存在机器路径依赖。
            root = Path(temporary)
            script = root / "scripts/generate_embedded_contract.py"
            script.parent.mkdir()
            script.write_bytes(GENERATOR_PATH.read_bytes())
            source = root / GENERATOR.CONTRACT.relative_to(ROOT)
            source.parent.mkdir(parents=True)
            source.write_bytes(self.encoded)
            source.with_name("contract.sha256").write_bytes(self.digest)
            subprocess.run([sys.executable, str(script)], cwd=root, check=True)
            output = root / GENERATOR.OUTPUT.relative_to(ROOT)
            self.assertEqual(output.read_bytes(), GENERATOR.OUTPUT.read_bytes())
            output.write_bytes(output.read_bytes() + b"# stale\n")
            before = output.read_bytes()
            result = subprocess.run([sys.executable, str(script), "--check"], cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"stale embedded artifact", result.stderr)
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
