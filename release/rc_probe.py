from __future__ import annotations

import argparse
import json
import socket
from contextlib import contextmanager
from pathlib import Path

import safeprompt.adapters.paddle as paddle_adapter
from safeprompt.app import uie_model_dir
from safeprompt.core import detect, mask
from safeprompt.ner import to_findings
from safeprompt.recovery import ActiveRecoverySession
from safeprompt.storage import _protect, _unprotect


@contextmanager
def recording_network_guard(attempts: list[str]):
    original_socket = socket.socket
    original_create_connection = socket.create_connection

    class OfflineSocket(original_socket):
        def connect(self, address):
            attempts.append(repr(address))
            raise RuntimeError(f"network access blocked: {address!r}")

    def blocked_create_connection(address, *args, **kwargs):
        attempts.append(repr(address))
        raise RuntimeError(f"network access blocked: {address!r}")

    socket.socket = OfflineSocket
    socket.create_connection = blocked_create_connection
    try:
        yield
    finally:
        socket.socket = original_socket
        socket.create_connection = original_create_connection


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rc-probe", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path)
    args = parser.parse_args()
    attempts: list[str] = []
    paddle_adapter.deny_network = lambda: recording_network_guard(attempts)
    model_dir = (args.model_dir or uie_model_dir()).resolve()
    text = ("韩静反馈海川大学的门户无法登录。\n"
            "服务器：10.21.3.15\n电话：13812345678\n"
            "邮箱：hanjing@example.com\npassword=123456")
    unavailable = False
    error = None
    try:
        recognizer = paddle_adapter.load_uie_local(model_dir)
        results = recognizer.recognize(text)
    except Exception as caught:
        results = []
        unavailable = True
        error = f"{type(caught).__name__}: {caught}"
    dpapi_sample = b"SafePrompt RC synthetic sample"
    dpapi_roundtrip = _unprotect(_protect(dpapi_sample)) == dpapi_sample
    entity_findings = to_findings(text, results)
    findings = detect(text, extra_candidates=entity_findings)
    safe_text, resolved = mask(text, findings)
    recovery = ActiveRecoverySession()
    recovery.replace(resolved)
    ai_reply = ("建议先联系<PERSON_1>确认账号状态。\n"
                "如仍无法解决，可联系<ORG_1>管理员，\n"
                "并确认<EMAIL_1>是否有效。")
    restored = recovery.restore(ai_reply)
    clock = [0.0]
    lifecycle = ActiveRecoverySession(ttl_seconds=900, clock=lambda: clock[0])
    lifecycle.replace(resolved)
    clock[0] = 900.0
    expiry_ok = not lifecycle.active
    lifecycle.replace(resolved)
    _, newer = mask("李明", detect("李明", [("李明", "PERSON", True)]))
    lifecycle.replace(newer)
    overwrite_ok = lifecycle.restore("<PERSON_1>").text == "李明"
    lifecycle.clear()
    clear_ok = not lifecycle.active
    expected_safe = ("<PERSON_1>反馈<ORG_1>的门户无法登录。\n"
                     "服务器：<IP_1>\n电话：<PHONE_1>\n"
                     "邮箱：<EMAIL_1>\npassword=<PASSWORD_1>")
    expected_restored = ("建议先联系韩静确认账号状态。\n"
                         "如仍无法解决，可联系海川大学管理员，\n"
                         "并确认hanjing@example.com是否有效。")
    dictionary_ok = detect("测试客户", [("测试客户", "CUSTOMER", True)])[0].source == "dictionary"
    degraded_safe = mask("10.0.0.1 测试客户", detect(
        "10.0.0.1 测试客户", [("测试客户", "CUSTOMER", True)]))[0]
    payload = {
        "model_dir": str(model_dir),
        "unavailable": unavailable,
        "error": error,
        "network_attempts": attempts,
        "dpapi_roundtrip": dpapi_roundtrip,
        "entities": [
            {"category": item.category, "text": item.text, "start": item.start, "end": item.end}
            for item in results
        ],
        "safe_text": safe_text,
        "safe_text_matches": safe_text == expected_safe,
        "dictionary_ok": dictionary_ok,
        "degraded_safe_text": degraded_safe,
        "recovery": {
            "text": restored.text,
            "matches": restored.text == expected_restored,
            "restored_count": restored.restored_count,
            "unknown_count": restored.unknown_count,
            "expiry_ok": expiry_ok,
            "overwrite_ok": overwrite_ok,
            "clear_ok": clear_ok,
        },
    }
    args.output.resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    expected = [("PERSON", "韩静"), ("ORG", "海川大学")]
    actual = [(item.category, item.text) for item in results]
    full_ok = (actual == expected and safe_text == expected_safe and restored.text == expected_restored
               and expiry_ok and overwrite_ok and clear_ok
               and dictionary_ok and not attempts and dpapi_roundtrip)
    degraded_ok = unavailable and degraded_safe == "<IP_1> <CUSTOMER_1>" and not attempts and dpapi_roundtrip
    return 0 if full_ok else (2 if degraded_ok else 1)


if __name__ == "__main__":
    raise SystemExit(run())
