from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDialog

import safeprompt.app as app_module


ORIGINAL = ("韩静反馈海川大学的门户无法登录。\n"
            "服务器：10.21.3.15\n电话：13812345678\n"
            "邮箱：hanjing@example.com\npassword=123456")
SAFE = ("<PERSON_1>反馈<ORG_1>的门户无法登录。\n"
        "服务器：<IP_1>\n电话：<PHONE_1>\n"
        "邮箱：<EMAIL_1>\npassword=<PASSWORD_1>")
AI_REPLY = ("建议先联系<PERSON_1>确认账号状态。\n"
            "如仍无法解决，可联系<ORG_1>管理员，\n"
            "并确认<EMAIL_1>是否有效。")
RESTORED = ("建议先联系韩静确认账号状态。\n"
            "如仍无法解决，可联系海川大学管理员，\n"
            "并确认hanjing@example.com是否有效。")


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui-probe", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    clipboard = app.clipboard()
    previous = clipboard.text()
    controller = app_module.SafePromptApp(app)
    deadline = time.monotonic() + 60
    controller.ner.start_loading()
    while controller.ner.loading and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.05)
    loaded = not controller.ner.loading and not controller.ner.unavailable
    process_listener = bool(controller.hotkeys.listener and controller.hotkeys.listener.is_alive())
    recovery_listener = bool(controller.recovery_hotkey.listener and controller.recovery_hotkey.listener.is_alive())
    tray_visible = controller.tray.isVisible()
    original_preview_exec = app_module.PreviewDialog.exec
    original_recovery_exec = app_module.RecoveryDialog.exec
    preview_called = recovery_preview_called = False
    actual_safe = actual_restored = ""

    def copy_preview(dialog):
        nonlocal preview_called
        preview_called = True
        dialog.copy_safe()
        return QDialog.DialogCode.Accepted

    def copy_recovery(dialog):
        nonlocal recovery_preview_called
        recovery_preview_called = True
        dialog.copy_restored()
        return QDialog.DialogCode.Accepted

    try:
        app_module.PreviewDialog.exec = copy_preview
        app_module.RecoveryDialog.exec = copy_recovery
        clipboard.setText(ORIGINAL)
        controller.process_clipboard()
        actual_safe = clipboard.text()
        safe_ok = actual_safe == SAFE and controller.recovery.active
        clipboard.setText(AI_REPLY)
        controller.restore_clipboard()
        actual_restored = clipboard.text()
        recovery_ok = actual_restored == RESTORED
    finally:
        app_module.PreviewDialog.exec = original_preview_exec
        app_module.RecoveryDialog.exec = original_recovery_exec
        controller.stop_listener()
        clipboard.setText(previous)
        QCoreApplication.processEvents()
    payload = {
        "model_loaded": loaded,
        "tray_visible": tray_visible,
        "process_hotkey_listener_alive": process_listener,
        "recovery_hotkey_listener_alive": recovery_listener,
        "safe_clipboard_ok": safe_ok,
        "preview_called": preview_called,
        "actual_safe_clipboard": actual_safe,
        "recovery_session_created": safe_ok,
        "restored_clipboard_ok": recovery_ok,
        "recovery_preview_called": recovery_preview_called,
        "actual_restored_clipboard": actual_restored,
        "clipboard_restored_after_probe": clipboard.text() == previous,
    }
    args.output.resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(payload.values()) else 1


if __name__ == "__main__":
    raise SystemExit(run())
