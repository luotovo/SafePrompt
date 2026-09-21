from pathlib import Path

import safeprompt.app as app_module
from safeprompt.app import SettingsDialog, application_dir, uie_model_dir
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
