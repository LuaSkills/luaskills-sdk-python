"""
High-level Python client for the LuaSkills public JSON FFI surface.
LuaSkills 公共 JSON FFI 表面的高级 Python 客户端。
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlparse

from .ffi import LuaSkillsJsonFfi, ManagedSessionWakeCallback
from .roots import RuntimeRoots, normalized_path
from .runtime_assets import host_options_from_runtime_manifest, load_runtime_install_manifest
from .types import Authority, JsonValue, LuaInvocationContext, RuntimeSkillRoot, SkillInstallSourceType, authority_value, roots_to_json

# Generic JSON object payload used by runtime-lease and system helpers.
# 运行时租约与 system 辅助器使用的通用 JSON 对象载荷。
JsonMap = dict[str, JsonValue]

# Supported skill lifecycle JSON FFI action names.
# 受支持的 skill 生命周期 JSON FFI 动作名称。
SkillLifecycleAction = Literal["disable_skill", "enable_skill", "uninstall_skill", "install_skill", "update_skill"]

# Runtime whitelist for skill lifecycle actions accepted by FFI name construction.
# FFI 函数名构造接受的 skill 生命周期动作运行时白名单。
SKILL_LIFECYCLE_ACTIONS: tuple[SkillLifecycleAction, ...] = (
    "disable_skill",
    "enable_skill",
    "uninstall_skill",
    "install_skill",
    "update_skill",
)

# Exact Rust SkillInstallRequest JSON keys accepted by SDK lifecycle wrappers.
# SDK 生命周期封装接受的精确 Rust SkillInstallRequest JSON 键。
SKILL_INSTALL_REQUEST_KEYS = frozenset(("skill_id", "source", "source_type"))

# Source types whose source locator is parsed as an absolute remote URL.
# source 定位值会被解析为绝对远程 URL 的来源类型。
URL_SKILL_INSTALL_SOURCE_TYPES = frozenset((
    SkillInstallSourceType.URL.value,
    SkillInstallSourceType.PRIVATE_URL_MANIFEST.value,
))

# Supported runtime-lease JSON FFI action names.
# 受支持的运行时租约 JSON FFI 动作名称。
RuntimeLeaseAction = Literal["create", "eval", "status", "list", "close"]

# Runtime whitelist for runtime-lease actions accepted by raw dispatch.
# 原始分发接受的运行时租约动作运行时白名单。
RUNTIME_LEASE_ACTIONS: tuple[RuntimeLeaseAction, ...] = ("create", "eval", "status", "list", "close")


class LuaSkillsClient:
    """
    High-level LuaSkills SDK client over the public JSON FFI surface.
    基于公共 JSON FFI 表面的高级 LuaSkills SDK 客户端。
    """

    def __init__(
        self,
        *,
        library_path: str | os.PathLike[str] | None = None,
        runtime_root: str | os.PathLike[str] | None = None,
        engine_options: dict[str, Any] | None = None,
        host_options: dict[str, Any] | None = None,
        pool_config: dict[str, Any] | None = None,
        ensure_runtime_layout: bool = True,
    ) -> None:
        """
        Create one native LuaSkills engine and wrap it in a high-level client.
        创建一个原生 LuaSkills 引擎并封装为高级客户端。
        """

        runtime_root_path = Path(runtime_root or Path.cwd() / "luaskills-runtime").expanduser().resolve()
        self.ffi = LuaSkillsJsonFfi(library_path, runtime_root_path)
        options = engine_options or create_engine_options(runtime_root_path, host_options=host_options, pool_config=pool_config)
        if engine_options is None and ensure_runtime_layout:
            RuntimeRoots.ensure_layout(runtime_root_path)
        handle = self.ffi.call_json("luaskills_ffi_engine_new_json", {"options": options})
        self._engine_id = int(handle["engine_id"])
        self._lifecycle_condition = threading.Condition()
        self._active_calls = 0
        self._closing = False
        self._closed = False
        self.config = SkillConfigClient(self)
        self.skills = SkillManagementClient(self, system_plane=False)

    @property
    def engine_id(self) -> int:
        """
        Return the immutable native engine handle identifier.
        返回不可变的原生引擎句柄标识符。
        """

        return self._engine_id

    @property
    def closed(self) -> bool:
        """
        Return whether the native engine handle has been released.
        返回原生引擎句柄是否已经释放。
        """

        with self._lifecycle_condition:
            return self._closed

    def __enter__(self) -> "LuaSkillsClient":
        """
        Return this client when used as a context manager.
        作为上下文管理器使用时返回当前客户端。
        """

        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """
        Close the native engine handle when leaving a context manager.
        离开上下文管理器时关闭原生引擎句柄。
        """

        self.close()

    @staticmethod
    def version(
        *,
        library_path: str | os.PathLike[str] | None = None,
        runtime_root: str | os.PathLike[str] | None = None,
    ) -> dict[str, Any]:
        """
        Query the JSON FFI version without creating a runtime engine.
        不创建运行时引擎并查询 JSON FFI 版本。
        """

        return LuaSkillsJsonFfi(library_path, runtime_root).call_json_no_input("luaskills_ffi_version_json")

    @staticmethod
    def describe(
        *,
        library_path: str | os.PathLike[str] | None = None,
        runtime_root: str | os.PathLike[str] | None = None,
    ) -> dict[str, Any]:
        """
        Query the JSON FFI self-description without creating a runtime engine.
        不创建运行时引擎并查询 JSON FFI 自描述。
        """

        return LuaSkillsJsonFfi(library_path, runtime_root).call_json_no_input("luaskills_ffi_describe_json")

    def poll_managed_session_events(
        self,
        max_events: int,
        authority: Authority | str = Authority.SYSTEM,
    ) -> JsonMap:
        """
        Destructively drain one bounded engine-level managed-session event batch.
        以破坏性方式排空一批有界的引擎级受管会话事件。
        """

        if max_events <= 0:
            raise ValueError("max_events must be positive")
        return cast(JsonMap, self._call(
            "luaskills_ffi_managed_session_events_poll_json",
            {"engine_id": self.engine_id, "max_events": max_events, "authority": authority_value(authority)},
        ))

    def wait_managed_session_events(
        self,
        max_events: int,
        timeout_ms: int,
        authority: Authority | str = Authority.SYSTEM,
    ) -> JsonMap:
        """
        Wait for and destructively drain one bounded engine-level managed-session event batch.
        等待并以破坏性方式排空一批有界的引擎级受管会话事件。
        """

        if max_events <= 0:
            raise ValueError("max_events must be positive")
        if timeout_ms < 0:
            raise ValueError("timeout_ms must be non-negative")
        return cast(JsonMap, self._call(
            "luaskills_ffi_managed_session_events_wait_json",
            {
                "engine_id": self.engine_id,
                "max_events": max_events,
                "timeout_ms": timeout_ms,
                "authority": authority_value(authority),
            },
        ))

    def set_managed_session_wake_callback(self, callback: ManagedSessionWakeCallback | None) -> None:
        """
        Register, replace, or clear this engine's managed-session wake callback.
        注册、替换或清除当前引擎的受管会话唤醒回调。
        """

        self.ffi.set_managed_session_wake_callback(self.engine_id, callback)

    def system(self, authority: Authority | str = Authority.SYSTEM) -> "SystemSkillManagementClient":
        """
        Return one system-management namespace bound to host-injected authority.
        返回绑定到宿主注入权限的 system 管理命名空间。
        """

        return SystemSkillManagementClient(self, authority)

    def runtime_leases(self) -> "RuntimeLeaseClient":
        """
        Return one runtime-lease namespace over the public JSON FFI surface.
        返回一个基于公共 JSON FFI 接口的运行时租约命名空间。
        """

        return RuntimeLeaseClient(self)

    def load_from_roots(self, skill_roots: list[RuntimeSkillRoot | dict[str, str]]) -> dict[str, Any]:
        """
        Load skills from the formal ordered root chain.
        从正式有序 root 链加载 skills。
        """

        return self._call("luaskills_ffi_load_from_roots_json", {
            "engine_id": self.engine_id,
            "skill_roots": roots_to_json(skill_roots),
        })

    def reload_from_roots(self, skill_roots: list[RuntimeSkillRoot | dict[str, str]]) -> dict[str, Any]:
        """
        Reload skills from the formal ordered root chain.
        从正式有序 root 链重载 skills。
        """

        return self._call("luaskills_ffi_reload_from_roots_json", {
            "engine_id": self.engine_id,
            "skill_roots": roots_to_json(skill_roots),
        })

    def list_entries(self, authority: Authority | str = Authority.DELEGATED_TOOL) -> list[dict[str, Any]]:
        """
        List runtime entries visible to the selected authority.
        列出指定权限可见的运行时入口。
        """

        return self._call("luaskills_ffi_list_entries_json", {"engine_id": self.engine_id, "authority": authority_value(authority)})

    def list_skill_help(self, authority: Authority | str = Authority.DELEGATED_TOOL) -> list[dict[str, Any]]:
        """
        List runtime help trees visible to the selected authority.
        列出指定权限可见的运行时帮助树。
        """

        return self._call("luaskills_ffi_list_skill_help_json", {"engine_id": self.engine_id, "authority": authority_value(authority)})

    def render_skill_help_detail(
        self,
        skill_id: str,
        flow_name: str = "main",
        *,
        authority: Authority | str = Authority.DELEGATED_TOOL,
        request_context: JsonValue | None = None,
    ) -> dict[str, Any] | None:
        """
        Render one help flow detail visible to the selected authority.
        渲染指定权限可见的单个帮助流程详情。
        """

        return self._call("luaskills_ffi_render_skill_help_detail_json", {
            "engine_id": self.engine_id,
            "skill_id": skill_id,
            "flow_name": flow_name,
            "request_context": request_context,
            "authority": authority_value(authority),
        })

    def prompt_argument_completions(
        self,
        prompt_name: str,
        argument_name: str,
        authority: Authority | str = Authority.DELEGATED_TOOL,
    ) -> list[str] | None:
        """
        Query prompt argument completions visible to the selected authority.
        查询指定权限可见的 prompt 参数补全项。
        """

        return self._call("luaskills_ffi_prompt_argument_completions_json", {
            "engine_id": self.engine_id,
            "prompt_name": prompt_name,
            "argument_name": argument_name,
            "authority": authority_value(authority),
        })

    def is_skill(self, tool_name: str, authority: Authority | str = Authority.DELEGATED_TOOL) -> bool:
        """
        Return whether one canonical tool name is visible as a skill entry.
        返回指定 canonical 工具名是否可见为 skill 入口。
        """

        result = self._call("luaskills_ffi_is_skill_json", {
            "engine_id": self.engine_id,
            "tool_name": tool_name,
            "authority": authority_value(authority),
        })
        return bool(result["value"])

    def skill_name_for_tool(self, tool_name: str, authority: Authority | str = Authority.DELEGATED_TOOL) -> str | None:
        """
        Resolve the owning skill id for one visible canonical tool name.
        解析单个可见 canonical 工具名称所属的 skill id。
        """

        result = self._call("luaskills_ffi_skill_name_for_tool_json", {
            "engine_id": self.engine_id,
            "tool_name": tool_name,
            "authority": authority_value(authority),
        })
        return result.get("skill_id")

    def call_skill(
        self,
        tool_name: str,
        args: JsonValue | None = None,
        invocation_context: LuaInvocationContext | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Call one active skill entry by canonical tool name.
        按 canonical 工具名称调用单个已激活 skill 入口。
        """

        return self._call("luaskills_ffi_call_skill_json", {
            "engine_id": self.engine_id,
            "tool_name": tool_name,
            "args": args or {},
            "invocation_context": invocation_context_to_json(invocation_context),
        })

    def run_lua(
        self,
        code: str,
        args: JsonValue | None = None,
        invocation_context: LuaInvocationContext | dict[str, Any] | None = None,
    ) -> Any:
        """
        Execute one inline Lua snippet against the active runtime.
        针对当前活动运行时执行单段内联 Lua。
        """

        return self._call("luaskills_ffi_run_lua_json", {
            "engine_id": self.engine_id,
            "code": code,
            "args": args or {},
            "invocation_context": invocation_context_to_json(invocation_context),
        })

    def close(self) -> dict[str, Any] | None:
        """
        Release the native engine handle.
        释放原生引擎句柄。
        """

        engine_id = self._begin_close()
        if engine_id is None:
            return None
        try:
            result = self.ffi.call_json("luaskills_ffi_engine_free_json", {"engine_id": engine_id})
        except BaseException as exc:
            self._finish_close(exc)
            raise
        self._finish_close(None)
        return result

    def _call(self, function_name: str, payload: dict[str, Any]) -> Any:
        """
        Call one JSON FFI function after checking the engine handle state.
        检查引擎句柄状态后调用一个 JSON FFI 函数。
        """

        self._begin_call()
        try:
            return self.ffi.call_json(function_name, payload)
        finally:
            self._end_call()

    def _begin_call(self) -> None:
        """
        Reserve the native engine handle for one FFI dispatch.
        为单次 FFI 分发保留原生引擎句柄。
        """

        with self._lifecycle_condition:
            if self._closed:
                raise RuntimeError(f"LuaSkills engine {self._engine_id} is already closed")
            if self._closing:
                raise RuntimeError(f"LuaSkills engine {self._engine_id} is closing")
            self._active_calls += 1

    def _end_call(self) -> None:
        """
        Release one active FFI call reservation and wake pending close calls.
        释放一个活跃 FFI 调用占用并唤醒等待中的关闭调用。
        """

        with self._lifecycle_condition:
            self._active_calls -= 1
            if self._active_calls == 0:
                self._lifecycle_condition.notify_all()

    def _begin_close(self) -> int | None:
        """
        Start the exclusive close phase after all active FFI calls finish.
        在所有活跃 FFI 调用结束后启动独占关闭阶段。
        """

        with self._lifecycle_condition:
            while self._closing:
                self._lifecycle_condition.wait()
            if self._closed:
                return None
            self._closing = True
            while self._active_calls > 0:
                self._lifecycle_condition.wait()
            return self._engine_id

    def _finish_close(self, close_error: BaseException | None) -> None:
        """
        Complete the close phase and publish the final lifecycle state.
        完成关闭阶段并发布最终生命周期状态。
        """

        with self._lifecycle_condition:
            if close_error is None:
                self._closed = True
            self._closing = False
            self._lifecycle_condition.notify_all()


class SkillConfigClient:
    """
    Skill-config namespace backed by the unified runtime config store.
    基于统一运行时配置存储的 skill 配置命名空间。
    """

    def __init__(self, client: LuaSkillsClient) -> None:
        """
        Create one skill-config namespace for a parent SDK client.
        为父级 SDK 客户端创建一个 skill 配置命名空间。
        """

        self.client = client

    def list(self, skill_id: str | None = None) -> list[dict[str, Any]]:
        """
        List flattened config records, optionally limited to one skill id.
        列出扁平化配置记录，并可选限制到单个 skill id。
        """

        return self.client._call("luaskills_ffi_skill_config_list_json", {"engine_id": self.client.engine_id, "skill_id": skill_id})

    def get(self, skill_id: str, key: str) -> dict[str, Any]:
        """
        Get one config value by skill id and key.
        按 skill id 与 key 获取单个配置值。
        """

        return self.client._call("luaskills_ffi_skill_config_get_json", {"engine_id": self.client.engine_id, "skill_id": skill_id, "key": key})

    def set(self, skill_id: str, key: str, value: str) -> dict[str, Any]:
        """
        Set one config value by skill id and key.
        按 skill id 与 key 设置单个配置值。
        """

        return self.client._call("luaskills_ffi_skill_config_set_json", {
            "engine_id": self.client.engine_id,
            "skill_id": skill_id,
            "key": key,
            "value": value,
        })

    def delete(self, skill_id: str, key: str) -> dict[str, Any]:
        """
        Delete one config value by skill id and key.
        按 skill id 与 key 删除单个配置值。
        """

        return self.client._call("luaskills_ffi_skill_config_delete_json", {"engine_id": self.client.engine_id, "skill_id": skill_id, "key": key})


class SkillManagementClient:
    """
    Ordinary and system lifecycle namespace over JSON FFI management entrypoints.
    覆盖 JSON FFI 管理入口的普通与 system 生命周期命名空间。
    """

    def __init__(
        self,
        client: LuaSkillsClient,
        *,
        system_plane: bool,
        authority: Authority | str = Authority.SYSTEM,
    ) -> None:
        """
        Create one lifecycle namespace for a parent SDK client.
        为父级 SDK 客户端创建一个生命周期命名空间。
        """

        self.client = client
        self.system_plane = system_plane
        self.authority = authority

    def disable(self, skill_roots: list[RuntimeSkillRoot | dict[str, str]], skill_id: str, reason: str | None = None) -> dict[str, Any]:
        """
        Disable one skill through formal root-chain lifecycle state.
        通过正式 root 链生命周期状态停用单个 skill。
        """

        return self.client._call(self._function_name("disable_skill"), {
            "engine_id": self.client.engine_id,
            "skill_roots": roots_to_json(skill_roots),
            "skill_id": skill_id,
            "reason": reason,
            **self._authority_payload(),
        })

    def enable(self, skill_roots: list[RuntimeSkillRoot | dict[str, str]], skill_id: str) -> dict[str, Any]:
        """
        Enable one skill through formal root-chain lifecycle state.
        通过正式 root 链生命周期状态启用单个 skill。
        """

        return self.client._call(self._function_name("enable_skill"), {
            "engine_id": self.client.engine_id,
            "skill_roots": roots_to_json(skill_roots),
            "skill_id": skill_id,
            **self._authority_payload(),
        })

    def install(
        self,
        skill_roots: list[RuntimeSkillRoot | dict[str, str]],
        request: dict[str, Any],
        *,
        target_root: RuntimeSkillRoot | dict[str, str] | None = None,
        authority: Authority | str | None = None,
    ) -> dict[str, Any]:
        """
        Install one managed skill through the current lifecycle namespace.
        通过当前生命周期命名空间安装单个受管 skill。
        """

        return self._apply("install_skill", skill_roots, request, target_root=target_root, authority=authority)

    def update(
        self,
        skill_roots: list[RuntimeSkillRoot | dict[str, str]],
        request: dict[str, Any],
        *,
        target_root: RuntimeSkillRoot | dict[str, str] | None = None,
        authority: Authority | str | None = None,
    ) -> dict[str, Any]:
        """
        Update one managed skill through the current lifecycle namespace.
        通过当前生命周期命名空间更新单个受管 skill。
        """

        return self._apply("update_skill", skill_roots, request, target_root=target_root, authority=authority)

    def uninstall(
        self,
        skill_roots: list[RuntimeSkillRoot | dict[str, str]],
        skill_id: str,
        *,
        options: dict[str, Any] | None = None,
        target_root: RuntimeSkillRoot | dict[str, str] | None = None,
        authority: Authority | str | None = None,
    ) -> dict[str, Any]:
        """
        Uninstall one skill and optionally clean its databases.
        卸载单个 skill，并可选清理其数据库。
        """

        return self.client._call(self._function_name("uninstall_skill"), {
            "engine_id": self.client.engine_id,
            "skill_roots": roots_to_json(skill_roots),
            "skill_id": skill_id,
            "options": options or {},
            "target_root": root_to_json(target_root),
            **self._authority_payload(authority),
        })

    def _apply(
        self,
        action_name: Literal["install_skill", "update_skill"],
        skill_roots: list[RuntimeSkillRoot | dict[str, str]],
        request: dict[str, Any],
        *,
        target_root: RuntimeSkillRoot | dict[str, str] | None,
        authority: Authority | str | None,
    ) -> dict[str, Any]:
        """
        Execute one install or update JSON FFI action.
        执行单个 install 或 update JSON FFI 动作。
        """

        validated_request = validate_skill_install_request(action_name, request)
        return self.client._call(self._function_name(action_name), {
            "engine_id": self.client.engine_id,
            "skill_roots": roots_to_json(skill_roots),
            "request": validated_request,
            "target_root": root_to_json(target_root),
            **self._authority_payload(authority),
        })

    def _function_name(self, action_name: SkillLifecycleAction) -> str:
        """
        Build the concrete JSON FFI function name for the current namespace.
        为当前命名空间构造具体 JSON FFI 函数名称。
        """

        base_name = skill_lifecycle_action_value(action_name)
        prefix = "system_" if self.system_plane else ""
        return f"luaskills_ffi_{prefix}{base_name}_json"

    def _authority_payload(self, authority: Authority | str | None = None) -> dict[str, str]:
        """
        Build the authority payload required by system JSON FFI entrypoints.
        构造 system JSON FFI 入口要求的权限载荷。
        """

        if not self.system_plane:
            return {}
        return {"authority": authority_value(authority or self.authority)}


class SystemSkillManagementClient(SkillManagementClient):
    """
    System engine namespace with host-injected authority.
    携带宿主注入权限的 system 引擎命名空间。
    """

    def __init__(self, client: LuaSkillsClient, authority: Authority | str) -> None:
        """
        Create one system engine namespace for a parent SDK client.
        为父级 SDK 客户端创建一个 system 引擎命名空间。
        """

        super().__init__(client, system_plane=True, authority=authority)

    def install_private_url_manifest(
        self,
        skill_roots: list[RuntimeSkillRoot | dict[str, str]],
        skill_id: str,
        manifest_url: str,
        *,
        target_root: RuntimeSkillRoot | dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Install one host-approved private URL-manifest skill through the system-private JSON FFI endpoint.
        通过 system 私有 JSON FFI 入口安装单个宿主已批准的私有 URL manifest 技能。
        """

        return self._private_url_manifest("install", skill_roots, skill_id, manifest_url, target_root=target_root)

    def update_private_url_manifest(
        self,
        skill_roots: list[RuntimeSkillRoot | dict[str, str]],
        skill_id: str,
        manifest_url: str,
        *,
        target_root: RuntimeSkillRoot | dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Update one host-approved private URL-manifest skill through the system-private JSON FFI endpoint.
        通过 system 私有 JSON FFI 入口更新单个宿主已批准的私有 URL manifest 技能。
        """

        return self._private_url_manifest("update", skill_roots, skill_id, manifest_url, target_root=target_root)

    def _call_object(self, function_name: str, payload: JsonMap | None = None) -> JsonMap:
        """
        Call one authority-bound JSON FFI function and require an object-shaped result payload.
        调用一个绑定 authority 的 JSON FFI 函数并要求返回对象形状结果载荷。
        """

        return require_json_map(
            self.client._call(function_name, self._with_engine_authority(payload or {})),
            f"{function_name} object result",
        )

    def _call_value(self, function_name: str, payload: JsonMap | None = None) -> JsonValue:
        """
        Call one authority-bound JSON FFI function and return any decoded JSON result shape.
        调用一个绑定 authority 的 JSON FFI 函数并返回任意已解码 JSON 结果形状。
        """

        return self.client._call(function_name, self._with_engine_authority(payload or {}))

    def runtime_leases(self) -> "RuntimeLeaseClient":
        """
        Return one authority-bound runtime-lease namespace.
        返回一个绑定 authority 的运行时租约命名空间。
        """

        return RuntimeLeaseClient(self.client, authority=self.authority)

    def list_entries(self) -> list[dict[str, Any]]:
        """
        List runtime entries visible to the bound authority.
        列出当前绑定 authority 可见的运行时入口。
        """

        result = self._call_value("luaskills_ffi_list_entries_json")
        if not isinstance(result, list):
            raise RuntimeError("luaskills_ffi_list_entries_json did not return one array result")
        return [entry for entry in result if isinstance(entry, dict)]

    def list_skill_help(self) -> list[dict[str, Any]]:
        """
        List skill help trees visible to the bound authority.
        列出当前绑定 authority 可见的技能帮助树。
        """

        result = self._call_value("luaskills_ffi_list_skill_help_json")
        if not isinstance(result, list):
            raise RuntimeError("luaskills_ffi_list_skill_help_json did not return one array result")
        return [entry for entry in result if isinstance(entry, dict)]

    def render_skill_help_detail(
        self,
        skill_id: str,
        flow_name: str = "main",
        request_context: JsonValue | None = None,
    ) -> dict[str, Any] | None:
        """
        Render one help flow detail visible to the bound authority.
        渲染当前绑定 authority 可见的单个帮助流程详情。
        """

        payload: JsonMap = {
            "skill_id": skill_id,
            "flow_name": flow_name,
        }
        if request_context is not None:
            payload["request_context"] = request_context
        result = self._call_value("luaskills_ffi_render_skill_help_detail_json", payload)
        if result is None:
            return None
        return require_json_map(result, "luaskills_ffi_render_skill_help_detail_json object result")

    def prompt_argument_completions(self, prompt_name: str, argument_name: str) -> list[str] | None:
        """
        Query prompt argument completions visible to the bound authority.
        查询当前绑定 authority 可见的 prompt 参数补全项。
        """

        result = self._call_value(
            "luaskills_ffi_prompt_argument_completions_json",
            {
                "prompt_name": prompt_name,
                "argument_name": argument_name,
            },
        )
        if result is None:
            return None
        if not isinstance(result, list):
            raise RuntimeError("luaskills_ffi_prompt_argument_completions_json did not return one array result")
        return [value for value in result if isinstance(value, str)]

    def is_skill(self, tool_name: str) -> bool:
        """
        Return whether one canonical tool name resolves to one visible skill entry.
        返回某个 canonical 工具名是否解析为一个可见技能入口。
        """

        result = self._call_object(
            "luaskills_ffi_is_skill_json",
            {
                "tool_name": tool_name,
            },
        )
        value = result.get("value")
        if isinstance(value, bool):
            return value
        raise RuntimeError("luaskills_ffi_is_skill_json did not return one boolean value field")

    def skill_name_for_tool(self, tool_name: str) -> str | None:
        """
        Resolve the visible owning skill id for one canonical tool name when available.
        在可见时解析某个 canonical 工具名所属的技能标识。
        """

        result = self._call_object(
            "luaskills_ffi_skill_name_for_tool_json",
            {
                "tool_name": tool_name,
            },
        )
        skill_id = result.get("skill_id")
        if skill_id is None or isinstance(skill_id, str):
            return skill_id
        raise RuntimeError("luaskills_ffi_skill_name_for_tool_json did not return a nullable string field")

    def _with_engine_authority(self, payload: JsonMap) -> JsonMap:
        """
        Attach the bound engine id and authority to one outgoing payload.
        为单个发出的载荷附加已绑定的引擎标识与 authority。
        """

        return {
            **payload,
            "engine_id": self.client.engine_id,
            "authority": authority_value(self.authority),
        }

    def _private_url_manifest(
        self,
        action_name: Literal["install", "update"],
        skill_roots: list[RuntimeSkillRoot | dict[str, str]],
        skill_id: str,
        manifest_url: str,
        *,
        target_root: RuntimeSkillRoot | dict[str, str] | None,
    ) -> dict[str, Any]:
        """
        Execute one host-private URL-manifest install or update operation.
        执行单个宿主私有 URL manifest 安装或更新操作。
        """

        validate_private_url_manifest_input(skill_id, manifest_url)
        return require_json_map(
            self.client._call(
                f"luaskills_ffi_system_private_{action_name}_skill_from_url_manifest_json",
                {
                    "engine_id": self.client.engine_id,
                    "skill_roots": roots_to_json(skill_roots),
                    "skill_id": skill_id,
                    "manifest_url": manifest_url,
                    "target_root": root_to_json(target_root),
                    "authority": authority_value(Authority.SYSTEM),
                },
            ),
            f"private URL manifest {action_name} result",
        )


def skill_lifecycle_action_value(action: str) -> SkillLifecycleAction:
    """
    Return one validated skill lifecycle action string for JSON FFI function names.
    返回一个用于 JSON FFI 函数名的已验证 skill 生命周期动作字符串。
    """

    if action in SKILL_LIFECYCLE_ACTIONS:
        return cast(SkillLifecycleAction, action)
    raise ValueError(f"unsupported skill lifecycle action: {action}")


def validate_skill_install_request(action_name: SkillLifecycleAction, request: dict[str, Any]) -> dict[str, JsonValue]:
    """
    Return a protocol-shaped install or update request after rejecting malformed SDK input.
    拒绝格式错误的 SDK 输入后返回符合协议形状的安装或更新请求。
    """

    if not isinstance(request, dict):
        raise ValueError("skill install request must be one JSON object")
    unknown_keys = sorted(str(key) for key in request if not isinstance(key, str) or key not in SKILL_INSTALL_REQUEST_KEYS)
    if unknown_keys:
        raise ValueError(f"skill install request contains unsupported keys: {', '.join(unknown_keys)}")
    source_type = require_skill_install_source_type(request.get("source_type"))
    skill_id = optional_exact_non_blank_string(request.get("skill_id"), "skill_id")
    source = optional_exact_non_blank_string(request.get("source"), "source")
    if source is not None and source_type in URL_SKILL_INSTALL_SOURCE_TYPES:
        validate_http_url(source, "source")
    validate_skill_install_request_presence(action_name, source_type, skill_id, source)
    validated: dict[str, JsonValue] = {"source_type": source_type}
    if skill_id is not None:
        validated["skill_id"] = skill_id
    if source is not None:
        validated["source"] = source
    return validated


def require_skill_install_source_type(value: object) -> str:
    """
    Return one supported Rust SkillInstallSourceType value from an SDK request field.
    从 SDK 请求字段返回一个受支持的 Rust SkillInstallSourceType 值。
    """

    if isinstance(value, SkillInstallSourceType):
        return value.value
    if isinstance(value, str) and value in {source_type.value for source_type in SkillInstallSourceType}:
        return value
    raise ValueError("skill install request source_type must be one of github, official_hub, url, private_url_manifest")


def validate_skill_install_request_presence(
    action_name: SkillLifecycleAction,
    source_type: str,
    skill_id: str | None,
    source: str | None,
) -> None:
    """
    Enforce the identifiers and source locators consumed by the native resolver for one lifecycle action.
    强制校验原生解析器在单个生命周期动作中会消费的标识与来源定位值。
    """

    if action_name == "install_skill":
        validate_skill_install_presence(source_type, skill_id, source)
    elif action_name == "update_skill":
        validate_skill_update_presence(source_type, skill_id, source)


def validate_skill_install_presence(source_type: str, skill_id: str | None, source: str | None) -> None:
    """
    Enforce required fields for one install request before FFI dispatch.
    在 FFI 分发前强制校验单个安装请求的必填字段。
    """

    if source_type == SkillInstallSourceType.GITHUB.value and source is None:
        raise ValueError("github install request requires source")
    if source_type == SkillInstallSourceType.OFFICIAL_HUB.value and skill_id is None and source is None:
        raise ValueError("official_hub install request requires skill_id or source")
    if source_type == SkillInstallSourceType.URL.value and (skill_id is None or source is None):
        raise ValueError("url install request requires skill_id and source")
    if source_type == SkillInstallSourceType.PRIVATE_URL_MANIFEST.value and (skill_id is None or source is None):
        raise ValueError("private_url_manifest install request requires skill_id and source")


def validate_skill_update_presence(source_type: str, skill_id: str | None, source: str | None) -> None:
    """
    Enforce required fields for one update request before FFI dispatch.
    在 FFI 分发前强制校验单个更新请求的必填字段。
    """

    if source_type in (SkillInstallSourceType.GITHUB.value, SkillInstallSourceType.OFFICIAL_HUB.value):
        if skill_id is None and source is None:
            raise ValueError(f"{source_type} update request requires skill_id or source")
    elif skill_id is None:
        raise ValueError(f"{source_type} update request requires skill_id")


def validate_private_url_manifest_input(skill_id: str, manifest_url: str) -> None:
    """
    Validate the dedicated private URL-manifest shortcut payload before FFI dispatch.
    在 FFI 分发前校验专用私有 URL manifest 快捷入口载荷。
    """

    require_exact_non_blank_string(skill_id, "skill_id")
    validate_http_url(manifest_url, "manifest_url")


def optional_exact_non_blank_string(value: object, field_name: str) -> str | None:
    """
    Return an optional exact JSON string while rejecting empty or implicitly trimmed values.
    返回可选的精确 JSON 字符串，同时拒绝空值或需要隐式裁剪的值。
    """

    if value is None:
        return None
    if isinstance(value, str):
        return require_exact_non_blank_string(value, field_name)
    raise ValueError(f"skill install request {field_name} must be a string")


def require_exact_non_blank_string(value: str, field_name: str) -> str:
    """
    Return one non-empty string that does not require SDK-side whitespace normalization.
    返回一个不需要 SDK 侧空白规范化的非空字符串。
    """

    if not value or value.strip() != value:
        raise ValueError(f"skill install request {field_name} must be a non-empty string without surrounding whitespace")
    return value


def validate_http_url(value: str, field_name: str) -> None:
    """
    Reject non-HTTP, relative, or credential-bearing URLs before native download resolution.
    在原生下载解析前拒绝非 HTTP、相对路径或携带账号信息的 URL。
    """

    require_exact_non_blank_string(value, field_name)
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"skill install request {field_name} must be an absolute HTTP or HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"skill install request {field_name} must not include credentials")


def runtime_lease_action_value(action: str) -> RuntimeLeaseAction:
    """
    Return one validated runtime-lease action string for JSON FFI function names.
    返回一个用于 JSON FFI 函数名的已验证运行时租约动作字符串。
    """

    if action in RUNTIME_LEASE_ACTIONS:
        return cast(RuntimeLeaseAction, action)
    raise ValueError(f"unsupported runtime lease action: {action}")


class RuntimeLeaseClient:
    """
    Stateful runtime-lease namespace over the JSON FFI runtime-lease entrypoints.
    覆盖 JSON FFI 运行时租约入口的有状态运行时租约命名空间。
    """

    def __init__(
        self,
        client: LuaSkillsClient,
        authority: Authority | str | None = None,
    ) -> None:
        """
        Create one runtime-lease namespace for a parent SDK client.
        为父级 SDK 客户端创建一个运行时租约命名空间。
        """

        self.client = client
        self.authority = authority

    def call_raw(self, action: RuntimeLeaseAction, payload: JsonMap) -> JsonMap:
        """
        Dispatch one raw runtime-lease JSON request without applying success checks.
        分发单个原始运行时租约 JSON 请求而不附加成功校验。
        """

        request_payload: JsonMap = {
            **payload,
            "engine_id": self.client.engine_id,
        }
        if self.authority is not None:
            request_payload["authority"] = authority_value(self.authority)
        return require_json_map(
            self.client._call(self._runtime_lease_function_name(action), request_payload),
            f"runtime lease {action} result",
        )

    def create(
        self,
        sid: str,
        ttl_sec: int | None = None,
        replace: bool = False,
        *,
        cwd: str | None = None,
        workspace_root: str | None = None,
        lua_roots: list[str] | None = None,
        c_roots: list[str] | None = None,
        mounts: JsonValue | None = None,
        system_package: JsonMap | None = None,
    ) -> JsonMap:
        """
        Create or replace one persistent runtime lease.
        创建或替换一个持久运行时租约。
        """

        if self.authority is not None and (lua_roots is not None or c_roots is not None):
            raise ValueError("system runtime lease create does not accept lua_roots or c_roots")
        if self.authority is not None:
            if system_package is None:
                raise ValueError("system runtime lease create requires system_package")
            require_system_runtime_package(system_package)

        payload: JsonMap = {
            "sid": sid,
            "replace": replace,
        }
        if ttl_sec is not None:
            payload["ttl_sec"] = ttl_sec
        if cwd is not None:
            payload["cwd"] = cwd
        if workspace_root is not None:
            payload["workspace_root"] = workspace_root
        if lua_roots is not None:
            payload["lua_roots"] = lua_roots
        if c_roots is not None:
            payload["c_roots"] = c_roots
        if mounts is not None:
            payload["mounts"] = mounts
        if self.authority is not None:
            payload["system_package"] = system_package
        return require_runtime_lease_ok(
            self.call_raw("create", payload),
            "runtime lease create",
        )

    def create_handle(
        self,
        sid: str,
        ttl_sec: int | None = None,
        replace: bool = False,
        *,
        cwd: str | None = None,
        workspace_root: str | None = None,
        lua_roots: list[str] | None = None,
        c_roots: list[str] | None = None,
        mounts: JsonValue | None = None,
        system_package: JsonMap | None = None,
    ) -> "RuntimeLeaseHandle":
        """
        Create one runtime-lease handle object from one fresh create response.
        基于一份新的 create 响应创建一个运行时租约句柄对象。
        """

        return RuntimeLeaseHandle.from_payload(
            self,
            self.create(
                sid,
                ttl_sec=ttl_sec,
                replace=replace,
                cwd=cwd,
                workspace_root=workspace_root,
                lua_roots=lua_roots,
                c_roots=c_roots,
                mounts=mounts,
                system_package=system_package,
            ),
        )

    def bind_handle(self, payload: JsonMap) -> "RuntimeLeaseHandle":
        """
        Rebuild one runtime-lease handle object from one persisted payload.
        基于一份已持久化载荷重建一个运行时租约句柄对象。
        """

        return RuntimeLeaseHandle.from_payload(self, payload)

    def eval(
        self,
        lease_id: str,
        code: str,
        args: JsonMap | None = None,
        timeout_ms: int = 60_000,
        sid: str | None = None,
        generation: int | None = None,
        invocation_context: LuaInvocationContext | dict[str, Any] | None = None,
    ) -> JsonMap:
        """
        Evaluate one Lua chunk inside one persistent runtime lease.
        在一个持久运行时租约中执行单个 Lua 代码块。
        """

        payload: JsonMap = {
            "lease_id": lease_id,
            "code": code,
            "args": args or {},
            "timeout_ms": timeout_ms,
            "invocation_context": invocation_context_to_json(invocation_context),
        }
        if sid is not None:
            payload["sid"] = sid
        if generation is not None:
            payload["generation"] = generation
        return require_runtime_lease_ok(self.call_raw("eval", payload), "runtime lease eval")

    def status(
        self,
        lease_id: str,
        sid: str | None = None,
        generation: int | None = None,
    ) -> JsonMap:
        """
        Read one runtime lease status payload with optional identity guards.
        读取单个运行时租约状态载荷，并可附带可选身份护栏。
        """

        payload: JsonMap = {
            "lease_id": lease_id,
        }
        if sid is not None:
            payload["sid"] = sid
        if generation is not None:
            payload["generation"] = generation
        return self.call_raw("status", payload)

    def list(self, sid: str | None = None) -> JsonMap:
        """
        List active runtime leases and optionally filter by one SID.
        列出活跃运行时租约，并可按单个 SID 过滤。
        """

        payload: JsonMap = {}
        if sid is not None:
            payload["sid"] = sid
        return self.call_raw("list", payload)

    def list_handles(self, sid: str | None = None) -> list["RuntimeLeaseHandle"]:
        """
        List active runtime-lease handles rebuilt from the current lease listing payload.
        基于当前租约列表载荷重建活跃运行时租约句柄列表。
        """

        leases = self.list(sid).get("leases")
        if not isinstance(leases, list):
            raise RuntimeError("runtime lease list payload is missing the leases array")
        return [
            self.bind_handle(require_json_map(lease, "runtime lease entry"))
            for lease in leases
        ]

    def find_handle(self, sid: str) -> "RuntimeLeaseHandle | None":
        """
        Return the first active runtime-lease handle for one SID when present.
        返回某个 SID 的第一个活跃运行时租约句柄（如果存在）。
        """

        handles = self.list_handles(sid)
        return handles[0] if handles else None

    def close(
        self,
        lease_id: str,
        sid: str | None = None,
        generation: int | None = None,
    ) -> JsonMap:
        """
        Close one runtime lease and return its final status payload with optional identity guards.
        关闭单个运行时租约并返回其最终状态载荷，并可附带可选身份护栏。
        """

        payload: JsonMap = {
            "lease_id": lease_id,
        }
        if sid is not None:
            payload["sid"] = sid
        if generation is not None:
            payload["generation"] = generation
        return self.call_raw("close", payload)

    def uses_system_runtime_lease_endpoints(self) -> bool:
        """
        Return whether this helper will dispatch runtime-lease requests to dedicated system entrypoints.
        返回当前辅助器是否会把运行时租约请求分发到专用 system 入口。
        """

        return self.authority is not None

    def _runtime_lease_function_name(self, action: RuntimeLeaseAction) -> str:
        """
        Resolve the concrete runtime-lease JSON FFI entrypoint name for one logical action.
        为单个逻辑动作解析具体的运行时租约 JSON FFI 入口名称。
        """

        action_value = runtime_lease_action_value(action)
        public_name = f"luaskills_ffi_runtime_lease_{action_value}_json"
        if self.authority is None:
            return public_name
        return f"luaskills_ffi_system_runtime_lease_{action_value}_json"


class RuntimeLeaseHandle:
    """
    Stable host-side runtime-lease handle that carries lease identity guards automatically.
    自动携带租约身份护栏的稳定宿主侧运行时租约句柄。
    """

    def __init__(
        self,
        sessions: RuntimeLeaseClient,
        lease_id: str,
        sid: str,
        generation: int,
    ) -> None:
        """
        Bind one session client to one concrete lease identity triplet.
        将一个会话客户端绑定到一个具体的租约身份三元组。
        """

        self.sessions = sessions
        self.lease_id = lease_id
        self.sid = sid
        self.generation = generation

    @classmethod
    def from_payload(cls, sessions: RuntimeLeaseClient, payload: JsonMap) -> "RuntimeLeaseHandle":
        """
        Construct one runtime-lease handle from one payload that contains identity fields.
        从包含身份字段的一份载荷中构造一个运行时租约句柄。
        """

        return cls(
            sessions=sessions,
            lease_id=require_runtime_lease_string_field(payload, "lease_id"),
            sid=require_runtime_lease_string_field(payload, "sid"),
            generation=require_runtime_lease_int_field(payload, "generation"),
        )

    def identity_payload(self) -> JsonMap:
        """
        Export the stable lease identity fields for persistence or raw FFI calls.
        导出稳定租约身份字段，供持久化或原始 FFI 调用使用。
        """

        return {
            "lease_id": self.lease_id,
            "sid": self.sid,
            "generation": self.generation,
        }

    def eval(
        self,
        code: str,
        args: JsonMap | None = None,
        timeout_ms: int = 60_000,
        invocation_context: LuaInvocationContext | dict[str, Any] | None = None,
    ) -> JsonMap:
        """
        Evaluate Lua code while automatically attaching the stored lease identity guards.
        执行 Lua 代码时自动附带已保存的租约身份护栏。
        """

        return self.sessions.eval(
            self.lease_id,
            code,
            args=args,
            timeout_ms=timeout_ms,
            sid=self.sid,
            generation=self.generation,
            invocation_context=invocation_context,
        )

    def status(self) -> JsonMap:
        """
        Read the current lease status while automatically attaching the stored identity guards.
        读取当前租约状态时自动附带已保存的身份护栏。
        """

        return self.sessions.status(self.lease_id, sid=self.sid, generation=self.generation)

    def close(self) -> JsonMap:
        """
        Close the current lease while automatically attaching the stored identity guards.
        关闭当前租约时自动附带已保存的身份护栏。
        """

        return self.sessions.close(self.lease_id, sid=self.sid, generation=self.generation)


def require_runtime_lease_ok(payload: JsonMap, action: str) -> JsonMap:
    """
    Require one runtime-lease payload to report success.
    要求单个运行时租约载荷报告成功。
    """

    if payload.get("ok") is True:
        return payload
    raise RuntimeError(
        f"{action} failed: {payload.get('error_code') or 'unknown'}: {payload.get('message') or 'Unknown runtime lease error'}"
    )


def require_system_runtime_package(payload: JsonMap) -> None:
    """
    Validate the exact trusted System Plugin package descriptor required by Rust.
    校验 Rust 强制要求的精确信任 System Plugin 包描述符。
    """

    if set(payload) != {"id", "root", "dependencies_file"}:
        raise ValueError("system_package must contain exactly id, root, and dependencies_file")
    for field_name in ("id", "root", "dependencies_file"):
        value = payload[field_name]
        if not isinstance(value, str) or not value:
            raise ValueError(f"system_package {field_name} must be one non-empty string")


def require_runtime_lease_string_field(payload: JsonMap, field_name: str) -> str:
    """
    Read one required runtime-lease string field from one payload object.
    从一份载荷对象中读取一个必填的运行时租约字符串字段。
    """

    value = payload.get(field_name)
    if isinstance(value, str) and value:
        return value
    raise RuntimeError(f"runtime lease payload is missing required string field: {field_name}")


def require_runtime_lease_int_field(payload: JsonMap, field_name: str) -> int:
    """
    Read one required runtime-lease integer field from one payload object.
    从一份载荷对象中读取一个必填的运行时租约整数字段。
    """

    value = payload.get(field_name)
    if isinstance(value, int):
        return value
    raise RuntimeError(f"runtime lease payload is missing required integer field: {field_name}")


def require_json_map(value: JsonValue, context: str) -> JsonMap:
    """
    Require one arbitrary JSON value to be one plain object map.
    要求某个任意 JSON 值必须是普通对象映射。
    """

    if isinstance(value, dict):
        return value
    raise RuntimeError(f"{context} must be one JSON object")


def create_engine_options(
    runtime_root: str | os.PathLike[str],
    *,
    host_options: dict[str, Any] | None = None,
    pool_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build complete engine options from SDK defaults and caller overrides.
    基于 SDK 默认值和调用方覆盖构造完整引擎选项。
    """

    return {
        "pool_config": {**default_pool_config(), **(pool_config or {})},
        "host_options": merge_host_options(default_host_options(runtime_root), host_options or {}),
    }


def default_pool_config() -> dict[str, int]:
    """
    Return the SDK default VM pool configuration.
    返回 SDK 默认虚拟机池配置。
    """

    return {"min_size": 1, "max_size": 4, "idle_ttl_secs": 60}


def default_host_options(runtime_root: str | os.PathLike[str]) -> dict[str, Any]:
    """
    Return the SDK default host options for one runtime root.
    返回单个 runtime root 对应的 SDK 默认宿主选项。
    """

    root = Path(runtime_root).expanduser().resolve()
    base_options = {
        "runtime_root": normalized_path(root),
        "temp_dir": None,
        "resources_dir": None,
        "lua_packages_dir": None,
        "host_provided_tool_root": None,
        "host_provided_lua_root": None,
        "host_provided_ffi_root": None,
        "system_lua_lib_dir": None,
        "download_cache_root": None,
        "dependency_dir_name": "",
        "state_dir_name": "",
        "database_dir_name": "",
        "skill_config_file_path": None,
        "allow_network_download": True,
        "github_base_url": None,
        "github_api_base_url": None,
        "sqlite_library_path": None,
        "sqlite_provider_mode": "dynamic_library",
        "sqlite_callback_mode": "standard",
        "lancedb_library_path": None,
        "lancedb_provider_mode": "dynamic_library",
        "lancedb_callback_mode": "standard",
        "space_controller": default_space_controller_options(),
        "cache_config": None,
        "runlua_pool_config": None,
        "reserved_entry_names": [],
        "ignored_skill_ids": [],
        "capabilities": {
            "enable_skill_management_bridge": False,
            "enable_managed_io_compat": True,
        },
    }
    manifest = load_runtime_install_manifest(root)
    return merge_host_options(base_options, host_options_from_runtime_manifest(manifest)) if manifest else base_options


def default_space_controller_options() -> dict[str, Any]:
    """
    Return the SDK default space-controller options.
    返回 SDK 默认 space-controller 选项。
    """

    return {
        "endpoint": None,
        "auto_spawn": False,
        "executable_path": None,
        "process_mode": "managed",
        "minimum_uptime_secs": 300,
        "idle_timeout_secs": 900,
        "default_lease_ttl_secs": 120,
        "connect_timeout_secs": 5,
        "startup_timeout_secs": 15,
        "startup_retry_interval_ms": 250,
        "lease_renew_interval_secs": 30,
    }


def merge_host_options(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """
    Merge caller-provided host overrides over one complete host option object.
    将调用方提供的宿主覆盖合并到一个完整宿主选项对象上。
    """

    merged = {**base, **overrides}
    if "space_controller" in overrides:
        merged["space_controller"] = {**base["space_controller"], **overrides["space_controller"]}
    if "capabilities" in overrides:
        merged["capabilities"] = {**base["capabilities"], **overrides["capabilities"]}
    return merged


def invocation_context_to_json(context: LuaInvocationContext | dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Convert an optional invocation context into a JSON FFI object.
    将可选调用上下文转换为 JSON FFI 对象。
    """

    if context is None:
        return None
    if isinstance(context, LuaInvocationContext):
        return context.to_json()
    return {
        "request_context": context.get("request_context"),
        "client_budget": context.get("client_budget") or {},
        "tool_config": context.get("tool_config") or {},
    }


def root_to_json(root: RuntimeSkillRoot | dict[str, str] | None) -> dict[str, str] | None:
    """
    Convert an optional runtime root value into one JSON FFI object.
    将可选运行时 root 值转换为 JSON FFI 对象。
    """

    if root is None:
        return None
    return root.to_json() if isinstance(root, RuntimeSkillRoot) else root
