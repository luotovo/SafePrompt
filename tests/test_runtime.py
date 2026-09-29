import pytest

from safeprompt.runtime import HotkeyManager, apply_settings_transaction, set_startup, startup_enabled
import safeprompt.runtime as runtime


class Listener:
    def __init__(self, mapping, fail=False):
        self.mapping, self.fail, self.started, self.stopped = mapping, fail, False, False

    def start(self):
        if self.fail:
            raise RuntimeError("conflict")
        self.started = True

    def stop(self):
        self.stopped = True


def test_hotkey_switch_success_and_failure_keeps_old_listener():
    created = []
    def factory(mapping):
        listener = Listener(mapping, "b" in next(iter(mapping)))
        created.append(listener)
        return listener
    manager = HotkeyManager(lambda: None, factory)
    assert manager.switch("<ctrl>+a")[0]
    first = manager.listener
    assert not manager.switch("<ctrl>+b")[0]
    assert manager.listener is first and not first.stopped
    assert manager.switch("<ctrl>+c")[0]
    assert first.stopped


def test_startup_enable_disable_is_idempotent(monkeypatch):
    values = {}
    class Key:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(runtime.winreg, "CreateKey", lambda *_: Key())
    monkeypatch.setattr(runtime.winreg, "OpenKey", lambda *_: Key())
    monkeypatch.setattr(runtime.winreg, "SetValueEx", lambda key, name, zero, kind, value: values.__setitem__(name, value))
    monkeypatch.setattr(runtime.winreg, "QueryValueEx", lambda key, name: (values[name], runtime.winreg.REG_SZ) if name in values else (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(runtime.winreg, "DeleteValue", lambda key, name: values.pop(name) if name in values else (_ for _ in ()).throw(FileNotFoundError()))
    set_startup(True, "command"); set_startup(True, "command")
    assert startup_enabled("command")
    set_startup(False, "command"); set_startup(False, "command")
    assert not startup_enabled("command")


def test_startup_failure_does_not_persist_or_change_settings():
    manager = HotkeyManager(lambda: None, lambda mapping: Listener(mapping))
    assert manager.switch("<ctrl>+a")[0]
    previous = {"hotkey": "<ctrl>+a", "startup": False}
    updated = {"hotkey": "<ctrl>+a", "startup": True}
    persisted = []
    def fail_startup(enabled, command):
        raise OSError("registry denied")
    success, _ = apply_settings_transaction(previous, updated, manager, "command", persisted.append, fail_startup)
    assert not success
    assert persisted == [] and previous == {"hotkey": "<ctrl>+a", "startup": False}
