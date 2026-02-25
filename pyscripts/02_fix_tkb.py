#!/usr/bin/env python3
"""Normalise Transkribus image name exports.

Some image name lists use underscores between all segments (e.g.
``WSTLA_OKA_B1_1_095_1_00001.jpg``) although downstream code expects the
hyphenated base form (``WSTLA-OKA-B1-1-095-1_00001.jpg``). This script rewrites
all ``*_image_name.xml`` files under ``data/mets`` so the prefix uses hyphens
while the page counter keeps the trailing underscore.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import xml.etree.ElementTree as ET


METS_DIR = Path(os.environ.get("METS_DIR", "./data/mets")).resolve()


def normalise_image_name(value: str) -> str:
	"""Convert ``WSTLA_*`` style names to the hyphenated form expected later."""

	text = value.strip()
	if not text.startswith("WSTLA_"):
		return text

	stem, suffix = os.path.splitext(text)
	segments = stem.split("_")
	if len(segments) <= 1:
		return text

	prefix_segments = segments[:-1]
	counter = segments[-1]

	# Pad the numeric counter to 5 digits (e.g. 56 -> 00056)
	if counter.isdigit() and len(counter) < 5:
		counter = counter.zfill(5)

	prefix = "-".join(prefix_segments)
	return f"{prefix}_{counter}{suffix}"


def process_image_name_file(path: Path) -> bool:
	"""Rewrite *path* in place if any item benefits from normalisation."""

	try:
		tree = ET.parse(path)
	except ET.ParseError as exc:  # pragma: no cover - defensive guard
		print(f"Failed to parse {path}: {exc}", file=sys.stderr)
		return False

	root = tree.getroot()
	changed = False

	for item in root.findall(".//item"):
		if item.text is None:
			continue
		replacement = normalise_image_name(item.text)
		if replacement != item.text:
			item.text = replacement
			changed = True

	if changed:
		# Serialise without XML declaration to stay close to the source format.
		serialised = ET.tostring(root, encoding="unicode")
		path.write_text(serialised, encoding="utf-8")

	return changed


def main() -> int:
	if not METS_DIR.exists():
		print(f"METS directory {METS_DIR} not found; nothing to fix.")
		return 0

	files = sorted(METS_DIR.glob("**/*_image_name.xml"))
	if not files:
		print("No *_image_name.xml files found; nothing to do.")
		return 0

	total = 0
	updated = 0
	for file_path in files:
		total += 1
		if process_image_name_file(file_path):
			updated += 1
			print(f"Normalised image names in {file_path}")

	print(f"Checked {total} image name files; updated {updated}.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
