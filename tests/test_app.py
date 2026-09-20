from safeprompt.app import SettingsDialog
from safeprompt.storage import default_settings
from PySide6.QtWidgets import QApplication


def test_settings_dialog_preserves_complete_schema():
    app = QApplication.instance() or QApplication([])
    settings = default_settings()
    dialog = SettingsDialog(settings)
    value = dialog.value()
    assert set(value) == {"dictionary", "hotkey", "high_risk_warning", "category_defaults", "startup"}
