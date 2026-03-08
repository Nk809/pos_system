import platform
import shutil
import subprocess
from datetime import datetime

from config import SCANNER_NAME_HINTS
from features.thermal_printer import get_printer_routes_status, get_printer_status


def _run_command(args):
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=2.5, check=False)
    except Exception:
        return ""
    return (completed.stdout or completed.stderr or "").strip()


def _run_command_result(args, input_text=None, timeout=8.0):
    try:
        completed = subprocess.run(
            args,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return 1, str(exc)
    return completed.returncode, (completed.stdout or completed.stderr or "").strip()


def _run_command_with_input(args, input_text, timeout=8.0):
    _returncode, output = _run_command_result(args, input_text=input_text, timeout=timeout)
    return output


def _compact_output(text, limit=140):
    clean_text = " ".join(str(text or "").split())
    if len(clean_text) <= limit:
        return clean_text
    return clean_text[: max(limit - 3, 0)] + "..."


def _scanner_keywords():
    keywords = []
    for raw_value in SCANNER_NAME_HINTS:
        value = str(raw_value or "").strip().lower()
        if value and value not in keywords:
            keywords.append(value)
    return keywords


def _matching_scanner_lines():
    matches = []
    keywords = _scanner_keywords()

    try:
        import usb.core

        for device in usb.core.find(find_all=True) or []:
            parts = [
                str(getattr(device, "product", "") or "").strip(),
                str(getattr(device, "manufacturer", "") or "").strip(),
            ]
            label = " ".join(part for part in parts if part).strip()
            lowered = label.lower()
            if label and any(keyword in lowered for keyword in keywords):
                matches.append(label)
    except Exception:
        pass

    if matches:
        return matches

    if shutil.which("lsusb"):
        for line in _run_command(["lsusb"]).splitlines():
            lowered = line.lower()
            if any(keyword in lowered for keyword in keywords):
                matches.append(line.strip())

    deduped = []
    seen = set()
    for item in matches:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def get_scanner_status(last_scan_at=None, last_scan_value=""):
    matches = _matching_scanner_lines()

    recent_scan_text = "No scan captured yet."
    if last_scan_at is not None:
        age_seconds = max(int((datetime.now() - last_scan_at).total_seconds()), 0)
        if age_seconds < 60:
            recent_scan_text = f"Last scan {age_seconds}s ago"
        else:
            recent_scan_text = f"Last scan at {last_scan_at.strftime('%H:%M:%S')}"

    if matches:
        return {
            "label": "Barcode Scanner",
            "state": "Connected",
            "connected": True,
            "message": f"Scanner or dongle detected: {matches[0]}",
            "detail": recent_scan_text,
            "last_scan_value": str(last_scan_value or "").strip(),
        }

    return {
        "label": "Barcode Scanner",
        "state": "Listening",
        "connected": False,
        "message": "Keyboard-wedge scanner input is enabled. Generic dongles may not expose a device name.",
        "detail": recent_scan_text,
        "last_scan_value": str(last_scan_value or "").strip(),
    }


def get_wifi_radio_status():
    if shutil.which("nmcli"):
        output = _run_command(["nmcli", "radio", "wifi"]).strip().lower()
        if output == "enabled":
            return {"label": "Wi-Fi Radio", "state": "On", "connected": True, "message": "Wi-Fi radio is enabled."}
        if output == "disabled":
            return {"label": "Wi-Fi Radio", "state": "Off", "connected": False, "message": "Wi-Fi radio is disabled."}

    if platform.system() == "Windows" and shutil.which("netsh"):
        output = _run_command(["netsh", "wlan", "show", "interfaces"]).lower()
        if "state" in output and "connected" in output:
            return {"label": "Wi-Fi Radio", "state": "On", "connected": True, "message": "Wi-Fi interface is connected."}
        if "there is no wireless interface on the system" in output:
            return {"label": "Wi-Fi Radio", "state": "Unavailable", "connected": False, "message": "No Wi-Fi interface detected."}

    return {
        "label": "Wi-Fi Radio",
        "state": "Unknown",
        "connected": False,
        "message": "Wi-Fi radio status is unavailable on this system.",
    }


def get_bluetooth_radio_status():
    if shutil.which("bluetoothctl"):
        output = _run_command(["bluetoothctl", "show"]).lower()
        if "powered: yes" in output:
            return {
                "label": "Bluetooth Radio",
                "state": "On",
                "connected": True,
                "message": "Bluetooth radio is enabled.",
            }
        if "powered: no" in output:
            return {
                "label": "Bluetooth Radio",
                "state": "Off",
                "connected": False,
                "message": "Bluetooth radio is disabled.",
            }

    if platform.system() == "Windows":
        return {
            "label": "Bluetooth Radio",
            "state": "Unknown",
            "connected": False,
            "message": "Bluetooth radio status is not probed automatically on Windows.",
        }

    return {
        "label": "Bluetooth Radio",
        "state": "Unknown",
        "connected": False,
        "message": "Bluetooth radio status is unavailable on this system.",
    }


def set_wifi_radio_enabled(enabled=True):
    if shutil.which("nmcli"):
        state = "on" if enabled else "off"
        returncode, output = _run_command_result(["nmcli", "radio", "wifi", state], timeout=6.0)
        action = "enabled" if enabled else "disabled"
        if returncode == 0:
            return {
                "success": True,
                "message": f"Wi-Fi radio {action}. {output}".strip(),
            }
        return {
            "success": False,
            "message": f"Unable to change Wi-Fi radio. {_compact_output(output)}",
        }

    return {
        "success": False,
        "message": "Wi-Fi radio cannot be changed automatically on this device.",
    }


def set_bluetooth_radio_enabled(enabled=True):
    if shutil.which("bluetoothctl"):
        state = "on" if enabled else "off"
        returncode, output = _run_command_result(["bluetoothctl"], f"power {state}\nquit\n", timeout=6.0)
        action = "enabled" if enabled else "disabled"
        if returncode == 0:
            return {
                "success": True,
                "message": f"Bluetooth radio {action}. {_compact_output(output)}".strip(),
            }
        return {
            "success": False,
            "message": f"Unable to change Bluetooth radio. {_compact_output(output)}",
        }

    return {
        "success": False,
        "message": "Bluetooth radio cannot be changed automatically on this device.",
    }


def connect_bluetooth_device(address):
    device_address = str(address or "").strip()
    if not device_address:
        return {"success": False, "message": "Bluetooth address is required to connect the wireless printer."}

    if shutil.which("bluetoothctl"):
        output = _run_command_with_input(
            ["bluetoothctl"],
            (
                "power on\n"
                f"pair {device_address}\n"
                f"trust {device_address}\n"
                f"connect {device_address}\n"
                f"info {device_address}\n"
                "quit\n"
            ),
            timeout=18.0,
        )
        normalized = output.lower()
        if "connection successful" in normalized or "connected: yes" in normalized:
            return {"success": True, "message": f"Bluetooth device connected: {device_address}"}
        return {
            "success": False,
            "message": f"Bluetooth connect attempt failed. {_compact_output(output)}",
        }

    return {
        "success": False,
        "message": "Bluetooth connect is not available automatically on this device.",
    }


def get_device_status_snapshot(last_scan_at=None, last_scan_value=""):
    routes = get_printer_routes_status()
    active_printer = get_printer_status()

    return {
        "scanner": get_scanner_status(last_scan_at=last_scan_at, last_scan_value=last_scan_value),
        "wifi_radio": get_wifi_radio_status(),
        "bluetooth_radio": get_bluetooth_radio_status(),
        "printer": active_printer,
        "printer_routes": routes,
    }
