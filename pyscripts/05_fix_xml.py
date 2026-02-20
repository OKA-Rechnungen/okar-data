#!/usr/bin/env python3
"""Normalize TEI files by setting xml:id/base and aligning facsimile URLs."""

from __future__ import annotations

import os
import re
from pathlib import Path

import lxml.etree as ET

LOCAL_TIF_RE = re.compile(r'^\d+\.tif$', re.IGNORECASE)
COUNTER_RE = re.compile(r'(\d+)(\.[^.]+)$')

BASENAME = "/"
XML_NS = "http://www.w3.org/XML/1998/namespace"
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}

XML_DIR = Path("./data/editions")


def _load_tree(path: Path) -> ET._ElementTree:
    """Parse XML, falling back to recover mode on malformed input."""

    parser = ET.XMLParser(remove_blank_text=False)
    try:
        return ET.parse(str(path), parser=parser)
    except ET.XMLSyntaxError as exc:
        print(f"  Warning: {path.name} is not well-formed ({exc}); attempting recovery")
        recover_parser = ET.XMLParser(remove_blank_text=False, recover=True)
        return ET.parse(str(path), parser=recover_parser)


def _write_tree(tree: ET._ElementTree, path: Path) -> None:
    xml_bytes = ET.tostring(
        tree.getroot(), encoding="utf-8", xml_declaration=True, pretty_print=True
    )
    path.write_bytes(xml_bytes)


def _fix_graphic_urls(root: ET._Element, volume_name: str) -> None:
    for graphic in root.xpath('.//tei:graphic', namespaces=TEI_NS):
        url = graphic.get('url')
        if not url or url.lower().startswith('http'):
            continue

        if LOCAL_TIF_RE.match(url):
            # Align legacy "0001.tif" style links with the volume identifier.
            surface = graphic.getparent()
            xml_id = surface.get(f'{{{XML_NS}}}id') if surface is not None else None
            if xml_id:
                id_suffix = xml_id.split('_')[1] if '_' in xml_id else xml_id
                graphic.set('url', f"{volume_name}_{id_suffix}.tif")
            continue

        match = COUNTER_RE.search(url)
        if not match:
            continue

        counter, _extension = match.groups()
        padded = f"{int(counter):0{len(counter)}d}.tif"
        target = f"{volume_name}_{padded}"
        if target != url:
            graphic.set('url', target)


def _volume_name(filename: str) -> str:
    match = re.search(r"(WSTLA-OKA-B1-\d+-\d+-\d)", filename)
    return match.group(1) if match else os.path.splitext(filename)[0]


def main() -> int:
    xml_files = sorted(
        path for path in XML_DIR.iterdir() if path.name.startswith('WSTLA-OKA') and path.suffix == '.xml'
    )

    prev_entry: tuple[str, Path, ET._ElementTree] | None = None

    for current_path in xml_files:
        current_name = current_path.name
        print(f"Fixing {current_name}")
        tree = _load_tree(current_path)
        root = tree.getroot()

        volume_name = _volume_name(current_name)
        root.set(f'{{{XML_NS}}}id', "".join(os.path.splitext(current_name)))
        root.set(f'{{{XML_NS}}}base', BASENAME)

        if prev_entry:
            prev_name, prev_path, prev_tree = prev_entry
            prev_tree.getroot().set('next', current_name)
            _write_tree(prev_tree, prev_path)
            root.set('prev', prev_name)

        _fix_graphic_urls(root, volume_name)

        prev_entry = (current_name, current_path, tree)

    if prev_entry:
        _write_tree(prev_entry[2], prev_entry[1])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
