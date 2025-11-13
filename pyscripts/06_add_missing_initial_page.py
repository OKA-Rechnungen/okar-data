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
from pathlib import Path
from typing import Dict, Optional, Tuple

import lxml.etree as ET

from acdh_tei_pyutils.tei import TeiReader

TEI_DIR = os.environ.get("TEI_DIR", "./data/editions")
METS_DIR = Path(os.environ.get("METS_DIR", "./data/mets"))
NSMAP = {"tei": "http://www.tei-c.org/ns/1.0"}
TEI = "{http://www.tei-c.org/ns/1.0}"
XML = "{http://www.w3.org/XML/1998/namespace}"

FACSIMILE_REF_RE = re.compile(r"#(facs_\d+)")

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


def resolve_image_name_file(doc_id: str) -> Optional[Path]:
    """Return the path to the *_image_name.xml file for *doc_id*, if present."""

    if not METS_DIR.exists():
        return None
    candidates = sorted(METS_DIR.glob(f"**/{doc_id}_image_name.xml"))
    return candidates[0] if candidates else None


def load_image_sequence(mapping_path: Path) -> list[str]:
    """Read the Transkribus image name list for a document."""

    try:
        tree = ET.parse(mapping_path)
    except ET.ParseError:
        return []
    return [item.text.strip() for item in tree.findall(".//item") if item.text]


def apply_image_name_mapping(path: str, root, facsimile) -> bool:  # type: ignore[name-defined]
    """Align local graphic URLs with Transkribus image names when available."""

    doc_id = Path(path).stem
    mapping_path = resolve_image_name_file(doc_id)
    if mapping_path is None:
        return False

    image_names = load_image_sequence(mapping_path)
    if not image_names:
        return False

    surfaces = list(facsimile.findall(f"{TEI}surface"))
    if not surfaces:
        return False

    index = 0
    changed = False
    sequence_length = len(image_names)

    for surface in surfaces:
        if index >= sequence_length:
            break

        target_name = image_names[index]
        local_graphic = first_local_graphic(surface)
        if local_graphic is not None and local_graphic.get("url") != target_name:
            local_graphic.set("url", target_name)
            changed = True

        index += 1

    return changed

def extract_surface_id(value: Optional[str]) -> Optional[str]:
    """Return the base surface xml:id (e.g. ``facs_123``) from a facs attribute."""

    if not value:
        return None
    match = FACSIMILE_REF_RE.search(value)
    if not match:
        return None
    return match.group(1)


def nearest_child_in_container(node: ET._Element, container: ET._Element) -> Optional[ET._Element]:  # type: ignore[name-defined]
    """Return the highest ancestor of *node* that is a direct child of *container*."""

    current = node
    while current is not None and current.getparent() is not container:
        current = current.getparent()
    return current


def compute_node_positions(container: ET._Element) -> Dict[ET._Element, int]:  # type: ignore[name-defined]
    """Return document-order positions for descendants of *container*."""

    return {element: index for index, element in enumerate(container.iter())}


def collect_last_ab_blocks(container: ET._Element) -> Dict[str, ET._Element]:  # type: ignore[name-defined]
    """Return the last ``<ab>`` encountered for each surface within *container*."""

    mapping: Dict[str, ET._Element] = {}
    for ab in container.xpath(".//tei:ab[@facs]", namespaces=NSMAP):
        surface_id = extract_surface_id(ab.get("facs"))
        if surface_id:
            mapping[surface_id] = ab
    return mapping


def reorder_page_breaks(root) -> bool:  # type: ignore[name-defined]
    """Ensure each ``<pb>`` follows the content that still references its surface."""

    bodies = root.xpath(".//tei:body", namespaces=NSMAP)
    if not bodies:
        return False

    changed = False
    for body in bodies:
        containers = [body] + body.xpath(".//tei:div", namespaces=NSMAP)
        for container in containers:
            if not isinstance(container.tag, str):
                continue

            pb_nodes = [child for child in container if child.tag == f"{TEI}pb"]
            if len(pb_nodes) < 2:
                continue

            last_blocks = collect_last_ab_blocks(container)
            if not last_blocks:
                continue

            positions = compute_node_positions(container)
            for index, pb in enumerate(pb_nodes):
                surface_id = extract_surface_id(pb.get("facs"))
                if not surface_id:
                    continue

                block = last_blocks.get(surface_id)
                if block is None:
                    continue

                anchor = nearest_child_in_container(block, container)
                if anchor is None:
                    continue

                if anchor not in positions:
                    positions = compute_node_positions(container)
                last_pos = positions[anchor]
                insertion_point = anchor

                j = index + 1
                while j < len(pb_nodes):
                    candidate = pb_nodes[j]
                    if candidate.getparent() is not container:
                        j += 1
                        continue

                    if candidate not in positions:
                        positions = compute_node_positions(container)
                        last_pos = positions[anchor]

                    candidate_pos = positions[candidate]
                    if candidate_pos > last_pos:
                        break

                    container.remove(candidate)
                    insert_index = container.index(insertion_point)
                    container.insert(insert_index + 1, candidate)
                    insertion_point = candidate
                    positions = compute_node_positions(container)
                    last_pos = positions[anchor]
                    changed = True
                    j += 1

            if changed:
                positions = compute_node_positions(container)

    return changed


def rename_descendants(surface, old_id: str, new_id: str, id_map: Dict[str, str]) -> None:  # type: ignore[name-defined]
    """Rename descendant xml:id values that are prefixed with *old_id*."""

    descendants = list(surface.xpath(".//*[@xml:id]", namespaces=NSMAP))
    for node in descendants:
        current_id = node.get(f"{XML}id")
        if not current_id:
            continue
        if current_id == old_id:
            node.set(f"{XML}id", new_id)
            id_map[current_id] = new_id
        elif current_id.startswith(f"{old_id}_"):
            replacement = f"{new_id}{current_id[len(old_id):]}"
            node.set(f"{XML}id", replacement)
            id_map[current_id] = replacement


def update_id_references(root, id_map: Dict[str, str]) -> bool:  # type: ignore[name-defined]
    """Replace references to old xml:id values throughout the document."""

    if not id_map:
        return False

    changed = False
    replacements = [(old, new) for old, new in id_map.items() if old != new]
    if not replacements:
        return False

    replacements.sort(key=lambda item: len(item[0]), reverse=True)

    def replace_standalone_token(value: str, old: str, new: str) -> tuple[str, bool]:
        """Replace *old* with *new* unless the match runs into extra digits."""

        cursor = 0
        result: list[str] = []
        touched = False
        token_len = len(old)

        while True:
            hit = value.find(old, cursor)
            if hit == -1:
                result.append(value[cursor:])
                break

            tail_index = hit + token_len
            if tail_index < len(value) and value[tail_index].isdigit():
                result.append(value[cursor:tail_index])
                cursor = tail_index
                continue

            result.append(value[cursor:hit])
            result.append(new)
            cursor = tail_index
            touched = True

        return "".join(result), touched

    xml_id_key = f"{XML}id"
    for element in root.iter():
        for attr, value in list(element.attrib.items()):
            if attr == xml_id_key:
                continue
            if not isinstance(value, str):
                continue
            new_value = value
            for old, new in replacements:
                if old not in new_value:
                    continue
                new_value, token_replaced = replace_standalone_token(new_value, old, new)
                if token_replaced:
                    changed = True
            if new_value != value:
                element.set(attr, new_value)
    return changed


def normalise_surface_ids(root, facsimile) -> bool:  # type: ignore[name-defined]
    """Ensure surfaces are ordered and labelled according to image numbering."""

    surfaces = list(facsimile.findall(f"{TEI}surface"))
    if not surfaces:
        return False

    placeholder = None
    ordered_surfaces = []
    numeric_bucket: list[Tuple[int, int, ET._Element]] = []  # type: ignore[name-defined]
    fallback_bucket: list[Tuple[int, ET._Element]] = []

    for index, surface in enumerate(surfaces):
        sid = surface.get(f"{XML}id")
        if sid == "facs_0":
            placeholder = surface
            continue
        graphic = first_local_graphic(surface)
        parsed = parse_numeric_suffix(graphic.get("url", "")) if graphic is not None else None
        if parsed:
            numeric_bucket.append((parsed[1], index, surface))
        else:
            fallback_bucket.append((index, surface))

    numeric_bucket.sort()
    fallback_bucket.sort()

    if placeholder is not None:
        ordered_surfaces.append(placeholder)
    ordered_surfaces.extend(surface for _, _, surface in numeric_bucket)
    ordered_surfaces.extend(surface for _, surface in fallback_bucket)

    if ordered_surfaces == surfaces:
        # Already in correct order but possibly mislabelled
        pass
    else:
        for surface in list(facsimile):
            facsimile.remove(surface)
        for surface in ordered_surfaces:
            facsimile.append(surface)

    id_map: Dict[str, str] = {}
    counter = 1
    changed = False
    for surface in ordered_surfaces:
        sid = surface.get(f"{XML}id")
        if sid == "facs_0":
            continue
        new_id = f"facs_{counter}"
        counter += 1
        if sid != new_id:
            rename_descendants(surface, sid, new_id, id_map)
            surface.set(f"{XML}id", new_id)
            id_map[sid] = new_id
            changed = True
        else:
            id_map.setdefault(sid, new_id)

    changed = update_id_references(root, id_map) or changed
    return changed


def synchronise_page_breaks(root, facsimile) -> bool:  # type: ignore[name-defined]
    """Align pb@facs attributes with the ordered surfaces."""

    pb_nodes = root.xpath(".//tei:body//tei:pb", namespaces=NSMAP)
    if not pb_nodes:
        return False

    surfaces = [surface for surface in facsimile.findall(f"{TEI}surface") if surface.get(f"{XML}id") != "facs_0"]
    if not surfaces:
        return False

    limit = min(len(pb_nodes), len(surfaces))
    changed = False
    for index in range(limit):
        pb = pb_nodes[index]
        surface = surfaces[index]
        facs_value = f"#{surface.get(f'{XML}id')}"
        if pb.get("facs") != facs_value:
            pb.set("facs", facs_value)
            changed = True

    if reorder_page_breaks(root):
        changed = True
    return changed


def surface_numeric_details(facsimile, skip_placeholder: bool = True) -> list[Tuple[ET._Element, ET._Element, Tuple[str, int, int, str]]]:  # type: ignore[name-defined]
    """Return surfaces with a parseable numeric suffix."""

    details: list[Tuple[ET._Element, ET._Element, Tuple[str, int, int, str]]] = []  # type: ignore[name-defined]
    for surface in facsimile.findall(f"{TEI}surface"):
        if skip_placeholder and surface.get(f"{XML}id") == "facs_0":
            continue
        graphic = first_local_graphic(surface)
        if graphic is None:
            continue
        parsed = parse_numeric_suffix(graphic.get("url", ""))
        if not parsed:
            continue
        details.append((surface, graphic, parsed))
    return details


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

    numeric_surfaces = surface_numeric_details(facsimile, skip_placeholder=True)
    if not numeric_surfaces:
        return False

    smallest_value = None
    for _, _, parsed in numeric_surfaces:
        value = parsed[1]
        if smallest_value is None or value < smallest_value:
            smallest_value = value

    if smallest_value is None or smallest_value > 1:
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

    updated = apply_image_name_mapping(path, root, facsimile)
    if remove_redundant_placeholder(root, facsimile):
        updated = True
    if normalise_surface_ids(root, facsimile):
        updated = True
    if synchronise_page_breaks(root, facsimile):
        updated = True

    surfaces = facsimile.findall(f"{TEI}surface")
    if not surfaces:
        if updated:
            ET.indent(root, space="  ")
            tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return False

    numeric_surfaces = surface_numeric_details(facsimile, skip_placeholder=True)

    min_page_value: Optional[int] = None
    for _, _, parsed in numeric_surfaces:
        value = parsed[1]
        if min_page_value is None or value < min_page_value:
            min_page_value = value

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

    if min_page_value is not None and min_page_value <= 1:
        if updated:
            ET.indent(root, space="  ")
            tei.tree.write(path, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return updated

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
                print(f"Updated lead page handling in {path}")
        except Exception as exc:  # noqa: BLE001 broad but logged
            print(f"Failed to update {path}: {exc}")
    print(f"Added placeholders in {updated} file(s)")


if __name__ == "__main__":
    main()
