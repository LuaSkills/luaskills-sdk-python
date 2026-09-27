"""
Generate Python wire types from the verified, packaged Rust contract without native code or network access.
从经验证且随包分发的 Rust 契约生成 Python 线类型，无需原生代码或网络访问。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import keyword
from pathlib import Path
from typing import Any


# All paths are repository-relative; installed SDKs keep the same contract inside their package.
# 所有路径均相对仓库；安装后的 SDK 在包内保留相同契约。
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "src/luaskills/contracts/embedded/v1/contract.json"
OUTPUT = ROOT / "src/luaskills/embedded_contract.py"
# These keywords are emitted by the pinned Rust generator; unfamiliar semantics must stop generation.
# 这些关键字来自固定的 Rust 生成器；不熟悉的语义必须停止生成。
KEYWORDS = frozenset({
    "$defs", "$schema", "$ref", "title", "description", "default", "type",
    "properties", "required", "additionalProperties", "items", "uniqueItems",
    "oneOf", "anyOf", "const", "format", "minimum",
})
# JSON Schema metadata does not change the Python shape; runtime constraints remain native authority.
# JSON Schema 元数据不改变 Python 形状；运行时约束仍由原生端负责。
ANNOTATIONS = frozenset({"$defs", "$schema", "title", "description", "default"})


def identifier(value: str) -> str:
    """
    Convert one wire name into a PascalCase identifier; reject names that cannot be represented exactly.
    将一个线名称转换为大驼峰标识符；拒绝无法准确表达的名称。
    Return the stable generated name or raise ValueError before publishing files.
    返回稳定生成名称，或在发布文件前抛出 ValueError。
    """
    # Preserve existing Rust acronym spelling while normalizing snake_case command names.
    # 保留 Rust 既有缩写拼写，同时规范化下划线命令名。
    result = "".join(part[:1].upper() + part[1:] for part in value.split("_"))
    if not result.isidentifier() or keyword.iskeyword(result):
        raise ValueError(f"unsupported wire identifier: {value!r}")
    return result


def verified_contract(path: Path) -> tuple[dict[str, Any], bytes, bytes]:
    """
    Read the exact contract and adjacent Rust SHA-256 file at path, rejecting changed bytes or format.
    读取 path 指定的精确契约及相邻 Rust SHA-256 文件，拒绝字节或格式变动。
    Return parsed metadata, original contract bytes and original digest bytes without normalizing them.
    返回解析元数据、原契约字节及原摘要字节，不对其规范化。
    """
    # Check before parsing so line-ending conversion and truncated copies are detectable.
    # 解析前检查，使换行转换和不完整复制可被发现。
    encoded = path.read_bytes()
    digest = path.with_name("contract.sha256").read_bytes()
    expected = (hashlib.sha256(encoded).hexdigest() + "  contract.json\n").encode("ascii")
    if digest != expected:
        raise ValueError(f"embedded contract SHA-256 mismatch: {path}")
    # JSON duplicate members must not silently overwrite an earlier schema or metadata value.
    # JSON 重复成员不得静默覆盖较早的 Schema 或元数据值。
    document = json.loads(encoded, object_pairs_hook=unique_object)
    if document["contract_version"] != 1 or document["generator"]["schema_draft"] != "2020-12":
        raise ValueError("unsupported embedded contract format or JSON Schema draft")
    return document, encoded, digest


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """
    Build one JSON object from decoder pairs and reject duplicate names instead of losing their evidence.
    从解码器键值对构造一个 JSON 对象，拒绝重复名称，避免丢失其证据。
    Return the unique mapping; duplicate members raise ValueError.
    返回唯一映射；重复成员抛出 ValueError。
    """
    # The decoder invokes this for every nested object, including definitions and field schemas.
    # 解码器对每个嵌套对象调用此函数，包含定义和字段 Schema。
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate contract member: {name}")
        result[name] = value
    return result


def verify_references(root: dict[str, Any]) -> None:
    """
    Verify each reference against its own independent root, before definitions from outputs are merged.
    在合并输出定义前，针对各自独立根验证每个引用。
    Return nothing; reject foreign, missing or nested definition namespaces.
    无返回值；拒绝外部、缺失或嵌套定义命名空间。
    """
    # Walk only schema-bearing keywords; defaults and application examples are ordinary JSON values.
    # 仅遍历承载 Schema 的关键字；默认值及应用示例属于普通 JSON 值。
    definitions = root.get("$defs", {})
    pending = [root]
    while pending:
        schema = pending.pop()
        if not isinstance(schema, dict):
            raise ValueError("boolean or non-object schemas are not supported")
        if "$defs" in schema and schema is not root:
            raise ValueError("nested schema definition namespaces are not supported")
        if "$ref" in schema:
            reference = schema["$ref"]
            if not isinstance(reference, str) or not reference.startswith("#/$defs/") or reference[8:] not in definitions:
                raise ValueError(f"reference does not belong to its independent root: {reference!r}")
        for name in ("$defs", "properties"):
            if name in schema:
                pending.extend(schema[name].values())
        for name in ("oneOf", "anyOf"):
            if name in schema:
                pending.extend(schema[name])
        if "items" in schema:
            pending.append(schema["items"])
        if isinstance(schema.get("additionalProperties"), dict):
            pending.append(schema["additionalProperties"])


class PythonTypes:
    """
    Render one direction of JSON Schema into Python 3.10 types while preserving optional versus null fields.
    将一个方向的 JSON Schema 渲染为 Python 3.10 类型，同时区分可省略字段与空值。
    Input definitions must never share a namespace with serialize-direction output definitions.
    输入定义不得与序列化方向的输出定义共享命名空间。
    """

    def __init__(self, prefix: str, definitions: dict[str, Any]) -> None:
        """
        Retain explicit prefix and definitions; initialize deterministic declaration and collision tracking.
        保留显式 prefix 和 definitions；初始化确定性声明及冲突追踪。
        Return a generator that performs no writes and rejects unsupported schema branches.
        返回不执行写入且拒绝不支持 Schema 分支的生成器。
        """
        # Definition names are reserved before visiting fields so forward references remain exact.
        # 遍历字段前预留定义名，使前向引用保持精确。
        self.prefix = prefix
        self.definitions = definitions
        self.names = {name: prefix + identifier(name) for name in definitions}
        if len(set(self.names.values())) != len(self.names):
            raise ValueError("colliding normalized definition names")
        # One generated identifier has exactly one schema owner, including anonymous nested objects.
        # 一个生成标识符恰有一个 Schema 所有者，包含匿名嵌套对象。
        self.owners: dict[str, Any] = {}
        self.lines: list[str] = []

    def validate(self, schema: Any, name: str) -> None:
        """
        Validate supported schema keywords and combinations for name before rendering its Python shape.
        在渲染 name 的 Python 形状前校验支持的 Schema 关键字及组合。
        Return nothing; raise ValueError for unsupported constraints rather than degrading to Any.
        无返回值；对不支持的约束抛出 ValueError，不降级为 Any。
        """
        if not isinstance(schema, dict) or set(schema) - KEYWORDS:
            raise ValueError(f"unsupported schema at {name}: {schema!r}")
        if schema.get("format") not in (None, "uint", "uint32", "uint64"):
            raise ValueError(f"unsupported numeric format at {name}")
        # Siblings of references and alternatives can impose intersections, which need explicit support.
        # 引用或备选项的同级关键字可能施加交集约束，必须明确支持。
        for selector in ("$ref", "oneOf", "anyOf"):
            if selector in schema and set(schema) - ANNOTATIONS - {selector}:
                raise ValueError(f"unsupported combined schema at {name}")
        if "$schema" in schema and schema["$schema"] != "https://json-schema.org/draft/2020-12/schema":
            raise ValueError(f"unsupported schema dialect at {name}")

    def expression(self, schema: dict[str, Any], name: str) -> str:
        """
        Render schema at name into a type expression and retain declarations for nested structured objects.
        将 name 处的 schema 渲染为类型表达式，并保留嵌套结构对象的声明。
        Return explicit JSON types, references or unions; unknown structures fail generation.
        返回显式 JSON 类型、引用或联合；未知结构使生成失败。
        """
        self.validate(schema, name)
        if "$ref" in schema:
            # Only exact local definition references are present in the independently rooted Rust schemas.
            # 独立根 Rust Schema 只包含精确的局部定义引用。
            reference = schema["$ref"]
            if not reference.startswith("#/$defs/") or reference[8:] not in self.names:
                raise ValueError(f"unresolved local reference at {name}: {reference}")
            return repr(self.names[reference[8:]])
        for selector in ("oneOf", "anyOf"):
            if selector in schema:
                # Const-only alternatives form one Literal, making runtime get_args values authoritative too.
                # 仅常量的备选项形成一个 Literal，使运行时 get_args 的值同样具有权威。
                variants = schema[selector]
                if not isinstance(variants, list) or not variants:
                    raise ValueError(f"empty or invalid alternatives at {name}")
                for variant in variants:
                    self.validate(variant, name)
                if all("const" in variant for variant in variants):
                    return "Literal[" + ", ".join(self.literal(variant["const"]) for variant in variants) + "]"
                return "Union[" + ", ".join(
                    self.expression(variant, self.branch_name(name, variant)) for variant in variants
                ) + "]"
        if "const" in schema:
            return "Literal[" + self.literal(schema["const"]) + "]"
        # Rust arbitrary serde_json::Value is explicitly unconstrained; this is not a fallback for unknown schemas.
        # Rust 任意 serde_json::Value 明确不受约束；这不是未知 Schema 的兜底。
        if not (set(schema) - ANNOTATIONS):
            return "JsonValue"
        shape = schema.get("type")
        if isinstance(shape, list):
            if not shape or any(not isinstance(item, str) for item in shape):
                raise ValueError(f"invalid type union at {name}")
            return "Union[" + ", ".join(self.expression({**schema, "type": item}, name + identifier(item)) for item in shape) + "]"
        if shape == "object":
            if "properties" not in schema:
                # Map values retain their actual schema; unconstrained maps hold recursive JSON values.
                # 映射值保留其实际 Schema；无约束映射包含递归 JSON 值。
                additional = schema.get("additionalProperties", True)
                if additional is True:
                    return "Dict[str, JsonValue]"
                if isinstance(additional, dict):
                    return "Dict[str, " + self.expression(additional, name + "Value") + "]"
                if additional is not False:
                    raise ValueError(f"unsupported object map at {name}")
            self.object_type(schema, name)
            return repr(name)
        if shape == "array":
            if "items" not in schema:
                raise ValueError(f"array without items at {name}")
            return "List[" + self.expression(schema["items"], name + "Item") + "]"
        if shape in ("string", "integer", "number", "boolean", "null"):
            return {"string": "str", "integer": "int", "number": "float", "boolean": "bool", "null": "None"}[shape]
        raise ValueError(f"unsupported type at {name}: {schema!r}")

    @staticmethod
    def literal(value: Any) -> str:
        """
        Render one supported scalar JSON constant as a Python Literal member.
        将一个受支持 JSON 标量常量渲染为 Python Literal 成员。
        Return a quoted literal, or raise ValueError for non-literal shapes.
        返回带引号字面量，或对非字面量形状抛出 ValueError。
        """
        if type(value) not in (str, int, bool) and value is not None:
            raise ValueError(f"unsupported literal: {value!r}")
        return repr(value)

    @staticmethod
    def branch_name(parent: str, schema: dict[str, Any]) -> str:
        """
        Derive a stable branch identifier from its wire discriminator or exact anonymous shape.
        从线判别字段或精确匿名形状派生稳定分支标识符。
        Return a name independent of alternative ordering, preserving names when siblings are added.
        返回独立于备选项顺序的名称，添加同级项时保留名称。
        """
        # Tagged core commands provide their own name; untagged shapes use a deterministic content identity.
        # 带标记的核心命令提供自身名称；无标记形状使用确定性内容身份。
        properties = schema.get("properties", {})
        if "type" in properties and "const" in properties["type"]:
            return parent + identifier(properties["type"]["const"])
        encoded = json.dumps(schema, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return parent + "Shape" + hashlib.sha256(encoded).hexdigest()[:12]

    def object_type(self, schema: dict[str, Any], name: str) -> None:
        """
        Emit name as a TypedDict with separate required and optional field groups from schema.
        根据 schema 将 name 输出为 TypedDict，分开必需字段组与可省略字段组。
        Return nothing; generated inheritance supports Python 3.10 without typing_extensions.
        无返回值；生成的继承无需 typing_extensions 即支持 Python 3.10。
        """
        if name in self.owners:
            if self.owners[name] != schema:
                raise ValueError(f"generated type collision: {name}")
            return
        self.owners[name] = schema
        # A structured object plus schema-typed extra properties requires an intersection unsupported by TypedDict.
        # 结构对象与带 Schema 的额外属性需要 TypedDict 不支持的交集。
        if isinstance(schema.get("additionalProperties"), dict):
            raise ValueError(f"typed additional properties alongside fields at {name}")
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        if required - properties.keys():
            raise ValueError(f"required fields without definitions at {name}")
        # Keep member spelling exact; native validation remains responsible for extra fields and value bounds.
        # 保持成员拼写精确；额外字段和值边界继续由原生校验负责。
        fields: dict[str, str] = {}
        for field, child in sorted(properties.items()):
            if not field.isidentifier() or keyword.iskeyword(field):
                raise ValueError(f"unsupported Python field at {name}: {field}")
            fields[field] = self.expression(child, name + identifier(field))
        optional = properties.keys() - required
        if required and optional:
            # The private required base is reserved like any other generated declaration.
            # 私有必需字段基类像其他生成声明一样预留名称。
            base = "_" + name + "Required"
            if base in self.owners:
                raise ValueError(f"generated required-base collision: {base}")
            self.owners[base] = schema
            self.emit_class(base, "TypedDict", True, {field: fields[field] for field in fields if field in required}, schema)
            self.emit_class(name, base, False, {field: fields[field] for field in fields if field in optional}, schema)
        else:
            self.emit_class(name, "TypedDict", not optional, fields, schema)

    def emit_class(self, name: str, base: str, total: bool, fields: dict[str, str], schema: dict[str, Any]) -> None:
        """
        Append a documented TypedDict with name, base, total flag, fields and original schema descriptions.
        追加具有文档的 TypedDict，包含 name、base、total 标记、fields 及原始 schema 说明。
        Return nothing; declarations are kept in deterministic dependency-first order.
        无返回值；声明以确定性的依赖优先顺序保留。
        """
        self.lines.extend([
            f"class {name}({base}, total={total}):",
            '    """',
            f"    Wire fields for {name}; native validation enforces semantic constraints.",
            f"    {name} 的线字段；原生校验负责语义约束。",
        ])
        # Preserve upstream bilingual field semantics instead of maintaining a second SDK explanation.
        # 保留上游双语字段语义，不另行维护一套 SDK 说明。
        for line in schema.get("description", "").splitlines():
            self.lines.append("    " + line.replace("\\", "\\\\").replace('"', '\\"'))
        self.lines.append('    """')
        for field, expression in fields.items():
            for line in schema["properties"][field].get("description", "").splitlines():
                self.lines.append("    # " + line)
            self.lines.extend([
                f"    # Exact wire member {field}; {'required' if total else 'omittable'} independently of nullability.",
                f"    # 精确线成员 {field}；{'必需' if total else '可省略'}与是否可为空值相互独立。",
                f"    {field}: {expression}",
            ])
        self.lines.extend(["", ""])


    def declare(self, schema: dict[str, Any], name: str) -> None:
        """
        Render a top-level named schema as its object declaration or explicit alias.
        将顶层命名 Schema 渲染为其对象声明或显式别名。
        Return nothing and reject identifiers already owned by a different declaration.
        无返回值，并拒绝已由不同声明拥有的标识符。
        """
        if name in self.owners:
            raise ValueError(f"duplicate top-level generated name: {name}")
        # Object schemas register their own name, while primitive and union definitions need an alias.
        # 对象 Schema 注册自身名称；原始及联合定义需要别名。
        expression = self.expression(schema, name)
        if name not in self.owners:
            self.owners[name] = schema
            self.lines.extend([
                f"# Exact wire shape of {name}, derived from the packaged core schema.",
                f"# 从包内核心 Schema 派生的 {name} 精确线形状。",
                f"{name}: TypeAlias = {expression}", "", "",
            ])


def generate(document: dict[str, Any], encoded: bytes) -> bytes:
    """
    Generate all request/response types and metadata from document and its original encoded bytes.
    从 document 及其原始 encoded 字节生成所有请求／响应类型与元数据。
    Return reproducible UTF-8 Python source, rejecting missing commands, conflicts or unsupported schemas.
    返回可复现 UTF-8 Python 源码，拒绝缺失命令、冲突或不支持的 Schema。
    """
    # Root routing coverage is part of the generated artifact, not an SDK-maintained command list.
    # 根路由覆盖属于生成产物，而非 SDK 维护的命令列表。
    if set(document["root_responses"]) != set(document["commands"]) - {"runtime"}:
        raise ValueError("root response coverage differs from the core command list")
    if set(document["runtime_responses"]) != set(document["runtime_commands"]):
        raise ValueError("runtime response coverage differs from the core command list")
    # Identically named output definitions are merged only after structural equality is proven.
    # 同名输出定义仅在已证明结构相等后合并。
    output_roots = {"OutputErrorResponse": document["error_response"]}
    output_roots.update({"OutputRoot" + identifier(name) + "Response": schema for name, schema in document["root_responses"].items()})
    output_roots.update({"OutputRuntime" + identifier(name) + "Response": schema for name, schema in document["runtime_responses"].items()})
    for root in [document["request"], *output_roots.values()]:
        verify_references(root)
    definitions: dict[str, Any] = {}
    for root in output_roots.values():
        for name, schema in root.get("$defs", {}).items():
            if name in definitions and definitions[name] != schema:
                raise ValueError(f"conflicting output definition: {name}")
            definitions[name] = schema
    # Input/output separation preserves serde default/skip rules even for equally named Rust types.
    # 输入／输出分离保留 serde 默认／省略规则，即使 Rust 类型名称相同。
    inputs = PythonTypes("Input", document["request"].get("$defs", {}))
    outputs = PythonTypes("Output", definitions)
    for generator in (inputs, outputs):
        for name, schema in sorted(generator.definitions.items()):
            generator.declare(schema, generator.names[name])
    inputs.declare(document["request"], "InputRequest")
    for name, schema in sorted(output_roots.items()):
        outputs.declare(schema, name)
    # Numeric native codes retain their exact signed C ABI values, distinct from structured business errors.
    # 数字原生状态码保留其精确有符号 C ABI 值，独立于结构化业务错误。
    statuses = document["native_status"]
    if not statuses or any(type(value) is not int for value in statuses.values()) or len(set(statuses.values())) != len(statuses) or len({name.upper() for name in statuses}) != len(statuses):
        raise ValueError("invalid or duplicated native status codes")
    lines = [
        '"""',
        "Generated embedded wire shapes; run scripts/generate_embedded_contract.py to update.",
        "生成的嵌入式线形状；运行 scripts/generate_embedded_contract.py 更新。",
        "Types describe JSON shape; core validation owns bounds, authorization and lifecycle semantics.",
        "类型描述 JSON 形状；核心校验负责边界、授权及生命周期语义。",
        '"""', "", "from __future__ import annotations", "",
        "from enum import IntEnum",
        "from typing import Dict, List, Literal, TypeAlias, TypedDict, Union", "",
        "# Recursive JSON values preserve exact integers within native bounds and explicit null separately from absence.",
        "# 递归 JSON 值保留原生边界内的精确整数，并将显式空值与缺失分开。",
        'JsonValue: TypeAlias = Union[None, bool, int, float, str, List["JsonValue"], Dict[str, "JsonValue"]]', "",
    ]
    for name, value in {
        "EMBEDDED_PROTOCOL_VERSION": document["protocol_version"],
        "EMBEDDED_CONTRACT_VERSION": document["contract_version"],
        "EMBEDDED_CORE_VERSION": document["core_version"],
        "EMBEDDED_CONTRACT_SHA256": hashlib.sha256(encoded).hexdigest(),
        "EMBEDDED_ROOT_COMMANDS": tuple(document["commands"]),
        "EMBEDDED_RUNTIME_COMMANDS": tuple(document["runtime_commands"]),
    }.items():
        lines.extend([f"# Generated contract metadata: {name}.", f"# 生成的契约元数据：{name}。", f"{name} = {value!r}", ""])
    lines.extend(["", "class EmbeddedNativeStatus(IntEnum):", '    """',
                  "    Exact native transport return codes from the Rust contract.",
                  "    来自 Rust 契约的精确原生传输返回码。", '    """'])
    for name, value in sorted(statuses.items(), key=lambda pair: pair[1]):
        if not name.isidentifier() or keyword.iskeyword(name):
            raise ValueError(f"invalid native status name: {name}")
        lines.extend([f"    # Native status {name}.", f"    # 原生状态 {name}。", f"    {name.upper()} = {value}"])
    lines.extend(["", "", *inputs.lines, *outputs.lines])
    # Export only generated public declarations and metadata, keeping typing imports private to the module.
    # 仅导出生成的公开声明及元数据，使 typing 导入留在模块内部。
    names = sorted([name for name in inputs.owners | outputs.owners if not name.startswith("_")])
    lines.extend(["# Public generated type names; metadata remains directly importable by name.",
                  "# 公开生成类型名；元数据仍可按名称直接导入。",
                  "__all__ = " + repr(["JsonValue", "EmbeddedNativeStatus", *names]), ""])
    return "\n".join(lines).encode("utf-8")


def main() -> None:
    """
    Generate/check from the packaged copy, optionally synchronizing an explicitly supplied Rust contract file.
    从包内副本生成／检查，可选择同步显式指定的 Rust 契约文件。
    Return nothing; check mode never writes and generation validates all outputs before the first write.
    无返回值；检查模式不写入，生成在首次写入前校验全部输出。
    """
    # Explicit source selection is deliberate synchronization, never sibling-directory discovery or fallback.
    # 显式源码选择是主动同步，绝不探测相邻目录或兜底。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--source", type=Path, help="Exact upstream contract.json to synchronize or compare")
    args = parser.parse_args()
    document, encoded, digest = verified_contract(args.source if args.source is not None else CONTRACT)
    generated = generate(document, encoded)
    # Ensure Python syntax is valid before copying source metadata or generated code.
    # 复制源元数据或生成代码前，确保 Python 语法有效。
    compile(generated, str(OUTPUT), "exec")
    artifacts = {CONTRACT: encoded, CONTRACT.with_name("contract.sha256"): digest, OUTPUT: generated}
    for path, content in artifacts.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                raise SystemExit(f"stale embedded artifact: {path}; run scripts/generate_embedded_contract.py")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


if __name__ == "__main__":
    main()
