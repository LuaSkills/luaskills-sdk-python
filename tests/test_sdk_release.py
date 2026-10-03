"""Exercise exact publication bytes and fail-closed release boundaries without publishing or Cargo.
在不发布及不运行 Cargo 的前提下验证精确发布字节及关闭门禁边界。
"""

import argparse
import base64
import copy
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Test imports the production helper directly instead of duplicating its decisions.
# 测试直接导入正式 helper，不复制其判断。
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sdk_release", ROOT / "scripts/release/sdk_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseGateTests(unittest.TestCase):
    """Build real SDK wheel/sdist once and verify negative publication paths with controlled fixtures.
    一次构建真实 SDK wheel/sdist，并以受控夹具验证负向发布路径。
    """

    @classmethod
    def setUpClass(cls):
        """Create independent real packaging fixtures from current SDK source; return nothing.
        从当前 SDK 源码创建独立真实打包夹具；无返回值。
        """
        cls.temporary = tempfile.TemporaryDirectory(prefix="luaskills-release-tests-")
        cls.root = Path(cls.temporary.name)
        project = cls.root / "project"
        project.mkdir()
        for name in ("pyproject.toml", "README.md", "README_cn.md", "LICENSE", "VERSION", "MANIFEST.in"):
            shutil.copyfile(ROOT / name, project / name)
        shutil.copytree(ROOT / "src", project / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        cls.dist = cls.root / "dist"
        # Offline fixture uses the already installed backend; production build never skips tool requirements.
        # 离线夹具使用已安装后端；正式构建绝不跳过工具要求。
        release.run([sys.executable, "-m", "build", "--no-isolation", "--skip-dependency-check", "--outdir", str(cls.dist)], project)
        cls.plan = {**release.source_metadata(ROOT), "schema_version": release.SCHEMA,
                    "source_sha": "a" * 40, "mode": "publish", "core_tag": release.source_metadata(ROOT)["default_core_tag"],
                    "core_commit": "b" * 40, "core_version": "0.5.7", "platforms": ["fixture-platform", "fixture-other"]}
        cls.artifacts = release.verify_artifacts(cls.plan, cls.dist)

    @classmethod
    def tearDownClass(cls):
        """Release independent temporary fixtures; return nothing.
        释放独立临时夹具；无返回值。
        """
        cls.temporary.cleanup()

    def evidence(self):
        """Return one consistent fixture plan, core prerequisite and complete native report list.
        返回一组一致的夹具计划、核心前置证明及完整原生报告列表。
        """
        plan = copy.deepcopy(self.plan)
        inputs = {"library_sha256": "c" * 64, "description_sha256": "d" * 64,
                  "archive_sha256": "e" * 64, "build": {"inputs_sha256": "f" * 64}}
        prerequisite = {"complete": True, "phase": "complete", "core_tag": plan["core_tag"],
                        "core_commit": plan["core_commit"], "core_version": plan["core_version"],
                        "sdk_inputs": {platform: inputs for platform in plan["platforms"]}}
        reports = [{"schema_version": release.SCHEMA, **{key: plan[key] for key in
                    ("source_sha", "sdk_version", "core_tag", "core_commit", "core_version")},
                    "platform": platform, "python_role": role, "python": plan["python"][role],
                    "artifacts": self.artifacts, "inputs": inputs, "accepted": True, "log_sha256": "1" * 64}
                   for platform in plan["platforms"] for role in release.ROLES]
        return plan, prerequisite, reports

    def test_real_wheel_sdist_metadata_and_strict_twine(self):
        """Require real fixture metadata and strict twine success; return nothing.
        要求真实夹具元数据及严格 twine 成功；无返回值。
        """
        self.assertEqual(release.verify_artifacts(self.plan, self.dist, self.artifacts), self.artifacts)
        output = release.run([sys.executable, "-m", "twine", "check", "--strict",
                              *[str(self.dist / record["filename"]) for record in self.artifacts.values()]])
        self.assertIn("PASSED", output)

    def test_actual_blob_denial_stops_real_pypi_preparation(self):
        """Run actual recheck/current_intent and transport; HTTP403 blocks fresh Core and PyPI upload preparation.
        运行实际 recheck／current_intent 及传输；HTTP403 阻止新 Core 验收及 PyPI 上传准备。
        """
        # Plan, prerequisite and reports are the existing complete fixture; only unrelated native verification is isolated.
        # plan、prerequisite 及 reports 为既有完整夹具；仅隔离无关原生验证。
        plan, prerequisite, reports = self.evidence()
        with tempfile.TemporaryDirectory(prefix="ls-blob-pypi-") as temporary, RepositoryRootTests.transport(self) as state:
            # Directory holds genuine package-bound aggregate and prerequisite bytes used by actual recheck.
            # directory 保存实际 recheck 使用的真实绑定包聚合及前置字节。
            directory = Path(temporary)
            path, aggregate = directory / "prerequisites.json", directory / "aggregate.json"
            release.write_json(path, prerequisite)
            plan["prerequisites_sha256"] = release.sha256(path)
            release.write_json(aggregate, {"accepted": True, "plan": plan, "artifacts": self.artifacts})
            # Coordinator retains its actual HTTP/write gate; only local Git identity is controlled for the fixture.
            # coordinator 保留实际 HTTP／写门禁；仅控制夹具的本地 Git 身份。
            coordinator = release.publication_coordinator()
            state.status = 403
            with patch.object(release, "core_module", return_value=state.authority), \
                    patch.object(release, "publication_coordinator", return_value=coordinator), \
                    patch.object(coordinator, "checked_source"), \
                    patch.object(state.authority, "recheck") as fresh_core, \
                    patch.object(release, "prepare_publish") as upload:
                with self.assertRaises(release.urllib.error.HTTPError) as rejection:
                    release.recheck(argparse.Namespace(aggregate=aggregate, prerequisites=path, artifacts=self.dist,
                        core_root=ROOT, output=directory / "fresh", intent="publish", github_output=None))
                self.assertEqual(rejection.exception.code, 403)
                fresh_core.assert_not_called()
                upload.assert_not_called()
            self.assertFalse((directory / "fresh/publish-proof.json").exists())

    def test_changed_package_bytes_and_wrong_default_core_tag_fail(self):
        """Reject a changed byte or different explicit core tag in real packages; return nothing.
        拒绝真实包中的字节变化或不同显式核心标签；无返回值。
        """
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for record in self.artifacts.values():
                shutil.copyfile(self.dist / record["filename"], directory / record["filename"])
            with (directory / self.artifacts["wheel"]["filename"]).open("ab") as stream:
                stream.write(b"changed")
            with self.assertRaisesRegex(ValueError, "bytes changed"):
                release.verify_artifacts(self.plan, directory, self.artifacts)
        plan = dict(self.plan, core_tag="v999.0.0")
        with self.assertRaisesRegex(ValueError, "default core asset"):
            release.verify_artifacts(plan, self.dist)

    def test_complete_matrix_and_missing_duplicate_identity_negative(self):
        """Accept only complete exact reports, rejecting missing, duplicate or changed identity; return nothing.
        仅接受完整精确报告，拒绝缺少、重复或身份变化；无返回值。
        """
        plan, prerequisite, reports = self.evidence()
        self.assertTrue(release.aggregate_reports(plan, self.artifacts, reports, prerequisite)["accepted"])
        for changed in (reports[:-1], reports + reports[:1], [report for report in reports if report["platform"] != "fixture-other"]):
            with self.assertRaises(ValueError):
                release.aggregate_reports(plan, self.artifacts, changed, prerequisite)
        for field, value in (("source_sha", "0" * 40), ("sdk_version", "99.0.0"), ("python", "3.9"), ("accepted", False)):
            changed = copy.deepcopy(reports)
            changed[0][field] = value
            with self.assertRaises(ValueError):
                release.aggregate_reports(plan, self.artifacts, changed, prerequisite)
        prerequisite["complete"] = False
        with self.assertRaisesRegex(ValueError, "Complete"):
            release.aggregate_reports(plan, self.artifacts, reports, prerequisite)

    def test_report_enumeration_order_preserves_identical_evidence(self):
        """Require identical aggregates for the same reports in different orders; return nothing.
        要求同一批报告以不同顺序输入时产生相同聚合凭证；无返回值。
        """
        # Use the existing complete, byte-bound package and native-report fixture.
        # 使用既有完整、绑定包字节及原生报告的夹具。
        plan, prerequisite, reports = self.evidence()
        # Keep the caller's report list unchanged while testing archive/download reorderings.
        # 测试归档及下载重排时保持调用方报告列表不变。
        original = copy.deepcopy(reports)
        # Compare complete evidence, including each report's actual identity and package binding.
        # 比较完整凭证，包含每份报告的实际身份及包绑定。
        expected = release.aggregate_reports(plan, self.artifacts, reports, prerequisite)
        # Reversed and rotated inputs represent independent delivery orders of the same reports.
        # 逆序及轮转输入表示同一批报告的不同独立送达顺序。
        for reordered in (list(reversed(reports)), reports[1:] + reports[:1]):
            self.assertEqual(release.aggregate_reports(plan, self.artifacts, reordered, prerequisite), expected)
        self.assertEqual(reports, original)

    def test_missing_core_fixture_does_not_expose_environment_values(self):
        """Reject a missing Core fixture without revealing unrelated environment values; return nothing.
        拒绝缺失的 Core 夹具，同时不泄露无关环境变量值；无返回值。
        """
        # Use a controlled sentinel rather than any actual process credential.
        # 使用受控哨兵，而不使用任何实际进程凭证。
        sentinel = "controlled-environment-value-sentinel"
        # Capture only the missing-fixture assertion under an isolated environment mapping.
        # 在隔离环境映射中仅捕获缺失夹具断言。
        with patch.dict(os.environ, {"FIXTURE_PRIVATE_VALUE": sentinel}, clear=True):
            with self.assertRaises(AssertionError) as failure:
                self.recovery_authority()
        self.assertIn("explicit frozen core checkout", str(failure.exception))
        self.assertNotIn(sentinel, str(failure.exception))

    def test_strict_twine_tool_is_mandatory_before_native(self):
        """Reject unavailable twine before native ownership or process execution; return nothing.
        在原生拥有权或进程执行前拒绝不可用 twine；无返回值。
        """
        with patch.object(release.importlib.util, "find_spec", return_value=None), patch.object(release, "run") as process:
            with self.assertRaisesRegex(ValueError, "requires twine"):
                release.native_accept(self.plan, self.artifacts, self.dist, {}, self.root / "missing-twine.log")
            process.assert_not_called()

    def test_recheck_does_not_accept_copied_consumer_success(self):
        """Require the public helper's actual fresh consumption despite copied success JSON; return nothing.
        即使存在复制成功 JSON，也要求公共 helper 实际新消费；无返回值。
        """
        plan, prerequisite, reports = self.evidence()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "prerequisites.json"
            release.write_json(path, prerequisite)
            plan["prerequisites_sha256"] = release.sha256(path)
            aggregate = directory / "aggregate.json"
            release.write_json(aggregate, release.aggregate_reports(plan, self.artifacts, reports, prerequisite))
            authority = unittest.mock.Mock()
            authority.recheck.side_effect = ValueError("actual registry consumer failed; pasted success is insufficient")
            with patch.object(release, "core_module", return_value=authority), patch.object(release, "publication_preflight"), \
                    patch.object(release, "publication_coordinator"):
                with self.assertRaisesRegex(ValueError, "actual registry consumer failed"):
                    release.recheck(argparse.Namespace(aggregate=aggregate, prerequisites=path, artifacts=self.dist,
                                                       core_root=directory, output=directory / "fresh", intent="recover"))
            authority.recheck.assert_called_once()
            self.assertFalse((directory / "fresh/publish-proof.json").exists())

    def test_official_pypi_records_need_exact_two_tested_bytes(self):
        """Reject forged hashes, yanked files, unexpected files and nonofficial URLs; return nothing.
        拒绝伪造摘要、撤销文件、意外文件及非正式 URL；无返回值。
        """
        response = {"info": {"name": self.plan["name"], "version": self.plan["sdk_version"]},
                    "urls": [{"filename": record["filename"], "size": record["size"],
                              "digests": {"sha256": record["sha256"]}, "yanked": False,
                              "packagetype": "bdist_wheel" if kind == "wheel" else "sdist",
                              "url": "https://files.pythonhosted.org/packages/" + record["filename"]}
                             for kind, record in self.artifacts.items()]}
        self.assertEqual(set(release.pypi_records(self.plan, self.artifacts, response)), {"wheel", "sdist"})
        for field, value in (("yanked", True), ("digests", {"sha256": "0" * 64}), ("url", "https://mirror.invalid/file")):
            changed = copy.deepcopy(response)
            changed["urls"][0][field] = value
            with self.assertRaises(ValueError):
                release.pypi_records(self.plan, self.artifacts, changed)
        response["urls"].append(copy.deepcopy(response["urls"][0]))
        with self.assertRaises(ValueError):
            release.pypi_records(self.plan, self.artifacts, response)

    def test_existing_assets_equal_reuse_and_changed_refusal(self):
        """Reuse equal existing bytes and reject every replacement; return nothing.
        复用相同现有字节并拒绝任何替换；无返回值。
        """
        self.assertEqual(release.immutable_assets({"one": "a"}, {"one": "a", "two": "b"}), {"two"})
        with self.assertRaisesRegex(ValueError, "replacement is forbidden"):
            release.immutable_assets({"one": "a"}, {"one": "b"})

    def exercise_index_consumer_path(self, relative_output):
        """Execute production verify_pypi with a real venv and interpreter; return both observed calls.
        使用真实 venv 与解释器执行生产 verify_pypi；返回两个被观察调用。
        relative_output selects a relative output or its absolute control; only external/business payloads are isolated.
        relative_output 选择相对输出或其绝对对照；仅隔离外部与业务载荷。
        """
        with tempfile.TemporaryDirectory(prefix="luaskills-index-path-") as temporary:
            # Root and initial_directory isolate the real venv and restore the caller's process directory.
            # Root 与 initial_directory 隔离真实 venv，并恢复调用方进程目录。
            root = Path(temporary).resolve()
            initial_directory = Path.cwd()
            # Aggregate and inputs retain production's accepted package/core identity checks without a native fixture.
            # Aggregate 与 inputs 保留生产已接受包／核心身份检查，不使用原生夹具。
            aggregate = root / "aggregate.json"
            inputs = root / "inputs.json"
            release.write_json(aggregate, {"accepted": True, "plan": self.plan, "artifacts": self.artifacts})
            release.write_json(inputs, {"platform": self.plan["platforms"][0], "source_commit": self.plan["core_commit"],
                "core_version": self.plan["core_version"], "library": "controlled-native-library",
                "library_sha256": "0" * 64, "description": "controlled-native-description"})
            # Response and bodies use the real already-built package bytes behind a narrow offline HTTP boundary.
            # Response 与 bodies 在窄离线 HTTP 边界后使用真实已构建包字节。
            response = {"info": {"name": self.plan["name"], "version": self.plan["sdk_version"]}, "urls": [
                {"filename": record["filename"], "size": record["size"], "digests": {"sha256": record["sha256"]},
                 "yanked": False, "packagetype": "bdist_wheel" if kind == "wheel" else "sdist",
                 "url": "https://files.pythonhosted.org/" + record["filename"]}
                for kind, record in self.artifacts.items()]}
            bodies = [io.BytesIO(json.dumps(response).encode()),
                      *[io.BytesIO((self.dist / record["filename"]).read_bytes()) for record in self.artifacts.values()]]
            # Output and expected_environment bind the relative case to the same actual absolute venv root.
            # Output 与 expected_environment 将相对用例绑定到同一个实际绝对 venv 根。
            output = Path("official-pypi") if relative_output else root / "official-pypi"
            expected_environment = root / "official-pypi/index-consumer"
            # Original_run remains the real production subprocess implementation; observations contain no secrets.
            # Original_run 保持真实生产子进程实现；observations 不包含秘密。
            original_run = release.run
            observations = []
            # Probe replaces only pip/native business payloads and reports the interpreter that actually launched.
            # Probe 仅替换 pip／原生业务载荷，报告实际启动的解释器。
            probe = "import json,os,sys; print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,'cwd':os.getcwd()}))"

            def observe_payload(command, cwd=None, env=None):
                """Launch command's actual executable in its actual cwd/env through original_run; return observed JSON.
                经 original_run 在 command 的实际 cwd／env 启动实际 executable；返回观察 JSON。
                command must be exactly a production pip or embedded consumer payload, never a general mocked process.
                command 必须精确属于生产 pip 或嵌入消费者载荷，绝非泛用模拟进程。
                """
                self.assertIn(command[1:4], (["-I", "-m", "pip"], ["-I", "-m", "luaskills.examples.embedded_runtime"]))
                # Actual_output is produced by a real venv Python process; FileNotFoundError is deliberately unaltered.
                # Actual_output 来自真实 venv Python 进程；FileNotFoundError 故意原样传播。
                actual_output = original_run([command[0], "-I", "-c", probe], cwd=cwd, env=env)
                observations.append({"command": command, "cwd_argument": str(cwd), "actual": json.loads(actual_output),
                    "pip_config_file": None if env is None else env.get("PIP_CONFIG_FILE"),
                    "injected_pip_setting_present": env is not None and "PIP_EXTRA_INDEX_URL" in env})
                return actual_output

            try:
                os.chdir(root)
                with patch.object(release.urllib.request, "urlopen", side_effect=bodies), \
                        patch.object(release, "native_accept") as native_boundary, \
                        patch.object(release, "run", side_effect=observe_payload), \
                        patch.dict(os.environ, {"PIP_EXTRA_INDEX_URL": "controlled-unused-setting"}):
                    release.verify_pypi(argparse.Namespace(aggregate=aggregate, inputs=inputs, output=output))
                native_boundary.assert_called_once()
            finally:
                os.chdir(initial_directory)
                print("INDEX_CONSUMER_PATH_OBSERVATIONS=" + json.dumps({"relative_output": relative_output, "observations": observations}))
            self.assertEqual(len(observations), 2)
            for observation in observations:
                self.assertEqual(Path(observation["actual"]["prefix"]).resolve(), expected_environment)
                self.assertEqual(Path(observation["actual"]["cwd"]).resolve(), expected_environment)
                self.assertEqual(Path(observation["actual"]["executable"]).resolve(),
                    (expected_environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")).resolve())
                self.assertTrue(Path(observation["command"][0]).is_absolute(), "Consumer executable must remain absolute when cwd changes")
                self.assertTrue(Path(observation["cwd_argument"]).is_absolute(), "Consumer environment must be absolute before creation")
            self.assertEqual(observations[0]["command"][1:], ["-I", "-m", "pip", "--isolated", "install", "--no-cache-dir",
                "--no-deps", "--only-binary=:all:", "--index-url", "https://pypi.org/simple", "--require-hashes", "-r",
                str(expected_environment.parent / "requirements.txt")])
            self.assertEqual(observations[0]["pip_config_file"], os.devnull)
            self.assertFalse(observations[0]["injected_pip_setting_present"])
            self.assertEqual(observations[1]["command"][1:], ["-I", "-m", "luaskills.examples.embedded_runtime",
                "--library", "controlled-native-library", "--library-sha256", "0" * 64,
                "--description", "controlled-native-description", "--mode", "both"])
            self.assertEqual((expected_environment.parent / "requirements.txt").read_text(),
                f"{self.plan['name']}=={self.plan['sdk_version']} --hash=sha256:{self.artifacts['wheel']['sha256']}\n")
            return observations

    def test_verify_pypi_absolute_output_launches_real_index_interpreter(self):
        """Run the absolute-output control through production verify_pypi and real isolated interpreter calls.
        经生产 verify_pypi 与真实隔离解释器调用执行绝对输出对照。
        """
        self.exercise_index_consumer_path(False)

    def test_verify_pypi_relative_output_launches_real_index_interpreter(self):
        """Run relative output through production verify_pypi; absolute executable/cwd prevents POSIX re-resolution.
        经生产 verify_pypi 执行相对输出；绝对 executable／cwd 阻止 POSIX 二次解析。
        """
        self.exercise_index_consumer_path(True)

    def test_partial_pypi_recovery_hashes_actual_bytes_and_stages_only_missing(self):
        """Recover either actual partial artifact or full publication; reject changed bytes and unknown HTTP.
        恢复任一实际部分产物或完整发布；拒绝变化字节及未知 HTTP。
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            aggregate = root / "aggregate.json"
            release.write_json(aggregate, {"accepted": True, "plan": self.plan, "artifacts": self.artifacts})
            for number, existing in enumerate(((), ("wheel",), ("sdist",), ("wheel", "sdist"))):
                response = {"info": {"name": self.plan["name"], "version": self.plan["sdk_version"]}, "urls": [
                    {"filename": self.artifacts[kind]["filename"], "size": self.artifacts[kind]["size"],
                     "digests": {"sha256": self.artifacts[kind]["sha256"]}, "yanked": False,
                     "packagetype": "bdist_wheel" if kind == "wheel" else "sdist",
                     "url": "https://files.pythonhosted.org/" + kind} for kind in existing]}
                bodies = [io.BytesIO(json.dumps(response).encode()),
                          *[io.BytesIO((self.dist / self.artifacts[kind]["filename"]).read_bytes()) for kind in existing]]
                if not existing:
                    bodies = [urllib.error.HTTPError("fixture", 404, "version absent", {}, None)]
                args = argparse.Namespace(aggregate=aggregate, artifacts=self.dist, output=root / str(number),
                                          github_output=root / (str(number) + ".outputs"))
                with patch.object(release.urllib.request, "urlopen", side_effect=bodies):
                    decision = release.prepare_publish(args)
                missing = set(self.artifacts) - set(existing)
                self.assertEqual(decision["upload_required"], bool(missing))
                self.assertEqual({path.name for path in (args.output / "packages").iterdir()},
                                 {self.artifacts[kind]["filename"] for kind in missing})
                self.assertIn("upload_required=" + str(bool(missing)).lower(), args.github_output.read_text())
            for number, failure in enumerate(("hash", "metadata", "unknown", "race")):
                changed = copy.deepcopy(response)
                if failure == "metadata":
                    changed["urls"][0]["digests"]["sha256"] = "0" * 64
                bodies = [io.BytesIO(json.dumps(changed).encode()), io.BytesIO(b"tampered actual bytes")]
                if failure == "unknown":
                    bodies = [urllib.error.HTTPError("fixture", 503, "unknown", {}, None)]
                if failure == "race":
                    bodies = [io.BytesIO(json.dumps(changed).encode()),
                              urllib.error.HTTPError("fixture", 404, "file disappeared", {}, None)]
                args = argparse.Namespace(aggregate=aggregate, artifacts=self.dist, output=root / ("bad" + str(number)), github_output=None)
                with patch.object(release.urllib.request, "urlopen", side_effect=bodies):
                    with self.assertRaises((ValueError, urllib.error.HTTPError)):
                        release.prepare_publish(args)
                self.assertFalse(args.output.exists())

    def test_bootstrap_uses_public_host_authority_and_never_self_asserted_complete(self):
        """Derive a uniquely declared host and call both public gates; reject complete or malformed inputs.
        派生唯一声明宿主并调用两个公共门禁；拒绝完整或格式错误输入。
        """
        authority = unittest.mock.Mock()
        authority.candidate.PLATFORMS = {"core-host": ("fixture", "linux", "x86_64"),
                                        "core-other": ("fixture", "macos", "aarch64")}
        inputs = {"phase": "github-only", "complete": False, "core_tag": "v0.5.7",
                  "core_commit": "b" * 40, "platform": "core-host", "toolchain": "9.8.7"}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for number, changes in enumerate(({}, {"complete": True}, {"toolchain": "stable"}, {"platform": "core-other"})):
                authority.toolchain_inputs.return_value = dict(inputs, **changes)
                args = argparse.Namespace(core_root=ROOT, core_tag=inputs["core_tag"], core_commit=inputs["core_commit"],
                                          output=root / str(number), github_output=root / (str(number) + ".outputs"))
                with patch.object(release, "core_module", return_value=authority), patch.object(release, "run") as process:
                    if not changes:
                        self.assertEqual(release.bootstrap(args), inputs)
                        self.assertIn("toolchain=9.8.7", args.github_output.read_text())
                    else:
                        with self.assertRaisesRegex(ValueError, "different identity"):
                            release.bootstrap(args)
                        self.assertFalse((args.output / "toolchain.json").exists())
                    process.assert_not_called()
                authority.run_gate.assert_called_with(inputs["core_tag"], inputs["core_commit"], args.output / "core", phase="github-only")
                authority.toolchain_inputs.assert_called_with(args.output / "core/prerequisites.json", "core-host")

    def test_wrong_existing_git_tag_refuses_draft_mutations_and_unknown_is_not_absence(self):
        """Reject wrong Git tag before SDK/examples mutations and recognize absence only through HTTP 404.
        在 SDK 或示例修改前拒绝错误 Git 标签，且仅以 HTTP 404 识别不存在。
        """
        authority = unittest.mock.Mock()
        for tag in ("v0.5.7", "examples-v0.5.7"):
            with patch.dict(os.environ, {"GITHUB_REF": "refs/heads/main", "GITHUB_TOKEN": "fixture-only", "GH_TOKEN": "fixture-only"}), \
                    patch.object(release, "release_get", side_effect=[{"default_branch": "main"}, {"object": {"type": "commit", "sha": "b" * 40}}]), \
                    patch.object(release.urllib.request, "build_opener") as opener, \
                    patch.object(release, "run") as mutate, patch.object(release, "find_release") as lookup:
                opener.return_value.open.return_value = io.BytesIO(b'{"ref":"fixture present"}')
                with self.assertRaisesRegex(ValueError, "tag differs"):
                    release.publish_immutable(authority, tag, "a" * 40, self.dist)
                mutate.assert_not_called()
                lookup.assert_not_called()
        with patch.dict(os.environ, {"GH_TOKEN": "fixture-only"}), patch.object(release.urllib.request, "build_opener") as opener:
            for status in (404, 503):
                opener.return_value.open.side_effect = urllib.error.HTTPError("fixture", status, "fixture", {}, None)
                if status == 404:
                    self.assertFalse(release.sdk_tag_available(authority, authority.Http(), "v0.5.7", "a" * 40))
                else:
                    with self.assertRaisesRegex(ValueError, "Cannot determine"):
                        release.sdk_tag_available(authority, authority.Http(), "v0.5.7", "a" * 40)

    def test_freeze_rejects_old_workflow_definition_and_core_default_mismatch(self):
        """Reject old definition/new checkout and independent core mismatch before public calls.
        在公共调用前拒绝旧定义配新检出及独立核心不匹配。
        """
        args = argparse.Namespace(root=ROOT, source_sha="a" * 40, core_tag="v999.0.0", core_commit="b" * 40,
                                  default_branch="main", core_root=ROOT, output=self.root / "freeze", github_output=None)
        env = {"GITHUB_SHA": args.source_sha, "GITHUB_WORKFLOW_SHA": "c" * 40, "GITHUB_REF": "refs/heads/main",
               "GITHUB_REPOSITORY": release.SDK_REPOSITORY}
        with patch.dict(os.environ, env), patch.object(release, "core_module") as authority:
            with self.assertRaisesRegex(ValueError, "definition SHA"):
                release.freeze(args)
            authority.assert_not_called()
        env["GITHUB_WORKFLOW_SHA"] = args.source_sha
        with patch.dict(os.environ, env), patch.object(release, "run", side_effect=[args.source_sha, ""]), patch.object(release, "core_module") as authority:
            with self.assertRaisesRegex(ValueError, "default asset tag"):
                release.freeze(args)
            authority.assert_not_called()

    def test_formal_proof_requires_separate_source_and_explicit_attempt_identities(self):
        """Reject source drift or missing positive attempt identities before remote consumption.
        在远程消费前拒绝源码漂移或缺少明确正数轮次身份。
        """
        args = argparse.Namespace(source_sha="a" * 40, sdk_version="0.5.7", core_tag="v0.5.7", core_commit="b" * 40,
                                  completion_source_sha="c" * 40, candidate_run_id=123, candidate_run_attempt=1,
                                  completion_run_id=456, completion_run_attempt=2,
                                  platform="fixture-platform", core_root=ROOT, output=self.root / "formal")
        coordinator = release.publication_coordinator()
        with patch.object(coordinator, "authorities") as authority, patch.object(coordinator.api, "verify_pypi") as consumer:
            with self.assertRaisesRegex(ValueError, "source to match"):
                coordinator.formal_proof(args)
            args.completion_source_sha = args.source_sha
            args.candidate_run_attempt = 0
            with self.assertRaisesRegex(ValueError, "positive explicit"):
                coordinator.formal_proof(args)
            authority.assert_not_called()
            consumer.assert_not_called()

    def test_duplicate_json_and_evidence_overwrite_fail(self):
        """Reject duplicate evidence keys and overwriting an existing report; return nothing.
        拒绝重复凭证键及覆盖现有报告；无返回值。
        """
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            path.write_text('{"accepted":true,"accepted":false}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                release.read_json(path)
            with self.assertRaises(FileExistsError):
                release.write_json(path, {"accepted": True})

    def test_cli_missing_arguments_and_skip_consumer_switch_fail(self):
        """Exercise production CLI rejection without HTTP/Cargo or external mutation; return nothing.
        在无 HTTP、Cargo 或外部修改下验证正式 CLI 拒绝；无返回值。
        """
        for arguments in (("validate",), ("formal-proof", "--skip-consumer"), ("recheck", "--fake-success")):
            result = subprocess.run([sys.executable, str(ROOT / "scripts/release/sdk_release.py"), *arguments],
                                    capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)

    def test_workflow_yaml_pins_and_publish_boundary(self):
        """Parse real workflows and assert fixed definition, separate interpreters and upload adjacency.
        解析真实工作流并断言固定定义、独立解释器及上传邻接。
        """
        import yaml
        workflow = yaml.load((ROOT / ".github/workflows/sdk-release.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.assertEqual(workflow["run-name"], "Python SDK ${{ inputs.source_sha }} ${{ inputs.mode }}")
        jobs = workflow["jobs"]
        publisher = jobs["publish"]
        self.assertEqual(publisher["environment"], "production")
        self.assertEqual(publisher["permissions"]["id-token"], "write")
        index = next(index for index, step in enumerate(publisher["steps"]) if step.get("uses", "").startswith("pypa/gh-action-pypi-publish@"))
        self.assertIn("sdk_release.py recheck", publisher["steps"][index - 1]["run"])
        self.assertEqual(publisher["steps"][index]["with"]["packages-dir"], "fresh-publication/upload/packages")
        self.assertEqual(publisher["steps"][index]["if"], "steps.publication.outputs.upload_required == 'true'")
        self.assertEqual(publisher["permissions"]["attestations"], "write")
        self.assertEqual(publisher["permissions"]["actions"], "read")
        native = json.dumps(jobs["native"])
        self.assertIn("steps.control.outputs.python-path", native)
        self.assertIn("steps.native-python.outputs.python-path", native)
        for filename in ("sdk-release.yml", "examples-release.yml"):
            value = yaml.load((ROOT / ".github/workflows" / filename).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
            for job in value["jobs"].values():
                if job["runs-on"] == "ubuntu-24.04" and any("sdk_release.py recheck" in step.get("run", "")
                        or "sdk_release.py freeze" in step.get("run", "") or "sdk_release.py formal-proof" in step.get("run", "")
                        for step in job["steps"]):
                    self.assertTrue(any("sdk_release.py bootstrap" in step.get("run", "") for step in job["steps"]))
                    self.assertTrue(any(step.get("env", {}).get("TOOLCHAIN") == "${{ steps.bootstrap.outputs.toolchain }}"
                                        for step in job["steps"]))
                for step in job["steps"]:
                    if "uses" in step:
                        self.assertRegex(step["uses"], r"@[0-9a-f]{40}$")
                    self.assertNotIn("--clobber", step.get("run", ""))
                    self.assertNotIn("rustup default", step.get("run", ""))
            self.assertNotIn("CORE_CONSUMER_TOOLCHAIN", json.dumps(value))

    def test_attestation_requires_crypto_and_certificate_run_attempt(self):
        """Require successful gh cryptography and exact certificate/predicate attempts; return nothing.
        要求成功 gh 密码校验及精确证书、predicate 尝试；无返回值。
        """
        expected = f"https://github.com/{release.SDK_REPOSITORY}/actions/runs/123/attempts/2"
        certificate = {"runInvocationURI": expected, "sourceRepositoryURI": "https://github.com/" + release.SDK_REPOSITORY,
                       "sourceRepositoryDigest": "a" * 40, "buildSignerDigest": "a" * 40,
                       "runnerEnvironment": "github-hosted", "sourceRepositoryRef": "refs/heads/main",
                       "buildSignerURI": "https://github.com/" + release.SDK_REPOSITORY + "/.github/workflows/sdk-release.yml@refs/heads/main"}
        verified = [{"verificationResult": {"signature": {"certificate": certificate},
                     "statement": {"predicate": {"runDetails": {"metadata": {"invocationId": expected}}}}}}]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "verified.json"
            subject = Path(temporary) / "subject.bin"
            subject.write_bytes(b"actual fixture bytes")
            verified[0]["verificationResult"]["statement"]["subject"] = [{"name": subject.name, "digest": {"sha256": release.sha256(subject)}}]
            for certificate, predicate in ((expected, expected), (expected.replace("/2", "/1"), expected),
                                            (expected, expected.replace("/2", "/1"))):
                changed = copy.deepcopy(verified)
                changed[0]["verificationResult"]["signature"]["certificate"]["runInvocationURI"] = certificate
                changed[0]["verificationResult"]["statement"]["predicate"]["runDetails"]["metadata"]["invocationId"] = predicate
                process = subprocess.CompletedProcess([], 0, stdout=json.dumps(changed), stderr="")
                with patch.object(release.subprocess, "run", return_value=process) as verifier:
                    if certificate == predicate == expected:
                        release.verify_attestation(subject, "bundle", "a" * 40, 123, 2, output)
                    else:
                        with self.assertRaisesRegex(ValueError, "another run or attempt"):
                            release.verify_attestation(subject, "bundle", "a" * 40, 123, 2, output)
                    command = verifier.call_args.args[0]
                    self.assertIn("--bundle", command)
                    self.assertIn("--source-digest", command)
                    self.assertIn("--signer-digest", command)
                    self.assertIn("--deny-self-hosted-runners", command)
            with patch.object(release.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["gh", "attestation", "verify"])):
                with self.assertRaises(subprocess.CalledProcessError):
                    release.verify_attestation(subject, "bundle", "a" * 40, 123, 2, output)

    def test_rewritten_self_hash_group_rejected_before_fresh_pypi(self):
        """Reject edited aggregate/self-hashes despite unchanged successful issuer before fresh consumption.
        即使成功签发任务未变，也在新消费前拒绝修改后的聚合结果及自摘要。
        """
        plan, prerequisite, reports = self.evidence()
        for report in reports:
            report["log_sha256"] = "0" * 64
        aggregate = release.aggregate_reports(plan, self.artifacts, reports, prerequisite)
        content = json.dumps(aggregate).encode()
        proof = {"accepted": True, "aggregate_sha256": __import__("hashlib").sha256(content).hexdigest()}
        names = ("recovery-binding.json", "candidate-attestation.jsonl")
        bodies = {name: content for name in names}
        bodies["recovery-binding.json"] = json.dumps(proof).encode()
        bodies["candidate-attestation.jsonl"] = b'{"forged":"unsigned self-authored bundle"}'
        assets = {name: {"url": name, "name": name} for name in names}
        run_record = {"status": "completed", "conclusion": "success", "head_sha": plan["source_sha"],
                      "event": "workflow_dispatch", "path": ".github/workflows/sdk-release.yml", "run_attempt": 1,
                      "head_repository": {"full_name": release.SDK_REPOSITORY},
                      "display_title": f"Python SDK {plan['source_sha']} publish"}
        authority = unittest.mock.Mock()
        authority.Http.return_value.get.side_effect = lambda url, binary=False: (bodies[url], {})
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(source_sha=plan["source_sha"], sdk_version=plan["sdk_version"],
                                      core_tag=plan["core_tag"], core_commit=plan["core_commit"], candidate_run_id=123,
                                      candidate_run_attempt=1, completion_run_id=456, completion_run_attempt=2,
                                      completion_source_sha=plan["source_sha"],
                                      platform="fixture-platform", core_root=ROOT, output=Path(temporary) / "formal")
            coordinator = release.publication_coordinator()
            with patch.object(coordinator, "checked_source"), patch.object(coordinator, "authorities", return_value=(authority, unittest.mock.Mock(BINDING_FILENAME="recovery-binding.json"))), \
                    patch.object(release, "sdk_tag"), \
                    patch.object(release, "release_assets", return_value=assets), \
                    patch.object(release, "release_get", return_value={"id": 9, "draft": False, "prerelease": False}), \
                    patch.object(release.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["gh", "attestation", "verify"])) as verifier, \
                    patch.object(release, "verify_pypi") as consumer:
                with self.assertRaises(subprocess.CalledProcessError):
                    coordinator.api.sdk_tag = release.sdk_tag
                    coordinator.api.release_get = release.release_get
                    coordinator.api.release_assets = release.release_assets
                    coordinator.api.verify_pypi = release.verify_pypi
                    coordinator.formal_proof(args)
                self.assertEqual(verifier.call_args.args[0][:3], ["gh", "attestation", "verify"])
                consumer.assert_not_called()
                self.assertFalse((args.output / "accepted.json").exists())

    def test_draft_upload_readback_publish_order_and_final_no_append(self):
        """Publish all fixture bytes through draft first and reject appending to final; return nothing.
        先经草稿发布全部夹具字节，并拒绝向正式发布追加；无返回值。
        """
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "first").write_bytes(b"one")
            (directory / "second").write_bytes(b"two")
            authority = unittest.mock.Mock()
            assets, bodies, commands = {}, {}, []
            record = {"id": 9, "tag_name": "v0.5.7", "draft": True, "prerelease": False, "target_commitish": "a" * 40, "immutable": False}
            authority.Http.return_value.get.side_effect = lambda url, binary=False: (bodies[url], {})
            def command(arguments, cwd=None, env=None):
                """Record controlled publication commands and fixture uploads; return empty tool output.
                记录受控发布命令及夹具上传；返回空工具输出。
                """
                commands.append(arguments)
                if arguments[1] == "api":
                    return json.dumps({"id": 9})
                if arguments[1:3] == ["release", "upload"]:
                    path = Path(arguments[4])
                    bodies[path.name] = path.read_bytes()
                    assets[path.name] = {"name": path.name, "url": path.name}
                if arguments[1:3] == ["release", "edit"]:
                    record["draft"] = False
                return ""
            env = {"GITHUB_REF": "refs/heads/main", "GITHUB_TOKEN": "fixture-test-only"}
            def api(http, path):
                """Expose drafts by actual ID only; published-by-tag lookups always fail in this fixture.
                仅以实际 ID 暴露草稿；本夹具正式标签查询始终失败。
                """
                if path.startswith("releases/tags/"):
                    raise urllib.error.HTTPError("fixture", 404, "draft is not published", {}, None)
                return {"default_branch": "main"} if not path else record
            with patch.dict(os.environ, env), patch.object(release, "run", side_effect=command), \
                    patch.object(release, "find_release", side_effect=[None, record, record]), \
                    patch.object(release, "sdk_tag_available", return_value=False), \
                    patch.object(release, "release_get", side_effect=api), \
                    patch.object(release, "release_assets", side_effect=lambda http, release_id: dict(assets)), patch.object(release, "sdk_tag"):
                state = release.publish_immutable(authority, "v0.5.7", "a" * 40, directory)
                self.assertIs(state["server_release_immutable"], False)
                self.assertIn("draft=true", commands[0])
                self.assertEqual([item[1] for item in commands], ["api", "release", "release", "release"])
                self.assertIn("--draft=false", commands[-1])
                commands.clear()
                record["draft"] = True
                record["immutable"] = True
                (directory / "third").write_bytes(b"three")
                state = release.publish_immutable(authority, "v0.5.7", "a" * 40, directory)
                self.assertIs(state["server_release_immutable"], True)
                self.assertEqual([item[2] for item in commands], ["upload", "edit"])
                commands.clear()
                assets.pop("second")
                with self.assertRaisesRegex(ValueError, "cannot accept additional assets"):
                    release.publish_immutable(authority, "v0.5.7", "a" * 40, directory)
                self.assertFalse(any(item[2] == "upload" for item in commands))

    def test_draft_discovery_uses_complete_authenticated_pages(self):
        """Find unique draft through a short page's Link and reject ambiguous tags; return nothing.
        经短页 Link 查找唯一草稿并拒绝歧义标签；无返回值。
        """
        authority = unittest.mock.Mock()
        authority.candidate.decode_json.side_effect = json.loads
        http = unittest.mock.Mock()
        draft = {"id": 9, "tag_name": "v0.5.7", "draft": True}
        http.get.side_effect = [(b'[{"id":8,"tag_name":"other"}]', {"Link": '<next>; rel="next"'}),
                                (json.dumps([draft]).encode(), {})]
        self.assertEqual(release.find_release(authority, http, "v0.5.7"), draft)
        self.assertEqual(http.get.call_count, 2)
        http.get.side_effect = [(json.dumps([draft, dict(draft, id=10)]).encode(), {})]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            release.find_release(authority, http, "v0.5.7")

    def recovery_authority(self):
        """Load the real shared module from explicit SDK_RELEASE_TEST_CORE_ROOT; return its read-only authority.
        从明确 SDK_RELEASE_TEST_CORE_ROOT 加载真实共享模块；返回其只读权威。
        """
        # Test only presence so a missing fixture cannot expose the process environment in assertion output.
        # 仅检查是否存在，避免缺失夹具时通过断言输出暴露进程环境变量。
        self.assertTrue("SDK_RELEASE_TEST_CORE_ROOT" in os.environ, "Set the explicit frozen core checkout for shared-authority release fixtures")
        root = Path(os.environ["SDK_RELEASE_TEST_CORE_ROOT"]).resolve()
        sys.path.insert(0, str(root / "scripts/release"))
        import sdk_recovery
        self.assertEqual(Path(sdk_recovery.__file__).resolve(), root / "scripts/release/sdk_recovery.py")
        return sdk_recovery

    def signature_fixture(self, subject, bundle, source_sha, run_id, attempt, output, **kwargs):
        """Supply explicitly controlled normalized verifier facts for inventory logic, never a real signature proof.
        为清单逻辑提供明确受控的归一化验签事实，绝不作为真实签名证明。
        """
        self.assertEqual(Path(bundle).read_bytes(), b"controlled official-verifier fixture")
        return {"verified_subjects": {Path(subject).name: release.sha256(subject)},
                "verified_invocation_uri": f"https://github.com/{release.SDK_REPOSITORY}/actions/runs/{run_id}/attempts/{attempt}",
                "verified_source_sha": source_sha}

    def candidate_fixture(self, root):
        """Build a signed-inventory logic fixture with real packages/reports and original artifact-only identity.
        使用真实包及报告构建签名清单逻辑夹具，并保留原仅产物身份。
        """
        recovery = self.recovery_authority()
        coordinator = release.publication_coordinator()
        # Existing orchestration fixtures explicitly replace the unavailable real Core archive/native boundary.
        # 既有编排夹具显式替换其不具备的真实 Core 归档及原生边界。
        coordinator.core_proof_members = Mock(side_effect=lambda report, _: {
            path.relative_to(Path(report).parent).as_posix(): path
            for path in sorted(Path(report).parent.rglob("*")) if path.is_file()})
        authority = unittest.mock.Mock(MAX_BODY_BYTES=recovery.MAX_ARTIFACT_BYTES)
        authority.candidate.PLATFORMS = {"fixture-platform": ("fixture", "linux", "x86_64"),
                                        "fixture-other": ("fixture", "macos", "aarch64")}
        plan, prerequisite, reports = self.evidence()
        plan["mode"] = "artifact-only"
        plan["matrix"] = [{"platform": platform, "python_role": role, "python": plan["python"][role],
                           "runner": release.runner_for(record[1], record[2])}
                          for platform, record in authority.candidate.PLATFORMS.items() for role in release.ROLES]
        evidence, report_root, dist = root / "evidence", root / "reports", root / "distributions"
        (evidence / "core").mkdir(parents=True)
        release.write_json(evidence / "core/prerequisites.json", prerequisite)
        plan["prerequisites_sha256"] = release.sha256(evidence / "core/prerequisites.json")
        release.write_json(evidence / "plan.json", plan)
        dist.mkdir()
        for record in self.artifacts.values():
            shutil.copyfile(self.dist / record["filename"], dist / record["filename"])
        release.write_json(dist / "artifacts.json", self.artifacts)
        for report in reports:
            directory = report_root / (report["platform"] + "-" + report["python_role"])
            directory.mkdir(parents=True)
            (directory / "report.log").write_bytes(("controlled native log: " + directory.name).encode())
            report["log_sha256"] = release.sha256(directory / "report.log")
            release.write_json(directory / "report.json", report)
        aggregate = root / "aggregate.json"
        release.aggregate(argparse.Namespace(plan=evidence / "plan.json", artifacts=dist,
            prerequisites=evidence / "core/prerequisites.json", reports=report_root, output=aggregate))
        args = argparse.Namespace(aggregate=aggregate, artifacts=dist, evidence=evidence, reports=report_root,
                                  core_root=root, output=root / "candidate", github_output=root / "outputs")
        env = {"GITHUB_REPOSITORY": release.SDK_REPOSITORY, "GITHUB_SHA": plan["source_sha"],
               "GITHUB_WORKFLOW_SHA": plan["source_sha"], "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
        with patch.object(coordinator, "authorities", return_value=(authority, recovery)), patch.dict(os.environ, env):
            binding = coordinator.candidate_prepare(args)
        coordinator.core_proof_members.assert_called_once_with(evidence / "core/prerequisites.json", authority)
        (args.output / release.CANDIDATE_ATTESTATION).write_bytes(b"controlled official-verifier fixture")
        coordinator.api.verify_attestation = self.signature_fixture
        return SimpleNamespace(coordinator=coordinator, authority=authority, recovery=recovery,
                               plan=plan, binding=binding, candidate=args.output, root=root)

    def attempt_http(self, fixture, *, candidate_conclusion="failure", completion_conclusion="success", missing_job=None):
        """Expose only two exact attempt endpoints with real documented fields; return controlled read-only HTTP.
        仅暴露两个精确轮次端点及真实文档字段；返回受控只读 HTTP。
        """
        jobs = ["freeze-build", "aggregate", "candidate-evidence", *[
            "native-" + row["platform"] + "-" + row["python_role"] for row in fixture.plan["matrix"]]]
        http = unittest.mock.Mock()
        def read(url):
            """Return the explicitly selected original/current attempt or fail unexpected endpoints.
            返回明确选定的原始或当前轮次，或拒绝意外端点。
            """
            candidate = "/runs/123/attempts/1" in url
            self.assertTrue(candidate or "/runs/456/attempts/2" in url, url)
            run_id, attempt = (123, 1) if candidate else (456, 2)
            selected = jobs if candidate else ["publish"]
            if "/jobs?" in url:
                rows = [{"id": index + 1, "run_id": run_id, "head_sha": fixture.plan["source_sha"],
                         "run_url": f"https://api.github.com/repos/{release.SDK_REPOSITORY}/actions/runs/{run_id}",
                         "name": name, "status": "completed", "conclusion": "success"}
                        for index, name in enumerate(selected) if name != missing_job]
                return {"total_count": len(rows), "jobs": rows}
            return {"id": run_id, "run_attempt": attempt, "repository": {"full_name": release.SDK_REPOSITORY},
                    "head_repository": {"full_name": release.SDK_REPOSITORY}, "head_sha": fixture.plan["source_sha"],
                    "path": release.SDK_WORKFLOW, "workflow_id": 789, "status": "completed",
                    "conclusion": candidate_conclusion if candidate else completion_conclusion,
                    "event": "workflow_dispatch", "display_title": f"Python SDK {fixture.plan['source_sha']} " + ("artifact-only" if candidate else "recover")}
        http.json.side_effect = read
        return http

    def test_original_failed_artifact_only_candidate_preserves_status_and_requires_every_gate(self):
        """Allow verified original failure after successful gates without promoting its status; reject a missing gate.
        允许成功门禁后的已验证原失败轮次，但不提升其状态；拒绝缺少门禁。
        """
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.candidate_fixture(Path(temporary))
            for number, missing in enumerate((None, "candidate-evidence")):
                http = self.attempt_http(fixture, missing_job=missing)
                fixture.authority.Http.return_value = http
                output = fixture.root / str(number)
                output.mkdir()
                arguments = dict(source_sha=fixture.plan["source_sha"], run_id=123, attempt=1,
                    core_tag=fixture.plan["core_tag"], core_commit=fixture.plan["core_commit"], sdk_version=fixture.plan["sdk_version"])
                if missing:
                    with self.assertRaisesRegex(ValueError, "Missing required"):
                        fixture.coordinator.validate_candidate(fixture.candidate, output, fixture.authority, fixture.recovery, **arguments)
                else:
                    receipt = fixture.coordinator.validate_candidate(fixture.candidate, output, fixture.authority, fixture.recovery, **arguments)
                    self.assertEqual(receipt["attempt_evidence"]["attempt"]["conclusion"], "failure")
                    self.assertEqual(release.read_json(fixture.candidate / "aggregate.json")["plan"]["mode"], "artifact-only")
                self.assertTrue(all("/attempts/1" in call.args[0] for call in http.json.call_args_list))

    def test_original_signed_inventory_tamper_fails_before_attempt_or_mutation(self):
        """Reject changed real payload and extra files before issuer lookup or publication.
        在签发者查询或发布前拒绝真实载荷变化及额外文件。
        """
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.candidate_fixture(Path(temporary))
            path = fixture.candidate / self.artifacts["wheel"]["filename"]
            path.write_bytes(path.read_bytes() + b"edited")
            with self.assertRaisesRegex(ValueError, "inventory|evidence"):
                fixture.coordinator.verified_binding(fixture.candidate, fixture.recovery, fixture.plan["source_sha"], 123, 1)
            fixture.authority.Http.assert_not_called()
            path.write_bytes((self.dist / path.name).read_bytes())
            (fixture.candidate / "extra.json").write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError, "inventory|evidence"):
                fixture.coordinator.verified_binding(fixture.candidate, fixture.recovery, fixture.plan["source_sha"], 123, 1)

    def test_missing_original_artifact_never_rebuilds_or_publishes(self):
        """Propagate expired original download failure without new candidate or registry/release mutation.
        传播原下载过期错误，不创建新候选或修改 registry、Release。
        """
        coordinator = release.publication_coordinator()
        recovery = unittest.mock.Mock()
        recovery.download_artifact.side_effect = ValueError("Original artifact expired")
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(source_sha="a" * 40, core_tag="v0.5.7", core_commit="b" * 40,
                candidate_run_id=123, candidate_run_attempt=1, candidate_artifact_id=99, core_root=ROOT, output=Path(temporary) / "resolved")
            with patch.object(coordinator, "authorities", return_value=(unittest.mock.Mock(), recovery)), \
                    patch.object(coordinator, "checked_source"), patch.dict(os.environ, {"GITHUB_SHA": args.source_sha, "GITHUB_WORKFLOW_SHA": args.source_sha}), \
                    patch.object(coordinator.api, "publish_immutable") as publish:
                with self.assertRaisesRegex(ValueError, "expired"):
                    coordinator.candidate_resolve(args)
                publish.assert_not_called()
                self.assertFalse(args.output.exists())

    def test_current_artifact_only_intent_cannot_authorize_completion(self):
        """Refuse current artifact-only promotion before source checks or HTTP.
        在源码检查或 HTTP 前拒绝当前仅产物模式提升。
        """
        coordinator = release.publication_coordinator()
        authority = unittest.mock.Mock()
        with patch.object(coordinator, "checked_source") as source:
            with self.assertRaisesRegex(ValueError, "explicit publish or recover"):
                coordinator.current_intent("artifact-only", "a" * 40, authority)
            source.assert_not_called()
            authority.Http.assert_not_called()

    def test_completion_attempt_failure_cannot_borrow_latest_success(self):
        """Call the real common completion verifier with exact failed attempt; latest endpoints are forbidden.
        以精确失败轮次调用真实公共完成验证器；禁止最新端点。
        """
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.candidate_fixture(Path(temporary))
            http = self.attempt_http(fixture, completion_conclusion="failure")
            with self.assertRaisesRegex(ValueError, "completion attempt did not succeed"):
                fixture.recovery.verify_attempt(http, repository=release.SDK_REPOSITORY, workflow_path=release.SDK_WORKFLOW,
                    source_sha=fixture.plan["source_sha"], run_id=456, run_attempt=2, required_jobs=["publish"], phase="completion")
            self.assertEqual(len(http.json.call_args_list), 1)
            self.assertIn("/attempts/2", http.json.call_args.args[0])

    def test_completion_rerun_uses_new_receipt_and_never_reissues_original_assets(self):
        """Prepare two current attempts using one original inventory and verify independent immutable targets.
        使用一份原清单准备两个当前轮次，并验证独立不可变目标。
        """
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.candidate_fixture(Path(temporary))
            resolved = fixture.root / "resolved"
            resolved.mkdir()
            shutil.copytree(fixture.candidate, resolved / "candidate")
            wrapper = fixture.coordinator.verified_binding(fixture.candidate, fixture.recovery, fixture.plan["source_sha"], 123, 1)
            release.write_json(resolved / "candidate-receipt.json", {"binding": wrapper,
                "candidate_attestation_sha256": release.sha256(fixture.candidate / release.CANDIDATE_ATTESTATION)})
            release.write_json(resolved / "artifact-download.json", {"artifact": {"id": 99}})
            aggregate = resolved / "candidate/aggregate.json"
            core = fixture.root / "fresh-core"
            core.mkdir()
            release.write_json(core / "prerequisites.json", self.evidence()[1])
            proof = fixture.root / "consumer.json"
            release.write_json(proof, {"accepted": True, "aggregate_sha256": release.sha256(aggregate), "artifacts": self.artifacts,
                "source_sha": fixture.plan["source_sha"], "sdk_version": fixture.plan["sdk_version"], "core_commit": fixture.plan["core_commit"],
                "platform": "fixture-platform", "library_sha256": "c" * 64})
            (proof.parent / "native.log").write_bytes(b"controlled fresh native log fixture")
            publication = fixture.root / "publication.json"
            release.write_json(publication, {"aggregate_sha256": release.sha256(aggregate), "artifacts": self.artifacts,
                "prerequisites_sha256": release.sha256(core / "prerequisites.json")})
            state = fixture.root / "main.json"
            release.write_json(state, {"release_id": 17, "tag": "v" + fixture.plan["sdk_version"],
                                      "source_sha": fixture.plan["source_sha"], "server_release_immutable": True})
            original_files = fixture.coordinator.files(resolved / "candidate")
            completions = []
            for attempt in (2, 3):
                current = {"source_sha": fixture.plan["source_sha"], "run_id": 456, "run_attempt": attempt, "completion_intent": "recover"}
                args = argparse.Namespace(candidate=resolved, core_root=ROOT, intent="recover", proof=proof,
                    publication_proof=publication, publication_prerequisites=core / "prerequisites.json",
                    main_release_state=state, output=fixture.root / ("attempt-" + str(attempt)) / "completion")
                with patch.object(fixture.coordinator, "authorities", return_value=(fixture.authority, fixture.recovery)), \
                        patch.object(fixture.coordinator, "current_intent", return_value=current), patch.object(fixture.coordinator, "main_release"), \
                        patch.object(fixture.coordinator.api, "publish_immutable", return_value={"release_id": attempt}) as publish:
                    fixture.coordinator.core_proof_members.reset_mock()
                    completion = fixture.coordinator.completion_prepare(args)
                    fixture.coordinator.core_proof_members.assert_called_once_with(core / "prerequisites.json", fixture.authority)
                    publish.assert_not_called()
                    bundle = fixture.root / ("bundle-" + str(attempt))
                    bundle.write_bytes(b"controlled official-verifier fixture")
                    fixture.coordinator.publish_completion(argparse.Namespace(prepared=args.output, bundle=bundle,
                        core_root=ROOT, candidate=resolved, intent="recover"))
                    self.assertEqual(publish.call_args.args[1], f"recovery-v{fixture.plan['sdk_version']}-r456-a{attempt}")
                    self.assertEqual(publish.call_args.args[3], args.output)
                    self.assertEqual(completion["candidate_artifact_id"], 99)
                    self.assertEqual(completion["candidate_inventory"], fixture.binding["inventory"])
                    completions.append((args.output / "completion.json").read_bytes())
            self.assertNotEqual(*completions)
            self.assertEqual(fixture.coordinator.files(resolved / "candidate"), original_files)

    def test_examples_zip_and_sidecar_reproduce_exact_bytes_across_retries(self):
        """Run example packaging twice on identical frozen files/public proof; ZIP_STORED makes bytes repeatable.
        对相同冻结文件及公共证明两次运行示例打包；ZIP_STORED 使字节可重复。
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            formal = root / "formal"
            (formal / "fresh-pypi").mkdir(parents=True)
            release.write_json(formal / "aggregate.json", {"plan": self.plan})
            release.write_json(formal / "fresh-pypi/pypi-proof.json", {"accepted": True,
                "aggregate_sha256": release.sha256(formal / "aggregate.json"), "artifacts": self.artifacts,
                "source_sha": self.plan["source_sha"], "sdk_version": self.plan["sdk_version"]})
            release.write_json(formal / "resolved-inputs.json", {"library": "fixture", "library_sha256": "0" * 64, "description": "fixture"})
            tracked = "examples/embedded_runtime.py\0LICENSE\0README.md\0"
            env = {"GITHUB_SHA": self.plan["source_sha"], "GITHUB_WORKFLOW_SHA": self.plan["source_sha"], "GITHUB_REF": "refs/heads/main"}
            def process(arguments, cwd=None, env=None):
                """Isolate native/Git execution while exercising actual source bytes and archive construction.
                隔离原生及 Git 执行，同时验证实际源码字节及归档构造。
                """
                if arguments[:2] == ["git", "rev-parse"]:
                    return self.plan["source_sha"]
                if arguments[:2] == ["git", "status"]:
                    return ""
                if arguments[:2] == ["git", "ls-files"]:
                    return tracked
                return "controlled installed-example invocation fixture"
            with patch.dict(os.environ, env), patch.object(release, "run", side_effect=process):
                first = release.examples(argparse.Namespace(formal_proof=formal, root=ROOT, output=root / "first"))
                second = release.examples(argparse.Namespace(formal_proof=formal, root=ROOT, output=root / "second"))
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(Path(str(first) + ".sha256").read_bytes(), Path(str(second) + ".sha256").read_bytes())
            import zipfile
            with zipfile.ZipFile(first) as archive:
                self.assertTrue(all(member.compress_type == zipfile.ZIP_STORED for member in archive.infolist()))

    def test_two_chain_formal_proof_requires_exact_completion_before_fresh_consumer(self):
        """Exercise both real inventories/attempt APIs and package bytes; reject altered completion before fresh consumption.
        验证两份真实清单、轮次 API 及包字节；在新消费前拒绝变化完成凭据。
        """
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.candidate_fixture(Path(temporary))
            coordinator = fixture.coordinator
            http = self.attempt_http(fixture)
            fixture.authority.Http.return_value = http
            completion_root = fixture.root / "completion"
            completion_root.mkdir()
            release.write_json(completion_root / "formal-consumer.json", {"controlled_original_consumer_fixture": True})
            (completion_root / "formal-consumer.log").write_bytes(b"controlled original consumer log fixture")
            release.write_json(completion_root / "core-prerequisites.json", {"controlled_original_core_fixture": True})
            coordinator.archive_tree(completion_root / "completion-evidence.zip", {"core": fixture.root / "evidence/core"},
                                     fixture.root / "evidence/core", fixture.authority)
            main_state = {"release_id": 17, "tag": "v" + fixture.plan["sdk_version"],
                          "source_sha": fixture.plan["source_sha"], "server_release_immutable": True}
            wrapper = coordinator.verified_binding(fixture.candidate, fixture.recovery, fixture.plan["source_sha"], 123, 1)
            completion = {"schema_version": 2, "kind": "sdk-completion", "repository": release.SDK_REPOSITORY,
                "workflow_path": release.SDK_WORKFLOW, "sdk_source_sha": fixture.plan["source_sha"],
                "sdk_version": fixture.plan["sdk_version"], "core_tag": fixture.plan["core_tag"], "core_commit": fixture.plan["core_commit"],
                "completion_source_sha": fixture.plan["source_sha"], "candidate_run_id": 123, "candidate_run_attempt": 1,
                "candidate_artifact_id": 99, "completion_run_id": 456, "completion_run_attempt": 2, "completion_intent": "recover",
                "main_release": main_state, "candidate_binding_sha256": wrapper["binding_sha256"],
                "candidate_attestation_sha256": release.sha256(fixture.candidate / release.CANDIDATE_ATTESTATION),
                "candidate_inventory": fixture.binding["inventory"], "artifacts": self.artifacts,
                "inventory": fixture.recovery.inventory_for(coordinator.files(completion_root))}
            # Controlled signature facts isolate orchestration only; the independent crypto rejection test remains mandatory.
            # 受控签名事实仅隔离协调逻辑；独立密码验签拒绝测试仍为必需。
            release.write_json(completion_root / "completion.json", completion)
            (completion_root / "completion-attestation.jsonl").write_bytes(b"controlled official-verifier fixture")
            main_files = coordinator.files(fixture.candidate)
            completed_files = coordinator.files(completion_root)
            http.get.side_effect = lambda url, binary=False: ((main_files if url.startswith("main/") else completed_files)[url.split("/", 1)[1]], {})
            def assets(client, release_id):
                """Return exact fixture assets by actual release ID without draft/tag guessing.
                以实际发行 ID 返回精确夹具资产，不猜测草稿或标签。
                """
                prefix, bodies = ("main", main_files) if release_id == 17 else ("completion", completed_files)
                return {name: {"name": name, "url": prefix + "/" + name} for name in bodies}
            def record(client, path):
                """Return the two exact public release records for explicit source/attempt tags.
                返回两份对应明确源码及轮次标签的精确公共发行记录。
                """
                original = path == "releases/tags/" + main_state["tag"]
                return {"id": 17 if original else 18, "tag_name": main_state["tag"] if original else coordinator.completion_tag(fixture.plan["sdk_version"], 456, 2),
                        "draft": False, "prerelease": False, "immutable": True}
            def fresh_core(original, output):
                """Write controlled fresh prerequisite bytes without executing Cargo; return their explicit test result.
                不执行 Cargo，写入受控新前置字节；返回其明确测试结果。
                """
                output.mkdir()
                value = {"complete": True, "phase": "complete"}
                release.write_json(output / "prerequisites.json", value)
                return value
            def fresh_pypi(args):
                """Write controlled new consumer bytes so accepted header hashing is exercised without registry access.
                写入受控新消费者字节，以无 registry 访问验证 accepted 头摘要。
                """
                args.output.mkdir()
                release.write_json(args.output / "pypi-proof.json", {"controlled_fresh_consumer_fixture": True})
            fixture.authority.recheck.side_effect = fresh_core
            fixture.authority.resolve_sdk_inputs.return_value = {"controlled_resolved_inputs_fixture": True}
            coordinator.api.release_get = record
            coordinator.api.release_assets = assets
            coordinator.api.sdk_tag = unittest.mock.Mock()
            with patch.object(coordinator, "checked_source"), patch.object(coordinator, "authorities", return_value=(fixture.authority, fixture.recovery)), \
                    patch.object(coordinator.api, "verify_pypi", side_effect=fresh_pypi) as consumer:
                args = argparse.Namespace(source_sha=fixture.plan["source_sha"], completion_source_sha=fixture.plan["source_sha"],
                    sdk_version=fixture.plan["sdk_version"], core_tag=fixture.plan["core_tag"], core_commit=fixture.plan["core_commit"],
                    candidate_run_id=123, candidate_run_attempt=1, completion_run_id=456, completion_run_attempt=2,
                    core_root=ROOT, platform="fixture-platform", output=fixture.root / "formal-good")
                accepted = coordinator.formal_proof(args)
                self.assertEqual(accepted["candidate_run_id"], "123")
                self.assertEqual(accepted["completion_run_id"], "456")
                self.assertEqual(accepted["candidate_run_attempt"], 1)
                self.assertEqual(accepted["completion_run_attempt"], 2)
                self.assertEqual(accepted["registry_consumer_sha256"], release.sha256(args.output / accepted["registry_consumer_file"]))
                original_evidence = release.read_json(args.output / "formal-proof.json")["candidate_attempt_evidence"]
                self.assertEqual(original_evidence["attempt"]["conclusion"], "failure")
                self.assertEqual(consumer.call_count, 1)
                for number, change in enumerate(({"candidate_binding_sha256": "0" * 64}, {"candidate_artifact_id": 0},
                                                  {"artifacts": {}}, {"unexpected_field": True})):
                    completed_files["completion.json"] = json.dumps(dict(completion, **change)).encode()
                    args.output = fixture.root / ("formal-bad-" + str(number))
                    with self.assertRaises(ValueError):
                        coordinator.formal_proof(args)
                    self.assertEqual(consumer.call_count, 1)
                    self.assertFalse((args.output / "accepted.json").exists())
                completed_files["completion.json"] = json.dumps(completion).encode()
                http.json.side_effect = self.attempt_http(fixture, completion_conclusion="failure").json.side_effect
                args.output = fixture.root / "formal-failed-attempt"
                with self.assertRaisesRegex(ValueError, "completion attempt did not succeed"):
                    coordinator.formal_proof(args)
                self.assertEqual(consumer.call_count, 1)

    def publication_http_fixture(self, fixture, *, draft, bodies):
        """Serve actual paginated release/asset algorithms from controlled bytes; return mutable API state and command recorder.
        以受控字节服务真实分页发布及资产算法；返回可变 API 状态与命令记录器。
        """
        http = unittest.mock.Mock()
        record = {"id": 17, "tag_name": "v" + fixture.plan["sdk_version"], "draft": draft,
                  "prerelease": False, "target_commitish": fixture.plan["source_sha"], "immutable": True}
        state = SimpleNamespace(http=http, record=record, bodies=bodies, commands=[])
        base = "https://api.github.com/repos/" + release.SDK_REPOSITORY + "/"
        def api(url):
            """Read exact repository/release/asset pages, rejecting all unmodeled endpoints.
            读取精确仓库、发布及资产页，拒绝所有未建模端点。
            """
            # The empty REST path is the canonical repository root; asset paths retain the original slash separator.
            # 空 REST 路径为规范仓库根；资产路径保留原斜杠分隔符。
            if url == "https://api.github.com/repos/" + release.SDK_REPOSITORY:
                return {"default_branch": "main"}
            if url == base + "releases/17":
                return dict(record)
            self.assertEqual(url, base + "releases/17/assets?per_page=100&page=1")
            return [{"name": name, "url": "controlled-body/" + name} for name in sorted(bodies)]
        def read(url, binary=False):
            """Return actual asset bytes or the authenticated draft discovery page.
            返回实际资产字节或已认证草稿发现页。
            """
            if url.startswith("controlled-body/"):
                return bodies[url.removeprefix("controlled-body/")], {}
            self.assertEqual(url, base + "releases?per_page=100&page=1")
            return json.dumps([record]).encode(), {}
        def command(arguments, cwd=None, env=None):
            """Model actual upload/edit effects while recording every mutation; return empty CLI output.
            建模实际上传及修改效果，同时记录每次变更；返回空 CLI 输出。
            """
            state.commands.append(arguments)
            if arguments[1:3] == ["release", "upload"]:
                path = Path(arguments[4])
                bodies[path.name] = path.read_bytes()
            else:
                self.assertEqual(arguments[1:3], ["release", "edit"])
                record["draft"] = False
            return ""
        http.json.side_effect = api
        http.get.side_effect = read
        fixture.authority.Http.return_value = http
        fixture.authority.candidate.decode_json.side_effect = fixture.recovery.candidate.decode_json
        state.command = command
        return state

    def test_extra_assets_and_published_missing_assets_refuse_every_mutation(self):
        """Reject original full/partial drafts with extras and published extra/missing sets using real remote enumeration.
        通过真实远端枚举算法，拒绝带额外资产的原完整或部分草稿，以及正式发布的额外或缺少资产集合。
        """
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.candidate_fixture(Path(temporary))
            required = fixture.coordinator.files(fixture.candidate)
            missing_name = self.artifacts["wheel"]["filename"]
            cases = ((True, True, False), (True, True, True), (False, True, False), (False, False, True))
            for draft, extra, missing in cases:
                bodies = dict(required)
                if missing:
                    bodies.pop(missing_name)
                if extra:
                    bodies["orphan-proof.json"] = b"unrelated original attempt receipt"
                state = self.publication_http_fixture(fixture, draft=draft, bodies=bodies)
                env = {"GITHUB_REF": "refs/heads/main", "GITHUB_TOKEN": "controlled-only", "GH_TOKEN": "controlled-only"}
                with self.subTest(draft=draft, extra=extra, missing=missing), patch.dict(os.environ, env), \
                        patch.object(release, "sdk_tag_available", return_value=True), patch.object(release, "sdk_tag"), \
                        patch.object(release, "run", side_effect=state.command):
                    with self.assertRaisesRegex(ValueError, "unexpected assets|cannot accept additional assets"):
                        release.publish_immutable(fixture.authority, state.record["tag_name"], fixture.plan["source_sha"], fixture.candidate)
                    self.assertEqual(state.commands, [])
                    self.assertEqual(state.record["draft"], draft)
                    self.assertTrue(any("/assets?" in call.args[0] for call in state.http.json.call_args_list))

    def test_finalize_reenumerates_exact_assets_after_upload_and_tag_check(self):
        """Reject late extra/missing remote assets before edit and allow only an exactly completed partial draft.
        在正式修改前拒绝迟到的额外或缺少远端资产，仅允许精确补全的部分草稿。
        """
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.candidate_fixture(Path(temporary))
            required = fixture.coordinator.files(fixture.candidate)
            missing_name = self.artifacts["wheel"]["filename"]
            for injection in (None, "extra", "missing"):
                bodies = dict(required)
                bodies.pop(missing_name)
                state = self.publication_http_fixture(fixture, draft=True, bodies=bodies)
                tag_reads = []
                def tag_read(authority, http, tag, source_sha):
                    """Inject only after the legitimate upload and immediately before final asset enumeration.
                    仅在合法上传之后、最终资产枚举紧邻边界前注入。
                    """
                    tag_reads.append(tag)
                    if len(tag_reads) == 2:
                        if injection == "extra":
                            bodies["orphan-proof.json"] = b"late unrelated receipt"
                        elif injection == "missing":
                            bodies.pop(missing_name)
                    return True
                env = {"GITHUB_REF": "refs/heads/main", "GITHUB_TOKEN": "controlled-only", "GH_TOKEN": "controlled-only"}
                with self.subTest(injection=injection), patch.dict(os.environ, env), \
                        patch.object(release, "sdk_tag_available", side_effect=tag_read), patch.object(release, "sdk_tag"), \
                        patch.object(release, "run", side_effect=state.command):
                    if injection:
                        with self.assertRaisesRegex(ValueError, "asset set differs"):
                            release.publish_immutable(fixture.authority, state.record["tag_name"], fixture.plan["source_sha"], fixture.candidate)
                        self.assertTrue(state.record["draft"])
                        self.assertEqual([call[2] for call in state.commands], ["upload"])
                    else:
                        actual = release.publish_immutable(fixture.authority, state.record["tag_name"], fixture.plan["source_sha"], fixture.candidate)
                        self.assertEqual(actual["release_id"], 17)
                        self.assertFalse(state.record["draft"])
                        self.assertEqual([call[2] for call in state.commands], ["upload", "edit"])
                        self.assertEqual(bodies, required)
                    self.assertEqual(Path(state.commands[0][4]).name, missing_name)
                    self.assertEqual(sum("/assets?" in call.args[0] for call in state.http.json.call_args_list), 2)


class CoreProofSelectionTests(unittest.TestCase):
    """Exercise original complete Core bytes with the real resolver; return no publication evidence.
    使用真实解析器验证原完整 Core 字节；不产生发布证明。
    """

    @unittest.skipUnless("SDK_RELEASE_TEST_CORE_PROOF" in os.environ, "Explicit original complete Core proof required")
    def test_audit_retention_missing_required_and_tampered_copy(self):
        """Select original proof, retain every audit file, and reject missing/tampered bytes without synthetic large data.
        选择原证明、保留全部审计文件，并拒绝缺失、篡改字节，不合成大数据。
        """
        # Original and shared authority are explicit read-only inputs, with no alternate directory probing.
        # Original 及 shared 权威为明确只读输入，不探测备用目录。
        original = Path(os.environ["SDK_RELEASE_TEST_CORE_PROOF"]).resolve(strict=True)
        authority_root = Path(os.environ["SDK_RELEASE_TEST_CORE_ROOT"]).resolve(strict=True)
        sys.path.insert(0, str(authority_root / "scripts/release"))
        import sdk_prerequisites as shared
        # Coordinator uses the real selector rather than the older orchestration fixture replacement.
        # Coordinator 使用真实选择函数，不使用旧编排夹具替代。
        coordinator = release.publication_coordinator()
        with tempfile.TemporaryDirectory(prefix="cp-") as temporary:
            # An independent short-path copy preserves producer bytes without Windows hard-link path limits.
            # 独立短路径副本保留生产者字节，不受 Windows 硬链接路径上限影响。
            root = Path(temporary) / "core"
            shutil.copytree(original, root, copy_function=shutil.copyfile)
            selected = coordinator.core_proof_members(root / "prerequisites.json", shared)
            self.assertIn("candidate/luaskills-ffi-sdk-windows-x64.tar.gz", selected)
            self.assertNotIn("candidate/luaskills-demo-ffi-windows-x64.tar.gz", selected)
            self.assertNotIn("downloads/assets/luaskills-ffi-sdk-windows-x64.tar.gz", selected)
            for path in (root / "registry").rglob("*"):
                if path.is_file():
                    self.assertEqual(selected[path.relative_to(root).as_posix()].read_bytes(), path.read_bytes())
            # Missing authenticated manifest must still fail before any archive selection succeeds.
            # 已认证清单缺失时，任何归档选择成功前仍必须失败。
            required = root / "downloads/candidate-manifest.json"
            required.unlink()
            with self.assertRaises(FileNotFoundError):
                coordinator.core_proof_members(root / "prerequisites.json", shared)
            shutil.copyfile(original / "downloads/candidate-manifest.json", required)
            # Even a discarded source copy must retain the actual official hash.
            # 即使是被省略的源码副本，也必须保留实际正式摘要。
            source = shared.candidate.read_json(root / "candidate/candidate-manifest.json")["source_archive"]["name"]
            copy = root / "downloads/assets" / source
            copy.unlink()
            copy.write_bytes(b"tampered archive copy")
            with self.assertRaisesRegex(ValueError, "differs from official asset"):
                coordinator.core_proof_members(root / "prerequisites.json", shared)


class ArtifactMediaTests(unittest.TestCase):
    """Exercise the SDK adapter through real Core HTTP Requests and artifact byte validation offline.
    离线通过真实 Core HTTP Request 及制品字节验证测试 SDK 适配器。
    """

    def test_bound_archive_media_and_original_core_byte_guards(self):
        """Prove original 415, exact bound-media repair and retained byte/endpoint guards; return nothing.
        证明原 415、精确绑定媒体修复及字节／端点护栏保留；无返回值。
        """
        # Standard-library fixtures replace only network I/O, never Core get/download or SDK media decisions.
        # 标准库夹具仅替换网络 I/O，绝不替换 Core get/download 或 SDK 媒体决策。
        import hashlib
        import urllib.error
        import zipfile
        # Load the explicit Core authority and adjacent SDK production module, never a copied implementation.
        # 加载明确 Core 权威及相邻 SDK 正式模块，绝不加载复制实现。
        root = Path(os.environ["SDK_RELEASE_TEST_CORE_ROOT"]).resolve(strict=True)
        sys.path.insert(0, str(root / "scripts/release"))
        import sdk_prerequisites as shared
        import sdk_recovery as recovery
        specification = importlib.util.spec_from_file_location("artifact_media_publication", ROOT / "scripts/release/sdk_publication.py")
        publication = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(publication)
        wrapper = publication.ArtifactHttp
        self.assertEqual(Path(shared.__file__).resolve(), root / "scripts/release/sdk_prerequisites.py")
        # Offline identities are explicit fixture values and make no official signing claim.
        # 离线身份为明确夹具值，不声称官方签名。
        endpoint = "https://api.github.com/repos/test/repo/actions/artifacts/77"
        archive_url = endpoint + "/zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("original.txt", b"original ZIP bytes")
        # Actual ZIP bytes are consumed by the unmodified Core digest/size/unpack implementation.
        # 实际 ZIP 字节由未修改 Core 的摘要／大小／解包实现消费。
        content = buffer.getvalue()
        metadata = {"id": 77, "name": recovery.candidate_artifact_name(123, 1), "expired": False,
                    "workflow_run": {"id": 123, "head_sha": "a" * 40}, "size_in_bytes": len(content),
                    "digest": "sha256:" + hashlib.sha256(content).hexdigest()}
        arguments = dict(repository="test/repo", source_sha="a" * 40, run_id=123, artifact_id=77,
                         artifact_name=metadata["name"])
        # Exact unrelated routes expose accidental broader binary rewrites without probing a real network.
        # 精确无关路由暴露意外宽泛二进制改写，不探测真实网络。
        others = ("https://api.github.com/repos/test/repo/actions/artifacts/78/zip",
                  archive_url + "?part=1", "https://example.invalid/native.dll")
        routes = {archive_url: content, **{url: b"unrelated bytes" for url in others}}
        requests, reads = [], []

        class Response(io.BytesIO):
            """Retain byte-body fixture semantics while observing the real Core bounded read.
            保留字节正文夹具语义，同时观察真实 Core 有界读取。
            """

            def read(self, size=-1):
                """Record requested size and return original fixture bytes without altering the body.
                记录请求 size 并返回原夹具字节，不改变正文。
                """
                reads.append(size)
                return super().read(size)

        class Opener:
            """Serve declared routes and reject the bound ZIP's octet Accept with the original 415.
            提供已声明路由，并对绑定 ZIP 的 octet Accept 返回原 415。
            """

            def open(self, request, timeout):
                """Observe the real Request and timeout; return body or the explicit media rejection.
                观察真实 Request 及 timeout；返回正文或明确媒体拒绝。
                """
                # Store only safe URL/media/timeout facts, never the Request's authorization header.
                # 仅保存安全 URL／媒体／超时事实，绝不保存 Request 的授权头。
                accept = request.get_header("Accept")
                requests.append((request.full_url, accept, timeout))
                if request.full_url == archive_url and accept != "application/json":
                    raise urllib.error.HTTPError(request.full_url, 415, "Unsupported Accept", {}, io.BytesIO())
                # Metadata JSON encoding belongs only to its declared API route, not the ZIP body.
                # 元数据 JSON 编码仅属于已声明 API 路由，不属于 ZIP 正文。
                body = json.dumps(metadata).encode() if request.full_url == endpoint else routes[request.full_url]
                response = Response(body)
                response.status = 200
                response.headers = {"Content-Type": "application/json" if request.full_url == endpoint else "application/zip"}
                return response

        # The same real Core instance retains its original get/json implementations and bounded reads.
        # 同一真实 Core 实例保留原 get/json 实现及有界读取。
        http = shared.Http()
        opener = Opener()
        http.opener = opener
        with self.assertRaisesRegex(ValueError, "status 415"):
            recovery.download_artifact(http, **arguments)
        self.assertEqual(requests[-1], (archive_url, "application/octet-stream", 60))
        # Only the SDK wrapper changes bound media; Core still authenticates the ZIP digest/size and members.
        # 仅 SDK 包装改变绑定媒体；Core 仍认证 ZIP 摘要／大小及成员。
        adapted = wrapper(http, "test/repo", 77)
        evidence, files = recovery.download_artifact(adapted, **arguments)
        self.assertEqual(files, {"original.txt": b"original ZIP bytes"})
        self.assertEqual(evidence["archive_sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(requests[-1], (archive_url, "application/json", 60))
        self.assertIs(http.opener, opener)
        self.assertEqual(adapted.json(endpoint), metadata)
        self.assertEqual(requests[-1], (endpoint, "application/json", 60))
        for url in others:
            with self.subTest(url=url):
                self.assertEqual(adapted.get(url, binary=True)[0], b"unrelated bytes")
                self.assertEqual(requests[-1], (url, "application/octet-stream", 60))
                self.assertEqual(adapted.get(url, binary=False)[0], b"unrelated bytes")
                self.assertEqual(requests[-1], (url, "application/json", 60))
        self.assertEqual(adapted.get(archive_url, binary=False)[0], content)
        # Wrong API size or digest must still fail inside real Core before its artifact members are accepted.
        # 错误 API 大小或摘要仍须在真实 Core 内失败，之后才可能接受制品成员。
        for field, changed in (("size_in_bytes", len(content) + 1), ("digest", "sha256:" + "0" * 64)):
            with self.subTest(field=field):
                original = metadata[field]
                metadata[field] = changed
                with self.assertRaisesRegex(ValueError, "downloaded bytes differ"):
                    recovery.download_artifact(adapted, **arguments)
                metadata[field] = original
        # Even correctly sized/hashed JSON cannot replace ZIP: real Core's ZIP parser rejects it.
        # 即使大小／摘要正确，JSON 也不能替代 ZIP：真实 Core ZIP 解析器拒绝它。
        routes[archive_url] = b"{}"
        metadata["size_in_bytes"] = len(routes[archive_url])
        metadata["digest"] = "sha256:" + hashlib.sha256(routes[archive_url]).hexdigest()
        with self.assertRaises((ValueError, zipfile.BadZipFile)):
            recovery.download_artifact(adapted, **arguments)
        self.assertTrue(reads)
        self.assertTrue(all(size == shared.MAX_BODY_BYTES + 1 for size in reads))


class RepositoryRootTests(unittest.TestCase):
    """Exercise exact repository routes and existing-blob write authorization through real HTTPS openers.
    通过真实 HTTPS openers 验证精确仓库路由及既有 blob 写授权。
    """

    @contextlib.contextmanager
    def transport(self):
        """Yield exact offline release state using original Request/opener/redirect guards; return no network side effects.
        使用原 Request／opener／重定向护栏产生精确离线 release 状态；无网络副作用。
        """
        import urllib.response
        # The explicit frozen Core supplies its original Http/opener/body decoder, with no copied implementation.
        # 明确冻结 Core 提供原 Http／opener／正文解码器，不复制实现。
        root = Path(os.environ["SDK_RELEASE_TEST_CORE_ROOT"]).resolve(strict=True)
        sys.path.insert(0, str(root / "scripts/release"))
        import sdk_prerequisites as authority
        self.assertEqual(Path(authority.__file__).resolve(), root / "scripts/release/sdk_prerequisites.py")
        # Source and workflow bytes identify the sole current definition; OID uses Git's real blob format.
        # source 及 workflow 字节标识唯一当前定义；oid 使用真实 Git blob 格式。
        source = "a" * 40
        workflow = (ROOT / ".github/workflows/sdk-release.yml").read_bytes()
        oid = hashlib.sha1(b"blob " + str(len(workflow)).encode("ascii") + b"\0" + workflow).hexdigest()
        # Version comes from the current SDK authority so completion and preflight share the exact tag fixture.
        # Version 来自当前 SDK 权威，使 completion 与 preflight 共用精确标签夹具。
        version = release.source_metadata(ROOT)["sdk_version"]
        # Base and endpoints bind every GET/POST to the exact declared repository and immutable source.
        # base 及 endpoints 将每次 GET／POST 绑定到精确声明仓库及不可变源码。
        base = "https://api.github.com/repos/" + release.SDK_REPOSITORY
        endpoint = base + "/git/blobs"
        definition = base + "/contents/.github/workflows/sdk-release.yml?ref=" + source
        # Routes retain exact release fields; false metadata push deliberately cannot substitute for real authorization.
        # routes 保留精确 release 字段；刻意为 false 的元数据 push 不能代替真实授权。
        routes = {base: {"full_name": release.SDK_REPOSITORY, "permissions": {"push": False}, "default_branch": "main"},
                  base + "/git/ref/heads/main": {"object": {"type": "commit", "sha": source}},
                  base + "/git/ref/heads/other": {"object": {"type": "commit", "sha": "b" * 40}},
                  definition: {"type": "file", "encoding": "base64", "sha": oid,
                               "content": base64.b64encode(workflow).decode("ascii")},
                  base + "/git/ref/tags/v" + version: {"ref": "refs/tags/v" + version, "object": {"type": "commit", "sha": source}},
                  base + "/releases/assets/7": b"unchanged binary asset"}
        # State holds response controls/requests and the SDK-authoritative version; builder remains the original opener factory.
        # state 保存响应控制／请求及 SDK 权威版本；builder 保持原 opener 工厂。
        state = SimpleNamespace(base=base, source=source, workflow=workflow, oid=oid, definition=definition, version=version,
            endpoint=endpoint, routes=routes, requests=[], redirects=[], status=201, sha=oid,
            response_url=endpoint, blob_url=endpoint + "/" + oid, authority=authority)
        builder = release.urllib.request.build_opener

        class OfflineHTTPS(release.urllib.request.HTTPSHandler):
            """Replace only network I/O with exact JSON responses; real HTTP status processing still runs.
            仅以精确 JSON 响应替换网络 I/O；真实 HTTP 状态处理仍执行。
            """

            def https_open(self, request):
                """Capture original Request and return selected status/body; parameters include immutable URL/body/token.
                捕获原 Request 并返回选定 status／body；参数包括不可变 URL／正文／令牌。
                """
                state.requests.append(request)
                # POST body is checked at the transport boundary, not by mirroring production conditionals.
                # 在传输边界检查 POST 正文，不镜像生产条件分支。
                if request.get_method() == "POST":
                    self_test.assertEqual(request.full_url, endpoint)
                    self_test.assertEqual(json.loads(request.data),
                        {"content": base64.b64encode(workflow).decode("ascii"), "encoding": "base64"})
                    body, status = json.dumps({"sha": state.sha, "url": state.blob_url}).encode(), state.status
                    response_url = state.response_url
                elif request.full_url == base + "/":
                    body, status, response_url = b'{"message":"Not Found"}', 404, request.full_url
                else:
                    # Value is the sole route record; bytes stay unchanged for the existing binary path.
                    # value 为唯一路由记录；现有二进制路径保留原字节。
                    value = routes[request.full_url]
                    body, status, response_url = value if isinstance(value, bytes) else json.dumps(value).encode(), 200, request.full_url
                # Response reaches the real error processor; HTTP403 is not represented as a successful JSON object.
                # response 进入真实错误处理器；HTTP403 不表示为成功 JSON 对象。
                response = urllib.response.addinfourl(io.BytesIO(body), {"Content-Type": "application/json"}, response_url, status)
                response.msg = "Created" if status == 201 else "Forbidden" if status == 403 else "OK"
                return response

        def build_with_network_fixture(*handlers):
            """Retain original SafeRedirect handlers and append offline HTTPS I/O; return real OpenerDirector.
            保留原 SafeRedirect handlers 并添加离线 HTTPS I/O；返回真实 OpenerDirector。
            """
            state.redirects.extend(handlers)
            return builder(*handlers, OfflineHTTPS())

        # Self_test is this testcase used by the network handler; env binds only fixture credentials/current identity.
        # self_test 为网络 handler 使用的本 testcase；env 仅绑定夹具凭据／当前身份。
        self_test = self
        env = {"GH_TOKEN": "fixture-only", "GITHUB_TOKEN": "unused-second-token", "GITHUB_REF": "refs/heads/main",
               "GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": release.SDK_REPOSITORY,
               "GITHUB_SHA": source, "GITHUB_WORKFLOW_SHA": source, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
        with patch.dict(os.environ, env), patch.object(release.urllib.request, "build_opener", side_effect=build_with_network_fixture):
            yield state
        self.assertTrue(all(isinstance(handler, authority.SafeRedirect) for handler in state.redirects))

    def preflight(self, state, output):
        """Run the actual SDK preflight with state's fixed source and output receipt; return its original result.
        以 state 固定源码及 output 回执运行真实 SDK preflight；返回原结果。
        """
        return release.publication_preflight(state.authority, state.source, state.version)

    def test_root_preflight_and_nonempty_request_guards(self):
        """Accept one real-opener HTTP201 despite metadata push false, preserving authenticated GET/binary routes.
        即使元数据 push 为 false 也接受真实 opener HTTP201，保留已认证 GET／二进制路由。
        """
        with self.transport() as state, tempfile.TemporaryDirectory(prefix="ls-blob-") as temporary:
            self.preflight(state, Path(temporary) / "receipt.json")
            self.assertTrue(state.redirects)
            self.assertEqual(state.requests[0].full_url, state.base)
            self.assertEqual(state.requests[0].get_method(), "GET")
            self.assertEqual(state.requests[0].get_header("Authorization"), "Bearer fixture-only")
            # Posts and request are actual transport observations, never inferred from YAML permissions.
            # posts 及 request 为实际传输观察，绝非从 YAML 权限推断。
            posts = [request for request in state.requests if request.get_method() == "POST"]
            self.assertEqual(len(posts), 1)
            request = posts[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer fixture-only")
            self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")
            self.assertEqual(request.get_header("Content-type"), "application/json")
            self.assertEqual(request.get_header("X-github-api-version"), "2022-11-28")
            self.assertEqual(request.timeout, 60)
            # Http is the original Core instance; the nonempty binary release endpoint keeps its existing Accept and bytes.
            # http 为原 Core 实例；非空二进制 release 端点保留既有 Accept 及字节。
            http = state.authority.Http()
            self.assertEqual(http.get(state.base + "/releases/assets/7", binary=True)[0], b"unchanged binary asset")
            self.assertEqual(state.requests[-1].get_header("Accept"), "application/octet-stream")
            # Completion uses exactly the same gate; only its unrelated local Git-source check is isolated.
            # completion 使用完全相同门禁；仅隔离其无关本地 Git 源码检查。
            coordinator = release.publication_coordinator()
            with patch.object(coordinator, "checked_source"):
                result = coordinator.current_intent("publish", state.source, state.authority)
            self.assertEqual(result["source_sha"], state.source)
            self.assertEqual(sum(request.get_method() == "POST" for request in state.requests), 2)

    def test_existing_blob_write_rejections_preserve_original_gates(self):
        """Reject status/identity/token/source/workflow/tag errors through real preflight before downstream publication.
        通过真实 preflight 在下游发布前拒绝状态／身份／令牌／源码／工作流／标签错误。
        """
        # Cases select one exact altered fact and expected write count; no retries or alternate endpoints exist.
        # cases 选择唯一变化事实及预期写入数；不存在重试或备用端点。
        cases = ("forbidden", "not-created", "wrong-return-sha", "wrong-return-url", "redirected",
                 "missing-token", "identity", "default-branch", "source", "workflow", "workflow-type", "workflow-encoding", "workflow-sha", "tag")
        for case in cases:
            with self.subTest(case=case), self.transport() as state, tempfile.TemporaryDirectory(prefix="ls-blob-") as temporary:
                if case == "forbidden":
                    state.status = 403
                elif case == "not-created":
                    state.status = 200
                elif case == "wrong-return-sha":
                    state.sha = "b" * 40
                elif case == "wrong-return-url":
                    state.blob_url = "https://api.github.com/repos/other/repo/git/blobs/" + state.oid
                elif case == "redirected":
                    state.response_url = "https://api.github.com/repos/other/repo/git/blobs"
                elif case == "missing-token":
                    os.environ["GH_TOKEN"] = ""
                elif case == "identity":
                    state.routes[state.base]["full_name"] = "other/repo"
                elif case == "default-branch":
                    state.routes[state.base]["default_branch"] = "other"
                elif case == "source":
                    state.routes[state.base + "/git/ref/heads/main"]["object"]["sha"] = "b" * 40
                elif case == "workflow":
                    state.routes[state.definition]["content"] = base64.b64encode(b"edited definition").decode()
                elif case == "workflow-type":
                    state.routes[state.definition]["type"] = "dir"
                elif case == "workflow-encoding":
                    state.routes[state.definition]["encoding"] = "none"
                elif case == "workflow-sha":
                    state.routes[state.definition]["sha"] = "b" * 40
                else:
                    state.routes[state.base + "/git/ref/tags/v" + state.version]["object"]["sha"] = "b" * 40
                # Output is a new local receipt; failed authorization must never manufacture successful evidence.
                # output 为新本地回执；失败授权绝不能制造成功证据。
                output = Path(temporary) / "rejected.json"
                with self.assertRaises((ValueError, release.urllib.error.HTTPError)):
                    self.preflight(state, output)
                self.assertFalse(output.exists())
                self.assertEqual(sum(request.get_method() == "POST" for request in state.requests),
                                 1 if case in ("forbidden", "not-created", "wrong-return-sha", "wrong-return-url", "redirected") else 0)
                if case in ("forbidden", "tag"):
                    # Completion must share the same actual refusal, not a second metadata-only authority.
                    # completion 必须共享相同实际拒绝，绝非第二个仅元数据权威。
                    state.requests.clear()
                    coordinator = release.publication_coordinator()
                    with patch.object(coordinator, "checked_source"), \
                            self.assertRaises((ValueError, release.urllib.error.HTTPError)):
                        coordinator.current_intent("publish", state.source, state.authority)
                    self.assertEqual(sum(request.get_method() == "POST" for request in state.requests),
                                     1 if case == "forbidden" else 0)


if __name__ == "__main__":
    unittest.main()
