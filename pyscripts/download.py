#!/usr/bin/env python
import os
from pathlib import Path
from transkribus_utils.transkribus_utils import ACDHTranskribusUtils
import sys

user = os.environ.get("TR_USER")
pw = os.environ.get("TR_PW")
XSLT = "https://csae8092.github.io/page2tei/page2tei-0.xsl"
METS_DIR = Path("./data/mets")

os.makedirs(METS_DIR, exist_ok=True)
transkribus_client = ACDHTranskribusUtils(
    user=user, password=pw, transkribus_base_url="https://transkribus.eu/TrpServer/rest"
)


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
        pages = transkribus_client.get_doc_overview_md(docId, col_id)
        pages = pages["trp_return"]["pageList"]["pages"]
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
    if gt:
        cols = get_gt(col_id)
        print("Subset: ", len(cols))
        mpr_docs = transkribus_client.collection_to_mets(col_id, file_path=METS_DIR, filter_by_doc_ids=cols)
    else:
        mpr_docs = transkribus_client.collection_to_mets(col_id, file_path=METS_DIR)
    print(f"{METS_DIR}/{col_id}*.xml")
