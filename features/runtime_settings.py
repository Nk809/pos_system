import json
from pathlib import Path

from config import DATA_DIR


SETTINGS_PATH = Path(DATA_DIR) / "runtime_settings.json"


def _default_settings():
    return {
        "printer": {
            "network_address": "",
            "bluetooth_name": "",
            "bluetooth_address": "",
            "bluetooth_channel": "",
            "windows_name": "",
        }
    }


def load_runtime_settings():
    settings = _default_settings()
    if not SETTINGS_PATH.exists():
        return settings

    try:
        loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return settings

    if isinstance(loaded, dict):
        for top_key, top_value in loaded.items():
            if isinstance(top_value, dict):
                settings.setdefault(top_key, {}).update(top_value)
            else:
                settings[top_key] = top_value
    return settings


def save_runtime_settings(settings):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8")


def get_printer_setting(key, fallback=""):
    settings = load_runtime_settings()
    value = ((settings.get("printer") or {}).get(key))
    if value is None:
        return fallback
    value_text = str(value).strip()
    return value_text if value_text else fallback


def update_printer_settings(**kwargs):
    settings = load_runtime_settings()
    printer_settings = settings.setdefault("printer", {})
    for key, value in kwargs.items():
        printer_settings[str(key)] = str(value or "").strip()
    save_runtime_settings(settings)
    return settings
