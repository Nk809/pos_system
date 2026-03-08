import json
import re


def _to_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None


def _first_non_empty(mapping, keys):
    for key in keys:
        if key not in mapping:
            continue
        value = mapping.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _first_number(mapping, keys, caster):
    for key in keys:
        if key not in mapping:
            continue
        value = mapping.get(key)
        converted = _to_float(value) if caster is float else _to_int(value)
        if converted is not None:
            return converted
    return None


def parse_scanned_payload(raw_value):
    raw = (raw_value or "").strip()
    parsed = {"barcode": "", "name": "", "price": None, "qty": None, "stock": None}
    if not raw:
        return parsed

    details = {}

    try:
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            details = {str(key).strip().lower(): value for key, value in loaded.items()}
    except Exception:
        details = {}

    if not details:
        key_values = {}
        for block in re.split(r"[;\n|&]+", raw):
            chunk = block.strip()
            if not chunk:
                continue

            if "=" in chunk:
                key, value = chunk.split("=", 1)
            elif ":" in chunk:
                key, value = chunk.split(":", 1)
            else:
                continue

            key_values[key.strip().lower()] = value.strip()

        if key_values:
            details = key_values

    if details:
        parsed["barcode"] = _first_non_empty(details, ["barcode", "bar_code", "code", "sku", "ean", "upc", "item_code", "id"])
        parsed["name"] = _first_non_empty(details, ["name", "item", "product", "title"])
        parsed["price"] = _first_number(details, ["price", "mrp", "rate", "amount", "selling_price"], float)
        parsed["qty"] = _first_number(details, ["qty", "quantity"], int)
        parsed["stock"] = _first_number(details, ["stock", "available_stock", "on_hand"], int)
        return parsed

    for separator in (",", "|"):
        split_values = [part.strip() for part in raw.split(separator)]
        if len(split_values) in (3, 4):
            parsed["barcode"] = split_values[0]
            parsed["name"] = split_values[1]
            parsed["price"] = _to_float(split_values[2])
            if len(split_values) == 4:
                parsed["qty"] = _to_int(split_values[3])
            return parsed

    parsed["barcode"] = raw
    return parsed


def extract_scanned_code(raw_value):
    parsed = parse_scanned_payload(raw_value)
    return str(parsed.get("barcode") or "").strip()
