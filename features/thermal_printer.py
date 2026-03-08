import os
import socket
from datetime import datetime

from config import (
    PRINTER_BLUETOOTH_ADDRESS,
    PRINTER_BLUETOOTH_CHANNEL,
    PRINTER_BLUETOOTH_NAME,
    PRINTER_MODE,
    PRINTER_NETWORK_ADDR,
    PRINTER_PRODUCT,
    PRINTER_SERIAL_PORT,
    PRINTER_VENDOR,
    PRINTER_WINDOWS_NAME,
)
from features.runtime_settings import get_printer_setting

LINE_EQ = "=" * 32
LINE_DASH = "-" * 32
VALID_PRINTER_MODES = {"auto", "windows", "network", "wifi", "bluetooth", "serial", "usb"}
DEFAULT_NETWORK_PORT = 9100


def _is_windows():
    return os.name == "nt"


def _normalized_printer_mode():
    raw_mode = str(PRINTER_MODE or "auto").strip().lower()
    if raw_mode == "wifi":
        return "network"
    if raw_mode in VALID_PRINTER_MODES:
        return raw_mode
    return "auto"


def _configured_bluetooth_address():
    return str(get_printer_setting("bluetooth_address", PRINTER_BLUETOOTH_ADDRESS) or "").strip()


def _configured_network_address():
    return str(get_printer_setting("network_address", PRINTER_NETWORK_ADDR) or "").strip()


def _configured_bluetooth_channel():
    return _coerce_channel(get_printer_setting("bluetooth_channel", PRINTER_BLUETOOTH_CHANNEL))


def _configured_bluetooth_name():
    return str(get_printer_setting("bluetooth_name", PRINTER_BLUETOOTH_NAME) or "").strip()


def _configured_windows_name():
    return str(get_printer_setting("windows_name", PRINTER_WINDOWS_NAME) or "").strip()


def _load_printer_backends():
    try:
        from escpos.printer import Network, Serial, Usb

        return Usb, Serial, Network, None
    except Exception as first_exc:
        import sys
        from pathlib import Path

        # IDEs sometimes run /usr/bin/python3 even when project deps are in .venv.
        project_root = Path(__file__).resolve().parent.parent
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        candidate_sites = [
            project_root / ".venv" / "lib" / f"python{py_ver}" / "site-packages",
            project_root / ".venv" / "Lib" / "site-packages",
        ]
        for venv_site in candidate_sites:
            if not venv_site.is_dir():
                continue
            venv_site_text = str(venv_site)
            if venv_site_text not in sys.path:
                sys.path.append(venv_site_text)
            try:
                from escpos.printer import Network, Serial, Usb

                return Usb, Serial, Network, None
            except Exception:
                continue
        return None, None, None, first_exc


def _sanitize_for_printer(value, max_len=None):
    text = str(value).strip()
    safe_text = text.encode("ascii", "replace").decode("ascii")
    if max_len is not None:
        return safe_text[: int(max_len)]
    return safe_text


def _format_item_line(name, qty, line_total):
    clean_name = _sanitize_for_printer(name, max_len=15)
    qty_text = f"x{int(qty)}"
    return f"{clean_name:<15}{qty_text:>5}{float(line_total):>12.2f}"


def _build_receipt_text(
    cart,
    total,
    bill_no=None,
    payment_mode=None,
    subtotal=None,
    discount_percent=0.0,
    discount_amount=0.0,
):
    now = datetime.now()
    date_time_line = f"Date: {now:%Y-%m-%d}  Time: {now:%H:%M:%S}"
    subtotal_value = round(float(subtotal), 2) if subtotal is not None else round(sum(item["total"] for item in cart), 2)
    discount_percent_value = round(float(discount_percent or 0.0), 2)
    discount_amount_value = round(float(discount_amount or 0.0), 2)
    total_value = round(float(total), 2)

    lines = [
        LINE_EQ,
        "     MATCHLESS GIFT SHOP",
        "        ISKCON BURLA",
        LINE_EQ,
        date_time_line,
    ]
    if bill_no is not None:
        lines.append(f"Bill No: {bill_no}")
    if payment_mode:
        lines.append(f"Payment: {_sanitize_for_printer(payment_mode, max_len=12)}")
    lines.extend(
        [
            "        Thank you, visit again!",
            LINE_DASH,
            "Item            Qty       Price",
            LINE_DASH,
        ]
    )

    for item in cart:
        lines.append(_format_item_line(item["name"], item["qty"], item["total"]))

    lines.extend(
        [
            LINE_DASH,
            f"{'SUBTOTAL':<22}{subtotal_value:>10.2f}",
        ]
    )
    if discount_percent_value > 0 or discount_amount_value > 0:
        lines.append(f"{f'DISCOUNT({discount_percent_value:.2f}%)':<22}{discount_amount_value:>10.2f}")
    lines.extend(
        [
            f"{'TOTAL':<22}{total_value:>10.2f}",
            LINE_DASH,
            "        Hare Krishna",
            LINE_EQ,
        ]
    )
    return "\n".join(lines) + "\n"


def _build_receipt_payload(receipt_text):
    return receipt_text.encode("ascii", "replace") + b"\n\n\n\x1dV\x00"


def _coerce_channel(value):
    try:
        channel = int(value)
    except (TypeError, ValueError):
        channel = 1
    return channel if channel > 0 else 1


def _network_target():
    target = _configured_network_address()
    if not target:
        return None, None, ""

    if target.startswith("[") and "]" in target:
        host, _, port_text = target[1:].partition("]")
        port = DEFAULT_NETWORK_PORT
        if port_text.startswith(":"):
            try:
                port = int(port_text[1:])
            except ValueError:
                port = DEFAULT_NETWORK_PORT
        return host.strip(), port, f"[{host.strip()}]:{port}"

    if target.count(":") == 1:
        host, port_text = target.rsplit(":", 1)
        try:
            return host.strip(), int(port_text), f"{host.strip()}:{int(port_text)}"
        except ValueError:
            pass

    return target, DEFAULT_NETWORK_PORT, f"{target}:{DEFAULT_NETWORK_PORT}"


def _probe_tcp_endpoint(host, port, timeout=1.2):
    if not host or not port:
        return False, "missing host or port"
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, None
    except Exception as exc:
        return False, str(exc)


def _probe_bluetooth_endpoint(address, channel, timeout=2.0):
    family = getattr(socket, "AF_BLUETOOTH", None)
    proto = getattr(socket, "BTPROTO_RFCOMM", None)
    if family is None or proto is None:
        return False, "Bluetooth RFCOMM is not available in this Python/OS build."

    bt_sock = socket.socket(family, socket.SOCK_STREAM, proto)
    try:
        bt_sock.settimeout(timeout)
        bt_sock.connect((address, int(channel)))
        return True, None
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            bt_sock.close()
        except Exception:
            pass


def _discover_usb_candidates():
    candidates = []
    seen = set()

    def _add(vid, pid, source):
        try:
            vendor_id = int(vid)
            product_id = int(pid)
        except (TypeError, ValueError):
            return
        if vendor_id <= 0 or product_id <= 0:
            return
        key = (vendor_id, product_id)
        if key in seen:
            return
        seen.add(key)
        candidates.append((vendor_id, product_id, source))

    _add(PRINTER_VENDOR, PRINTER_PRODUCT, "configured")

    try:
        import usb.core

        for dev in usb.core.find(find_all=True) or []:
            vendor_id = int(getattr(dev, "idVendor", 0) or 0)
            product_id = int(getattr(dev, "idProduct", 0) or 0)
            if vendor_id <= 0 or product_id <= 0:
                continue

            printer_like = int(getattr(dev, "bDeviceClass", 0) or 0) == 7
            if not printer_like:
                try:
                    for cfg in dev:
                        for interface in cfg:
                            if int(getattr(interface, "bInterfaceClass", 0) or 0) == 7:
                                printer_like = True
                                break
                        if printer_like:
                            break
                except Exception:
                    pass

            if printer_like:
                _add(vendor_id, product_id, "auto")
    except Exception:
        pass

    return candidates


def _discover_usb_endpoints(vendor_id, product_id):
    endpoint_pairs = []
    seen = set()

    def _add(out_ep, in_ep):
        try:
            out_value = int(out_ep)
            in_value = int(in_ep)
        except (TypeError, ValueError):
            return
        key = (out_value, in_value)
        if key in seen:
            return
        seen.add(key)
        endpoint_pairs.append(key)

    try:
        import usb.core
        import usb.util

        dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
        if dev is not None:
            for cfg in dev:
                for interface in cfg:
                    if int(getattr(interface, "bInterfaceClass", 0) or 0) != 7:
                        continue
                    in_ep = None
                    out_eps = []
                    for ep in interface:
                        addr = int(getattr(ep, "bEndpointAddress", 0) or 0)
                        if not addr:
                            continue
                        if usb.util.endpoint_direction(addr) == usb.util.ENDPOINT_IN:
                            if in_ep is None:
                                in_ep = addr
                        else:
                            out_eps.append(addr)
                    for out_ep in out_eps:
                        _add(out_ep, in_ep or 0x82)
    except Exception:
        pass

    _add(0x01, 0x82)
    _add(0x02, 0x81)
    _add(0x03, 0x82)
    return endpoint_pairs


def _discover_windows_printers():
    printer_names = []
    seen = set()

    try:
        import win32print
    except Exception:
        return printer_names

    try:
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        for row in win32print.EnumPrinters(flags):
            if len(row) >= 3:
                name = str(row[2] or "").strip()
                if name and name not in seen:
                    seen.add(name)
                    printer_names.append(name)
    except Exception:
        return printer_names

    return printer_names


def _windows_target_printers():
    printer_names = []
    configured_name = _configured_windows_name()
    if configured_name:
        printer_names.append(configured_name)

    try:
        import win32print

        default_name = str(win32print.GetDefaultPrinter() or "").strip()
        if default_name and default_name not in printer_names:
            printer_names.append(default_name)
    except Exception:
        pass

    for name in _discover_windows_printers():
        if name not in printer_names:
            printer_names.append(name)
    return printer_names


def _bluetooth_windows_target_printers():
    if not _is_windows():
        return []

    printer_names = _windows_target_printers()
    if not printer_names:
        return []

    configured_name = _configured_windows_name()
    bluetooth_name = _configured_bluetooth_name().lower()

    if configured_name:
        return [name for name in printer_names if name == configured_name]

    if bluetooth_name:
        matches = [name for name in printer_names if bluetooth_name in name.lower()]
        if matches:
            return matches

    return [name for name in printer_names if "bluetooth" in name.lower()]


def _print_with_windows_spooler(receipt_text, printer_names=None):
    try:
        import win32print
    except Exception as exc:
        return {
            "success": False,
            "message": (
                "Windows printer support requires pywin32. "
                f"Install it in the app environment. Details: {exc}"
            ),
        }

    last_exception = None
    payload = receipt_text.encode("ascii", "replace") + b"\n\n\n\x1dV\x00"

    targets = list(printer_names or _windows_target_printers())
    for printer_name in targets:
        try:
            handle = win32print.OpenPrinter(printer_name)
            try:
                job = ("Matchless POS Receipt", None, "RAW")
                win32print.StartDocPrinter(handle, 1, job)
                try:
                    win32print.StartPagePrinter(handle)
                    try:
                        win32print.WritePrinter(handle, payload)
                    finally:
                        win32print.EndPagePrinter(handle)
                finally:
                    win32print.EndDocPrinter(handle)
            finally:
                win32print.ClosePrinter(handle)
            return {"success": True, "message": f"Receipt printed successfully on {printer_name}."}
        except Exception as exc:
            last_exception = exc

    if last_exception is None:
        return {
            "success": False,
            "message": "No Windows printer found. Configure PRINTER_WINDOWS_NAME or set a default printer.",
        }
    return {"success": False, "message": f"Windows printer unavailable ({last_exception})."}


def _status_for_windows():
    if not _is_windows():
        return {
            "success": False,
            "configured": False,
            "connected": False,
            "message": "Windows spooler is only available on Windows.",
            "transport": "winspool",
            "candidates": [],
        }

    windows_printers = _windows_target_printers()
    if windows_printers:
        return {
            "success": True,
            "configured": True,
            "connected": True,
            "message": f"Windows printer ready: {windows_printers[0]}",
            "transport": "winspool",
            "candidates": windows_printers[:5],
        }
    return {
        "success": False,
        "configured": False,
        "connected": False,
        "message": "No Windows printer found. Configure PRINTER_WINDOWS_NAME or set a default printer.",
        "transport": "winspool",
        "candidates": [],
    }


def _status_for_network():
    host, port, label = _network_target()
    if host:
        connected, error = _probe_tcp_endpoint(host, port)
        if connected:
            return {
                "success": True,
                "configured": True,
                "connected": True,
                "message": f"Wi-Fi printer reachable at {label}",
                "transport": "network",
                "candidates": [label],
            }
        return {
            "success": False,
            "configured": True,
            "connected": False,
            "message": f"Wi-Fi printer configured at {label} but not reachable ({error}).",
            "transport": "network",
            "candidates": [label],
        }
    return {
        "success": False,
        "configured": False,
        "connected": False,
        "message": "Wi-Fi printer is not configured. Set PRINTER_NETWORK_ADDR in config.py.",
        "transport": "network",
        "candidates": [],
    }


def _status_for_bluetooth():
    address = _configured_bluetooth_address()
    channel = _configured_bluetooth_channel()
    label = str(_configured_bluetooth_name() or address or "").strip()
    windows_targets = _bluetooth_windows_target_printers()

    if not address:
        if windows_targets:
            return {
                "success": True,
                "configured": True,
                "connected": True,
                "message": f"Bluetooth printer ready through Windows spooler: {windows_targets[0]}",
                "transport": "bluetooth",
                "candidates": windows_targets[:5],
            }
        return {
            "success": False,
            "configured": False,
            "connected": False,
            "message": (
                "Bluetooth printer is not configured. Set PRINTER_BLUETOOTH_ADDRESS, "
                "or on Windows set PRINTER_WINDOWS_NAME for a paired Bluetooth printer."
            ),
            "transport": "bluetooth",
            "candidates": [],
        }

    connected, error = _probe_bluetooth_endpoint(address, channel)
    if connected:
        return {
            "success": True,
            "configured": True,
            "connected": True,
            "message": f"Bluetooth printer connected: {label} (channel {channel})",
            "transport": "bluetooth",
            "candidates": [address],
        }
    if windows_targets:
        return {
            "success": True,
            "configured": True,
            "connected": True,
            "message": (
                f"Bluetooth RFCOMM probe failed ({error}), but Windows spooler is ready: {windows_targets[0]}"
            ),
            "transport": "bluetooth",
            "candidates": windows_targets[:5],
        }
    return {
        "success": False,
        "configured": True,
        "connected": False,
        "message": f"Bluetooth printer configured at {address} but not reachable ({error}).",
        "transport": "bluetooth",
        "candidates": [address],
    }


def _status_for_serial():
    if PRINTER_SERIAL_PORT:
        return {
            "success": True,
            "configured": True,
            "connected": True,
            "message": f"Serial printer configured on {PRINTER_SERIAL_PORT}",
            "transport": "serial",
            "candidates": [PRINTER_SERIAL_PORT],
        }
    return {
        "success": False,
        "configured": False,
        "connected": False,
        "message": "Serial printer is not configured. Set PRINTER_SERIAL_PORT in config.py.",
        "transport": "serial",
        "candidates": [],
    }


def _status_for_usb(Usb, import_error):
    if Usb is None:
        return {
            "success": False,
            "configured": False,
            "connected": False,
            "message": (
                "Printer package missing. Install python-escpos and pyusb in the Python "
                f"environment running the POS. Details: {import_error}"
            ),
            "transport": "usb",
            "candidates": [],
        }

    usb_candidates = _discover_usb_candidates()
    if usb_candidates:
        candidate_labels = [
            f"{vendor_id:04x}:{product_id:04x}"
            for vendor_id, product_id, _source in usb_candidates
        ]
        return {
            "success": True,
            "configured": True,
            "connected": True,
            "message": f"USB printer candidate detected: {', '.join(candidate_labels[:3])}",
            "transport": "usb",
            "candidates": candidate_labels,
        }
    return {
        "success": False,
        "configured": bool(PRINTER_VENDOR and PRINTER_PRODUCT),
        "connected": False,
        "message": "USB printer mode selected but no USB printer candidates were detected.",
        "transport": "usb",
        "candidates": [],
    }


def get_printer_routes_status():
    Usb, _Serial, _Network, import_error = _load_printer_backends()
    return {
        "windows": _status_for_windows(),
        "wifi": _status_for_network(),
        "bluetooth": _status_for_bluetooth(),
        "serial": _status_for_serial(),
        "usb": _status_for_usb(Usb, import_error),
    }


def get_printer_status():
    routes = get_printer_routes_status()
    mode = _normalized_printer_mode()

    if mode == "windows":
        status = dict(routes["windows"])
    elif mode == "network":
        status = dict(routes["wifi"])
    elif mode == "bluetooth":
        status = dict(routes["bluetooth"])
    elif mode == "serial":
        status = dict(routes["serial"])
    elif mode == "usb":
        status = dict(routes["usb"])
    else:
        checks = []
        if _is_windows():
            checks.append(routes["windows"])
        checks.extend([routes["wifi"], routes["bluetooth"], routes["serial"], routes["usb"]])
        status = next((item for item in checks if item.get("success")), None)
        if status is None:
            status = {
                "success": False,
                "configured": False,
                "connected": False,
                "message": "No printer detected. Configure PRINTER_MODE and printer connection details in config.py.",
                "transport": None,
                "candidates": [],
            }

    status["mode"] = mode
    return status


def print_test_receipt():
    sample_cart = [
        {
            "id": 0,
            "name": "Printer Test",
            "qty": 1,
            "price": 0.0,
            "total": 0.0,
        }
    ]
    return print_bill(
        sample_cart,
        total=0.0,
        bill_no="TEST",
        payment_mode="Test",
        subtotal=0.0,
        discount_percent=0.0,
        discount_amount=0.0,
    )


def print_bill(
    cart,
    total,
    bill_no=None,
    payment_mode=None,
    subtotal=None,
    discount_percent=0.0,
    discount_amount=0.0,
):
    receipt_text = _build_receipt_text(
        cart,
        total,
        bill_no=bill_no,
        payment_mode=payment_mode,
        subtotal=subtotal,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
    )
    payload = _build_receipt_payload(receipt_text)
    mode = _normalized_printer_mode()
    Usb, Serial, _Network, import_error = _load_printer_backends()
    windows_result = None
    last_exception = None
    usb_failures = []

    def _print(printer):
        printer.text(receipt_text)
        printer.cut()
        return {"success": True, "message": "Receipt printed successfully."}

    def _print_and_close(printer):
        try:
            return _print(printer)
        finally:
            close_method = getattr(printer, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception:
                    pass

    def _try_windows():
        nonlocal windows_result
        if not _is_windows():
            return None
        windows_result = _print_with_windows_spooler(receipt_text)
        if windows_result.get("success"):
            return windows_result
        return None

    def _try_network():
        nonlocal last_exception
        host, port, label = _network_target()
        if not host:
            return None
        try:
            with socket.create_connection((host, port), timeout=3.0) as sock:
                sock.sendall(payload)
            return {"success": True, "message": f"Receipt printed successfully on Wi-Fi printer {label}."}
        except Exception as exc:
            last_exception = exc
            return None

    def _try_bluetooth():
        nonlocal last_exception
        address = _configured_bluetooth_address()
        channel = _configured_bluetooth_channel()
        if address:
            family = getattr(socket, "AF_BLUETOOTH", None)
            proto = getattr(socket, "BTPROTO_RFCOMM", None)
            if family is None or proto is None:
                last_exception = RuntimeError("Bluetooth RFCOMM is not available in this Python/OS build.")
            else:
                bt_sock = socket.socket(family, socket.SOCK_STREAM, proto)
                try:
                    bt_sock.settimeout(5.0)
                    bt_sock.connect((address, channel))
                    bt_sock.sendall(payload)
                    label = str(_configured_bluetooth_name() or address).strip()
                    return {"success": True, "message": f"Receipt printed successfully on Bluetooth printer {label}."}
                except Exception as exc:
                    last_exception = exc
                finally:
                    try:
                        bt_sock.close()
                    except Exception:
                        pass

        windows_targets = _bluetooth_windows_target_printers()
        if windows_targets:
            result = _print_with_windows_spooler(receipt_text, printer_names=windows_targets)
            if result.get("success"):
                return result
            last_exception = RuntimeError(result.get("message", "Bluetooth printer unavailable via Windows spooler."))
        return None

    def _try_serial():
        nonlocal last_exception
        if not PRINTER_SERIAL_PORT or Serial is None:
            return None
        try:
            printer = Serial(PRINTER_SERIAL_PORT, baudrate=19200, timeout=1)
            return _print_and_close(printer)
        except Exception as exc:
            last_exception = exc
            return None

    def _try_usb():
        nonlocal last_exception
        if Usb is None:
            return None
        for vendor_id, product_id, source in _discover_usb_candidates():
            for out_ep, in_ep in _discover_usb_endpoints(vendor_id, product_id):
                try:
                    printer = Usb(vendor_id, product_id, timeout=1000, out_ep=out_ep, in_ep=in_ep)
                    return _print_and_close(printer)
                except Exception as exc:
                    last_exception = exc
                    usb_failures.append(
                        f"{vendor_id:04x}:{product_id:04x} ({source}, out={out_ep:#04x}, in={in_ep:#04x}) -> {exc}"
                    )
        return None

    if mode == "windows":
        result = _try_windows()
        if result:
            return result
    elif mode == "network":
        result = _try_network()
        if result:
            return result
    elif mode == "bluetooth":
        result = _try_bluetooth()
        if result:
            return result
    elif mode == "serial":
        result = _try_serial()
        if result:
            return result
    elif mode == "usb":
        result = _try_usb()
        if result:
            return result
    else:
        attempts = []
        if _is_windows():
            attempts.append(_try_windows)
        attempts.extend([_try_network, _try_bluetooth, _try_serial, _try_usb])
        for attempt in attempts:
            result = attempt()
            if result:
                return result

    if last_exception is None and Usb is None and mode in {"auto", "usb"}:
        import sys

        interpreter = sys.executable
        if _is_windows():
            return {
                "success": False,
                "message": (
                    f"{(windows_result or {}).get('message', 'Printer unavailable.')} "
                    "USB/serial fallback also unavailable because python-escpos is missing. "
                    f"Run: {interpreter} -m pip install python-escpos pyusb pywin32"
                ),
            }
        return {
            "success": False,
            "message": (
                "Printer package missing in current Python. "
                f"Run: {interpreter} -m pip install python-escpos pyusb "
                "(or select project .venv interpreter). "
                f"Details: {import_error}"
            ),
        }

    if last_exception is None:
        if mode == "windows":
            return windows_result or {
                "success": False,
                "message": "Windows printer mode selected but no Windows printer is configured.",
            }
        if mode == "network":
            return {"success": False, "message": "Wi-Fi printer mode selected but PRINTER_NETWORK_ADDR is empty."}
        if mode == "bluetooth":
            return {
                "success": False,
                "message": "Bluetooth printer mode selected but PRINTER_BLUETOOTH_ADDRESS is empty.",
            }
        if mode == "serial":
            return {"success": False, "message": "Serial printer mode selected but PRINTER_SERIAL_PORT is empty."}
        if mode == "usb":
            return {"success": False, "message": "USB printer mode selected but no USB printer candidates were detected."}

    error_text = str(last_exception or "unknown error").replace("\n", " ").strip()
    if len(error_text) > 180:
        error_text = error_text[:177] + "..."
    permission_hint = ""
    lowered_error = str(last_exception or "").lower()
    if not _is_windows() and ("access denied" in lowered_error or "insufficient permissions" in lowered_error):
        permission_hint = " Fix: add your user to 'lp' group and re-login."
    message = f"Printer unavailable ({error_text}). Sale saved; printing skipped.{permission_hint}"
    response = {"success": False, "message": message}
    if usb_failures:
        response["debug"] = "USB tries: " + " || ".join(usb_failures[:2])
    return response
