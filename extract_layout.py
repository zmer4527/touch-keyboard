#!/usr/bin/env python3
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_SOURCE = Path(__file__).resolve().parent.parent / "DroidDeck-main"


def balanced(text, open_index):
    depth = 0
    quote = None
    i = open_index
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:i], i + 1
        i += 1
    raise ValueError("unbalanced parentheses")


def split_args(text):
    args, depth, quote, start = [], 0, None, 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(text[start:i].strip())
            start = i + 1
        i += 1
    if text[start:].strip():
        args.append(text[start:].strip())
    return args


def unquote(value):
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value


def load_strings(path):
    if not path.is_file():
        return {}
    root = ET.parse(path).getroot()
    return {node.get("name"): node.text or "" for node in root.findall("string")}


def parse_file(path, strings, strings_zh):
    text = path.read_text(encoding="utf-8")
    block = text[text.index("PC_KEY_ROWS"):text.index("val PC_MODIFIERS")]
    rows_start = block.index("listOf(")
    rows_text, _ = balanced(block, rows_start + len("listOf"))

    rows = []
    cursor = 0
    while True:
        index = rows_text.find("listOf(", cursor)
        if index == -1:
            break
        row_text, cursor = balanced(rows_text, index + len("listOf"))
        keys = []
        key_cursor = 0
        while True:
            key_index = row_text.find("k(", key_cursor)
            if key_index == -1:
                break
            args_text, key_cursor = balanced(row_text, key_index + 1)
            args = split_args(args_text)
            label_id = None
            if args[0].startswith("R.string."):
                label_id = args[0][len("R.string."):]
                label = strings.get(label_id, label_id)
                label_zh = strings_zh.get(label_id, label)
            else:
                label = unquote(args[0])
                label_zh = label
            code = int(args[1])
            weight = 1.0
            shifted = None
            for arg in args[2:]:
                if arg.startswith("shifted"):
                    shifted = unquote(arg.split("=", 1)[1])
                elif re.fullmatch(r"\d+(\.\d+)?f", arg):
                    weight = float(arg[:-1])
            key = {"label": label, "evdev": code, "weight": weight}
            if label_id:
                key["label_id"] = label_id
            if label_zh != label:
                key["label_zh"] = label_zh
            if shifted:
                key["shifted"] = shifted
            keys.append(key)
        rows.append(keys)
    modifiers = re.search(r"PC_MODIFIERS[^=]*=\s*setOf\(([^)]*)\)", text)
    return rows, [int(v.strip()) for v in modifiers.group(1).split(",") if v.strip()]


def main():
    parser = argparse.ArgumentParser(description="Extract the DroidDeck PC keyboard layout into layout.json")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="DroidDeck-main checkout")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "layout.json")
    args = parser.parse_args()

    values = args.source / "app/src/main/res/values/strings.xml"
    values_zh = args.source / "app/src/main/res/values-zh-rCN/strings.xml"
    keys_kt = args.source / "app/src/main/java/com/droiddeck/launcher/input/PcKeys.kt"
    for path in (values, keys_kt):
        if not path.is_file():
            raise SystemExit(f"missing {path}")

    strings = load_strings(values)
    strings_zh = load_strings(values_zh)
    rows, modifiers = parse_file(keys_kt, strings, strings_zh)
    document = {
        "name": strings.get("drawer_pc_keyboard", "PC keyboard"),
        "name_zh": strings_zh.get("drawer_pc_keyboard", "PC 键盘"),
        "hide": strings.get("pckb_hide", "Hide"),
        "hide_zh": strings_zh.get("pckb_hide", "隐藏"),
        "source": "app/src/main/java/com/droiddeck/launcher/input/PcKeys.kt",
        "modifier_codes": modifiers,
        "rows": rows,
    }
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(rows)} rows, {sum(len(r) for r in rows)} keys)")


if __name__ == "__main__":
    main()
