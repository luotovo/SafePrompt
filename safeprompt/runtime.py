from __future__ import annotations

import winreg
import sys
from collections.abc import Callable

import six

# PySide/Shiboken inspects modules reached through pynput on Python 3.12.
# six's importer needs this compatibility attribute before pynput imports
# six.moves; applying the guard twice in frozen mode is harmless.
for finder in sys.meta_path:
    if finder.__class__.__name__ == "_SixMetaPathImporter" and not hasattr(finder, "_path"):
        finder._path = []

from pynput import keyboard


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "SafePrompt"


def startup_enabled(command: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return value == command
    except FileNotFoundError:
        return False


def set_startup(enabled: bool, command: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


class HotkeyManager:
    def __init__(self, callback: Callable[[], None], listener_factory=keyboard.GlobalHotKeys):
        self.callback = callback
        self.listener_factory = listener_factory
        self.listener = None
        self.hotkey = ""

    def switch(self, hotkey: str) -> tuple[bool, str]:
        try:
            keyboard.HotKey.parse(hotkey)
            replacement = self.listener_factory({hotkey: self.callback})
            replacement.start()
        except Exception as error:
            return False, str(error)
        previous = self.listener
        self.listener, self.hotkey = replacement, hotkey
        if previous:
            previous.stop()
        return True, ""

    def stop(self) -> None:
        if self.listener:
            self.listener.stop()


def apply_settings_transaction(previous: dict, updated: dict, hotkeys: HotkeyManager,
                               startup_command: str, persist: Callable[[dict], None],
                               startup_setter: Callable[[bool, str], None] = set_startup) -> tuple[bool, str]:
    startup_changed = updated["startup"] != previous["startup"]
    hotkey_changed = updated["hotkey"] != previous["hotkey"]
    try:
        if startup_changed:
            startup_setter(updated["startup"], startup_command)
        if hotkey_changed:
            success, error = hotkeys.switch(updated["hotkey"])
            if not success:
                raise ValueError(f"快捷键无效或不可用：{error}")
        persist(updated)
        return True, ""
    except Exception as error:
        if hotkey_changed and hotkeys.hotkey != previous["hotkey"]:
            hotkeys.switch(previous["hotkey"])
        if startup_changed:
            try:
                startup_setter(previous["startup"], startup_command)
            except OSError:
                pass
        return False, str(error)
