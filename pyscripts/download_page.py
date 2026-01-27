#!/usr/bin/env python
"""Download PAGE XML files from METS files to data/pages."""
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

METS_DIR = Path("./data/mets")
PAGES_DIR = Path("./data/pages")

NAMESPACES = {
    "mets": "http://www.loc.gov/METS/",
    "xlink": "http://www.w3.org/1999/xlink",
}

# Cache for doc_id -> folder_name mapping
_doc_title_cache: dict[str, str] = {}


def get_folder_name_from_mets(doc_id: str) -> str | None:
    """Look up the title from the METS file and extract folder name."""
    if doc_id in _doc_title_cache:
        return _doc_title_cache[doc_id]

    # Find the METS file for this doc_id
    mets_file = METS_DIR / "258178" / f"{doc_id}_mets.xml"
    if not mets_file.exists():
        # Try to find it in any subfolder
        mets_files = list(METS_DIR.glob(f"**/{doc_id}_mets.xml"))
        if not mets_files:
            return None
        mets_file = mets_files[0]

    tree = ET.parse(mets_file)
    root = tree.getroot()

    # Find trpDocMetadata/title (no namespace)
    title_elem = root.find(".//trpDocMetadata/title")
    if title_elem is None or not title_elem.text:
        return None

    title = title_elem.text
    # Extract folder name from title like "1561_WSTLA-OKA-B1-1-094-1-Ueberschriften-GT-1"
    # We want: WSTLA-OKA-B1-1-094-1
    match = re.search(r"(WSTLA-OKA-B1-1-\d{3}-\d)", title)
    if match:
        folder_name = match.group(1)
    else:
        # Fallback: use the title as-is
        folder_name = title

    _doc_title_cache[doc_id] = folder_name
    return folder_name


def download_page_xml_from_mets(mets_file: Path) -> None:
    """Extract PAGEXML URLs from a METS file and download them."""
    tree = ET.parse(mets_file)
    root = tree.getroot()

    # Find all PAGEXML file entries
    pagexml_files = root.findall(".//mets:fileGrp[@ID='PAGEXML']/mets:file", NAMESPACES)

    for pagexml in pagexml_files:
        seq = pagexml.get("SEQ")
        flocat = pagexml.find("mets:FLocat", NAMESPACES)
        if flocat is None:
            continue

        url = flocat.get(f"{{{NAMESPACES['xlink']}}}href")
        if not url:
            continue

        # Download the PAGE XML content first
        response = requests.get(url)
        response.raise_for_status()
        content = response.content

        # Parse the PAGE XML to get the docId from TranskribusMetadata
        page_tree = ET.fromstring(content)

        # Find TranskribusMetadata element and get docId
        transkribus_meta = page_tree.find(".//{*}TranskribusMetadata")
        if transkribus_meta is None:
            print(f"  Warning: No TranskribusMetadata found, skipping")
            continue

        doc_id = transkribus_meta.get("docId")
        if not doc_id:
            print(f"  Warning: No docId in TranskribusMetadata, skipping")
            continue

        # Look up the folder name from the METS file title
        folder_name = get_folder_name_from_mets(doc_id)
        if not folder_name:
            print(f"  Warning: Could not find folder name for docId {doc_id}, skipping")
            continue

        # Create output filename: folder_name + page number
        page_num = seq.zfill(5) if seq else "00001"
        output_filename = f"{folder_name}_{page_num}.xml"

        doc_dir = PAGES_DIR / folder_name
        doc_dir.mkdir(parents=True, exist_ok=True)

        output_file = doc_dir / output_filename
        if output_file.exists():
            print(f"  Skipping {output_file.name} (already exists)")
            continue

        print(f"  Saving -> {folder_name}/{output_filename}")
        output_file.write_bytes(content)


def main() -> int:
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Find all METS files
    mets_files = list(METS_DIR.glob("**/*_mets.xml"))
    print(f"Found {len(mets_files)} METS files")

    for mets_file in sorted(mets_files):
        print(f"Processing {mets_file.name}")
        download_page_xml_from_mets(mets_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
