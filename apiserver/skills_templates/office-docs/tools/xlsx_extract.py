#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import zipfile
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": SHEET_NS}


def _load_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    xml_bytes = archive.read("xl/sharedStrings.xml")
    root = ET.fromstring(xml_bytes)
    strings: List[str] = []
    for si in root.findall("main:si", NS):
        text_parts: List[str] = []
        for node in si.iter(f"{{{SHEET_NS}}}t"):
            if node.text:
                text_parts.append(node.text)
        strings.append("".join(text_parts))
    return strings


def _load_sheet_targets(archive: zipfile.ZipFile) -> List[Tuple[str, str]]:
    workbook_xml = archive.read("xl/workbook.xml")
    rels_xml = archive.read("xl/_rels/workbook.xml.rels")

    workbook = ET.fromstring(workbook_xml)
    rels = ET.fromstring(rels_xml)

    rel_map: Dict[str, str] = {}
    for rel in rels.findall(f"{{{RELS_NS}}}Relationship"):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id and target:
            rel_map[rel_id] = target

    sheet_targets: List[Tuple[str, str]] = []
    for sheet in workbook.findall("main:sheets/main:sheet", NS):
        name = sheet.attrib.get("name", "Sheet")
        rel_id = sheet.attrib.get(f"{{{REL_NS}}}id")
        target = rel_map.get(rel_id, "")
        if target:
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            sheet_targets.append((name, target))

    return sheet_targets


def _cell_ref_to_col_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref.upper())
    if not match:
        return 0
    letters = match.group(1)
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def _parse_sheet(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: List[str],
    max_rows: Optional[int],
) -> List[List[str]]:
    xml_bytes = archive.read(sheet_path)
    root = ET.fromstring(xml_bytes)
    rows: List[List[str]] = []

    for row in root.findall(".//main:row", NS):
        row_cells: Dict[int, str] = {}
        for cell in row.findall("main:c", NS):
            cell_ref = cell.attrib.get("r", "")
            col_index = _cell_ref_to_col_index(cell_ref)
            cell_type = cell.attrib.get("t")
            value = ""
            if cell_type == "s":
                value_node = cell.find("main:v", NS)
                if value_node is not None and value_node.text is not None:
                    try:
                        idx = int(value_node.text)
                        value = shared_strings[idx] if idx < len(shared_strings) else ""
                    except ValueError:
                        value = ""
            elif cell_type == "inlineStr":
                inline_node = cell.find(".//main:t", NS)
                if inline_node is not None and inline_node.text is not None:
                    value = inline_node.text
            else:
                value_node = cell.find("main:v", NS)
                if value_node is not None and value_node.text is not None:
                    value = value_node.text
            if col_index > 0:
                row_cells[col_index] = value

        if row_cells:
            max_col = max(row_cells.keys())
            row_values = [row_cells.get(i, "") for i in range(1, max_col + 1)]
            rows.append(row_values)
            if max_rows is not None and len(rows) >= max_rows:
                break

    return rows


def _format_sheet_csv(rows: List[List[str]], delimiter: str) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "sheet"


def _write_sheets(
    sheets: List[Tuple[str, str]],
    archive: zipfile.ZipFile,
    shared_strings: List[str],
    output_path: Optional[Path],
    delimiter: str,
    max_rows: Optional[int],
) -> None:
    if output_path is None:
        for name, path in sheets:
            rows = _parse_sheet(archive, path, shared_strings, max_rows)
            content = _format_sheet_csv(rows, delimiter)
            print(f"# Sheet: {name}")
            print(content.rstrip())
            print()
        return

    if output_path.is_dir() or output_path.suffix == "":
        output_path.mkdir(parents=True, exist_ok=True)
        extension = "tsv" if delimiter == "\t" else "csv"
        for name, path in sheets:
            rows = _parse_sheet(archive, path, shared_strings, max_rows)
            content = _format_sheet_csv(rows, delimiter)
            filename = f"{_sanitize_filename(name)}.{extension}"
            (output_path / filename).write_text(content, encoding="utf-8")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined: List[str] = []
    for name, path in sheets:
        rows = _parse_sheet(archive, path, shared_strings, max_rows)
        combined.append(f"# Sheet: {name}")
        combined.append(_format_sheet_csv(rows, delimiter).rstrip())
        combined.append("")
    output_path.write_text("\n".join(combined).rstrip() + "\n", encoding="utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract sheet data from a .xlsx file.")
    parser.add_argument("path", type=str, help="Path to the .xlsx file")
    parser.add_argument("--output", type=str, default=None, help="Output file or directory")
    parser.add_argument(
        "--format",
        type=str,
        default="csv",
        choices=["csv", "tsv"],
        help="Output delimiter format",
    )
    parser.add_argument("--max-rows", type=int, default=None, help="Limit rows per sheet")
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    xlsx_path = Path(args.path).expanduser().resolve()
    if not xlsx_path.exists():
        raise FileNotFoundError(f"File not found: {xlsx_path}")

    delimiter = "\t" if args.format == "tsv" else ","
    output_path = Path(args.output).expanduser().resolve() if args.output else None

    with zipfile.ZipFile(xlsx_path, "r") as archive:
        shared_strings = _load_shared_strings(archive)
        sheets = _load_sheet_targets(archive)
        if not sheets:
            raise RuntimeError("No worksheets found in the workbook")
        _write_sheets(sheets, archive, shared_strings, output_path, delimiter, args.max_rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
