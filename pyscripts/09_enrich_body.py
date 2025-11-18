#!/usr/bin/env python3

import json
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

TEI_NS = 'http://www.tei-c.org/ns/1.0'
XML_NS = 'http://www.w3.org/XML/1998/namespace'
NS = {'tei': TEI_NS, 'xml': XML_NS}

ET.register_namespace('', TEI_NS)
ET.register_namespace('xml', XML_NS)


def load_metadata(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def local_name(tag: str) -> str:
    return tag.split('}', 1)[-1] if '}' in tag else tag


def parse_folio(label: str):
    cleaned = (label or '').strip()
    match = re.match(r'^(\d+)([rv])$', cleaned.lower())
    if match:
        return int(match.group(1)), match.group(2)
    return None, None


def element_depth(root: ET.Element, target: ET.Element, level: int = 0) -> int | None:
    if root is target:
        return level
    for child in list(root):
        depth = element_depth(child, target, level + 1)
        if depth is not None:
            return depth
    return None


def indent_element(root: ET.Element, element: ET.Element, space: str = '    '):
    if not hasattr(ET, 'indent'):
        return
    level = element_depth(root, element) or 0
    ET.indent(element, space=space, level=level)


def classify_entry(categories: list[str]) -> dict[str, str | None]:
    normalized = [(c or '').strip() for c in categories]
    lowered = [c.lower() for c in normalized if c]
    has_end = any('ende' in c for c in lowered)
    has_sum = any('summe' in c for c in lowered)
    unit = 'section'
    span_type = 'section'
    if has_sum:
        unit = 'summary'
        span_type = 'summary'
    if has_end:
        unit = 'section-end'
        span_type = 'section-end'
    subtype = None
    if normalized and normalized[0]:
        subtype = normalized[0]
    elif len(normalized) > 1 and normalized[1]:
        subtype = normalized[1]
    label = next((c for c in normalized if c), None)
    return {'unit': unit, 'span_type': span_type, 'subtype': subtype, 'label': label}


def find_parent(root: ET.Element, target: ET.Element) -> ET.Element | None:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                return parent
    return None


def insert_after(root: ET.Element, reference: ET.Element, element: ET.Element) -> None:
    parent = find_parent(root, reference)
    if parent is None:
        raise ValueError('Could not determine parent for insertion')
    siblings = list(parent)
    if reference not in siblings:
        raise ValueError('Reference element missing from parent children')
    index = siblings.index(reference)
    parent.insert(index + 1, element)


def set_folio_attribute(ab: ET.Element, folio_label: str) -> bool:
    if not folio_label:
        return False
    existing = (ab.get('n') or '').strip()
    if not existing:
        ab.set('n', folio_label)
        return True
    tokens = existing.split()
    if folio_label not in tokens:
        tokens.append(folio_label)
        ab.set('n', ' '.join(tokens))
        return True
    return False


def folio_sort_key(label: str):
    number, side = parse_folio(label)
    if number is None:
        return (float('inf'), label)
    side_order = {'r': 0, 'v': 1}
    return (number, side_order.get(side or '', 2))


def image_sort_key(image_id: str):
    match = re.search(r'_(\d+)$', image_id)
    if match:
        return int(match.group(1))
    return float('inf')


def build_surface_lookup(root: ET.Element) -> dict:
    lookup: dict[str, list[str]] = {}
    for surface in root.findall('.//tei:surface', NS):
        facs_id = surface.get(f'{{{XML_NS}}}id')
        if not facs_id:
            continue
        urls: list[str] = []
        for graphic in surface.findall('tei:graphic', NS):
            url = graphic.get('url')
            if url:
                urls.append(url)
        lookup[facs_id] = urls
    return lookup


def build_page_index(body: ET.Element) -> list[dict]:
    pages: list[dict] = []
    current: dict | None = None
    for elem in body.iter():
        name = local_name(elem.tag)
        if name == 'pb':
            current = {
                'pb': elem,
                'abs': [],
                'xml_id': elem.get(f'{{{XML_NS}}}id'),
                'n': elem.get('n'),
                'facs': elem.get('facs'),
                'number': None,
                'last_marker': elem,
            }
            number = None
            xml_id = (current['xml_id'] or '').strip()
            if xml_id.startswith('img_'):
                try:
                    number = int(xml_id[4:])
                except ValueError:
                    number = None
            if number is None and current['n'] and current['n'].isdigit():
                number = int(current['n'])
            current['number'] = number
            pages.append(current)
        elif name == 'ab' and current is not None:
            current['abs'].append(elem)
    return pages


def find_page(pages: list[dict], surfaces: dict[str, list[str]], image_id: str) -> dict | None:
    suffix_match = re.search(r'_(\d+)$', image_id)
    suffix_number = int(suffix_match.group(1)) if suffix_match else None
    if suffix_number is not None:
        for page in pages:
            if page['number'] == suffix_number:
                return page
    image_filename = f"{image_id}.jpg"
    for page in pages:
        facs_ref = page['facs']
        if not facs_ref:
            continue
        facs_id = facs_ref.lstrip('#')
        urls = surfaces.get(facs_id, [])
        if image_filename in urls:
            return page
    return None


def choose_ab(candidates: list[ET.Element], folio_label: str, position: int, total: int):
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    _, side = parse_folio(folio_label)
    if side == 'v':
        for ab in candidates:
            if (ab.get('type') or '').endswith('page_1'):
                return ab
        return candidates[0]
    if side == 'r':
        for ab in candidates:
            if (ab.get('type') or '').endswith('page_2'):
                return ab
        return candidates[-1]
    if position == total - 1:
        return candidates[-1]
    return candidates[0]


def ensure_span_group(root: ET.Element) -> tuple[ET.Element, ET.Element]:
    standoff = root.find('.//tei:standOff', NS)
    if standoff is None:
        standoff = ET.SubElement(root, f'{{{TEI_NS}}}standOff')
    span_grp = standoff.find('tei:spanGrp', NS)
    if span_grp is None:
        span_grp = ET.SubElement(standoff, f'{{{TEI_NS}}}spanGrp')
    else:
        for child in list(span_grp):
            span_grp.remove(child)
    span_grp.text = None
    return standoff, span_grp


def build_span(
    span_id: str,
    target: str,
    categories: list,
    span_type: str | None = None,
    span_subtype: str | None = None,
) -> ET.Element:
    span = ET.Element(f'{{{TEI_NS}}}span')
    span.set(f'{{{XML_NS}}}id', span_id)
    if span_type:
        span.set('type', span_type)
    if span_subtype:
        span.set('subtype', span_subtype)
    span.set('target', target)
    if len(categories) >= 4 and categories[3].strip():
        measure = ET.SubElement(span, f'{{{TEI_NS}}}measure')
        measure.set('type', 'text')
        measure.text = categories[3].strip()
    payload = ' | '.join(filter(None, ((c or '').strip() for c in categories)))
    if payload:
        note = ET.SubElement(span, f'{{{TEI_NS}}}desc')
        note.text = payload
    return span


def attach_ana(element: ET.Element, span_id: str) -> bool:
    token = f'#{span_id}'
    existing = element.get('ana', '')
    if not existing:
        element.set('ana', token)
        return True
    tokens = existing.split()
    if token not in tokens:
        tokens.append(token)
        element.set('ana', ' '.join(tokens))
        return True
    return False


def remove_prior_milestones(root: ET.Element) -> int:
    removed = 0
    for milestone in list(root.findall('.//tei:milestone', NS)):
        xml_id = (milestone.get(f'{{{XML_NS}}}id') or '').strip()
        if not xml_id.startswith('ms'):
            continue
        ana_tokens = (milestone.get('ana') or '').split()
        if not any(token.startswith('#span') for token in ana_tokens):
            continue
        parent = find_parent(root, milestone)
        if parent is None:
            continue
        parent.remove(milestone)
        removed += 1
    return removed


def clear_ab_span_refs(body: ET.Element) -> int:
    cleared = 0
    for ab in body.findall('.//tei:ab', NS):
        ana = ab.get('ana')
        if not ana:
            continue
        tokens = ana.split()
        filtered = [token for token in tokens if not token.startswith('#span')]
        if len(filtered) == len(tokens):
            continue
        if filtered:
            ab.set('ana', ' '.join(filtered))
        else:
            ab.attrib.pop('ana', None)
        cleared += 1
    return cleared


def annotate_document(tei_path: Path, doc_metadata: dict) -> tuple[int, int, int, int]:
    tree = ET.parse(tei_path)
    root = tree.getroot()
    body = root.find('.//tei:body', NS)
    if body is None:
        print(f"⚠️  {tei_path.name}: body not found")
        return 0, 0, 0, 0
    surfaces = build_surface_lookup(root)
    pages = build_page_index(body)
    standoff, span_grp = ensure_span_group(root)
    remove_prior_milestones(root)
    clear_ab_span_refs(body)
    existing_ids = {
        elem.get(f'{{{XML_NS}}}id')
        for elem in root.findall('.//*[@xml:id]', NS)
        if elem.get(f'{{{XML_NS}}}id')
    }

    def next_identifier(prefix: str, counter: int) -> tuple[str, int]:
        current = counter
        while True:
            candidate = f"{prefix}{current:04d}"
            current += 1
            if candidate not in existing_ids:
                existing_ids.add(candidate)
                return candidate, current

    span_counter = 0
    milestone_counter = 0
    spans_created = 0
    milestones_inserted = 0
    ana_links = 0
    folio_updates = 0
    for image_id in sorted(doc_metadata.keys(), key=image_sort_key):
        folio_map = doc_metadata[image_id]
        if not folio_map:
            continue
        page = find_page(pages, surfaces, image_id)
        if page is None:
            print(f"  → {tei_path.name}: no page match for {image_id}")
            continue
        ab_candidates = page['abs']
        if not ab_candidates:
            print(f"  → {tei_path.name}: pb without ab for {image_id}")
            continue
        folio_items = sorted(folio_map.items(), key=lambda kv: folio_sort_key(kv[0]))
        for position, (folio_label, categories) in enumerate(folio_items):
            ab = choose_ab(ab_candidates, folio_label, position, len(folio_items))
            if ab is None:
                print(f"  → {tei_path.name}: no <ab> for {folio_label}")
                continue
            classification = classify_entry(categories)
            if set_folio_attribute(ab, folio_label):
                folio_updates += 1
            milestone_id, milestone_counter = next_identifier('ms', milestone_counter)
            milestone = ET.Element(f'{{{TEI_NS}}}milestone')
            milestone.set(f'{{{XML_NS}}}id', milestone_id)
            milestone.set('unit', classification['unit'] or 'section')
            milestone.set('n', folio_label)
            if classification['span_type']:
                milestone.set('type', classification['span_type'])
            if classification['subtype']:
                milestone.set('subtype', classification['subtype'])
            insert_after(body, page['last_marker'], milestone)
            page['last_marker'] = milestone
            milestones_inserted += 1
            span_id, span_counter = next_identifier('span', span_counter)
            span = build_span(
                span_id,
                f'#{milestone_id}',
                categories,
                span_type=classification['span_type'],
                span_subtype=classification['subtype'],
            )
            span_grp.append(span)
            if attach_ana(milestone, span_id):
                ana_links += 1
            if attach_ana(ab, span_id):
                ana_links += 1
            spans_created += 1
    indent_element(root, standoff)
    tree.write(tei_path, encoding='utf-8', xml_declaration=True)
    return spans_created, milestones_inserted, ana_links, folio_updates


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print('Usage: python enrich_body.py <metadata.json> <tei-directory>')
        return 1
    metadata_path = Path(argv[1])
    tei_dir = Path(argv[2])
    if not metadata_path.is_file():
        print(f"Metadata file not found: {metadata_path}")
        return 1
    if not tei_dir.is_dir():
        print(f"TEI directory not found: {tei_dir}")
        return 1
    metadata = load_metadata(metadata_path)
    tei_files = sorted(p for p in tei_dir.glob('*.xml') if p.is_file())
    if not tei_files:
        print(f"No TEI files found in {tei_dir}")
        return 0
    total_spans = 0
    total_milestones = 0
    total_ana_links = 0
    total_folio_updates = 0
    for tei_path in tei_files:
        doc_id = tei_path.stem
        doc_metadata = metadata.get(doc_id)
        if not doc_metadata:
            continue
        spans, milestones, ana_links, folio_updates = annotate_document(tei_path, doc_metadata)
        total_spans += spans
        total_milestones += milestones
        total_ana_links += ana_links
        total_folio_updates += folio_updates
    print(f"Spans created: {total_spans}")
    print(f"Milestones inserted: {total_milestones}")
    print(f"ana links updated: {total_ana_links}")
    print(f"ab folio @n updates: {total_folio_updates}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
