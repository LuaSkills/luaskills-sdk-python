"""
Retain one bounded pump mutation across native return, local application and explicit recovery.
跨原生返回、本地应用及显式恢复保留一个有界事件泵变更。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .embedded_transport import EmbeddedResultReleaseError


@dataclass
class PumpDelivery:
    """
    Own an exact encoded mutation and its local application until delivery is proven.
    拥有精确编码变更及其本地应用，直到交付得到证明。
    The pump admits at most one such record and retains it before entering native code.
    事件泵最多接纳一条此记录，并在进入原生代码前保留它。
    """

    # Command kind and bounded immutable frame identify the exact original native action.
    # 命令种类及有界不可变帧标识精确原始原生动作。
    kind: str
    encoded: bytes
    # Application retains concrete registration or request owners, never a name-based rediscovery.
    # 应用保留具体注册或请求所有者，绝不按名称重新发现。
    apply: Callable[[Any], None]
    # Successful null is distinguished from absent evidence by the explicit available flag.
    # 显式 available 标记区分成功空值与缺失证据。
    value: Any = None
    available: bool = False
    returned: bool = False
    error: BaseException | None = None

    def capture(self, request: Callable[[bytes], Any]) -> None:
        """
        Execute request once on the owned executor and retain its outcome before notifying the event loop.
        在拥有执行器上执行 request 一次，并在通知事件循环前保留结果。
        Return nothing; even an adapter interruption remains evidence on this already-rooted record.
        无返回值；即使适配器中断，证据仍保留在已建立根引用的记录上。
        """
        try:
            self.value = request(self.encoded)
            self.available = True
        except BaseException as error:
            self.error = error
        finally:
            self.returned = True

    def result(self) -> Any:
        """
        Read retained delivery without another native call; reject absent or malformed evidence explicitly.
        读取保留交付而不再次调用原生；显式拒绝缺失或畸形证据。
        Return the original successful value, including null, or decode a copied release-failure response.
        返回包含空值在内的原成功值，或解码释放失败时复制的响应。
        """
        if not self.returned:
            raise RuntimeError("callback mutation has not returned; replay is forbidden")
        if self.available:
            return self.value
        if isinstance(self.error, EmbeddedResultReleaseError):
            return self.error.delivered_result()
        raise RuntimeError("original callback mutation delivery is unavailable; replay is forbidden") from self.error
