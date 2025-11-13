#!/usr/bin/env python
import os
from pathlib import Path
from transkribus_utils.transkribus_utils import ACDHTranskribusUtils
from transkribus_filters import filter_doc_ids_with_transcriptions
import sys

user = os.environ.get("TR_USER")
pw = os.environ.get("TR_PW")
XSLT = "https://csae8092.github.io/page2tei/page2tei-0.xsl"
METS_DIR = Path("./data/mets")

os.makedirs(METS_DIR, exist_ok=True)
transkribus_client = ACDHTranskribusUtils(
    user=user, password=pw, transkribus_base_url="https://transkribus.eu/TrpServer/rest"
)

doc_id_subset = os.environ.get("TRANSKRIBUS_DOC_IDS", "")
#doc_id_subset = "6981834,10651984,7714156"
if doc_id_subset:
    TARGET_DOC_IDS = [item.strip() for item in doc_id_subset.split(",") if item.strip()]
else:
    TARGET_DOC_IDS = []


if len(sys.argv) > 1:
    gt = True
else:
    gt = False


def get_gt(col):
    gt_docs = []
    docs = transkribus_client.list_docs(col)
    print("Total: ", len(docs))
    for doc in docs:
        docId = doc["docId"]
        overview = transkribus_client.get_doc_overview_md(docId, col)
        if not overview or "trp_return" not in overview:
            continue
        pages = overview["trp_return"].get("pageList", {}).get("pages", [])
        if any(i["ctStatus"] == "GT" for i in pages):
            gt_docs.append(docId)
        else:
            print("Failed: ", docId)
    print("Partial: ", len(gt_docs))
    return gt_docs


with open("col_ids.txt", "r") as f:
    lines = f.readlines()
print(lines)

for y in lines:
    col_id = y.strip()
    print(f"processing collection: {col_id}")
    eligible_doc_ids = filter_doc_ids_with_transcriptions(transkribus_client, col_id)
    if TARGET_DOC_IDS:
        eligible_doc_ids = [doc_id for doc_id in eligible_doc_ids if doc_id in TARGET_DOC_IDS]

    if gt:
        cols = get_gt(col_id)
        print("Subset: ", len(cols))
        eligible_doc_ids = [doc_id for doc_id in eligible_doc_ids if doc_id in {str(x) for x in cols}]
    else:
        if TARGET_DOC_IDS:
            print(f"Requested doc IDs: {', '.join(TARGET_DOC_IDS)}")
    if not eligible_doc_ids:
        print(f"No eligible documents found for collection {col_id}, skipping download")
        continue

    mpr_docs = transkribus_client.collection_to_mets(
        col_id,
        file_path=str(METS_DIR),
        filter_by_doc_ids=eligible_doc_ids,
    )
    print(f"{METS_DIR}/{col_id}*.xml")
