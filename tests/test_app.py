from pathlib import Path

import safeprompt.app as app_module
from safeprompt.app import (RECOVERY_HOTKEY, PreviewDialog, RecoveryDialog, SettingsDialog,
                            application_dir, uie_model_dir)
from safeprompt.core import Finding
from safeprompt.recovery import RestoreResult
from safeprompt.storage import default_settings
from PySide6.QtWidgets import QApplication


def test_settings_dialog_preserves_complete_schema():
    app = QApplication.instance() or QApplication([])
    settings = default_settings()
    dialog = SettingsDialog(settings)
    value = dialog.value()
    assert set(value) == {"dictionary", "hotkey", "high_risk_warning", "category_defaults", "startup"}


def test_uie_model_path_does_not_depend_on_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert uie_model_dir() == application_dir() / "models" / "uie-nano-static"


def test_frozen_uie_model_is_beside_executable(monkeypatch):
    monkeypatch.setattr(app_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_module.sys, "executable", r"F:\\SafePrompt\\SafePrompt.exe")
    assert uie_model_dir() == Path(r"F:\\SafePrompt\\models\\uie-nano-static")


def test_recovery_hotkey_is_fixed():
    assert RECOVERY_HOTKEY == "<ctrl>+<shift>+r"


def test_recovery_mapping_is_created_only_after_safe_copy():
    app = QApplication.instance() or QApplication([])
    copied = []
    finding = Finding("PERSON", 0, 2, "韩静", "dictionary", "medium")
    dialog = PreviewDialog("韩静", [finding], True, copied.append)
    dialog.reject()
    assert copied == []
    dialog = PreviewDialog("韩静", [finding], True, copied.append)
    dialog.copy_safe()
    assert copied[0][0].replacement == "<PERSON_1>"


def test_recovery_preview_copies_only_after_user_action():
    app = QApplication.instance() or QApplication([])
    app.clipboard().setText("before")
    dialog = RecoveryDialog(RestoreResult("after", 1, 0))
    assert app.clipboard().text() == "before"
    dialog.copy_restored()
    assert app.clipboard().text() == "after"
