#!/usr/bin/env python3
"""Ensure each TEI document includes the leading page image.

Some METS exports omit the very first image page even though the source image
exists. This script inserts a placeholder ``<surface xml:id="facs_0">`` together
with a matching ``<pb>`` when the first available surface references a graphic
ending in ``*_00002.*`` (or higher). Conversely, if a placeholder was created
but the first surface already points to ``*_00001.*`` the redundant elements are
removed again.
"""

from __future__ import annotations

import glob
import os
import re
from typing import Optional, Tuple

import lxml.etree as ET

from acdh_tei_pyutils.tei import TeiReader

TEI_DIR = os.environ.get("TEI_DIR", "./data/editions")
NSMAP = {"tei": "http://www.tei-c.org/ns/1.0"}
TEI = "{http://www.tei-c.org/ns/1.0}"
XML = "{http://www.w3.org/XML/1998/namespace}"

FILE_PATTERN = os.path.join(TEI_DIR, "*.xml")
NUMERIC_SUFFIX_RE = re.compile(r"(.*_)(\d+)(\.[^.]+)$")
FALLBACK_SUFFIX_RE = re.compile(r"(.*?)(\d+)(\.[^.]+)$")


def parse_numeric_suffix(url: str) -> Optional[Tuple[str, int, int, str]]:
    """Return the numeric suffix details of a file name when present."""

    match = NUMERIC_SUFFIX_RE.match(url)
    if not match:
        match = FALLBACK_SUFFIX_RE.match(url)
    if not match:
        return None
    prefix, number, extension = match.groups()
    value = int(number)
    width = len(number)
    return prefix, value, width, extension


def derive_previous_image_url(url: str) -> Optional[str]:
    """Return the previous ``*_00001.*`` style URL when possible."""

    parsed = parse_numeric_suffix(url)
    if not parsed:
        return None
    prefix, value, width, extension = parsed
    if value <= 0:
        return None
    return f"{prefix}{value - 1:0{width}d}{extension}"


def first_local_graphic(surface) -> Optional[ET._Element]:  # type: ignore[name-defined]
    """Return the first non-HTTP graphic node from a surface, if available."""

    for graphic in surface.findall(f"{TEI}graphic"):
        url = graphic.get("url", "")
        if url and not url.lower().startswith("http"):
            return graphic
    return None


def collect_existing_graphic_urls(root) -> set[str]:  # type: ignore[name-defined]
    """Collect all graphic @url values to avoid duplicates."""

    return {node.get("url") for node in root.xpath(".//tei:graphic", namespaces=NSMAP) if node.get("url")}


def next_unique_id(base: str, used: set[str]) -> str:
    """Return a unique identifier based on *base* that is not present in *used*."""

    candidate = base
    counter = 1
    while candidate in used:
        candidate = f"{base}-{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def compute_leading_id(existing_id: Optional[str], used: set[str]) -> str:
    """Derive the preceding xml:id for the new pb element."""

    if existing_id:
        match = re.match(r"^(.*?)(\d+)$", existing_id)
        if match:
            prefix, digits = match.groups()
            number = int(digits)
            if number > 0:
                candidate = f"{prefix}{number - 1:0{len(digits)}d}"
                if candidate not in used:
                    used.add(candidate)
                    return candidate
    return next_unique_id("img_0000", used)


def compute_leading_n(value: Optional[str]) -> str:
    """Return the textual value for the leading pb@n attribute."""

    if value and value.isdigit():
        number = int(value)
        if number > 0:
            width = len(value)
            return f"{number - 1:0{width}d}"
    return "0"


def remove_redundant_placeholder(root, facsimile) -> bool:  # type: ignore[name-defined]
    """Drop a previously added facs_0 surface/pb when not required anymore."""

    placeholder = facsimile.find(f"{TEI}surface[@{XML}id='facs_0']")
    if placeholder is None:
        return False

    surfaces = facsimile.findall(f"{TEI}surface")
    next_surface = None
    for surface in surfaces:
        if surface is placeholder:
            continue
        next_surface = surface
        break
    if next_surface is None:
        return False

    graphic = first_local_graphic(next_surface)
    if graphic is None:
        return False

    parsed = parse_numeric_suffix(graphic.get("url", ""))
    if not parsed:
        return False
    _, value, _, _ = parsed
    if value > 1:
        return False

    for pb in root.xpath('.//tei:pb[@facs="#facs_0"]', namespaces=NSMAP):
        parent = pb.getparent()
        if parent is not None:
            parent.remove(pb)

    facsimile.remove(placeholder)
    return True


def ensure_placeholder(path: str) -> bool:
    """Synchronise placeholder surfaces and pb elements for missing page one."""

    tei = TeiReader(path)
    root = tei.tree.getroot()

    facsimiles = root.xpath(".//tei:facsimile", namespaces=NSMAP)
    if not facsimiles:
        return False
    facsimile = facsimiles[0]

    updated = remove_redundant_placeholder(root, facsimile)

    surfaces = facsimile.findall(f"{TEI}surface")
    if not surfaces:
        if updated:
            ET.indent(root, space="  ")
            tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return False

    first_real_surface = None
    for surface in surfaces:
        if surface.get(f"{XML}id") == "facs_0":
            continue
        first_real_surface = surface
        break
    if first_real_surface is None:
        if updated:
            ET.indent(root, space="  ")
            tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return False

    local_graphic = first_local_graphic(first_real_surface)
    if local_graphic is None:
        if updated:
            ET.indent(root, space="  ")
            tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return updated

    parsed = parse_numeric_suffix(local_graphic.get("url", ""))
    if not parsed:
        if updated:
            ET.indent(root, space="  ")
            tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return updated
    prefix, value, width, extension = parsed

    if value <= 1:
        if updated:
            ET.indent(root, space="  ")
            tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return updated

    placeholder_url = f"{prefix}{value - 1:0{width}d}{extension}"
    existing_urls = collect_existing_graphic_urls(root)

    pb_nodes = root.xpath(".//tei:body//tei:pb", namespaces=NSMAP)
    if not pb_nodes:
        if updated:
            ET.indent(root, space="  ")
            tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return updated

    first_surface_id = first_real_surface.get(f"{XML}id")
    first_pb_candidates = root.xpath(f".//tei:body//tei:pb[@facs='#{first_surface_id}']", namespaces=NSMAP)
    first_pb = first_pb_candidates[0] if first_pb_candidates else pb_nodes[0]
    if first_pb.get("n") == "0":
        if updated:
            ET.indent(root, space="  ")
            tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return updated

    placeholder_surface = facsimile.find(f"{TEI}surface[@{XML}id='facs_0']")
    if placeholder_surface is None and placeholder_url in existing_urls:
        if updated:
            ET.indent(root, space="  ")
            tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return updated
    surface_changed = False
    if placeholder_surface is None:
        surface_attrs = {k: v for k, v in first_real_surface.attrib.items() if k != f"{XML}id"}
        placeholder_surface = ET.Element(f"{TEI}surface", attrib=surface_attrs)
        placeholder_surface.set(f"{XML}id", "facs_0")
        facsimile.insert(0, placeholder_surface)
        surface_changed = True

    placeholder_graphic = first_local_graphic(placeholder_surface)
    if placeholder_graphic is None:
        placeholder_graphic = ET.SubElement(placeholder_surface, f"{TEI}graphic")
        surface_changed = True

    if placeholder_graphic.get("url") != placeholder_url:
        placeholder_graphic.set("url", placeholder_url)
        surface_changed = True

    for attr in ("width", "height", "n"):
        value_attr = local_graphic.get(attr)
        if value_attr and placeholder_graphic.get(attr) != value_attr:
            placeholder_graphic.set(attr, value_attr)
            surface_changed = True

    updated = updated or surface_changed

    placeholder_pb_exists = bool(root.xpath('.//tei:pb[@facs="#facs_0"]', namespaces=NSMAP))
    if not placeholder_pb_exists:
        existing_pb_ids = {node.get(f"{XML}id") for node in pb_nodes if node.get(f"{XML}id")}

        new_pb = ET.Element(f"{TEI}pb")
        new_pb.set("facs", "#facs_0")
        new_pb.set("n", compute_leading_n(first_pb.get("n")))
        new_pb.set(f"{XML}id", compute_leading_id(first_pb.get(f"{XML}id"), existing_pb_ids))

        first_pb.addprevious(new_pb)
        updated = True

    if updated:
        ET.indent(root, space="  ")
        tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
    return updated


def main() -> None:
    files = sorted(glob.glob(FILE_PATTERN))
    if not files:
        print(f"No TEI files found in {TEI_DIR}")
        return

    updated = 0
    for path in files:
        try:
            if ensure_placeholder(path):
                updated += 1
                print(f"Inserted placeholder lead page in {path}")
        except Exception as exc:  # noqa: BLE001 broad but logged
            print(f"Failed to update {path}: {exc}")
    print(f"Added placeholders in {updated} file(s)")


if __name__ == "__main__":
    main()
