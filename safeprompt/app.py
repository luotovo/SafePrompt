from __future__ import annotations

import socket
import os
import sys
import threading
import time
from importlib.util import find_spec
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from .runtime import HotkeyManager, apply_settings_transaction, startup_enabled
from PySide6.QtCore import QObject, QSize, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QMenu, QMessageBox,
    QPushButton, QPlainTextEdit, QSystemTrayIcon, QVBoxLayout, QWidget, QLineEdit,
    QTableWidget, QTableWidgetItem, QComboBox, QScrollArea, QStyle,
)
from .core import Finding, KNOWN_CATEGORIES, detect, mask
from .storage import load_settings, save_settings
from .adapters.onnx_uie import load_onnx_uie_local
from .ner import NerService, to_findings
from .person_lite import ChineseNameDetector
from .recovery import ActiveRecoverySession, RestoreResult

MAX_TEXT_LENGTH = 100_000
RECOVERY_HOTKEY = "<ctrl>+<shift>+r"


def tray_icon() -> QIcon:
    return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)


def dialog_size_for_screen(available: QSize, preferred: QSize) -> QSize:
    return QSize(min(preferred.width(), int(available.width() * 0.90)),
                 min(preferred.height(), int(available.height() * 0.85)))


def configure_preview_dialog(dialog: QDialog, preferred: QSize) -> QSize:
    screen = dialog.screen() or QApplication.primaryScreen()
    size = dialog_size_for_screen(screen.availableGeometry().size(), preferred)
    dialog.setMaximumSize(size)
    dialog.resize(size)
    return size


def configure_settings_dialog(dialog: QDialog) -> QSize:
    screen = dialog.screen() or QApplication.primaryScreen()
    size = dialog_size_for_screen(screen.availableGeometry().size(), QSize(760, 620))
    dialog.setMaximumSize(size)
    dialog.resize(size)
    return size


def application_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Return PyInstaller's data root, or the source/application directory."""
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled).resolve() if bundled else application_dir()


def uie_model_dir() -> Path:
    """Return the configurable, local-only ONNX UIE directory."""
    configured = os.environ.get("SAFEPROMPT_UIE_ONNX_DIR")
    return Path(configured).resolve() if configured else resource_dir() / "models" / "uie-nano-onnx"


def load_production_uie():
    """Load and warm the local model on NerService's background loader thread."""
    recognizer = load_onnx_uie_local(uie_model_dir())
    recognizer.recognize("本地实体识别模型预热。")
    return recognizer


def uie_runtime_available() -> bool:
    """UIE is an optional local enhancement, never a Core requirement."""
    return uie_model_dir().is_dir() and find_spec("onnxruntime") is not None


def entity_model_enabled(category_defaults: dict[str, bool]) -> bool:
    return any(category_defaults.get(category, False) for category in ("PERSON", "ORG"))


def startup_command() -> str:
    executable = f'"{Path(sys.executable).resolve()}"'
    if getattr(sys, "frozen", False):
        return executable
    return f'{executable} "{application_dir() / "main.py"}"'


class HotkeyBridge(QObject):
    triggered = Signal()
    restore_triggered = Signal()
    detection_completed = Signal(int, str, object, object)


class SingleInstance(QObject):
    """One process per user session; a second launch asks the first to open."""
    activated = Signal()
    port = 47992

    def __init__(self):
        super().__init__()
        try:
            self.server = socket.create_server(("127.0.0.1", self.port))
        except OSError:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                pass
            raise SystemExit(0)
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self) -> None:
        while True:
            try:
                connection, _ = self.server.accept()
                connection.close()
                self.activated.emit()
            except OSError:
                return

    def close(self) -> None:
        self.server.close()


class PreviewDialog(QDialog):
    def __init__(self, text: str, findings: list[Finding], high_risk_warning: bool,
                 on_copied: Callable[[list[Finding]], None] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.text, self.findings = text, findings
        self.high_risk_warning = high_risk_warning
        self.on_copied = on_copied
        self.setWindowTitle("SafePrompt - 脱敏预览")
        available_size = configure_preview_dialog(self, QSize(760, 560))
        layout = QVBoxLayout(self)
        counts = Counter(item.category for item in findings)
        layout.addWidget(QLabel(f"发现 {len(findings)} 项敏感信息：" + "、".join(f"{key} {value}" for key, value in counts.items())))
        self.findings_widget = QWidget()
        self.items = QVBoxLayout(self.findings_widget)
        self.items.setContentsMargins(0, 0, 0, 0)
        self.findings_scroll = QScrollArea()
        self.findings_scroll.setWidgetResizable(True)
        self.findings_scroll.setWidget(self.findings_widget)
        self.findings_scroll.setMaximumHeight(min(180, int(available_size.height() * 0.30)))
        layout.addWidget(self.findings_scroll)
        groups: dict[tuple[str, str], list[Finding]] = {}
        for finding in findings:
            groups.setdefault((finding.category, finding.original_value.casefold()), []).append(finding)
        self.checkboxes: dict[tuple[str, str], QCheckBox] = {}
        for key, grouped in groups.items():
            finding = grouped[0]
            suffix = f"（出现 {len(grouped)} 次）" if len(grouped) > 1 else ""
            check = QCheckBox(f"{finding.category}: {finding.original_value}  →  <{finding.category}_…>")
            check.setText(check.text() + suffix)
            check.setChecked(finding.selected)
            check.stateChanged.connect(self.refresh)
            self.items.addWidget(check)
            self.checkboxes[key] = check
        layout.addWidget(QLabel("将复制的文本"))
        self.preview = QPlainTextEdit(readOnly=True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.preview, 1)
        self.button_bar = QWidget()
        buttons = QHBoxLayout(self.button_bar)
        buttons.setContentsMargins(0, 0, 0, 0)
        high_risk = QPushButton("仅脱敏高风险项")
        high_risk.clicked.connect(self.select_high_risk)
        buttons.addWidget(high_risk)
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        copy = QPushButton("复制安全文本")
        copy.clicked.connect(self.copy_safe)
        buttons.addWidget(cancel)
        buttons.addWidget(copy)
        layout.addWidget(self.button_bar)
        self.safe_text = ""
        self.refresh()

    def selected_findings(self) -> list[Finding]:
        return [Finding(item.category, item.start, item.end, item.original_value, item.source,
                        item.risk_level,
                        self.checkboxes[(item.category, item.original_value.casefold())].isChecked(),
                        id=item.id)
                for item in self.findings]

    def refresh(self) -> None:
        self.safe_text, self.resolved_findings = mask(self.text, self.selected_findings())
        self.preview.setPlainText(self.safe_text)

    def select_high_risk(self) -> None:
        for key, check in self.checkboxes.items():
            check.setChecked(self.findings_for(key)[0].risk_level == "high")

    def findings_for(self, key: tuple[str, str]) -> list[Finding]:
        return [item for item in self.findings if (item.category, item.original_value.casefold()) == key]

    def copy_safe(self) -> None:
        unmasked = {item.category for item in self.selected_findings()
                    if item.risk_level == "high" and not item.selected}
        if self.high_risk_warning and unmasked:
            answer = QMessageBox.warning(self, "高风险信息未脱敏",
                                         f"仍会保留高风险信息：{', '.join(sorted(unmasked))}。确定复制吗？",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        clipboard = QApplication.clipboard()
        clipboard.setText(self.safe_text)
        if clipboard.text() != self.safe_text:
            QMessageBox.warning(self, "SafePrompt", "写入剪贴板失败，未创建恢复映射。")
            return
        if self.on_copied:
            self.on_copied(self.resolved_findings)
        self.accept()


class RecoveryDialog(QDialog):
    def __init__(self, result: RestoreResult, parent: QWidget | None = None):
        super().__init__(parent)
        self.result = result
        self.setWindowTitle("SafePrompt - 恢复预览")
        configure_preview_dialog(self, QSize(760, 460))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"已恢复 {result.restored_count} 处；未知占位符 {result.unknown_count} 处保持不变。"))
        layout.addWidget(QLabel("恢复后的内容包含原始敏感信息，请仅在可信环境中使用。"))
        self.preview = QPlainTextEdit(result.text, readOnly=True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.preview, 1)
        self.button_bar = QWidget()
        buttons = QHBoxLayout(self.button_bar)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        copy = QPushButton("复制恢复文本")
        copy.clicked.connect(self.copy_restored)
        buttons.addWidget(cancel)
        buttons.addWidget(copy)
        layout.addWidget(self.button_bar)

    def copy_restored(self) -> None:
        QApplication.clipboard().setText(self.result.text)
        self.accept()


class SettingsDialog(QDialog):
    CATEGORIES = ("CUSTOMER", "PROJECT", "DEPARTMENT", "SYSTEM", "TABLE_NAME", "FIELD_NAME")

    def __init__(self, settings: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("SafePrompt - 设置")
        configure_settings_dialog(self)
        layout = QVBoxLayout(self)
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_content = QWidget()
        content = QVBoxLayout(self.settings_content)
        content.addWidget(QLabel("快捷键（例如 <ctrl>+<shift>+s）"))
        self.hotkey = QLineEdit(settings["hotkey"])
        content.addWidget(self.hotkey)
        self.warning = QCheckBox("取消高风险项时显示强提醒")
        self.warning.setChecked(settings.get("high_risk_warning", True))
        content.addWidget(self.warning)
        content.addWidget(QLabel("类别默认脱敏策略"))
        self.category_checks: dict[str, QCheckBox] = {}
        category_grid = QGridLayout()
        for index, category in enumerate(sorted(KNOWN_CATEGORIES)):
            check = QCheckBox(category)
            check.setChecked(settings["category_defaults"].get(category, False))
            category_grid.addWidget(check, index // 3, index % 3)
            self.category_checks[category] = check
        content.addLayout(category_grid)
        self.startup = QCheckBox("登录 Windows 后自动启动")
        self.startup.setChecked(settings.get("startup", False))
        content.addWidget(self.startup)
        content.addWidget(QLabel("本地词库（ASCII 词条按单词边界匹配；同类重叠时最长词优先）"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["词条", "类别", "默认脱敏"])
        content.addWidget(self.table)
        for item in settings.get("dictionary", []):
            self.add_term(item)
        self.settings_scroll.setWidget(self.settings_content)
        layout.addWidget(self.settings_scroll, 1)
        self.button_bar = QWidget()
        actions = QHBoxLayout(self.button_bar)
        actions.setContentsMargins(0, 0, 0, 0)
        add = QPushButton("新增")
        add.clicked.connect(lambda: self.add_term())
        remove = QPushButton("删除所选")
        remove.clicked.connect(self.remove_selected)
        actions.addWidget(add)
        actions.addWidget(remove)
        actions.addStretch()
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self.accept)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)
        layout.addWidget(self.button_bar)

    def add_term(self, item: dict | None = None) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem((item or {}).get("term", "")))
        category = QComboBox()
        category.addItems(self.CATEGORIES)
        category.setCurrentText((item or {}).get("category", "CUSTOMER"))
        self.table.setCellWidget(row, 1, category)
        selected = QCheckBox()
        selected.setChecked((item or {}).get("default_selected", True))
        self.table.setCellWidget(row, 2, selected)

    def remove_selected(self) -> None:
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def value(self) -> dict:
        dictionary = []
        for row in range(self.table.rowCount()):
            term = self.table.item(row, 0).text().strip() if self.table.item(row, 0) else ""
            if term:
                dictionary.append({"term": term, "category": self.table.cellWidget(row, 1).currentText(),
                                   "default_selected": self.table.cellWidget(row, 2).isChecked()})
        return {**self.settings, "dictionary": dictionary, "hotkey": self.hotkey.text().strip(),
                "high_risk_warning": self.warning.isChecked(),
                "category_defaults": {category: check.isChecked() for category, check in self.category_checks.items()},
                "startup": self.startup.isChecked()}


class SafePromptApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = load_settings()
        self.ner = NerService(load_production_uie) if uie_runtime_available() else None
        self.person_fallback = ChineseNameDetector()
        self.detection_generation = 0
        self.last_detection_diagnostics: dict[str, object] = {}
        self.recovery: ActiveRecoverySession | None = None
        self.recovery_generation = 0
        self.startup_command = startup_command()
        actual_startup = startup_enabled(self.startup_command)
        if self.settings["startup"] != actual_startup:
            self.settings["startup"] = actual_startup
            save_settings(self.settings)
        self.bridge = HotkeyBridge()
        self.bridge.triggered.connect(self.process_clipboard)
        self.bridge.restore_triggered.connect(self.restore_clipboard)
        self.bridge.detection_completed.connect(self._finish_hybrid_detection)
        self.tray = QSystemTrayIcon(tray_icon(), self)
        menu = QMenu()
        process = QAction("处理剪贴板", self)
        process.triggered.connect(self.process_clipboard)
        menu.addAction(process)
        restore = QAction("恢复 AI 回复", self)
        restore.triggered.connect(self.restore_clipboard)
        menu.addAction(restore)
        clear_recovery = QAction("清除恢复映射", self)
        clear_recovery.triggered.connect(self.clear_recovery)
        menu.addAction(clear_recovery)
        settings = QAction("设置", self)
        settings.triggered.connect(self.open_settings)
        menu.addAction(settings)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(app.quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("SafePrompt：Ctrl+Shift+S 脱敏；Ctrl+Shift+R 恢复")
        self.tray.show()
        self.hotkeys = HotkeyManager(self.bridge.triggered.emit)
        self.recovery_hotkey = HotkeyManager(self.bridge.restore_triggered.emit)
        self.start_listener()
        if self.ner is not None and entity_model_enabled(self.settings["category_defaults"]):
            self.ner.start_loading()
        app.aboutToQuit.connect(self.stop_listener)

    def start_listener(self) -> None:
        success, error = self.hotkeys.switch(self.settings["hotkey"])
        if not success:
            QMessageBox.warning(None, "SafePrompt", f"快捷键无效或不可用：{error}")
        success, error = self.recovery_hotkey.switch(RECOVERY_HOTKEY)
        if not success:
            QMessageBox.warning(None, "SafePrompt", f"恢复快捷键无效或不可用：{error}")

    def stop_listener(self) -> None:
        self.hotkeys.stop()
        self.recovery_hotkey.stop()
        self._drop_recovery()

    def create_recovery(self, findings: list[Finding]) -> None:
        self._drop_recovery()
        session = ActiveRecoverySession()
        session.replace(findings)
        if not session.active:
            return
        self.recovery = session
        self.recovery_generation += 1
        generation = self.recovery_generation
        QTimer.singleShot(int(session.ttl_seconds * 1000), lambda: self._expire_recovery(generation))

    def _expire_recovery(self, generation: int) -> None:
        if generation == self.recovery_generation:
            self._drop_recovery()

    def _drop_recovery(self) -> None:
        if self.recovery is not None:
            self.recovery.clear()
            self.recovery = None
        self.recovery_generation += 1

    def clear_recovery(self) -> None:
        self._drop_recovery()
        self.tray.showMessage("SafePrompt", "恢复映射已清除。", QSystemTrayIcon.MessageIcon.Information, 2500)

    def restore_clipboard(self) -> None:
        if self.recovery is None or not self.recovery.active:
            self._drop_recovery()
            self.tray.showMessage("SafePrompt", "没有可用的恢复映射，或映射已过期。",
                                  QSystemTrayIcon.MessageIcon.Information, 3000)
            return
        RecoveryDialog(self.recovery.restore(self.app.clipboard().text())).exec()

    def open_settings(self) -> None:
        self.settings["startup"] = startup_enabled(self.startup_command)
        dialog = SettingsDialog(self.settings)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.value()
        if not updated["hotkey"]:
            QMessageBox.warning(None, "SafePrompt", "快捷键不能为空。")
            return
        success, error = apply_settings_transaction(self.settings, updated, self.hotkeys,
                                                    self.startup_command, save_settings)
        if not success:
            QMessageBox.warning(None, "SafePrompt", error)
            return
        self.settings = updated

    def activate(self) -> None:
        self.process_clipboard()

    def process_clipboard(self) -> None:
        text = self.app.clipboard().text()
        if not text.strip():
            self.tray.showMessage("SafePrompt", "剪贴板中没有文本。", QSystemTrayIcon.MessageIcon.Information, 2500)
            return
        if len(text) > MAX_TEXT_LENGTH:
            self.tray.showMessage("SafePrompt", "文本过长，请截取需要处理的部分（最多 100,000 个字符）。", QSystemTrayIcon.MessageIcon.Warning, 4000)
            return
        entity_enabled = entity_model_enabled(self.settings["category_defaults"])
        if self.ner is not None and entity_enabled:
            self.detection_generation += 1
            request_id = self.detection_generation
            requested_at = time.monotonic()
            self.ner.start_loading()
            if self.ner.loading:
                self.tray.showMessage("SafePrompt", "正在初始化本地实体识别模型，完成后将自动继续检测。",
                                      QSystemTrayIcon.MessageIcon.Information, 3000)
            threading.Thread(target=self._run_hybrid_detection,
                             args=(request_id, text, requested_at), daemon=True).start()
            return
        self._process_text(text, entity_enabled)

    def _run_hybrid_detection(self, request_id: int, text: str, requested_at: float) -> None:
        detect_started_at = time.monotonic()
        entities = self.ner.recognize(text, wait_for_ready=True) if self.ner is not None else []
        entities.extend(self.person_fallback.recognize(text))
        completed_at = time.monotonic()
        error = self.ner.failure_reason if self.ner is not None and self.ner.unavailable else None
        diagnostics = {
            "request_id": request_id,
            "backend_state": self.ner.state if self.ner is not None else "UNAVAILABLE",
            "requested_at": requested_at,
            "model_ready_at": self.ner.ready_at if self.ner is not None else None,
            "detect_started_at": detect_started_at,
            "completed_at": completed_at,
        }
        self.bridge.detection_completed.emit(request_id, text, entities, (error, diagnostics))

    def _finish_hybrid_detection(self, request_id: int, text: str, entities: object,
                                 result: object) -> None:
        error, diagnostics = result
        if request_id != self.detection_generation:
            return
        self.last_detection_diagnostics = diagnostics
        if error:
            self.tray.showMessage("SafePrompt", f"本地实体识别不可用：{error}",
                                  QSystemTrayIcon.MessageIcon.Critical, 6000)
            return
        self._process_text(text, True, entities)

    def _process_text(self, text: str, entity_enabled: bool, entities: object | None = None) -> None:
        dictionary = [(item["term"], item["category"], item["default_selected"])
                      for item in self.settings["dictionary"]]
        if entities is None:
            entities = self.ner.recognize(text) if self.ner is not None and entity_enabled else []
        model_entities = [item for item in entities if item.model != "person-lite"]
        fallback_entities = [item for item in entities if item.model == "person-lite"]
        entity_findings = to_findings(text, model_entities, self.settings["category_defaults"])
        entity_findings.extend(to_findings(text, fallback_entities, self.settings["category_defaults"],
                                           source="lightweight_person"))
        findings = detect(text, dictionary, self.settings["category_defaults"], entity_findings)
        if not findings:
            self.tray.showMessage("SafePrompt", "未发现已支持的敏感信息。", QSystemTrayIcon.MessageIcon.Information, 2500)
            return
        PreviewDialog(text, findings, self.settings["high_risk_warning"], self.create_recovery).exec()


def run() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    instance = SingleInstance()
    controller = SafePromptApp(app)
    instance.activated.connect(controller.activate)
    app.aboutToQuit.connect(instance.close)
    return app.exec()
