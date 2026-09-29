from pathlib import Path

import pytest
import safeprompt.app as app_module
from safeprompt.app import (RECOVERY_HOTKEY, PreviewDialog, RecoveryDialog, SettingsDialog,
                            application_dir, dialog_size_for_screen, load_production_uie, uie_runtime_available,
                            resource_dir, startup_command, tray_icon, uie_model_dir)
from safeprompt.core import Finding, detect, mask
from safeprompt.recovery import RestoreResult
from safeprompt.storage import default_settings
from safeprompt.ner import EntityResult
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QScrollArea


def test_settings_dialog_preserves_complete_schema():
    app = QApplication.instance() or QApplication([])
    settings = default_settings()
    dialog = SettingsDialog(settings)
    value = dialog.value()
    assert set(value) == {"dictionary", "hotkey", "high_risk_warning", "category_defaults", "startup"}


def test_settings_dialog_is_bounded_scrollable_and_keeps_actions_visible():
    app = QApplication.instance() or QApplication([])
    settings = default_settings()
    settings['dictionary'] = [{'term': f'term{index}', 'category': 'CUSTOMER', 'default_selected': True} for index in range(100)]
    dialog = SettingsDialog(settings)
    screen = QApplication.primaryScreen().availableGeometry().size()
    assert isinstance(dialog.settings_scroll, QScrollArea)
    assert dialog.settings_scroll.widget() is dialog.settings_content
    assert dialog.layout().itemAt(dialog.layout().count() - 1).widget() is dialog.button_bar
    assert dialog.button_bar.parentWidget() is dialog
    assert dialog.maximumWidth() <= int(screen.width() * 0.90)
    assert dialog.maximumHeight() <= int(screen.height() * 0.85)
    dialog.show(); app.processEvents()
    assert dialog.button_bar.isVisible()
    assert dialog.height() <= dialog.maximumHeight()


def test_settings_dialog_save_preserves_values():
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(default_settings())
    dialog.hotkey.setText('<ctrl>+<alt>+s')
    dialog.startup.setChecked(True)
    dialog.category_checks['IP'].setChecked(False)
    dialog.add_term({'term': 'clientA', 'category': 'CUSTOMER', 'default_selected': False})
    dialog.save_button.click()
    value = dialog.value()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert value['hotkey'] == '<ctrl>+<alt>+s' and value['startup'] is True
    assert value['category_defaults']['IP'] is False
    assert value['dictionary'] == [{'term': 'clientA', 'category': 'CUSTOMER', 'default_selected': False}]


def test_tray_icon_is_not_empty():
    QApplication.instance() or QApplication([])
    assert not tray_icon().isNull()


def test_uie_model_path_does_not_depend_on_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("SAFEPROMPT_UIE_ONNX_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert uie_model_dir() == application_dir() / "models" / "uie-nano-onnx"


def test_uie_model_path_can_be_configured_for_source_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("SAFEPROMPT_UIE_ONNX_DIR", str(tmp_path))
    assert uie_model_dir() == tmp_path.resolve()


def test_frozen_uie_model_is_beside_executable(monkeypatch):
    monkeypatch.delenv("SAFEPROMPT_UIE_ONNX_DIR", raising=False)
    monkeypatch.setattr(app_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_module.sys, "executable", r"F:\\SafePrompt\\SafePrompt.exe")
    assert uie_model_dir() == Path(r"F:\\SafePrompt\\models\\uie-nano-onnx")


def test_frozen_uie_model_uses_pyinstaller_resource_root(monkeypatch):
    monkeypatch.delenv("SAFEPROMPT_UIE_ONNX_DIR", raising=False)
    monkeypatch.setattr(app_module.sys, "_MEIPASS", r"F:\SafePrompt\_internal", raising=False)
    assert resource_dir() == Path(r"F:\SafePrompt\_internal")
    assert uie_model_dir() == Path(r"F:\SafePrompt\_internal\models\uie-nano-onnx")


def test_uie_runtime_is_optional(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "uie_model_dir", lambda: tmp_path / "missing")
    assert not uie_runtime_available()


def test_frozen_startup_command_runs_only_the_executable(monkeypatch):
    monkeypatch.setattr(app_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_module.sys, "executable", r"F:\\SafePrompt\\SafePrompt.exe")
    assert startup_command() == '"F:\\SafePrompt\\SafePrompt.exe"'


def test_development_startup_command_includes_main(monkeypatch):
    monkeypatch.delattr(app_module.sys, "frozen", raising=False)
    monkeypatch.setattr(app_module.sys, "executable", r"F:\\Python\\python.exe")
    assert startup_command() == f'"F:\\Python\\python.exe" "{application_dir() / "main.py"}"'


def test_production_uie_is_warmed_during_background_load(monkeypatch):
    calls = []
    recognizer = type("Recognizer", (), {"recognize": lambda self, text: calls.append(text) or []})()
    monkeypatch.setattr(app_module, "load_onnx_uie_local", lambda path: recognizer)
    assert load_production_uie() is recognizer
    assert calls == ["本地实体识别模型预热。"]


def test_first_entity_detection_waits_for_background_model_load(monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    previews = []
    completed = app_module.threading.Event()

    class FakeNer:
        loading = True
        unavailable = False
        failure_reason = None
        ready_at = 1.0
        state = "LOADING"

        def start_loading(self):
            return True

        def recognize(self, text, wait_for_ready=False):
            self.loading = False
            self.state = "READY"
            return [EntityResult("PERSON", 0, 2, "张伟", 0.99, "test")]

    class FakeTray:
        def showMessage(self, *args):
            pass

    class Controller:
        process_clipboard = app_module.SafePromptApp.process_clipboard
        _run_hybrid_detection = app_module.SafePromptApp._run_hybrid_detection
        _finish_hybrid_detection = app_module.SafePromptApp._finish_hybrid_detection
        _process_text = app_module.SafePromptApp._process_text

    controller = Controller()
    controller.app = qt_app
    controller.settings = default_settings()
    controller.ner = FakeNer()
    controller.person_fallback = type("Fallback", (), {"recognize": lambda self, text: []})()
    controller.tray = FakeTray()
    controller.create_recovery = lambda findings: None
    controller.detection_generation = 0
    controller.last_detection_diagnostics = {}

    class CompletedSignal:
        def emit(self, *args):
            controller._finish_hybrid_detection(*args)
            completed.set()

    controller.bridge = type("Bridge", (), {"detection_completed": CompletedSignal()})()
    monkeypatch.setattr(app_module.PreviewDialog, "exec", lambda dialog: previews.append(dialog))

    qt_app.clipboard().setText("张伟今天负责确认方案。")
    controller.process_clipboard()
    assert completed.wait(1)
    assert [item.original_value for item in previews[0].findings] == ["张伟"]
    assert controller.last_detection_diagnostics["request_id"] == 1


def test_stale_detection_result_cannot_replace_latest_request():
    processed = []

    class Controller:
        _finish_hybrid_detection = app_module.SafePromptApp._finish_hybrid_detection

    controller = Controller()
    controller.detection_generation = 2
    controller.last_detection_diagnostics = {}
    controller._process_text = lambda text, enabled, entities: processed.append(text)
    controller.tray = type("Tray", (), {"showMessage": lambda *args: None})()
    controller._finish_hybrid_detection(1, "旧请求", [], (None, {"request_id": 1}))
    controller._finish_hybrid_detection(2, "新请求", [], (None, {"request_id": 2}))
    assert processed == ["新请求"]
    assert controller.last_detection_diagnostics == {"request_id": 2}


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


def test_drop_recovery_clears_mapping_and_releases_app_reference():
    class RecoveryOwner:
        _drop_recovery = app_module.SafePromptApp._drop_recovery

    owner = RecoveryOwner()
    owner.recovery_generation = 1
    owner.recovery = app_module.ActiveRecoverySession()
    owner.recovery.replace([Finding("PERSON", 0, 2, "韩静", "dictionary", "medium",
                                            replacement="<PERSON_1>")])
    session = owner.recovery
    owner._drop_recovery()
    assert owner.recovery is None and not session.active


def test_recovery_timer_releases_session_without_user_action(monkeypatch):
    class RecoveryOwner:
        _drop_recovery = app_module.SafePromptApp._drop_recovery
        _expire_recovery = app_module.SafePromptApp._expire_recovery
        create_recovery = app_module.SafePromptApp.create_recovery

    scheduled = []
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda milliseconds, callback:
                        scheduled.append((milliseconds, callback)))
    owner = RecoveryOwner()
    owner.recovery = None
    owner.recovery_generation = 0
    owner.create_recovery([Finding("PERSON", 0, 2, "韩静", "dictionary", "medium",
                                   replacement="<PERSON_1>")])
    assert scheduled[0][0] == 900_000 and owner.recovery is not None
    scheduled[0][1]()
    assert owner.recovery is None


@pytest.mark.parametrize(('screen', 'expected'), [(QSize(1920, 1080), QSize(1728, 918)), (QSize(1366, 768), QSize(1229, 652)), (QSize(1280, 720), QSize(1152, 612))])
def test_dialog_size_is_bounded_for_common_screens(screen, expected):
    assert dialog_size_for_screen(screen, QSize(3000, 3000)) == expected


def test_long_mask_preview_is_scrollable_and_keeps_button_bar_outside_scroll():
    app = QApplication.instance() or QApplication([])
    text = "\n".join(f"line {index}: 10.0.0.1" for index in range(3000))
    dialog = PreviewDialog(text, detect(text), True)
    assert isinstance(dialog.findings_scroll, QScrollArea)
    assert dialog.preview.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap
    assert dialog.preview.toPlainText() == mask(text, detect(text))[0]
    assert dialog.layout().itemAt(dialog.layout().count() - 1).widget() is dialog.button_bar
    dialog.show()
    app.processEvents()
    assert dialog.button_bar.isVisible()


@pytest.mark.parametrize("text", [
    "\n".join(f"def line_{index}(): return {index}" for index in range(500)),
    "\n".join(f"log line {index}" for index in range(3000)),
    '{"content":[' + ",".join(f'{{"index":{index}}}' for index in range(1000)) + "]}",
    "x" * 20_000,
], ids=["500-lines-code", "3000-lines-log", "long-json", "long-single-line"])
def test_mask_preview_keeps_all_short_code_log_json_and_long_line_text(text):
    app = QApplication.instance() or QApplication([])
    dialog = PreviewDialog(text, [], True)
    assert dialog.preview.toPlainText() == text


def test_long_recovery_preview_is_complete_scrollable_and_bounded():
    app = QApplication.instance() or QApplication([])
    text = "\n".join(f"restored line {index}" for index in range(3000)) + "\n" + ("x" * 5000)
    dialog = RecoveryDialog(RestoreResult(text, 0, 0))
    screen = QApplication.primaryScreen().availableGeometry().size()
    assert dialog.preview.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap
    assert dialog.preview.toPlainText() == text
    assert dialog.maximumWidth() <= int(screen.width() * 0.90)
    assert dialog.maximumHeight() <= int(screen.height() * 0.85)
    assert dialog.layout().itemAt(dialog.layout().count() - 1).widget() is dialog.button_bar
