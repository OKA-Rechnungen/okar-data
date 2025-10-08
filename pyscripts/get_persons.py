#!/usr/bin/env python
import glob
import os
import pandas as pd
from sys import argv
from acdh_baserow_pyutils import BaseRowClient
from acdh_tei_pyutils.tei import TeiReader, ET

BASEROW_DB_ID = os.environ.get("BASEROW_DB_ID")
BASEROW_URL = os.environ.get("BASEROW_URL")
BASEROW_TOKEN = os.environ.get("BASEROW_TOKEN")
BASEROW_USER = os.environ.get("BASEROW_USER")
BASEROW_PW = os.environ.get("BASEROW_PW")
br_client = BaseRowClient(BASEROW_USER, BASEROW_PW, BASEROW_TOKEN, br_base_url=BASEROW_URL)
jwt_token = br_client.get_jwt_token()
os.makedirs("tmp", exist_ok=True)
files = br_client.dump_tables_as_json(BASEROW_DB_ID, folder_name="tmp")
source_directory = "./data/editions"
source_table = os.path.join("tmp", "Metadata.json")
schema_file = "tei_ms.xsd"
output_directory = "./data/indices"
input_file = "./data/indices/listperson.xml"
xml = "{http://www.w3.org/XML/1998/namespace}"
    
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



ok = extract_from_table(source_table)


doc = TeiReader(input_file)

listperson = doc.any_xpath(".//tei:text/tei:body/tei:listPerson")[0]
for j in ok:
    entry = ok[j]
    print(entry["surname1"])
    pid = entry["surname1"].split()[0]
    person = ET.SubElement(listperson, "person", attrib={f"{xml}id": pid})
    persname = ET.SubElement(person, "persName")
    ET.SubElement(persname, "forename").text = entry["forename"]
    ET.SubElement(persname, "surname").text = " ".join([entry["surname1"], entry["surname2"]])
    for role in entry["role"]:
        ET.SubElement(person, "occupation").text = role
    if len(entry["id"]) > 0:
        ET.SubElement(person, "idno", attrib={"type": "URI", "subtype": "WienGeschichteWiki"}).text = entry["id"]
        
        
with open(input_file, "w") as f:
    f.write(ET.tostring(doc.tree, pretty_print=True, encoding="unicode"))