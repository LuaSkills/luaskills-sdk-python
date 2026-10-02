"""Freeze, test and verify the exact Python SDK publication bytes.
冻结、测试及验证 Python SDK 精确发布字节。

Production requires an account-bound PyPI Trusted Publisher for the production environment.
生产要求在 PyPI 账号绑定 production environment 对应的 Trusted Publisher。
This repository cannot establish or verify that account configuration by running local gates.
本仓库运行本地门禁不能建立或验证该账号配置。

Bind PyPI luaskills-sdk to LuaSkills/luaskills-sdk-python, sdk-release.yml and production.
将 PyPI luaskills-sdk 绑定至 LuaSkills/luaskills-sdk-python、sdk-release.yml 及 production。
Publisher account ownership and environment configuration remain unverified deployment prerequisites.
发布者账号归属及 environment 配置仍是未经验证的部署前置条件。
Commit this workflow to the default branch before dispatching its identical full source/definition SHA.
调度相同完整源码及定义 SHA 前，先将此工作流提交到默认分支。
Artifact-only performs acceptance; the existing native distribution CLI also works before public releases.
仅产物模式执行验收；既有原生分发 CLI 也可在公共发布前使用。
Core GitHub release and actual Cargo registry consumption precede this independent SDK version.
核心 GitHub 发布及实际 Cargo registry 消费先于此独立 SDK 版本。
Python has no TypeScript serial prerequisite; downstream SDKs authenticate formal-proof accepted.json.
Python 没有 TypeScript 串行前置要求；下游 SDK 认证 formal-proof 的 accepted.json。
"""

from __future__ import annotations

import argparse
import ast
from email.parser import BytesParser
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import urllib.error
import venv
import zipfile

# Evidence version belongs to this SDK workflow, independently of the core manifest schema.
# 凭证版本属于此 SDK 工作流，独立于核心清单结构版本。
SCHEMA = 1
# Public SDK publication ownership is fixed, independently of the core repository.
# 公共 SDK 发布归属固定，独立于核心仓库。
SDK_REPOSITORY = "LuaSkills/luaskills-sdk-python"
# Candidate and completion signatures originate from this single frozen publication definition.
# 候选及完成签名来自此唯一冻结发布定义。
SDK_WORKFLOW = ".github/workflows/sdk-release.yml"
# The original candidate's official signature is retained verbatim across every completion attempt.
# 原候选的官方签名在每个完成轮次中逐字节保留。
CANDIDATE_ATTESTATION = "candidate-attestation.jsonl"
# Schema-two stages are dispatched only by this CLI; the coordinator owns their SDK-specific behavior.
# 结构二阶段仅由此 CLI 分发；协调器拥有其 SDK 专属行为。
PUBLICATION_COMMANDS = ("candidate-prepare", "candidate-seal", "candidate-resolve", "publish-candidate",
                        "completion-prepare", "publish-completion", "formal-proof")
# Native jobs run on both supported interpreter endpoints derived from project metadata.
# 原生任务运行于从项目元数据派生的两个受支持解释器端点。
ROLES = ("minimum", "current")
# CI-only tool versions support the minimum Python; SDK runtime dependencies are unchanged.
# 仅 CI 工具版本支持最低 Python；SDK 运行时依赖未变。
TOOL_REQUIREMENTS = ("build==1.5.0", "twine==6.2.0", "setuptools==84.0.0", "wheel==0.48.0", "packaging==26.2")


def tool_requirements(args):
    """Print the sole pinned CI tool requirements for args' interpreter setup; return nothing.
    打印 args 解释器准备所需的唯一固定 CI 工具依赖；无返回值。
    """
    print(" ".join(TOOL_REQUIREMENTS))


def require(condition, message):
    """Require condition or raise the explicit message; return nothing on acceptance.
    要求 condition 成立，否则抛出明确 message；验收通过时无返回值。
    """
    if not condition:
        raise ValueError(message)


def sha256(path):
    """Hash the exact regular file at path and return lowercase SHA-256; missing input fails.
    对 path 精确普通文件求摘要并返回小写 SHA-256；缺少输入时失败。
    """
    require(Path(path).is_file() and not Path(path).is_symlink(), "Evidence must be a regular file")
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    """Read path as strict JSON and return its value; duplicate object keys fail.
    将 path 读取为严格 JSON 并返回其值；重复对象键失败。
    """
    def pairs(entries):
        """Decode entries into one object rejecting duplicates; return that object.
        将 entries 解码为一个对象并拒绝重复；返回该对象。
        """
        result = {}
        for key, value in entries:
            require(key not in result, "Duplicate release evidence key")
            result[key] = value
        return result
    def constant(value):
        """Reject nonstandard JSON value; never return a nonfinite constant.
        拒绝非标准 JSON value；绝不返回非有限常量。
        """
        raise ValueError("Nonstandard release evidence JSON constant: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def write_json(path, value):
    """Exclusively write value to path as deterministic JSON; return nothing, never overwrite evidence.
    将 value 独占写入 path，采用确定性 JSON；无返回值，绝不覆盖凭证。
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def run(command, cwd=None, env=None):
    """Execute command directly in cwd with env; return stdout only after its real zero exit.
    在 cwd 中以 env 直接执行 command；仅真实零退出后返回 stdout。
    """
    try:
        return subprocess.run(command, cwd=cwd, env=env, check=True, text=True,
                              encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=1800).stdout
    except subprocess.CalledProcessError as error:
        # Preserve the actual failed tool diagnostics in Actions output before propagating failure.
        # 传播失败前，在 Actions 输出保留实际失败工具诊断。
        print(error.stdout)
        raise


def core_module(root, commit):
    """Load the prerequisite authority from root at exact commit; return that single module.
    从 root 的精确 commit 加载前置条件权威；返回此唯一模块。
    """
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Core commit must be a full lowercase SHA")
    require(run(["git", "rev-parse", "HEAD"], root).strip() == commit, "Core checkout SHA mismatch")
    require(not run(["git", "status", "--porcelain", "--untracked-files=no"], root).strip(), "Core checkout is modified")
    for name in ("candidate.py", "sdk_prerequisites.py"):
        relative = "scripts/release/" + name
        require(run(["git", "show", commit + ":" + relative], root) == (Path(root) / relative).read_text(encoding="utf-8"),
                "Core prerequisite authority differs from its frozen Git tree")
    # Core owns platform, archive, public registry consumption and artifact path rebasing.
    # 核心拥有平台、归档、公共 registry 消费及产物路径重定位。
    sys.path.insert(0, str(Path(root) / "scripts/release"))
    import sdk_prerequisites
    require(Path(sdk_prerequisites.__file__).resolve() == (Path(root) / "scripts/release/sdk_prerequisites.py").resolve(),
            "Core prerequisite import escaped the frozen checkout")
    return sdk_prerequisites


def recovery_module(root, commit):
    """Load the exact core-owned recovery authority from root/commit; return its verified module.
    从 root/commit 加载精确核心所有的恢复权威；返回已核实模块。
    """
    core_module(root, commit)
    relative = "scripts/release/sdk_recovery.py"
    require(run(["git", "show", commit + ":" + relative], root) == (Path(root) / relative).read_text(encoding="utf-8"),
            "Core recovery authority differs from its frozen Git tree")
    import sdk_recovery
    require(Path(sdk_recovery.__file__).resolve() == (Path(root) / relative).resolve(),
            "Core recovery import escaped the frozen checkout")
    return sdk_recovery


def publication_coordinator():
    """Load this CLI's adjacent SDK-only coordinator with existing gate functions; return its instance.
    加载此 CLI 相邻 SDK 专属协调器及已有门禁函数；返回实例。
    """
    from types import SimpleNamespace
    path = Path(__file__).with_name("sdk_publication.py")
    specification = importlib.util.spec_from_file_location("luaskills_sdk_publication", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.Publication(SimpleNamespace(**globals()))


def default_asset(source):
    """Read the authoritative DEFAULT_LUASKILLS_VERSION literal from source bytes; return its tag.
    从 source 字节读取权威 DEFAULT_LUASKILLS_VERSION 字面量；返回其标签。
    """
    values = [ast.literal_eval(node.value) for node in ast.parse(source).body
              if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "DEFAULT_LUASKILLS_VERSION" for target in node.targets)]
    require(len(values) == 1 and isinstance(values[0], str), "Default core asset authority is ambiguous")
    return values[0]


def source_metadata(root):
    """Read root's project version, supported Python endpoints and core asset tag; return metadata.
    读取 root 的项目版本、受支持 Python 端点及核心资产标签；返回元数据。
    """
    import tomllib
    from packaging.specifiers import SpecifierSet
    # Project metadata is the sole SDK version source; VERSION is only a checked mirror.
    # 项目元数据是 SDK 版本唯一来源；VERSION 仅是被校验的镜像。
    project = tomllib.loads((Path(root) / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    require(re.fullmatch(r"\d+\.\d+\.\d+", version) is not None, "Only final SDK versions may publish")
    require((Path(root) / "VERSION").read_text(encoding="utf-8").strip() == version, "VERSION mirror mismatch")
    versions = sorted({tuple(map(int, match.groups())) for item in project["classifiers"]
                       if (match := re.fullmatch(r"Programming Language :: Python :: (\d+)\.(\d+)", item))})
    require(len(versions) >= 2, "Supported Python endpoints are missing")
    require(all(".".join(map(str, value)) in SpecifierSet(project["requires-python"]) for value in versions),
            "Python classifiers contradict requires-python")
    return {"name": project["name"], "sdk_version": version,
            "python": dict(zip(ROLES, (".".join(map(str, versions[0])), ".".join(map(str, versions[-1]))))),
            "default_core_tag": default_asset((Path(root) / "src/luaskills/runtime_assets.py").read_bytes())}


def runner_for(os_name, architecture):
    """Map the core-declared OS and architecture to a hosted runner; return label or fail.
    将核心声明的操作系统及架构映射到托管 runner；返回标签或失败。
    """
    # These are runner capabilities, not a second platform or archive membership list.
    # 此处是 runner 能力映射，不是第二份平台或归档成员列表。
    runners = {("linux", "x86_64"): "ubuntu-24.04", ("linux", "aarch64"): "ubuntu-24.04-arm",
               ("macos", "x86_64"): "macos-15-intel", ("macos", "aarch64"): "macos-15",
               ("windows", "x86_64"): "windows-2025"}
    require((os_name, architecture) in runners, "Core platform has no declared hosted runner")
    return runners[os_name, architecture]


def bootstrap(args):
    """Read args' frozen public core proof and emit its exact hosted toolchain/platform; return inputs.
    读取 args 冻结核心的公共证明并输出精确宿主工具链及平台；返回输入。
    """
    authority = core_module(args.core_root, args.core_commit)
    # Hosted consumer membership is derived from the sole core platform declaration and existing runner mapping.
    # 宿主消费者成员由唯一核心平台声明及已有 runner 映射派生。
    platforms = [platform for platform, record in authority.candidate.PLATFORMS.items()
                 if runner_for(record[1], record[2]) == "ubuntu-24.04"]
    require(len(platforms) == 1, "Core toolchain consumer runner has ambiguous platform")
    require(not args.output.exists(), "Toolchain bootstrap output must be new")
    authority.run_gate(args.core_tag, args.core_commit, args.output / "core", phase="github-only")
    inputs = authority.toolchain_inputs(args.output / "core/prerequisites.json", platforms[0])
    require(inputs["phase"] == "github-only" and inputs["complete"] is False
            and inputs["core_tag"] == args.core_tag and inputs["core_commit"] == args.core_commit
            and inputs["platform"] == platforms[0]
            and re.fullmatch(r"\d+\.\d+\.\d+", inputs["toolchain"]) is not None,
            "Public core toolchain inputs have a different identity")
    write_json(args.output / "toolchain.json", inputs)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write("toolchain=" + inputs["toolchain"] + "\n")
            output.write("consumer_platform=" + platforms[0] + "\n")
    return inputs


def publication_preflight(authority, source_sha, version, artifacts=None):
    """Check current SDK tag and exact PyPI version before mutation; artifacts bind existing package bytes.
    在修改前检查当前 SDK 标签及精确 PyPI 版本；artifacts 绑定现有包字节。
    """
    http = authority.Http()
    repository = release_get(http, "")
    require(repository["full_name"] == SDK_REPOSITORY and repository["permissions"]["push"] is True,
            "The issuing GITHUB_TOKEN lacks the fixed SDK repository write permission")
    # Only HTTP 404 establishes absence; network errors and authorization failures never do.
    # 仅 HTTP 404 建立不存在事实；网络及授权失败绝不具有此含义。
    opener = urllib.request.build_opener(authority.SafeRedirect())
    headers = {"Accept": "application/json", "Authorization": "Bearer " + os.environ["GH_TOKEN"]}
    tag_url = f"https://api.github.com/repos/{SDK_REPOSITORY}/git/ref/tags/v{version}"
    try:
        with opener.open(urllib.request.Request(tag_url, headers=headers), timeout=60) as response:
            response.read()
    except urllib.error.HTTPError as error:
        error.close()
        require(error.code == 404, "Cannot verify SDK tag publication preflight")
    else:
        # Nested annotated-tag failures are unknown identity, not absence of the original exact ref.
        # 嵌套注解标签失败表示未知身份，不表示原精确引用不存在。
        sdk_tag(http, "v" + version, source_sha)
    # Exact PyPI recovery is checked only with the tested artifact manifest in prepare_publish.
    # 仅在 prepare_publish 持有已测产物清单时检查精确 PyPI 恢复。
    if artifacts is not None:
        # Authenticated pagination includes drafts, which the published-by-tag endpoint cannot expose.
        # 已认证分页包含草稿，正式标签端点无法暴露它们。
        existing_release = find_release(authority, http, "v" + version)
        if existing_release is None:
            return
        existing = {asset["name"]: hashlib.sha256(http.get(asset["url"], binary=True)[0]).hexdigest()
                    for asset in release_assets(http, existing_release["id"]).values()}
        immutable_assets(existing, {record["filename"]: record["sha256"] for record in artifacts.values()})


def freeze(args):
    """Freeze args' exact workflow/source/core identities and run public prerequisites; return plan.
    冻结 args 的精确工作流、源码及核心身份并执行公共前置验证；返回计划。
    """
    root = args.root.resolve()
    require(re.fullmatch(r"[0-9a-f]{40}", args.source_sha) is not None, "SDK source SHA must be full lowercase")
    require(os.environ["GITHUB_SHA"] == args.source_sha == os.environ["GITHUB_WORKFLOW_SHA"],
            "SDK source, event and workflow definition SHA must be identical")
    require(os.environ["GITHUB_REF"] == "refs/heads/" + args.default_branch,
            "Release workflow must execute its fixed definition on the default branch")
    require(os.environ["GITHUB_REPOSITORY"] == SDK_REPOSITORY,
            "Release must originate from the fixed SDK repository")
    require(run(["git", "rev-parse", "HEAD"], root).strip() == args.source_sha, "SDK checkout SHA mismatch")
    require(not run(["git", "status", "--porcelain"], root).strip(), "SDK source must be clean before freezing")
    metadata = source_metadata(root)
    require(metadata["default_core_tag"] == args.core_tag, "SDK default asset tag differs from explicit independent core tag")
    authority = core_module(args.core_root, args.core_commit)
    if args.mode == "publish":
        publication_preflight(authority, args.source_sha, metadata["sdk_version"])
    evidence = authority.run_gate(args.core_tag, args.core_commit, args.output / "core", phase="complete")
    # Platform membership and build OS/architecture come from the frozen core authority alone.
    # 平台成员及构建操作系统、架构仅来自冻结核心权威。
    require(set(evidence["sdk_inputs"]) == set(authority.candidate.PLATFORMS), "Core prerequisite platform set mismatch")
    matrix = [{"platform": platform, "python_role": role, "python": metadata["python"][role],
               "runner": runner_for(record[1], record[2])}
              for platform, record in authority.candidate.PLATFORMS.items() for role in ROLES]
    plan = {"schema_version": SCHEMA, **metadata, "source_sha": args.source_sha, "mode": args.mode,
            "core_tag": evidence["core_tag"], "core_commit": evidence["core_commit"],
            "core_version": evidence["core_version"], "platforms": list(evidence["sdk_inputs"]),
            "matrix": matrix, "prerequisites_sha256": sha256(args.output / "core/prerequisites.json")}
    consumer_platforms = {row["platform"] for row in matrix if row["runner"] == "ubuntu-24.04"}
    require(len(consumer_platforms) == 1, "Published PyPI consumer runner has ambiguous core platform")
    plan["consumer_platform"] = consumer_platforms.pop()
    write_json(args.output / "plan.json", plan)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")) + "\n")
            output.write("consumer_platform=" + plan["consumer_platform"] + "\n")
    return plan


def verify_artifacts(plan, directory, manifest=None):
    """Validate directory's only wheel/sdist against plan and optional manifest; return exact digests.
    对照 plan 及可选 manifest 校验 directory 中唯一 wheel/sdist；返回精确摘要。
    """
    directory = Path(directory)
    wheels, sources = list(directory.glob("*.whl")), list(directory.glob("*.tar.gz"))
    require(len(wheels) == len(sources) == 1, "Build must contain exactly one wheel and one sdist")
    artifacts = {}
    for path, kind in ((wheels[0], "wheel"), (sources[0], "sdist")):
        if kind == "wheel":
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                require(len(names) == len(set(names)), "Duplicate wheel members")
                metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
                require(len(metadata_names) == 1, "Wheel metadata identity is ambiguous")
                metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
                asset_tag = default_asset(archive.read("luaskills/runtime_assets.py"))
        else:
            with tarfile.open(path, "r:gz") as archive:
                members = archive.getmembers()
                require(len(members) == len({member.name for member in members}), "Duplicate sdist members")
                records = [member for member in members if member.name.count("/") == 1 and member.name.endswith("/PKG-INFO")]
                require(len(records) == 1 and records[0].isfile(), "Sdist metadata identity is ambiguous")
                metadata = BytesParser().parsebytes(archive.extractfile(records[0]).read())
                assets = [member for member in members if member.name.endswith("/src/luaskills/runtime_assets.py")]
                require(len(assets) == 1 and assets[0].isfile(), "Sdist default asset identity is ambiguous")
                asset_tag = default_asset(archive.extractfile(assets[0]).read())
        require(metadata["Name"] == plan["name"] and metadata["Version"] == plan["sdk_version"], "Packaged SDK identity mismatch")
        require(asset_tag == plan["core_tag"], "Packaged default core asset mismatch")
        artifacts[kind] = {"filename": path.name, "sha256": sha256(path), "size": path.stat().st_size}
    if manifest is not None:
        require(manifest == artifacts, "Tested package bytes changed")
    return artifacts


def build(args):
    """Build args' frozen checkout once and strictly check both distributions; return their manifest.
    对 args 的冻结检出仅构建一次并严格检查两种分发包；返回产物清单。
    """
    plan = read_json(args.plan)
    require(run(["git", "rev-parse", "HEAD"], args.root).strip() == plan["source_sha"], "Build checkout SHA mismatch")
    require(not run(["git", "status", "--porcelain"], args.root).strip(), "Build source is modified")
    require(importlib.util.find_spec("twine") is not None, "Formal release requires twine; missing tool cannot pass")
    require(not args.output.exists(), "Build output must be new")
    output = run([sys.executable, "-m", "build", "--no-isolation", "--outdir", str(args.output.resolve())], args.root)
    print(output)
    artifacts = verify_artifacts(plan, args.output)
    print(run([sys.executable, "-m", "twine", "check", "--strict", *[str(args.output / record["filename"]) for record in artifacts.values()]]))
    write_json(args.output / "artifacts.json", artifacts)
    return artifacts


def native_accept(plan, artifacts, directory, inputs, log):
    """Run mandatory strict metadata and installed native gates for inputs; retain real output in log.
    对 inputs 执行强制严格元数据及已安装原生门禁；在 log 保留真实输出。
    """
    require(importlib.util.find_spec("twine") is not None, "Formal native gate requires twine")
    directory = Path(directory).resolve()
    verify_artifacts(plan, directory, artifacts)
    require(sha256(inputs["library"]) == inputs["library_sha256"] and
            sha256(inputs["description"]) == inputs["description_sha256"], "Resolved core input bytes changed")
    commands = [[sys.executable, "-m", "twine", "check", "--strict", *[str(directory / record["filename"]) for record in artifacts.values()]],
                [sys.executable, "-X", "utf8", str(Path(__file__).parents[1] / "verify_embedded_native_distribution.py"),
                 "--wheel", str(directory / artifacts["wheel"]["filename"]), "--sdist", str(directory / artifacts["sdist"]["filename"]),
                 "--library", inputs["library"], "--library-sha256", inputs["library_sha256"], "--description", inputs["description"]]]
    # Gate performs isolated wheel and sdist installation, sync/async callbacks and ten startup regressions.
    # 门禁执行隔离 wheel 及 sdist 安装、同步异步回调及十项启动回归。
    with Path(log).open("x", encoding="utf-8") as stream:
        try:
            for command in commands:
                output = run(command, env=dict(os.environ, LUASKILLS_LIB=inputs["library"]))
                stream.write(output)
                print(output)
            # Real Lua/codec regressions also import each distribution from its own environment.
            # 真实 Lua 及编解码回归也从各分发包独立环境导入。
            output = installed_regressions(directory, artifacts, inputs)
            stream.write(output)
            print(output)
        except subprocess.CalledProcessError as error:
            stream.write(error.stdout)
            raise


def installed_regressions(directory, artifacts, inputs):
    """Install directory's wheel and rebuilt sdist independently; return no-skip native/codec test output.
    独立安装 directory 的 wheel 及重建 sdist；返回无跳过的原生编解码测试输出。
    """
    probe = """
import pathlib, sys, unittest, luaskills
if not pathlib.Path(luaskills.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):
    raise RuntimeError('SDK import escaped installed consumer')
startup = unittest.defaultTestLoader.discover(sys.argv[1], pattern='test_embedded_example_native_startup.py')
if startup.countTestCases() < 10:
    raise RuntimeError('The mandatory actual startup regression suite is incomplete')
suite = unittest.TestSuite()
for pattern in ('test_embedded_native_e2e.py', 'test_embedded_json_vectors.py'):
    suite.addTests(unittest.defaultTestLoader.discover(sys.argv[1], pattern=pattern))
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful() or bool(result.skipped) or result.testsRun < 10)
"""
    output = ""
    with tempfile.TemporaryDirectory(prefix="luaskills-formal-native-") as temporary:
        root = Path(temporary)
        built = root / "sdist-wheel"
        built.mkdir()
        output += run([sys.executable, "-m", "pip", "wheel", "--no-cache-dir", "--no-index", "--no-deps", "--no-build-isolation",
                       "--wheel-dir", str(built), str(directory / artifacts["sdist"]["filename"])], root)
        rebuilt = list(built.glob("*.whl"))
        require(len(rebuilt) == 1, "Sdist consumer must build exactly one wheel")
        for role, artifact in (("wheel", directory / artifacts["wheel"]["filename"]), ("sdist", rebuilt[0])):
            environment = root / role
            venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
            python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            output += run([str(python), "-I", "-m", "pip", "install", "--no-cache-dir", "--no-index", "--no-deps", str(artifact)], environment)
            output += run([str(python), "-I", "-X", "utf8", "-c", probe, str(Path(__file__).resolve().parents[2] / "tests")],
                          environment, dict(os.environ, LUASKILLS_LIB=inputs["library"]))
    return output


def validate(args):
    """Validate args' resolved inputs and frozen artifacts on the actual interpreter; return report.
    在实际解释器上校验 args 的已解析输入及冻结产物；返回报告。
    """
    plan, artifacts, inputs = read_json(args.plan), read_json(args.artifacts / "artifacts.json"), read_json(args.inputs)
    require(args.platform in plan["platforms"] and inputs["platform"] == args.platform, "Native platform identity mismatch")
    require(inputs["source_commit"] == plan["core_commit"] and inputs["core_version"] == plan["core_version"], "Native core identity mismatch")
    require(f"{sys.version_info.major}.{sys.version_info.minor}" == plan["python"][args.python_role], "Native interpreter endpoint mismatch")
    native_accept(plan, artifacts, args.artifacts, inputs, args.output.with_suffix(".log"))
    report = {"schema_version": SCHEMA, "source_sha": plan["source_sha"], "sdk_version": plan["sdk_version"],
              "core_tag": plan["core_tag"], "core_commit": plan["core_commit"], "core_version": plan["core_version"],
              "platform": args.platform, "python_role": args.python_role, "python": plan["python"][args.python_role],
              "artifacts": artifacts, "inputs": {key: inputs[key] for key in ("library_sha256", "description_sha256", "archive_sha256", "build")},
              "accepted": True, "log_sha256": sha256(args.output.with_suffix(".log"))}
    write_json(args.output, report)
    return report


def aggregate_reports(plan, artifacts, reports, prerequisites):
    """Require every exact platform/interpreter report and prerequisite binding; return aggregate.
    要求每份精确平台解释器报告及前置凭证绑定；返回聚合结果。
    """
    require(prerequisites["complete"] is True and prerequisites["phase"] == "complete", "Complete core publication prerequisite is mandatory")
    require(prerequisites["core_tag"] == plan["core_tag"] and prerequisites["core_commit"] == plan["core_commit"]
            and prerequisites["core_version"] == plan["core_version"] and set(prerequisites["sdk_inputs"]) == set(plan["platforms"]),
            "Core prerequisite identity mismatch")
    expected = {(platform, role) for platform in plan["platforms"] for role in ROLES}
    observed = set()
    for report in reports:
        key = (report["platform"], report["python_role"])
        require(key in expected and key not in observed, "Unexpected or duplicate native report")
        observed.add(key)
        require(report["schema_version"] == SCHEMA and report["accepted"] is True, "Native acceptance missing")
        require(all(report[field] == plan[field] for field in ("source_sha", "sdk_version", "core_tag", "core_commit", "core_version")), "Native report identity mismatch")
        require(report["python"] == plan["python"][key[1]] and report["artifacts"] == artifacts, "Native report interpreter or package bytes mismatch")
        inputs = prerequisites["sdk_inputs"][key[0]]
        require(report["inputs"] == {field: inputs[field] for field in ("library_sha256", "description_sha256", "archive_sha256", "build")}, "Native report frozen core bytes mismatch")
    require(observed == expected, "Missing mandatory platform/interpreter native report")
    # Canonical platform/role order lets signed evidence survive download and archive enumeration changes.
    # 按平台及解释器角色规范排序，使已签名凭证不受下载及归档遍历顺序变化影响。
    return {"schema_version": SCHEMA, "plan": plan, "artifacts": artifacts,
            "reports": sorted(reports, key=lambda report: (report["platform"], report["python_role"])), "accepted": True}


def aggregate(args):
    """Load args' actual artifacts and report logs and write a complete aggregate; return evidence.
    加载 args 的实际产物及报告日志并写入完整聚合结果；返回凭证。
    """
    plan = read_json(args.plan)
    require(sha256(args.prerequisites) == plan["prerequisites_sha256"], "Original prerequisites bytes changed")
    artifacts = verify_artifacts(plan, args.artifacts, read_json(args.artifacts / "artifacts.json"))
    paths = list(args.reports.rglob("report.json"))
    reports = []
    for path in paths:
        report = read_json(path)
        require(sha256(path.with_suffix(".log")) == report["log_sha256"], "Native acceptance log changed")
        reports.append(report)
    result = aggregate_reports(plan, artifacts, reports, read_json(args.prerequisites))
    write_json(args.output, result)
    return result


def recheck(args):
    """Recheck args' public core immediately before upload, then bind unchanged SDK bytes; return proof.
    在上传前立即重新检查 args 的公共核心，再绑定未变 SDK 字节；返回证明。
    """
    aggregate = read_json(args.aggregate)
    require(aggregate["accepted"] is True, "SDK aggregate has not passed")
    plan = aggregate["plan"]
    verify_artifacts(plan, args.artifacts, aggregate["artifacts"])
    packages = args.output / "measured-packages"
    packages.mkdir(parents=True)
    for record in aggregate["artifacts"].values():
        (packages / record["filename"]).write_bytes((args.artifacts / record["filename"]).read_bytes())
    verify_artifacts(plan, packages, aggregate["artifacts"])
    require(sha256(args.prerequisites) == plan["prerequisites_sha256"], "Prerequisites binding mismatch")
    authority = core_module(args.core_root, plan["core_commit"])
    # Original artifact-only intent is preserved; only the current protected completion authorizes publication.
    # 保留原仅产物意图；仅当前受保护完成阶段授权发布。
    publication_coordinator().current_intent(args.intent, plan["source_sha"], authority)
    publication_preflight(authority, plan["source_sha"], plan["sdk_version"], aggregate["artifacts"])
    # This invokes the actual public HTTP and fresh Cargo registry consumer; pasted success is never accepted.
    # 此处调用实际公共 HTTP 及新 Cargo registry 消费者；绝不接受粘贴成功结果。
    fresh = authority.recheck(args.prerequisites, args.output / "core")
    require(fresh["complete"] is True and fresh["phase"] == "complete", "Fresh public core recheck is incomplete")
    verify_artifacts(plan, args.artifacts, aggregate["artifacts"])
    verify_artifacts(plan, packages, aggregate["artifacts"])
    write_json(args.output / "publish-proof.json", {"aggregate_sha256": sha256(args.aggregate),
               "artifacts": aggregate["artifacts"], "prerequisites_sha256": sha256(args.output / "core/prerequisites.json")})
    prepare_publish(argparse.Namespace(aggregate=args.aggregate, artifacts=packages, output=args.output / "upload",
                                      github_output=args.github_output))
    return fresh


def pypi_records(plan, artifacts, response, *, allow_partial=False):
    """Validate exact-version response against tested bytes; allow_partial admits a nonempty tested subset.
    对照已测字节校验精确版本响应；allow_partial 允许非空已测子集。
    """
    require(response["info"]["name"] == plan["name"] and response["info"]["version"] == plan["sdk_version"], "PyPI project/version mismatch")
    require(1 <= len(response["urls"]) <= 2 if allow_partial else len(response["urls"]) == 2,
            "PyPI must contain exactly the two tested artifacts or an explicitly allowed nonempty subset")
    records = {}
    for record in response["urls"]:
        kind = {"bdist_wheel": "wheel", "sdist": "sdist"}[record["packagetype"]]
        require(kind not in records and record["yanked"] is False, "Duplicate or yanked PyPI artifact")
        expected = artifacts[kind]
        require(record["filename"] == expected["filename"] and record["size"] == expected["size"]
                and record["digests"]["sha256"] == expected["sha256"], "Official PyPI bytes differ from tested artifacts")
        require(record["url"].startswith("https://files.pythonhosted.org/"), "PyPI download is outside official file authority")
        records[kind] = record
    require(set(records).issubset(artifacts) if allow_partial else set(records) == set(artifacts), "Missing PyPI artifact")
    return records


def prepare_publish(args):
    """Validate official existing bytes and stage only args' missing tested packages; return upload decision.
    校验正式现有字节并仅暂存 args 缺少的已测包；返回上传决策。
    """
    aggregate = read_json(args.aggregate)
    require(aggregate["accepted"] is True, "Publication recovery requires an accepted measured aggregate")
    plan, artifacts = aggregate["plan"], aggregate["artifacts"]
    verify_artifacts(plan, args.artifacts, artifacts)
    records = {}
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://pypi.org/pypi/{plan['name']}/{plan['sdk_version']}/json",
                                                          headers={"Cache-Control": "no-cache"}), timeout=60) as response:
            records = pypi_records(plan, artifacts, json.load(response), allow_partial=True)
    except urllib.error.HTTPError as error:
        error.close()
        require(error.code == 404, "Cannot determine exact PyPI publication state")
    # Metadata alone cannot authorize resume: every already published file is independently downloaded and hashed.
    # 仅元数据不能授权恢复：每个已发布文件均独立下载并核算摘要。
    for kind, record in records.items():
        download_pypi_artifact(record, artifacts[kind])
    require(not args.output.exists(), "Publication recovery output must be new")
    packages = args.output / "packages"
    packages.mkdir(parents=True)
    missing = sorted(set(artifacts) - set(records))
    for kind in missing:
        record = artifacts[kind]
        destination = packages / record["filename"]
        destination.write_bytes((args.artifacts / record["filename"]).read_bytes())
        require(sha256(destination) == record["sha256"] and destination.stat().st_size == record["size"],
                "Missing publication package changed while staging")
    result = {"schema_version": SCHEMA, "source_sha": plan["source_sha"], "sdk_version": plan["sdk_version"],
              "artifacts": artifacts, "existing_types": sorted(records), "missing_types": missing,
              "missing_paths": [str((packages / artifacts[kind]["filename"]).resolve()) for kind in missing],
              "upload_required": bool(missing)}
    write_json(args.output / "upload-decision.json", result)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write("upload_required=" + str(result["upload_required"]).lower() + "\n")
    return result


def download_pypi_artifact(record, expected):
    """Read bounded official record bytes and require expected size/hash; close errors and return exact bytes.
    读取有界正式 record 字节并要求 expected 大小及摘要；关闭错误流并返回精确字节。
    """
    try:
        with urllib.request.urlopen(record["url"], timeout=60) as response:
            body = response.read(expected["size"] + 1)
    except urllib.error.HTTPError as error:
        error.close()
        raise ValueError("Cannot read existing official PyPI artifact bytes") from None
    require(len(body) == expected["size"] and hashlib.sha256(body).hexdigest() == expected["sha256"],
            "Downloaded PyPI artifact actual bytes differ from tested artifacts")
    return body


def verify_pypi(args):
    """Cold-download args' exact official PyPI bytes and independently install/accept them; return proof.
    冷下载 args 的精确正式 PyPI 字节并独立安装验收；返回证明。
    """
    aggregate = read_json(args.aggregate)
    require(aggregate["accepted"] is True, "PyPI verification needs accepted aggregate")
    plan, artifacts, inputs = aggregate["plan"], aggregate["artifacts"], read_json(args.inputs)
    require(inputs["platform"] in plan["platforms"] and inputs["source_commit"] == plan["core_commit"]
            and inputs["core_version"] == plan["core_version"], "Published consumer core identity mismatch")
    with urllib.request.urlopen(urllib.request.Request(f"https://pypi.org/pypi/{plan['name']}/{plan['sdk_version']}/json",
                                                    headers={"Cache-Control": "no-cache"}), timeout=60) as response:
        records = pypi_records(plan, artifacts, json.load(response))
    require(not args.output.exists(), "PyPI output must be new")
    args.output.mkdir(parents=True)
    for kind, record in records.items():
        body = download_pypi_artifact(record, artifacts[kind])
        (args.output / artifacts[kind]["filename"]).write_bytes(body)
    # The native gate consumes only these official, newly downloaded bytes in two new isolated installations.
    # 原生门禁仅在两个新隔离安装中消费这些正式新下载字节。
    native_accept(plan, artifacts, args.output, inputs, args.output / "native.log")
    # A separate cold index installation proves ordinary exact-version PyPI resolution with hashes.
    # 另一次冷索引安装以摘要证明普通精确版本 PyPI 解析。
    environment = args.output / "index-consumer"
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    requirements = args.output / "requirements.txt"
    requirements.write_text(f"{plan['name']}=={plan['sdk_version']} --hash=sha256:{artifacts['wheel']['sha256']}\n", encoding="utf-8")
    print(run([str(python), "-I", "-m", "pip", "--isolated", "install", "--no-cache-dir", "--no-deps", "--only-binary=:all:",
               "--index-url", "https://pypi.org/simple", "--require-hashes", "-r", str(requirements.resolve())], environment,
              {**{key: value for key, value in os.environ.items() if not key.startswith("PIP_")}, "PIP_CONFIG_FILE": os.devnull}))
    print(run([str(python), "-I", "-m", "luaskills.examples.embedded_runtime", "--library", inputs["library"],
               "--library-sha256", inputs["library_sha256"], "--description", inputs["description"], "--mode", "both"], environment))
    proof = {"schema_version": SCHEMA, "source_sha": plan["source_sha"], "sdk_version": plan["sdk_version"],
             "aggregate_sha256": sha256(args.aggregate), "artifacts": artifacts, "core_commit": plan["core_commit"],
             "platform": inputs["platform"], "library_sha256": inputs["library_sha256"], "accepted": True}
    write_json(args.output / "pypi-proof.json", proof)
    return proof


def release_get(http, path):
    """Read fixed SDK repository API path using http; return the authenticated JSON response.
    使用 http 读取固定 SDK 仓库 API path；返回已认证 JSON 响应。
    """
    return http.json(f"https://api.github.com/repos/{SDK_REPOSITORY}/{path}")


def sdk_tag(http, tag, source_sha):
    """Resolve SDK tag via actual Git objects to source_sha; return nothing or fail.
    经实际 Git 对象将 SDK tag 解析至 source_sha；无返回值或失败。
    """
    obj = release_get(http, "git/ref/tags/" + tag)["object"]
    seen = set()
    while obj["type"] == "tag":
        require(obj["sha"] not in seen and len(seen) < 32, "Invalid SDK annotated tag chain")
        seen.add(obj["sha"])
        obj = release_get(http, "git/tags/" + obj["sha"])["object"]
    require(obj["type"] == "commit" and obj["sha"] == source_sha, "SDK release tag differs from frozen source SHA")


def sdk_tag_available(authority, http, tag, source_sha):
    """Check exact tag absence or recursively confirmed source_sha before mutation; return whether present.
    在修改前检查精确标签不存在或递归确认 source_sha；返回是否存在。
    """
    opener = urllib.request.build_opener(authority.SafeRedirect())
    headers = {"Accept": "application/json", "Authorization": "Bearer " + os.environ["GH_TOKEN"]}
    try:
        with opener.open(urllib.request.Request(f"https://api.github.com/repos/{SDK_REPOSITORY}/git/ref/tags/{tag}",
                                              headers=headers), timeout=60) as response:
            response.read()
    except urllib.error.HTTPError as error:
        error.close()
        require(error.code == 404, "Cannot determine exact SDK Git tag identity")
        return False
    sdk_tag(http, tag, source_sha)
    return True


def immutable_assets(existing, required):
    """Compare existing filename/digest bytes with required; return missing names, rejecting replacements.
    将现有文件名摘要字节与 required 比较；返回缺少名称，拒绝替换。
    """
    for name in set(existing) & set(required):
        require(existing[name] == required[name], "Existing release asset differs; replacement is forbidden")
    return set(required) - set(existing)




def release_assets(http, release_id):
    """Return all exact release_id assets from fixed SDK API pagination; duplicate names fail.
    从固定 SDK API 分页返回 release_id 的全部精确资产；重复名称失败。
    """
    assets = {}
    for page in range(1, 101):
        records = release_get(http, f"releases/{release_id}/assets?per_page=100&page={page}")
        for record in records:
            require(record["name"] not in assets, "Duplicate SDK release asset name")
            assets[record["name"]] = record
        if len(records) < 100:
            return assets
    raise ValueError("SDK release asset pagination exceeded its bound")


def find_release(authority, http, tag):
    """Find exact tag uniquely through authenticated full release pagination; return record or None.
    经认证的完整发布分页唯一查找精确 tag；返回记录或 None。
    Drafts are not visible through the published-by-tag endpoint and must retain their actual ID.
    草稿不经正式标签端点暴露，必须保留其实际 ID。
    """
    matches, ids = [], set()
    for page in range(1, 101):
        body, headers = http.get(f"https://api.github.com/repos/{SDK_REPOSITORY}/releases?per_page=100&page={page}")
        records = authority.candidate.decode_json(body)
        require(isinstance(records, list), "Authenticated SDK release page must be an array")
        for record in records:
            require(type(record["id"]) is int and record["id"] > 0 and record["id"] not in ids, "Duplicate or invalid SDK release ID")
            ids.add(record["id"])
            if record["tag_name"] == tag:
                matches.append(record)
        # HTTP field names are case-insensitive; Link declares pages even when a filtered page is short.
        # HTTP 字段名称不区分大小写；即使过滤后页面较短，Link 仍声明后续页面。
        link = next((value for name, value in headers.items() if name.lower() == "link"), "")
        if not re.search(r';\s*rel="next"', link):
            require(len(matches) <= 1, "SDK tag has ambiguous draft/final releases")
            return matches[0] if matches else None
    raise ValueError("SDK release pagination exceeded its bound")


def verify_attestation(subject, bundle, source_sha, run_id, run_attempt, output, *, workflow_path=SDK_WORKFLOW):
    """Verify subject/bundle through gh for exact source/run/attempt/workflow_path; return authenticated facts.
    通过 gh 对精确 source/run/attempt/workflow_path 验证 subject/bundle；返回已认证事实。
    """
    command = ["gh", "attestation", "verify", str(subject), "--repo", SDK_REPOSITORY,
               "--signer-workflow", SDK_REPOSITORY + "/" + workflow_path,
               "--source-digest", source_sha, "--signer-digest", source_sha, "--deny-self-hosted-runners",
               "--bundle", str(bundle), "--format", "json"]
    # gh validates signatures/trusted roots; this helper only adds policy on its verified JSON result.
    # gh 验证签名及信任根；此 helper 仅对其已验证 JSON 结果增加策略。
    result = subprocess.run(command, capture_output=True, check=True, text=True, encoding="utf-8", timeout=1800)
    Path(output).write_text(result.stdout, encoding="utf-8")
    verified = read_json(output)
    require(isinstance(verified, list) and len(verified) == 1, "Exactly one verified publication attestation is required")
    expected = f"https://github.com/{SDK_REPOSITORY}/actions/runs/{run_id}/attempts/{run_attempt}"
    verification = verified[0]["verificationResult"]
    certificate = verification["signature"]["certificate"]
    # OIDC certificate extensions cannot be authored by the workflow; predicate alone is insufficient.
    # OIDC 证书扩展不能由工作流编写；仅 predicate 不足以证明来源。
    require(certificate["runInvocationURI"] == expected
            and verification["statement"]["predicate"]["runDetails"]["metadata"]["invocationId"] == expected,
            "Verified publication certificate/predicate belongs to another run or attempt")
    require(certificate["sourceRepositoryURI"] == "https://github.com/" + SDK_REPOSITORY
            and certificate["sourceRepositoryDigest"] == certificate["buildSignerDigest"] == source_sha
            and certificate["runnerEnvironment"] == "github-hosted"
            and certificate["buildSignerURI"] == "https://github.com/" + SDK_REPOSITORY
                + "/" + workflow_path + "@" + certificate["sourceRepositoryRef"],
            "Verified publication certificate source/workflow/runner identity mismatch")
    subjects = [record for record in verification["statement"]["subject"] if record["name"] == Path(subject).name]
    require(len(subjects) == 1 and subjects[0]["digest"] == {"sha256": sha256(subject)},
            "Verified publication subject name or actual byte digest mismatch")
    return {"verified_subjects": {Path(subject).name: subjects[0]["digest"]["sha256"]},
            "verified_invocation_uri": certificate["runInvocationURI"],
            "verified_source_sha": certificate["sourceRepositoryDigest"]}


def publish_immutable(authority, tag, source_sha, directory):
    """Publish directory to tag/source_sha through a complete draft; return observed final server state.
    经完整草稿将 directory 发布至 tag/source_sha；返回实际观察的正式服务端状态。
    """
    http = authority.Http()
    repository = release_get(http, "")
    require(os.environ["GITHUB_REF"] == "refs/heads/" + repository["default_branch"], "SDK publication definition must be on the default branch")
    # gh uses the current job's GITHUB_TOKEN; no PAT, login, clobber or force-tag operation exists.
    # gh 使用当前任务的 GITHUB_TOKEN；不存在 PAT、登录、clobber 或强制标签操作。
    env = dict(os.environ, GH_TOKEN=os.environ["GITHUB_TOKEN"])
    sdk_tag_available(authority, http, tag, source_sha)
    release = find_release(authority, http, tag)
    if release is None:
        # The create API returns the authoritative draft ID, unlike a published tag lookup.
        # 创建 API 返回权威草稿 ID，与正式标签查询不同。
        created = json.loads(run(["gh", "api", f"repos/{SDK_REPOSITORY}/releases", "--method", "POST",
                                  "-f", "tag_name=" + tag, "-f", "target_commitish=" + source_sha,
                                  "-F", "draft=true", "-F", "prerelease=false", "-f", "name=" + tag,
                                  "-f", "body=Exact tested Python SDK assets and verified publication provenance."], env=env))
        require(type(created["id"]) is int and created["id"] > 0, "SDK release create did not return an actual draft ID")
        release_id = created["id"]
    else:
        release_id = release["id"]
    release = release_get(http, "releases/" + str(release_id))
    require(release["tag_name"] == tag and release["prerelease"] is False, "Unexpected SDK release identity")
    required = {path.name: sha256(path) for path in Path(directory).iterdir() if path.is_file()}
    assets = release_assets(http, release["id"])
    # Extra assets cannot become part of the frozen inventory and must fail before any upload or finalization.
    # 额外资产不能成为冻结清单的一部分，必须在任何上传或正式发布前失败。
    require(set(assets).issubset(required), "SDK release contains unexpected assets outside the frozen inventory")
    existing = {name: hashlib.sha256(http.get(asset["url"], binary=True)[0]).hexdigest()
                for name, asset in assets.items()}
    missing = immutable_assets(existing, required)
    if release["draft"] is False:
        require(not missing, "Published SDK release cannot accept additional assets")
        sdk_tag(http, tag, source_sha)
        return release_state(release, source_sha)
    require(release["draft"] is True and release["target_commitish"] == source_sha,
            "Draft SDK release must target the exact frozen source SHA")
    for name in sorted(missing):
        print(run(["gh", "release", "upload", tag, str(Path(directory) / name), "--repo", SDK_REPOSITORY], env=env))
    # A draft's target_commitish does not establish an existing tag's identity at the publish boundary.
    # 草稿 target_commitish 不能建立发布边界上现有标签的身份。
    sdk_tag_available(authority, http, tag, source_sha)
    # Check every actual asset immediately before finalization; the earlier subset allowed only draft completion.
    # 在正式发布紧邻边界检查每份实际资产；此前子集判断仅允许补全草稿。
    uploaded_assets = release_assets(http, release["id"])
    require(set(uploaded_assets) == set(required), "Draft release asset set differs from the exact frozen inventory")
    uploaded = {name: hashlib.sha256(http.get(asset["url"], binary=True)[0]).hexdigest()
                for name, asset in uploaded_assets.items()}
    require(not immutable_assets(uploaded, required), "Draft release is missing tested bytes")
    print(run(["gh", "release", "edit", tag, "--repo", SDK_REPOSITORY, "--draft=false"], env=env))
    final = release_get(http, "releases/" + str(release_id))
    require(final["draft"] is False and final["tag_name"] == tag, "SDK release failed to finalize its actual draft ID")
    sdk_tag(http, tag, source_sha)
    return release_state(final, source_sha)


def release_state(record, source_sha):
    """Record actual final record identity and immutable setting without requiring it enabled; return observation.
    记录实际正式 record 身份及 immutable 设置，不要求其启用；返回观察结果。
    """
    require(type(record["immutable"]) is bool, "Release server did not report its immutable setting")
    return {"release_id": record["id"], "tag": record["tag_name"], "source_sha": source_sha,
            "server_release_immutable": record["immutable"]}






def examples(args):
    """Package args' exact tracked examples after fresh official-package execution; return archive path.
    在新正式包执行后打包 args 的精确已跟踪示例；返回归档路径。
    """
    proof = read_json(args.formal_proof / "fresh-pypi/pypi-proof.json")
    aggregate = read_json(args.formal_proof / "aggregate.json")
    plan = aggregate["plan"]
    require(proof["accepted"] is True and proof["source_sha"] == plan["source_sha"]
            and proof["aggregate_sha256"] == sha256(args.formal_proof / "aggregate.json"), "Fresh official PyPI consumer proof is missing")
    require(run(["git", "rev-parse", "HEAD"], args.root).strip() == plan["source_sha"]
            and not run(["git", "status", "--porcelain", "--untracked-files=no"], args.root).strip(), "Examples checkout differs from frozen SDK SHA")
    inputs = read_json(args.formal_proof / "resolved-inputs.json")
    environment = args.formal_proof / "fresh-pypi/index-consumer"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    print(run([str(python.resolve()), "-I", "-X", "utf8", str((args.root / "examples/embedded_runtime.py").resolve()),
               "--library", inputs["library"], "--library-sha256", inputs["library_sha256"],
               "--description", inputs["description"], "--mode", "both"], environment))
    # Git's frozen file list excludes installed environments and generated runtime databases.
    # Git 冻结文件列表排除已安装环境及生成运行时数据库。
    tracked = run(["git", "ls-files", "-z"], args.root).split("\0")
    files = {name: (args.root / name).read_bytes() for name in tracked
             if name.startswith("examples/") or name in ("LICENSE", "README.md", "README_cn.md")}
    for name, content in files.items():
        if name.endswith(".py"):
            compile(content, name, "exec")
    files["requirements.txt"] = f"{plan['name']}=={plan['sdk_version']} --hash=sha256:{proof['artifacts']['wheel']['sha256']}\n".encode()
    files["PUBLICATION.json"] = json.dumps(proof, sort_keys=True, indent=2).encode()
    files["EXAMPLES_RELEASE.md"] = (
        "Install requirements.txt with --require-hashes from https://pypi.org/simple.\n"
        "从 https://pypi.org/simple 使用 --require-hashes 安装 requirements.txt。\n"
        "Embedded examples require the exact core library and frozen description.\n"
        "嵌入示例要求精确核心库及冻结描述。\n"
        "The release workflow executed embedded_runtime.py against the cold installed official package.\n"
        "发布工作流已使用冷安装的正式包执行 embedded_runtime.py。\n").encode()
    args.output.mkdir(parents=True, exist_ok=False)
    name = f"luaskills-sdk-python-examples-{plan['sdk_version']}"
    path = args.output / (name + ".zip")
    # Stored members remove zlib-version drift so fixed source/public package identity reproduces exact bytes.
    # 存储成员消除 zlib 版本漂移，使固定源码及公共包身份可复现精确字节。
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_STORED) as archive:
        for filename, content in sorted(files.items()):
            member = zipfile.ZipInfo(name + "/" + filename, date_time=(1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_STORED
            archive.writestr(member, content)
    (args.output / (path.name + ".sha256")).write_text(f"{sha256(path)}  {path.name}\n", encoding="utf-8")
    return path


def publish_examples(args):
    """Publish args' independent examples tag at proven SDK source; return nothing, never replace assets.
    在已证明 SDK 源码上发布 args 的独立示例标签；无返回值，绝不替换资产。
    """
    proof = read_json(args.formal_proof / "fresh-pypi/pypi-proof.json")
    aggregate = read_json(args.formal_proof / "aggregate.json")
    plan = aggregate["plan"]
    require(proof["accepted"] is True and proof["aggregate_sha256"] == sha256(args.formal_proof / "aggregate.json"), "Official examples consumer proof is missing")
    require(os.environ["GITHUB_SHA"] == os.environ["GITHUB_WORKFLOW_SHA"] == plan["source_sha"]
            and os.environ["GITHUB_REPOSITORY"] == SDK_REPOSITORY, "Examples workflow/source identity mismatch")
    authority = core_module(args.core_root, plan["core_commit"])
    http = authority.Http()
    require(os.environ["GITHUB_REF"] == "refs/heads/" + release_get(http, "")["default_branch"], "Examples definition must be on default branch")
    sdk_tag(http, "v" + plan["sdk_version"], plan["source_sha"])
    state = publish_immutable(authority, "examples-v" + plan["sdk_version"], plan["source_sha"], args.assets)
    write_json(args.assets.parent / "examples-release-state.json", state)


def main():
    """Parse exact release subcommands without skip/fake-success switches; return nonzero on failure.
    解析精确发布子命令，无跳过或伪成功开关；失败时返回非零。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("bootstrap", "freeze", "build", "validate", "aggregate", "recheck", "prepare-publish", "verify-pypi",
                 "examples", "publish-examples", "tool-requirements", *PUBLICATION_COMMANDS):
        command = commands.add_parser(name)
        if name not in ("publish-examples", "tool-requirements", "candidate-seal", "publish-completion"):
            command.add_argument("--output", type=Path, required=True)
        if name == "tool-requirements":
            continue
        elif name in ("candidate-seal", "publish-completion"):
            command.add_argument("--prepared", type=Path, required=True)
            command.add_argument("--bundle", type=Path, required=True)
            command.add_argument("--core-root", type=Path, required=True)
            if name == "publish-completion":
                command.add_argument("--candidate", type=Path, required=True)
                command.add_argument("--intent", choices=("publish", "recover"), required=True)
        elif name in ("examples", "publish-examples"):
            command.add_argument("--formal-proof", type=Path, required=True)
            if name == "examples":
                command.add_argument("--root", type=Path, default=Path.cwd())
            else:
                command.add_argument("--assets", type=Path, required=True)
                command.add_argument("--core-root", type=Path, required=True)
        elif name == "formal-proof":
            for flag in ("source-sha", "completion-source-sha", "sdk-version", "core-tag", "core-commit", "platform"):
                command.add_argument("--" + flag, required=True)
            for flag in ("candidate-run-id", "candidate-run-attempt", "completion-run-id", "completion-run-attempt"):
                command.add_argument("--" + flag, type=int, required=True)
            command.add_argument("--core-root", type=Path, required=True)
        elif name == "candidate-prepare":
            for flag in ("aggregate", "artifacts", "evidence", "reports", "core-root"):
                command.add_argument("--" + flag, type=Path, required=True)
            command.add_argument("--github-output", type=Path)
        elif name == "candidate-resolve":
            for flag in ("source-sha", "core-tag", "core-commit"):
                command.add_argument("--" + flag, required=True)
            for flag in ("candidate-run-id", "candidate-run-attempt", "candidate-artifact-id"):
                command.add_argument("--" + flag, type=int, required=True)
            command.add_argument("--core-root", type=Path, required=True)
        elif name in ("publish-candidate", "completion-prepare"):
            command.add_argument("--candidate", type=Path, required=True)
            command.add_argument("--core-root", type=Path, required=True)
            command.add_argument("--intent", choices=("publish", "recover"), required=True)
            if name == "completion-prepare":
                for flag in ("proof", "publication-proof", "publication-prerequisites", "main-release-state"):
                    command.add_argument("--" + flag, type=Path, required=True)
        elif name in ("bootstrap", "freeze"):
            for flag in (("core-tag", "core-commit") if name == "bootstrap" else ("source-sha", "core-tag", "core-commit", "default-branch")):
                command.add_argument("--" + flag, required=True)
            command.add_argument("--core-root", type=Path, required=True)
            command.add_argument("--root", type=Path, default=Path.cwd())
            command.add_argument("--github-output", type=Path)
            if name == "freeze":
                command.add_argument("--mode", choices=("artifact-only", "publish"), required=True)
        elif name == "build":
            command.add_argument("--root", type=Path, default=Path.cwd())
            command.add_argument("--plan", type=Path, required=True)
        else:
            if name in ("validate", "aggregate"):
                command.add_argument("--plan", type=Path, required=True)
            else:
                command.add_argument("--aggregate", type=Path, required=True)
            if name in ("validate", "verify-pypi"):
                command.add_argument("--inputs", type=Path, required=True)
            if name != "verify-pypi":
                command.add_argument("--artifacts", type=Path, required=True)
            if name == "validate":
                command.add_argument("--platform", required=True)
                command.add_argument("--python-role", choices=ROLES, required=True)
            if name in ("aggregate", "recheck"):
                command.add_argument("--prerequisites", type=Path, required=True)
            if name == "aggregate":
                command.add_argument("--reports", type=Path, required=True)
            if name == "recheck":
                command.add_argument("--core-root", type=Path, required=True)
                command.add_argument("--intent", choices=("publish", "recover"), required=True)
            if name in ("recheck", "prepare-publish"):
                command.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        if args.command in PUBLICATION_COMMANDS:
            getattr(publication_coordinator(), args.command.replace("-", "_"))(args)
        else:
            globals()[args.command.replace("-", "_")](args)
    except (ValueError, KeyError, OSError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"SDK release gate failed: {error}\n")


if __name__ == "__main__":
    main()
