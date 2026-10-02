"""Coordinate original signed SDK candidates and independent publication completions.
协调原始已签名 SDK 候选与独立发布完成凭据。

The only CLI remains sdk_release.py; exact attempts and inventories belong to frozen core sdk_recovery.py.
唯一 CLI 保持 sdk_release.py；精确轮次及清单归属冻结核心 sdk_recovery.py。
"""

import argparse
import os
from pathlib import Path
import tempfile
import zipfile


class Publication:
    """Use release_api's existing gates to authenticate and complete immutable candidates; methods return evidence.
    使用 release_api 的已有门禁认证并完成不可变候选；方法返回凭据。
    """

    def __init__(self, release_api):
        """Retain the sole CLI's release_api and source root without loading native resources; return nothing.
        保留唯一 CLI 的 release_api 及源码根，不加载原生资源；无返回值。
        """
        # SDK source remains the existing CLI's physical checkout, never an artifact-selected import.
        # SDK 源码保持已有 CLI 的物理检出，绝不由制品选择导入路径。
        self.api = release_api
        self.sdk_root = Path(release_api.__file__).resolve().parents[2]

    def authorities(self, root, commit):
        """Load root/commit's authenticated public and recovery modules; return the two fixed authorities.
        加载 root/commit 的已认证公共及恢复模块；返回两个固定权威。
        """
        return self.api.core_module(root, commit), self.api.recovery_module(root, commit)

    def files(self, directory):
        """Read directory's exact root regular files; return bytes and reject nested/symlink evidence.
        读取 directory 的精确根普通文件；返回字节并拒绝嵌套或符号链接凭据。
        """
        result = {}
        for path in sorted(Path(directory).iterdir()):
            self.api.require(path.is_file() and not path.is_symlink(), "Publication inventory requires root regular files")
            result[path.name] = path.read_bytes()
        return result

    def write_files(self, directory, files):
        """Write already validated root files into a new directory; return nothing and never overwrite.
        将已验证根文件写入新目录；无返回值，绝不覆盖。
        """
        Path(directory).mkdir(parents=True, exist_ok=False)
        for name, body in files.items():
            with (Path(directory) / name).open("xb") as stream:
                stream.write(body)

    def archive_tree(self, destination, trees):
        """Archive named trees deterministically into destination; reject links and return nothing.
        将命名 trees 确定性归档至 destination；拒绝链接，无返回值。
        """
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for prefix, root in trees.items():
                for path in sorted(Path(root).rglob("*")):
                    if path.is_file():
                        self.api.require(not path.is_symlink(), "Publication archive cannot contain symlinks")
                        member = zipfile.ZipInfo(prefix + "/" + path.relative_to(root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                        member.compress_type = zipfile.ZIP_DEFLATED
                        archive.writestr(member, path.read_bytes())

    def extract_tree(self, archive_path, directory, limit):
        """Extract archive_path's bounded regular members into new directory; return nothing and reject aliases/escapes.
        将 archive_path 的有界普通成员解包至新 directory；无返回值，拒绝别名及逃逸。
        """
        self.api.require(not Path(directory).exists(), "Publication evidence extraction must be new")
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            self.api.require(len(names) == len(set(names)) and len(names) == len({name.casefold() for name in names}),
                             "Duplicate publication archive members")
            self.api.require(sum(member.file_size for member in archive.infolist()) <= limit,
                             "Publication evidence expansion exceeds the public body limit")
            for member in archive.infolist():
                path = Path(member.filename)
                self.api.require(not path.is_absolute() and ".." not in path.parts and "\\" not in member.filename
                                 and ":" not in member.filename and (member.external_attr >> 16 & 0o170000) in (0, 0o100000),
                                 "Unsafe publication evidence member")
                destination = Path(directory) / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as stream:
                    stream.write(archive.read(member))

    def current_intent(self, intent, sdk_source_sha, authority):
        """Require explicit current intent and fixed source/default-branch token ownership; return completion identity.
        要求明确当前 intent 及固定源码、默认分支令牌归属；返回完成身份。
        """
        self.api.require(intent in ("publish", "recover"), "Current completion requires explicit publish or recover intent")
        self.api.require(os.environ["GITHUB_ACTIONS"] == "true" and os.environ["GITHUB_EVENT_NAME"] == "workflow_dispatch"
                         and os.environ["GITHUB_REPOSITORY"] == self.api.SDK_REPOSITORY
                         and os.environ["GITHUB_SHA"] == os.environ["GITHUB_WORKFLOW_SHA"] == sdk_source_sha,
                         "Current completion must use the original fixed SDK source and workflow definition")
        self.checked_source(sdk_source_sha)
        repository = self.api.release_get(authority.Http(), "")
        self.api.require(os.environ["GITHUB_REF"] == "refs/heads/" + repository["default_branch"]
                         and repository["permissions"]["push"] is True,
                         "Current completion requires the default branch and issuing repository write token")
        return {"run_id": int(os.environ["GITHUB_RUN_ID"]), "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
                "source_sha": os.environ["GITHUB_SHA"], "completion_intent": intent}

    def candidate_prepare(self, args):
        """Freeze args' measured packages, complete native logs and original core evidence before mutations; return binding.
        在修改前冻结 args 已测包、完整原生日志及原核心证据；返回绑定。
        """
        aggregate = self.api.read_json(args.aggregate)
        plan = aggregate["plan"]
        self.api.require(aggregate["accepted"] is True and os.environ["GITHUB_REPOSITORY"] == self.api.SDK_REPOSITORY
                         and os.environ["GITHUB_SHA"] == os.environ["GITHUB_WORKFLOW_SHA"] == plan["source_sha"],
                         "Candidate evidence must originate from its exact SDK definition")
        authority, recovery = self.authorities(args.core_root, plan["core_commit"])
        self.api.verify_artifacts(plan, args.artifacts, aggregate["artifacts"])
        # Recompute from actual logs so the signed inventory cannot preserve only caller-authored report hashes.
        # 从实际日志重新计算，避免已签名清单仅保留调用方编写的报告摘要。
        with tempfile.TemporaryDirectory(prefix="luaskills-candidate-aggregate-") as temporary:
            recomputed = self.api.aggregate(argparse.Namespace(plan=args.evidence / "plan.json", artifacts=args.artifacts,
                prerequisites=args.evidence / "core/prerequisites.json", reports=args.reports, output=Path(temporary) / "aggregate.json"))
        self.api.require(recomputed == aggregate, "Candidate native report/log inventory differs from accepted aggregate")
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "aggregate.json").write_bytes(args.aggregate.read_bytes())
        (args.output / "artifacts.json").write_bytes((args.artifacts / "artifacts.json").read_bytes())
        for record in aggregate["artifacts"].values():
            (args.output / record["filename"]).write_bytes((args.artifacts / record["filename"]).read_bytes())
        self.archive_tree(args.output / "candidate-evidence.zip", {"evidence": args.evidence, "reports": args.reports})
        run_id, attempt = int(os.environ["GITHUB_RUN_ID"]), int(os.environ["GITHUB_RUN_ATTEMPT"])
        binding = {"schema_version": recovery.SCHEMA_VERSION, "kind": "sdk-candidate", "repository": self.api.SDK_REPOSITORY,
                   "workflow_path": self.api.SDK_WORKFLOW, "source_sha": plan["source_sha"], "run_id": run_id,
                   "run_attempt": attempt, "artifact_name": recovery.candidate_artifact_name(run_id, attempt),
                   "inventory": recovery.inventory_for(self.files(args.output))}
        self.api.write_json(args.output / recovery.BINDING_FILENAME, binding)
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as output:
                output.write("artifact_name=" + binding["artifact_name"] + "\n")
        return binding

    def verified_binding(self, directory, recovery, source_sha, run_id, attempt, *, workflow_path=None):
        """Verify directory's official candidate signature and full physical inventory; return public verified wrapper.
        验证 directory 的官方候选签名及完整物理清单；返回公共已验证包装对象。
        """
        workflow = self.api.SDK_WORKFLOW if workflow_path is None else workflow_path
        with tempfile.TemporaryDirectory(prefix="luaskills-binding-verification-") as temporary:
            facts = self.api.verify_attestation(Path(directory) / recovery.BINDING_FILENAME,
                Path(directory) / self.api.CANDIDATE_ATTESTATION, source_sha, run_id, attempt,
                Path(temporary) / "official.json", workflow_path=workflow)
        wrapper = recovery.verify_signed_binding((Path(directory) / recovery.BINDING_FILENAME).read_bytes(), **facts,
            repository=self.api.SDK_REPOSITORY, workflow_path=workflow, source_sha=source_sha, run_id=run_id,
            run_attempt=attempt, artifact_name=recovery.candidate_artifact_name(run_id, attempt))
        recovery.verify_inventory(wrapper, self.files(directory), attestation_filename=self.api.CANDIDATE_ATTESTATION)
        return wrapper

    def candidate_seal(self, args):
        """Retain args' official bundle with original payload and authenticate its binding; return verified wrapper.
        将 args 官方 bundle 与原载荷一同保留并认证绑定；返回已验证包装对象。
        """
        aggregate = self.api.read_json(args.prepared / "aggregate.json")
        _, recovery = self.authorities(args.core_root, aggregate["plan"]["core_commit"])
        destination = args.prepared / self.api.CANDIDATE_ATTESTATION
        with destination.open("xb") as stream:
            stream.write(args.bundle.read_bytes())
        return self.verified_binding(args.prepared, recovery, aggregate["plan"]["source_sha"],
                                     int(os.environ["GITHUB_RUN_ID"]), int(os.environ["GITHUB_RUN_ATTEMPT"]))

    def validate_candidate(self, directory, output, authority, recovery, *, source_sha, run_id, attempt,
                           core_tag, core_commit, sdk_version):
        """Authenticate exact candidate files, old attempt and complete SDK-specific evidence; return candidate receipt.
        认证精确候选文件、原轮次及完整 SDK 专属证据；返回候选回执。
        """
        wrapper = self.verified_binding(directory, recovery, source_sha, run_id, attempt)
        aggregate = self.api.read_json(Path(directory) / "aggregate.json")
        plan = aggregate["plan"]
        self.api.require(plan["source_sha"] == source_sha and plan["sdk_version"] == sdk_version
                         and plan["core_tag"] == core_tag and plan["core_commit"] == core_commit,
                         "Original candidate SDK/version/core identity mismatch")
        metadata = self.api.source_metadata(self.sdk_root)
        matrix = [{"platform": platform, "python_role": role, "python": metadata["python"][role],
                   "runner": self.api.runner_for(record[1], record[2])}
                  for platform, record in authority.candidate.PLATFORMS.items() for role in self.api.ROLES]
        self.api.require(set(plan["platforms"]) == set(authority.candidate.PLATFORMS)
                         and plan["matrix"] == matrix and plan["python"] == metadata["python"]
                         and plan["default_core_tag"] == metadata["default_core_tag"] == core_tag,
                         "Original candidate platform/interpreter/default-asset declaration mismatch")
        self.api.verify_artifacts(plan, directory, aggregate["artifacts"])
        self.api.require({row["filename"] for row in wrapper["binding"]["inventory"]}
                         == {"aggregate.json", "artifacts.json", "candidate-evidence.zip",
                             *[record["filename"] for record in aggregate["artifacts"].values()]},
                         "Original candidate payload differs from the frozen SDK file roles")
        self.extract_tree(Path(directory) / "candidate-evidence.zip", output / "original", authority.MAX_BODY_BYTES)
        original = output / "original"
        with tempfile.TemporaryDirectory(prefix="luaskills-original-aggregate-") as temporary:
            recomputed = self.api.aggregate(argparse.Namespace(plan=original / "evidence/plan.json", artifacts=Path(directory),
                prerequisites=original / "evidence/core/prerequisites.json", reports=original / "reports",
                output=Path(temporary) / "aggregate.json"))
        self.api.require(recomputed == aggregate, "Original signed native logs differ from aggregate")
        # Matrix names are frozen explicitly in the workflow and derived from the verified plan, never UI parsing.
        # 矩阵名称在工作流中明确冻结，并从已验证计划派生，绝不解析 UI 格式。
        jobs = ["freeze-build", "aggregate", "candidate-evidence", *[
            "native-" + row["platform"] + "-" + row["python_role"] for row in plan["matrix"]]]
        observed = recovery.verify_attempt(authority.Http(), repository=self.api.SDK_REPOSITORY,
            workflow_path=self.api.SDK_WORKFLOW, source_sha=source_sha, run_id=run_id, run_attempt=attempt,
            required_jobs=jobs, phase="candidate")
        self.api.require(plan["mode"] in ("artifact-only", "publish")
                         and observed["attempt"]["event"] == "workflow_dispatch"
                         and observed["attempt"]["display_title"] == f"Python SDK {source_sha} {plan['mode']}",
                         "Original candidate did not execute its preserved frozen acceptance mode")
        receipt = {"schema_version": recovery.SCHEMA_VERSION, "binding": wrapper, "attempt_evidence": observed,
                   "candidate_attestation_sha256": self.api.sha256(Path(directory) / self.api.CANDIDATE_ATTESTATION)}
        self.api.write_json(output / "candidate-receipt.json", receipt)
        return receipt

    def candidate_resolve(self, args):
        """Download args' explicit original artifact and authenticate exact candidate attempt; return receipt.
        下载 args 明确原制品并认证精确候选轮次；返回回执。
        """
        authority, recovery = self.authorities(args.core_root, args.core_commit)
        self.api.require(args.source_sha == os.environ["GITHUB_SHA"] == os.environ["GITHUB_WORKFLOW_SHA"],
                         "First-version recovery requires identical SDK and completion source SHA")
        self.checked_source(args.source_sha)
        artifact, files = recovery.download_artifact(authority.Http(), repository=self.api.SDK_REPOSITORY,
            source_sha=args.source_sha, run_id=args.candidate_run_id, artifact_id=args.candidate_artifact_id,
            artifact_name=recovery.candidate_artifact_name(args.candidate_run_id, args.candidate_run_attempt))
        args.output.mkdir(parents=True, exist_ok=False)
        self.write_files(args.output / "candidate", files)
        metadata = self.api.source_metadata(self.sdk_root)
        receipt = self.validate_candidate(args.output / "candidate", args.output, authority, recovery,
            source_sha=args.source_sha, run_id=args.candidate_run_id, attempt=args.candidate_run_attempt,
            core_tag=args.core_tag, core_commit=args.core_commit, sdk_version=metadata["sdk_version"])
        self.api.write_json(args.output / "artifact-download.json", artifact)
        return receipt

    def candidate_receipt(self, directory):
        """Read directory's authenticated candidate receipt and original plan; return both values.
        读取 directory 的已认证候选回执及原计划；返回两者。
        """
        receipt = self.api.read_json(Path(directory) / "candidate-receipt.json")
        plan = self.api.read_json(Path(directory) / "candidate/aggregate.json")["plan"]
        return receipt, plan

    def publish_candidate(self, args):
        """Reauthenticate args' original inventory and publish exactly those bytes; return actual main release state.
        再认证 args 原清单并仅发布其精确字节；返回实际主发行状态。
        """
        receipt, plan = self.candidate_receipt(args.candidate)
        authority, recovery = self.authorities(args.core_root, plan["core_commit"])
        self.current_intent(args.intent, plan["source_sha"], authority)
        binding = receipt["binding"]["binding"]
        self.verified_binding(args.candidate / "candidate", recovery, plan["source_sha"], binding["run_id"], binding["run_attempt"])
        state = self.api.publish_immutable(authority, "v" + plan["sdk_version"], plan["source_sha"], args.candidate / "candidate")
        self.api.write_json(args.output, state)
        return state

    def main_release(self, authority, directory, state, source_sha):
        """Read state's actual release ID and require every original directory byte/source; return observed record.
        读取 state 的实际发行 ID，并要求每份原 directory 字节及源码一致；返回观察记录。
        """
        http = authority.Http()
        record = self.api.release_get(http, "releases/" + str(state["release_id"]))
        self.api.require(record["id"] == state["release_id"] and record["tag_name"] == state["tag"]
                         and record["draft"] is False and record["prerelease"] is False,
                         "Completion main release ID/tag/final state mismatch")
        self.api.sdk_tag(http, state["tag"], source_sha)
        assets = self.api.release_assets(http, record["id"])
        originals = self.files(directory)
        self.api.require(set(assets) == set(originals), "Main release has missing or extra candidate files")
        for name, body in originals.items():
            self.api.require(http.get(assets[name]["url"], binary=True)[0] == body,
                             "Main release bytes differ from the original signed candidate")
        return record

    def completion_prepare(self, args):
        """Bind fresh core/PyPI consumption and actual main release to original candidate plus current intent; return receipt.
        将新核心及 PyPI 消费、实际主发行绑定原候选及当前意图；返回回执。
        """
        receipt, plan = self.candidate_receipt(args.candidate)
        authority, recovery = self.authorities(args.core_root, plan["core_commit"])
        current = self.current_intent(args.intent, plan["source_sha"], authority)
        original = receipt["binding"]["binding"]
        self.verified_binding(args.candidate / "candidate", recovery, plan["source_sha"], original["run_id"], original["run_attempt"])
        publication = self.api.read_json(args.publication_proof)
        consumer = self.api.read_json(args.proof)
        prerequisites = self.api.read_json(args.publication_prerequisites)
        self.api.require(prerequisites["phase"] == "complete" and prerequisites["complete"] is True
                         and prerequisites["core_tag"] == plan["core_tag"] and prerequisites["core_commit"] == plan["core_commit"]
                         and prerequisites["core_version"] == plan["core_version"]
                         and set(prerequisites["sdk_inputs"]) == set(plan["platforms"]),
                         "Completion fresh core prerequisite identity/platform set mismatch")
        aggregate_path = args.candidate / "candidate/aggregate.json"
        self.api.require(consumer["accepted"] is True and consumer["aggregate_sha256"] == self.api.sha256(aggregate_path)
                         and consumer["source_sha"] == plan["source_sha"] and consumer["sdk_version"] == plan["sdk_version"]
                         and consumer["core_commit"] == plan["core_commit"]
                         and consumer["platform"] in plan["platforms"]
                         and consumer["library_sha256"] == prerequisites["sdk_inputs"][consumer["platform"]]["library_sha256"]
                         and consumer["artifacts"] == self.api.read_json(aggregate_path)["artifacts"]
                         and consumer["artifacts"] == publication["artifacts"]
                         and publication["aggregate_sha256"] == consumer["aggregate_sha256"]
                         and publication["prerequisites_sha256"] == self.api.sha256(args.publication_prerequisites),
                         "Completion fresh actual consumer/core proof binding mismatch")
        state = self.api.read_json(args.main_release_state)
        self.main_release(authority, args.candidate / "candidate", state, plan["source_sha"])
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "formal-consumer.json").write_bytes(args.proof.read_bytes())
        # The current native log belongs to the new completion, not to the immutable original matrix.
        # 当前原生日志归属新完成凭据，不归属不可变原矩阵。
        (args.output / "formal-consumer.log").write_bytes((args.proof.parent / "native.log").read_bytes())
        (args.output / "core-prerequisites.json").write_bytes(args.publication_prerequisites.read_bytes())
        self.archive_tree(args.output / "completion-evidence.zip", {"core": args.publication_prerequisites.parent})
        completion = {"schema_version": recovery.SCHEMA_VERSION, "kind": "sdk-completion",
            "repository": self.api.SDK_REPOSITORY, "workflow_path": self.api.SDK_WORKFLOW,
            "sdk_source_sha": plan["source_sha"], "sdk_version": plan["sdk_version"],
            "core_tag": plan["core_tag"], "core_commit": plan["core_commit"], "completion_source_sha": current["source_sha"],
            "candidate_run_id": original["run_id"], "candidate_run_attempt": original["run_attempt"],
            "candidate_artifact_id": self.api.read_json(args.candidate / "artifact-download.json")["artifact"]["id"],
            "completion_run_id": current["run_id"], "completion_run_attempt": current["run_attempt"],
            "completion_intent": current["completion_intent"], "main_release": state,
            "candidate_binding_sha256": receipt["binding"]["binding_sha256"],
            "candidate_attestation_sha256": receipt["candidate_attestation_sha256"],
            "candidate_inventory": original["inventory"], "artifacts": consumer["artifacts"],
            "inventory": recovery.inventory_for(self.files(args.output))}
        self.api.write_json(args.output / "completion.json", completion)
        return completion

    def completion_tag(self, version, run_id, attempt):
        """Return the explicit independent recovery release tag for version/run_id/attempt.
        返回 version/run_id/attempt 明确的独立恢复发行标签。
        """
        return f"recovery-v{version}-r{run_id}-a{attempt}"

    def completion_files(self, directory, recovery, completion):
        """Require complete directory bytes match completion's signed payload inventory; return nothing.
        要求完整 directory 字节匹配 completion 已签名载荷清单；无返回值。
        """
        files = self.files(directory)
        expected = {row["filename"] for row in recovery.validate_inventory(completion["inventory"])}
        self.api.require(expected == {"formal-consumer.json", "formal-consumer.log", "core-prerequisites.json", "completion-evidence.zip"},
                         "Completion payload differs from its frozen consumer/core file roles")
        self.api.require(set(files) == expected | {"completion.json", "completion-attestation.jsonl"},
                         "Completion has missing or extra receipt files")
        recovery.compare_inventory(completion["inventory"], {name: files[name] for name in expected})

    def publish_completion(self, args):
        """Sign-check current completion and publish its separate draft without touching original assets; return state.
        验签当前完成凭据并发布独立草稿，不修改原资产；返回状态。
        """
        completion = self.api.read_json(args.prepared / "completion.json")
        authority, recovery = self.authorities(args.core_root, completion["core_commit"])
        current = self.current_intent(args.intent, completion["sdk_source_sha"], authority)
        self.api.require(completion["completion_run_id"] == current["run_id"]
                         and completion["completion_run_attempt"] == current["run_attempt"]
                         and completion["completion_source_sha"] == current["source_sha"]
                         and completion["completion_intent"] == args.intent, "Current completion identity/intent differs from receipt")
        with (args.prepared / "completion-attestation.jsonl").open("xb") as stream:
            stream.write(args.bundle.read_bytes())
        with tempfile.TemporaryDirectory(prefix="luaskills-completion-signature-") as temporary:
            self.api.verify_attestation(args.prepared / "completion.json", args.prepared / "completion-attestation.jsonl",
                current["source_sha"], current["run_id"], current["run_attempt"], Path(temporary) / "official.json")
        self.completion_files(args.prepared, recovery, completion)
        self.main_release(authority, args.candidate / "candidate", completion["main_release"], completion["sdk_source_sha"])
        tag = self.completion_tag(completion["sdk_version"], current["run_id"], current["run_attempt"])
        state = self.api.publish_immutable(authority, tag, current["source_sha"], args.prepared)
        self.api.write_json(args.prepared.parent / "completion-release-state.json", state)
        return state

    def checked_source(self, source_sha):
        """Require source_sha's exact clean SDK CLI and coordinator Git bytes; return nothing.
        要求 source_sha 的精确干净 SDK CLI 及协调器 Git 字节；无返回值。
        """
        self.api.require(self.api.run(["git", "rev-parse", "HEAD"], self.sdk_root).strip() == source_sha
                         and not self.api.run(["git", "status", "--porcelain", "--untracked-files=no"], self.sdk_root).strip(),
                         "Formal proof code must use its exact unmodified SDK source")
        for name in ("sdk_release.py", "sdk_publication.py"):
            self.api.require(self.api.run(["git", "show", source_sha + ":scripts/release/" + name], self.sdk_root)
                             == (self.sdk_root / "scripts/release" / name).read_text(encoding="utf-8"),
                             "Formal proof code differs from frozen SDK Git tree")

    def download_release(self, http, record, directory, names):
        """Download exact names from record's authenticated asset IDs into new directory; return assets.
        从 record 已认证资产 ID 下载精确 names 至新 directory；返回资产。
        """
        assets = self.api.release_assets(http, record["id"])
        self.write_files(directory, {name: http.get(assets[name]["url"], binary=True)[0] for name in names})
        return assets

    def formal_proof(self, args):
        """Authenticate both explicit chains and current registry consumption without latest-run substitution; return proof.
        认证两条明确链及当前 registry 消费，不以最新运行替代；返回证明。
        """
        self.api.require(args.source_sha == args.completion_source_sha,
                         "First-version formal recovery requires the original and completion SDK source to match")
        self.api.require(self.api.re.fullmatch(r"[0-9a-f]{40}", args.source_sha) is not None
                         and self.api.re.fullmatch(r"[0-9a-f]{40}", args.core_commit) is not None
                         and all(type(value) is int and value > 0 for value in
                             (args.candidate_run_id, args.candidate_run_attempt, args.completion_run_id, args.completion_run_attempt)),
                         "Formal proof requires exact full source commits and positive explicit attempt identities")
        self.checked_source(args.completion_source_sha)
        metadata = self.api.source_metadata(self.sdk_root)
        self.api.require(metadata["sdk_version"] == args.sdk_version and metadata["default_core_tag"] == args.core_tag,
                         "Formal proof SDK version/default core asset differs from its frozen source")
        authority, recovery = self.authorities(args.core_root, args.core_commit)
        http = authority.Http()
        main = self.api.release_get(http, "releases/tags/v" + args.sdk_version)
        self.api.require(main["draft"] is False and main["prerelease"] is False, "Original SDK main release must be public final")
        self.api.sdk_tag(http, "v" + args.sdk_version, args.source_sha)
        args.output.mkdir(parents=True, exist_ok=False)
        candidate_dir = args.output / "candidate"
        assets = self.download_release(http, main, candidate_dir, (recovery.BINDING_FILENAME, self.api.CANDIDATE_ATTESTATION))
        # Signature authentication precedes every use of inventory-selected asset names or old issuer metadata.
        # 签名认证先于使用清单所选资产名称或原签发者元数据。
        with tempfile.TemporaryDirectory(prefix="luaskills-original-signature-") as temporary:
            facts = self.api.verify_attestation(candidate_dir / recovery.BINDING_FILENAME,
                candidate_dir / self.api.CANDIDATE_ATTESTATION, args.source_sha, args.candidate_run_id,
                args.candidate_run_attempt, Path(temporary) / "official.json")
        wrapper = recovery.verify_signed_binding((candidate_dir / recovery.BINDING_FILENAME).read_bytes(), **facts,
            repository=self.api.SDK_REPOSITORY, workflow_path=self.api.SDK_WORKFLOW, source_sha=args.source_sha,
            run_id=args.candidate_run_id, run_attempt=args.candidate_run_attempt,
            artifact_name=recovery.candidate_artifact_name(args.candidate_run_id, args.candidate_run_attempt))
        names = {row["filename"] for row in wrapper["binding"]["inventory"]}
        self.api.require(set(assets) == names | {recovery.BINDING_FILENAME, self.api.CANDIDATE_ATTESTATION},
                         "Original SDK release differs from the exact signed candidate inventory")
        for name in sorted(names):
            with (candidate_dir / name).open("xb") as stream:
                stream.write(http.get(assets[name]["url"], binary=True)[0])
        receipt = self.validate_candidate(candidate_dir, args.output, authority, recovery, source_sha=args.source_sha,
            run_id=args.candidate_run_id, attempt=args.candidate_run_attempt, core_tag=args.core_tag,
            core_commit=args.core_commit, sdk_version=args.sdk_version)
        tag = self.completion_tag(args.sdk_version, args.completion_run_id, args.completion_run_attempt)
        completed_release = self.api.release_get(http, "releases/tags/" + tag)
        self.api.require(completed_release["draft"] is False and completed_release["prerelease"] is False,
                         "Independent completion release must be public final")
        self.api.sdk_tag(http, tag, args.completion_source_sha)
        completed_dir = args.output / "completion"
        completed_assets = self.download_release(http, completed_release, completed_dir,
                                                 ("completion.json", "completion-attestation.jsonl"))
        self.api.verify_attestation(completed_dir / "completion.json", completed_dir / "completion-attestation.jsonl",
            args.completion_source_sha, args.completion_run_id, args.completion_run_attempt, args.output / "completion-official.json")
        completion = self.api.read_json(completed_dir / "completion.json")
        expected = {"schema_version": recovery.SCHEMA_VERSION, "kind": "sdk-completion", "repository": self.api.SDK_REPOSITORY,
            "workflow_path": self.api.SDK_WORKFLOW, "sdk_source_sha": args.source_sha, "sdk_version": args.sdk_version,
            "core_tag": args.core_tag, "core_commit": args.core_commit, "completion_source_sha": args.completion_source_sha,
            "candidate_run_id": args.candidate_run_id, "candidate_run_attempt": args.candidate_run_attempt,
            "completion_run_id": args.completion_run_id, "completion_run_attempt": args.completion_run_attempt,
            "candidate_binding_sha256": receipt["binding"]["binding_sha256"],
            "candidate_attestation_sha256": receipt["candidate_attestation_sha256"],
            "candidate_inventory": wrapper["binding"]["inventory"]}
        self.api.require(all(completion[name] == value for name, value in expected.items())
                         and completion["completion_intent"] in ("publish", "recover")
                         and completion["main_release"]["release_id"] == main["id"]
                         and completion["main_release"]["tag"] == "v" + args.sdk_version
                         and completion["main_release"]["source_sha"] == args.source_sha
                         and completion["artifacts"] == self.api.read_json(candidate_dir / "aggregate.json")["artifacts"]
                         and type(completion["candidate_artifact_id"]) is int and completion["candidate_artifact_id"] > 0,
                         "Completion chain identity/candidate/main release mismatch")
        self.api.require(set(completion) == set(expected) | {"completion_intent", "main_release", "artifacts", "inventory", "candidate_artifact_id"},
                         "Completion receipt has unknown or missing fields")
        names = {row["filename"] for row in recovery.validate_inventory(completion["inventory"])}
        self.api.require(set(completed_assets) == names | {"completion.json", "completion-attestation.jsonl"},
                         "Completion release differs from its signed inventory")
        for name in sorted(names):
            with (completed_dir / name).open("xb") as stream:
                stream.write(http.get(completed_assets[name]["url"], binary=True)[0])
        self.completion_files(completed_dir, recovery, completion)
        observed = recovery.verify_attempt(http, repository=self.api.SDK_REPOSITORY, workflow_path=self.api.SDK_WORKFLOW,
            source_sha=args.completion_source_sha, run_id=args.completion_run_id, run_attempt=args.completion_run_attempt,
            required_jobs=["publish"], phase="completion")
        self.api.require(observed["attempt"]["event"] == "workflow_dispatch"
                         and observed["attempt"]["display_title"] == f"Python SDK {args.completion_source_sha} {completion['completion_intent']}",
                         "Completion did not execute the explicit formal publish/recover definition")
        original_core = args.output / "original/evidence/core/prerequisites.json"
        fresh = authority.recheck(original_core, args.output / "fresh-core")
        self.api.require(fresh["complete"] is True and fresh["phase"] == "complete", "Current formal core registry consumer is incomplete")
        self.api.write_json(args.output / "resolved-inputs.json", authority.resolve_sdk_inputs(args.output / "fresh-core/prerequisites.json", args.platform))
        aggregate = args.output / "aggregate.json"
        aggregate.write_bytes((candidate_dir / "aggregate.json").read_bytes())
        self.api.verify_pypi(argparse.Namespace(aggregate=aggregate, inputs=args.output / "resolved-inputs.json", output=args.output / "fresh-pypi"))
        consumer = args.output / "fresh-formal-consumer.json"
        consumer.write_bytes((args.output / "fresh-pypi/pypi-proof.json").read_bytes())
        accepted = {"schema_version": recovery.SCHEMA_VERSION, "sdk_source_sha": args.source_sha, "sdk_version": args.sdk_version,
            "core_tag": args.core_tag, "core_commit": args.core_commit, "candidate_run_id": str(args.candidate_run_id),
            "candidate_run_attempt": args.candidate_run_attempt, "completion_run_id": str(args.completion_run_id),
            "completion_run_attempt": args.completion_run_attempt, "completion_source_sha": args.completion_source_sha,
            "repository": self.api.SDK_REPOSITORY, "accepted": True, "registry_consumer_file": consumer.name,
            "registry_consumer_sha256": self.api.sha256(consumer)}
        self.api.write_json(args.output / "formal-proof.json", {**accepted, "candidate_attempt_evidence": receipt["attempt_evidence"],
            "completion_attempt_evidence": observed, "main_release": self.api.release_state(main, args.source_sha)})
        self.api.write_json(args.output / "accepted.json", accepted)
        return accepted
