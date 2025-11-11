#!/usr/bin/env python3
"""Utility helpers to select Transkribus documents we need to download."""
from __future__ import annotations

import re
from typing import Iterable, List

_TITLE_EXTRACTION_PATTERN = re.compile(r"^\d{4}_(WSTLA-OKA-.*)$")
_TARGET_FILENAME_PATTERN = re.compile(r"^WSTLA-OKA-B\d+-\d+-\d{3}-\d+$")


def _normalise_title(raw_title: str | None) -> str:
    """Return the expected TEI filename derived from the Transkribus doc title."""
    if not raw_title:
        return ""
    condensed = raw_title.replace(" ", "").strip()
    if not condensed:
        return ""
    match = _TITLE_EXTRACTION_PATTERN.match(condensed)
    if match:
        return match.group(1)
    if condensed.startswith("WSTLA-OKA-"):
        return condensed
    return ""


def _has_transcription(metadata: dict | None, pages: Iterable[dict]) -> bool:
    """Determine whether a document contains any transcription data."""
    if metadata:
        for key in ("nrOfTranscribedLines", "nrOfTranscribedPages"):
            value = metadata.get(key)
            if isinstance(value, str) and value.isdigit():
                value = int(value)
            if isinstance(value, int) and value > 0:
                return True
    for page in pages or []:
        transcripts = page.get("transcripts")
        if transcripts:
            if isinstance(transcripts, list) and transcripts:
                return True
            if isinstance(transcripts, dict) and transcripts:
                return True
    return False


def filter_doc_ids_with_transcriptions(client, col_id: str | int) -> List[str]:
    """Return doc IDs whose TEI filenames match the target pattern and contain text."""
    try:
        documents = client.list_docs(col_id)
    except Exception as exc:  # pragma: no cover - network errors
        raise RuntimeError(f"Failed to list documents for collection {col_id}: {exc}") from exc

    selected: List[str] = []
    skipped_no_transcription: list[str] = []
    skipped_bad_title: list[str] = []

    for doc in documents:
        doc_id = doc.get("docId")
        if doc_id is None:
            continue
        try:
            overview = client.get_doc_overview_md(doc_id, col_id)
        except Exception:  # pragma: no cover - network errors
            continue
        if not overview or "trp_return" not in overview:
            continue
        payload = overview["trp_return"]
        metadata = payload.get("md", {}) or {}
        target_name = _normalise_title(metadata.get("title"))
        if not target_name or not _TARGET_FILENAME_PATTERN.fullmatch(target_name):
            skipped_bad_title.append(str(doc_id))
            continue
        pages = payload.get("pageList", {}).get("pages", [])
        if not _has_transcription(metadata, pages):
            skipped_no_transcription.append(str(doc_id))
            continue
        selected.append(str(doc_id))

    print(
        f"Collection {col_id}: {len(selected)} eligible, "
        f"{len(skipped_no_transcription)} skipped without transcription, "
        f"{len(skipped_bad_title)} skipped due to title pattern"
    )
    return selected
