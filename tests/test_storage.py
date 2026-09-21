import safeprompt.storage as storage


def test_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "SETTINGS_FILE", tmp_path / "settings.bin")
    value = storage.default_settings() | {"dictionary": [{"term": "客户A", "category": "CUSTOMER", "default_selected": True}]}
    value["category_defaults"]["IP"] = False
    storage.save_settings(value)
    assert storage.load_settings() == value


def test_corrupt_settings_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "SETTINGS_FILE", tmp_path / "settings.bin")
    tmp_path.mkdir(exist_ok=True)
    storage.SETTINGS_FILE.write_bytes(b"broken")
    assert storage.load_settings() == storage.default_settings()
    assert (tmp_path / "settings.corrupt").exists()


def test_corrupt_settings_does_not_overwrite_prior_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "SETTINGS_FILE", tmp_path / "settings.bin")
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "settings.corrupt").write_bytes(b"old")
    storage.SETTINGS_FILE.write_bytes(b"new")
    storage.load_settings()
    assert (tmp_path / "settings.corrupt.1").read_bytes() == b"new"


def test_default_settings_are_independent():
    first, second = storage.default_settings(), storage.default_settings()
    first["dictionary"].append("x")
    assert second["dictionary"] == []


def test_invalid_or_missing_fields_fall_back(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path); monkeypatch.setattr(storage, "SETTINGS_FILE", tmp_path / "settings.bin")
    storage.save_settings({"dictionary": "bad", "hotkey": "", "startup": "yes", "unknown": 1})
    loaded = storage.load_settings()
    assert loaded == storage.default_settings()


def test_nested_schema_filters_invalid_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path); monkeypatch.setattr(storage, "SETTINGS_FILE", tmp_path / "settings.bin")
    storage.save_settings({"dictionary": [{"term": "客户A", "category": "CUSTOMER", "default_selected": False},
                                           {"term": "", "category": "CUSTOMER", "default_selected": True},
                                           {"term": "x", "category": "UNKNOWN", "default_selected": True}],
                           "category_defaults": {"IP": False, "UNKNOWN": True, "PHONE": "no"}})
    loaded = storage.load_settings()
    assert loaded["dictionary"] == [{"term": "客户A", "category": "CUSTOMER", "default_selected": False}]
    assert loaded["category_defaults"]["IP"] is False
    assert "UNKNOWN" not in loaded["category_defaults"]


def test_recovery_mapping_is_not_part_of_persistent_settings():
    settings = storage.default_settings()
    assert "recovery" not in settings and "mapping" not in settings
