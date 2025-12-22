#!/usr/bin/env python
import argparse
import os
import sys
from pathlib import Path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download METS for Transkribus collections listed in col_ids.txt. "
            "By default, applies project filters (e.g. requires transcriptions)."
        )
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Download all documents in each collection (bypasses project filters and ignores "
            "TRANSKRIBUS_DOC_IDS and --gt)."
        ),
    )
    parser.add_argument(
        "--gt",
        action="store_true",
        help="Restrict to documents that contain at least one GT page.",
    )
    parser.add_argument(
        "legacy",
        nargs="?",
        help="Legacy positional arg (kept for backwards compatibility). Use --gt instead.",
    )

    args = parser.parse_args(argv)
    # Backwards compatibility: historically, *any* positional arg enabled GT mode.
    if args.legacy is not None:
        args.gt = True
    return args


def get_gt_doc_ids(transkribus_client, col_id: str) -> list[str]:
    gt_doc_ids: list[str] = []
    docs = transkribus_client.list_docs(col_id)
    print("Total: ", len(docs))
    for doc in docs:
        doc_id = str(doc["docId"])
        overview = transkribus_client.get_doc_overview_md(doc_id, col_id)
        if not overview or "trp_return" not in overview:
            continue
        pages = overview["trp_return"].get("pageList", {}).get("pages", [])
        if any(page.get("ctStatus") == "GT" for page in pages):
            gt_doc_ids.append(doc_id)
        else:
            print("Failed: ", doc_id)
    print("Partial: ", len(gt_doc_ids))
    return gt_doc_ids


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    # Defer these imports so `--help` works even if deps
    # aren't installed in the current environment.
    from transkribus_utils.transkribus_utils import ACDHTranskribusUtils
    from transkribus_filters import filter_doc_ids_with_transcriptions

    user = os.environ.get("TR_USER")
    pw = os.environ.get("TR_PW")
    mets_dir = Path("./data/mets")
    os.makedirs(mets_dir, exist_ok=True)

    transkribus_client = ACDHTranskribusUtils(
        user=user, password=pw, transkribus_base_url="https://transkribus.eu/TrpServer/rest"
    )

    doc_id_subset = os.environ.get("TRANSKRIBUS_DOC_IDS", "")
    if args.all:
        # --all means truly "all" regardless of other constraints.
        target_doc_ids: list[str] = []
    elif doc_id_subset:
        target_doc_ids = [item.strip() for item in doc_id_subset.split(",") if item.strip()]
    else:
        target_doc_ids = []

    with open("col_ids.txt", "r") as f:
        lines = f.readlines()
    print(lines)

    for y in lines:
        col_id = y.strip()
        if not col_id:
            continue
        print(f"processing collection: {col_id}")

        if args.all:
            docs = transkribus_client.list_docs(col_id)
            eligible_doc_ids = [str(doc["docId"]) for doc in docs]
        else:
            eligible_doc_ids = filter_doc_ids_with_transcriptions(transkribus_client, col_id)

        if (not args.all) and target_doc_ids:
            print(f"Requested doc IDs: {', '.join(target_doc_ids)}")
            eligible_doc_ids = [doc_id for doc_id in eligible_doc_ids if doc_id in target_doc_ids]

        if (not args.all) and args.gt:
            gt_doc_ids = set(get_gt_doc_ids(transkribus_client, col_id))
            print("Subset: ", len(gt_doc_ids))
            eligible_doc_ids = [doc_id for doc_id in eligible_doc_ids if doc_id in gt_doc_ids]

        if not eligible_doc_ids:
            print(f"No eligible documents found for collection {col_id}, skipping download")
            continue

        transkribus_client.collection_to_mets(
            col_id,
            file_path=str(mets_dir),
            filter_by_doc_ids=eligible_doc_ids,
        )
        print(f"{mets_dir}/{col_id}*.xml")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
