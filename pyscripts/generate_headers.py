#!/usr/bin/env python
# Executable file that calls library maketei
import glob
import os
import pandas as pd
from sys import argv
from acdh_baserow_pyutils import BaseRowClient
from acdh_tei_pyutils.tei import TeiReader, ET

xml = "{http://www.w3.org/XML/1998/namespace}"
BASEROW_DB_ID = os.environ.get("BASEROW_DB_ID")
BASEROW_URL = os.environ.get("BASEROW_URL")
BASEROW_TOKEN = os.environ.get("BASEROW_TOKEN")
BASEROW_USER = os.environ.get("BASEROW_USER")
BASEROW_PW = os.environ.get("BASEROW_PW")
br_client = BaseRowClient(BASEROW_USER, BASEROW_PW, BASEROW_TOKEN, br_base_url=BASEROW_URL)
jwt_token = br_client.get_jwt_token()
os.makedirs("tmp", exist_ok=True)
files = br_client.dump_tables_as_json(BASEROW_DB_ID, folder_name="tmp")
source_directory = "./data/editions2"
source_table = os.path.join("tmp", "Metadata.json")
schema_file = "tei_ms.xsd"
output_directory = "./data/indices"
template = "./data/constants/template.xml"

i = 1


def get_info(doc):
    ttltitle = doc.any_xpath(".//tei:fileDesc/tei:titleStmt/tei:title")[0].text
    srctitle = doc.any_xpath(".//tei:fileDesc/tei:sourceDesc/tei:bibl/tei:title")[0].text
    srcidno = doc.any_xpath(".//tei:fileDesc/tei:sourceDesc/tei:bibl/tei:idno")[0].text
    return (ttltitle, srctitle, srcidno)


templatetei = TeiReader(template)

teiheader = templatetei.any_xpath(".//tei:teiHeader")[0]
standoff = templatetei.any_xpath(".//tei:standOff")[0]


for input_file in glob.glob(os.path.join(source_directory, "*.xml")):
    print(f"{i}\t\tParsing {input_file}")
    i += 1
    teifile = TeiReader(input_file)
    origtitle = get_info(teifile)
    
    # Find and replace the existing teiHeader with the template teiHeader
    existing_header = teifile.any_xpath(".//tei:teiHeader")[0]
    root = teifile.tree.getroot()
    
    # Remove the existing header
    root.remove(existing_header)
    
    # Insert the new header from template at the beginning
    root.insert(0, teiheader)
    
    # Add standOff after teiHeader (check if it doesn't already exist)
    existing_standoff = teifile.any_xpath(".//tei:standOff")
    if not existing_standoff:
        root.insert(1, standoff)
        print(f"\t\tAdded standOff section to {input_file}")
    
    
    def extract_from_table(table):
    df = pd.read_json(table, orient="index").fillna("")
    oberkaemmerer = {}
    for idx, row in df.iterrows():
        for i in ["1", "2", "3", "4", "5"]:
            identifier = row[f"Creator{i}/Identifier"]
            title = row[f"Creator{i}/Title"]
            forename = row[f"Creator{i}/FirstName"]
            surname1 = row[f"Creator{i}/LastName"]
            surname2 = row[f"Creator{i}/LastName2"]
            role = row[f"Creator{i}/PersonalName"]
            note =  row[f"Creator{i}/PersonalName"]
            if len(identifier.strip()) > 0:
                okey = identifier
            elif surname1:
                okey = surname1.split()[0]
            else:
                okey = False
            if okey:
                if okey not in oberkaemmerer:
                    oberkaemmerer[okey] = {"id": identifier,
                                           "title": [title],
                                           "forename": forename,
                                           "surname1": surname1,
                                           "surname2": surname2,
                                           "role": [role],
                                           "note": [note],
                                        }
                else:
                    if title not in oberkaemmerer[okey]["title"]:
                        oberkaemmerer[okey]["title"].append(title)
                    if role not in oberkaemmerer[okey]["role"]:
                        oberkaemmerer[okey]["role"].append(role)
                    if note not in oberkaemmerer[okey]["note"]:
                        oberkaemmerer[okey]["note"].append(note)          
    return oberkaemmerer
    
    
    
    # Save the modified file
    teifile.tree.write(input_file, encoding="utf-8", xml_declaration=True, pretty_print=True)
    print(f"\t\tUpdated teiHeader in {input_file}")

print(f"Completed processing {i-1} files. All teiHeaders have been replaced with the template.")

