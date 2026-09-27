"""
Exercise shared embedded JSON vectors through the production response decoder.
通过生产响应解码器执行共享嵌入式 JSON 向量。
"""

from __future__ import annotations

import json
import importlib.resources
import struct
import unittest

from luaskills.embedded_transport import EmbeddedTransport
from luaskills.embedded_json import decode_embedded_json, encode_embedded_json


def fingerprint(value):
    """
    Return a semantic fingerprint of value, preserving integer intent and all binary64 bits.
    返回 value 的语义指纹，保留整数意图及全部双精度浮点位。
    """
    if value is None:
        return ["null"]
    if type(value) is bool:
        return ["boolean", value]
    if type(value) is int:
        return ["integer", str(value)]
    if type(value) is float:
        return ["float", struct.pack(">d", value).hex()]
    if type(value) is str:
        return ["string", value]
    if type(value) is list:
        return ["array", [fingerprint(child) for child in value]]
    if type(value) is dict:
        return ["object", {key: fingerprint(child) for key, child in value.items()}]
    raise AssertionError(f"unsupported decoded type: {type(value)}")


class EmbeddedJsonVectorTests(unittest.TestCase):
    """
    Use the core corpus bundled inside the exact SDK contract; never probe neighboring repositories.
    使用精确 SDK 契约内分发的核心语料；绝不探测相邻仓库。
    """

    @classmethod
    def setUpClass(cls):
        """
        Read the packaged corpus once and reject an unsupported vector version before assertions.
        一次性读取包内语料，并在断言前拒绝不支持的向量版本。
        """
        # The contract digest covers every shared vector along with the generated wire schema.
        # 契约摘要将每个共享向量与生成的线 Schema 一同覆盖。
        cls.corpus = json.loads(importlib.resources.files("luaskills").joinpath("contracts", "embedded", "v1", "contract.json").read_text(encoding="utf-8"))["json_vectors"]
        if cls.corpus["version"] != 1:
            raise AssertionError("unsupported shared JSON vector version")

    def test_valid_response_values(self):
        """
        Decode every valid value inside the actual success envelope and compare exact semantic evidence.
        在实际成功信封内解码全部有效值，并比较精确语义证据。
        """
        for case in self.corpus["valid"]:
            with self.subTest(case=case["id"]):
                decoded = EmbeddedTransport._decode('{"protocol_version":1,"status":"ok","result":' + case["json"] + '}')
                self.assertEqual(fingerprint(decoded), case["expected"])
                encoded = encode_embedded_json(decoded, 4096)
                self.assertEqual(fingerprint(decode_embedded_json(encoded.decode("utf-8"))), case["expected"])
                self.assertEqual(encode_embedded_json(decoded, len(encoded)), encoded)
                with self.assertRaises(ValueError):
                    encode_embedded_json(decoded, len(encoded) - 1)

    def test_invalid_response_values(self):
        """
        Reject shared malformed values before exposing any result to an SDK caller.
        在向 SDK 调用方暴露任何结果前，拒绝共享畸形值。
        """
        for case in self.corpus["invalid"]:
            with self.subTest(case=case["id"]):
                with self.assertRaises(ValueError):
                    EmbeddedTransport._decode('{"protocol_version":1,"status":"ok","result":' + case["json"] + '}')

    def test_invalid_response_envelopes(self):
        """
        Reject invalid envelope versions, discriminators, presence and error shapes from the shared corpus.
        拒绝共享语料中的无效信封版本、判别、字段存在性及错误形状。
        """
        for case in self.corpus["invalid_envelopes"]:
            with self.subTest(case=case["id"]):
                with self.assertRaises(ValueError):
                    EmbeddedTransport._decode(case["json"])

    def test_invalid_utf8(self):
        """
        Reject raw invalid byte sequences using the same strict UTF-8 decode as native transport.
        使用与原生传输相同的严格 UTF-8 解码拒绝原始无效字节序列。
        """
        for case in self.corpus["invalid_bytes"]:
            with self.subTest(case=case["id"]):
                with self.assertRaises(UnicodeDecodeError):
                    decode_embedded_json(bytes.fromhex(case["hex"]).decode("utf-8"))

    def test_encoder_rejects_coercion_cycles_and_hooks(self):
        """
        Reject non-JSON input without coercing object keys or invoking subclass serialization hooks.
        拒绝非 JSON 输入，不强制转换对象键或调用子类序列化钩子。
        """
        # A self-reference is invalid, while sharing a child without a cycle remains legal.
        # 自引用无效；共享无循环子项仍然合法。
        cycle = []
        cycle.append(cycle)
        for value in [1 << 64, -(1 << 63) - 1, float("nan"), float("inf"),
            {1: "converted"}, {None: 1}, (1, 2), b"bytes", {1, 2}, cycle, "\ud800"]:
            with self.subTest(kind=type(value)):
                with self.assertRaises(ValueError):
                    encode_embedded_json(value, 4096)
        child = {"ok": True}
        self.assertEqual(decode_embedded_json(encode_embedded_json([child, child], 4096).decode()), [child, child])

        class Hostile(dict):
            """
            Fail if the encoder tries to use an application-defined mapping hook.
            若编码器试图使用应用定义的映射钩子则失败。
            """

            def items(self):
                """
                Raise immediately; exact-type rejection must precede this hook.
                立即抛错；精确类型拒绝必须先于此钩子。
                """
                raise AssertionError("mapping hook executed")

        with self.assertRaises(ValueError):
            encode_embedded_json(Hostile(), 4096)


if __name__ == "__main__":
    unittest.main()
