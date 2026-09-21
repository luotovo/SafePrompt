from __future__ import annotations

import socket
import sys
import threading
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from .runtime import HotkeyManager, apply_settings_transaction, startup_enabled
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QMenu, QMessageBox,
    QPushButton, QPlainTextEdit, QSystemTrayIcon, QVBoxLayout, QWidget, QLineEdit,
    QTableWidget, QTableWidgetItem, QComboBox,
)
from .core import Finding, KNOWN_CATEGORIES, detect, mask
from .storage import load_settings, save_settings
from .adapters.paddle import load_uie_local
from .ner import NerService, to_findings
from .recovery import ActiveRecoverySession, RestoreResult

MAX_TEXT_LENGTH = 100_000
RECOVERY_HOTKEY = "<ctrl>+<shift>+r"


def application_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def uie_model_dir() -> Path:
    """The model remains external beside the source tree or frozen executable."""
    return application_dir() / "models" / "uie-nano-static"


class HotkeyBridge(QObject):
    triggered = Signal()
    restore_triggered = Signal()


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
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        counts = Counter(item.category for item in findings)
        layout.addWidget(QLabel(f"发现 {len(findings)} 项敏感信息：" + "、".join(f"{key} {value}" for key, value in counts.items())))
        self.items = QVBoxLayout()
        layout.addLayout(self.items)
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
        layout.addWidget(self.preview)
        buttons = QHBoxLayout()
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
        layout.addLayout(buttons)
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
        self.resize(760, 460)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"已恢复 {result.restored_count} 处；未知占位符 {result.unknown_count} 处保持不变。"))
        layout.addWidget(QLabel("恢复后的内容包含原始敏感信息，请仅在可信环境中使用。"))
        self.preview = QPlainTextEdit(result.text, readOnly=True)
        layout.addWidget(self.preview)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        copy = QPushButton("复制恢复文本")
        copy.clicked.connect(self.copy_restored)
        buttons.addWidget(cancel)
        buttons.addWidget(copy)
        layout.addLayout(buttons)

    def copy_restored(self) -> None:
        QApplication.clipboard().setText(self.result.text)
        self.accept()


class SettingsDialog(QDialog):
    CATEGORIES = ("CUSTOMER", "PROJECT", "DEPARTMENT", "SYSTEM", "TABLE_NAME", "FIELD_NAME")

    def __init__(self, settings: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("SafePrompt - 设置")
        self.resize(650, 460)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("快捷键（例如 <ctrl>+<shift>+s）"))
        self.hotkey = QLineEdit(settings["hotkey"])
        layout.addWidget(self.hotkey)
        self.warning = QCheckBox("取消高风险项时显示强提醒")
        self.warning.setChecked(settings.get("high_risk_warning", True))
        layout.addWidget(self.warning)
        layout.addWidget(QLabel("类别默认脱敏策略"))
        self.category_checks: dict[str, QCheckBox] = {}
        category_row = QHBoxLayout()
        for category in sorted(KNOWN_CATEGORIES):
            check = QCheckBox(category)
            check.setChecked(settings["category_defaults"].get(category, False))
            category_row.addWidget(check)
            self.category_checks[category] = check
        layout.addLayout(category_row)
        self.startup = QCheckBox("登录 Windows 后自动启动")
        self.startup.setChecked(settings.get("startup", False))
        layout.addWidget(self.startup)
        layout.addWidget(QLabel("本地词库（ASCII 词条按单词边界匹配；同类重叠时最长词优先）"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["词条", "类别", "默认脱敏"])
        layout.addWidget(self.table)
        for item in settings.get("dictionary", []):
            self.add_term(item)
        actions = QHBoxLayout()
        add = QPushButton("新增")
        add.clicked.connect(lambda: self.add_term())
        remove = QPushButton("删除所选")
        remove.clicked.connect(self.remove_selected)
        actions.addWidget(add)
        actions.addWidget(remove)
        actions.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

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
        self.ner = NerService(lambda: load_uie_local(uie_model_dir()))
        self.recovery = ActiveRecoverySession()
        self.startup_command = f'"{sys.executable}" "{Path(__file__).resolve().parent.parent / "main.py"}"'
        actual_startup = startup_enabled(self.startup_command)
        if self.settings["startup"] != actual_startup:
            self.settings["startup"] = actual_startup
            save_settings(self.settings)
        self.bridge = HotkeyBridge()
        self.bridge.triggered.connect(self.process_clipboard)
        self.bridge.restore_triggered.connect(self.restore_clipboard)
        self.tray = QSystemTrayIcon(QIcon(), self)
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
        self.recovery.clear()

    def clear_recovery(self) -> None:
        self.recovery.clear()
        self.tray.showMessage("SafePrompt", "恢复映射已清除。", QSystemTrayIcon.MessageIcon.Information, 2500)

    def restore_clipboard(self) -> None:
        if not self.recovery.active:
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
        dictionary = [(item["term"], item["category"], item["default_selected"])
                      for item in self.settings["dictionary"]]
        first_load = self.ner.start_loading()
        if first_load:
            self.tray.showMessage("SafePrompt", "正在后台初始化本地实体识别模型，本次先使用规则与词库。",
                                  QSystemTrayIcon.MessageIcon.Information, 3000)
        entities = self.ner.recognize(text)
        entity_findings = to_findings(text, entities, self.settings["category_defaults"])
        findings = detect(text, dictionary, self.settings["category_defaults"], entity_findings)
        if not findings:
            self.tray.showMessage("SafePrompt", "未发现已支持的敏感信息。", QSystemTrayIcon.MessageIcon.Information, 2500)
            return
        PreviewDialog(text, findings, self.settings["high_risk_warning"], self.recovery.replace).exec()


def run() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    instance = SingleInstance()
    controller = SafePromptApp(app)
    instance.activated.connect(controller.activate)
    app.aboutToQuit.connect(instance.close)
    return app.exec()
