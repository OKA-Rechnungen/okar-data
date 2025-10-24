#!/usr/bin/env python
# Executable file that calls library maketei
import glob
import os
import pandas as pd
from acdh_baserow_pyutils import BaseRowClient
from acdh_tei_pyutils.tei import TeiReader, ET
from datetime import date

today = date.today().isoformat()
nsmap = {
    "tei": "http://www.tei-c.org/ns/1.0",
    "mets": "http://www.loc.gov/METS/",
    "mods": "http://www.loc.gov/mods/v3",
    "dv": "http://dfg-viewer.de/",
    "default": "http://www.tei-c.org/ns/1.0"
}
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
source_directory = "./data/editions3"
source_table = os.path.join("tmp", "Metadata.json")
schema_file = "tei_ms.xsd"
output_directory = "./data/indices"


def extract_from_table(table, ttl):
    # Check if the filename exists in the table
    matching_rows = table.loc[table["Filename"] == ttl]
    if matching_rows.empty:
        print(f"Warning: Filename '{ttl}' not found in metadata table")
        return None

    row = matching_rows.iloc[0]
    idno = row["NonLinkedIdentifier"].strip()
    title = row["Title"].strip()
    altTitle = row["AlternativeTitle"].strip()
    startDate = row["CoverageStartDate"].strip()
    endDate = row["CoverageEndDate"].strip()
    pages = row["Pages"].strip()
    desc = row["Description"].strip()
    desc2 = row["Description II"].strip()
    toc = row["TableOfContents"].strip()
    note = row["Note"].strip()
    oberkaemmerer = {}
    for i in ["1", "2", "3", "4", "5"]:
        if row[f"Creator{i}/Title"]:
            surname = " ".join((row[f"Creator{i}/LastName"].strip(), row[f"Creator{i}/LastName2"].strip())).strip()
            oberkaemmerer[row[f"Creator{i}/PersonalName"]] = {"idno": row[f"Creator{i}/Identifier"],
                                                              "title": row[f"Creator{i}/Title"].strip(),
                                                              "forename": row[f"Creator{i}/FirstName"].strip(),
                                                              "surname": surname,
                                                              "role": row[f"Creator{i}/PersonalName"].strip(),
                                                              "note": row[f"Creator{i}/Note"].strip(),
                                                              "xmlid": surname.split()[0].strip().lower()
                                                              }
    return {"idno": idno, "title": title, "altTitle": altTitle, "startDate": startDate,
            "endDate": endDate, "pages": pages, "desc": desc, "desc2": desc2, "toc": toc,
            "note": note, "oberkaemmerer": oberkaemmerer}


def clean_formatting(element):
    """Clean up formatting using lxml's built-in indentation"""
    # Remove existing text/tail to clean up
    for elem in element.iter():
        if elem.text and elem.text.strip() == '':
            elem.text = None
        if elem.tail and elem.tail.strip() == '':
            elem.tail = None
    # Use lxml's indent function for proper formatting
    ET.indent(element, space="  ")


def populate_people(listperson, people):
    resps = []
    for j in people:
        entry = people[j]
        pid = entry["xmlid"]
        person = ET.SubElement(listperson, "person", attrib={f"{xml}id": pid, "role": j})
        persname = ET.SubElement(person, "persName", attrib={"type": "norm"})
        ET.SubElement(persname, "forename").text = entry["forename"]
        ET.SubElement(persname, "surname").text = entry["surname"]
        ET.SubElement(person, "persName", attrib={"type": "orig"}).text = entry["title"]
        ET.SubElement(person, "occupation").text = j
        if len(entry["idno"]) > 0:
            ET.SubElement(person, "idno", attrib={"type": "URI", "subtype": "WienGeschichteWiki"}).text = entry["idno"]
        if len(entry["note"]) > 0:
            ET.SubElement(person, "note").text = entry["note"]
        respstmt = ET.Element("respStmt")
        ET.SubElement(respstmt, "resp").text = j
        ET.SubElement(respstmt, "persName", attrib={"ref": f"#{pid}", "role": j}).text = entry["title"]
        resps.append(respstmt)
    return resps


def populate_others(doc, values):
    doc.xpath(".//tei:fileDesc/tei:titleStmt/tei:title[@level='a' and @type='main']",
              namespaces=nsmap)[0].text = values["title"]

    # Find msDesc and add origDate and TOC
    mscontents = doc.xpath(".//tei:fileDesc/tei:sourceDesc/tei:msDesc/tei:msContents", namespaces=nsmap)[0]
    p_elem = ET.SubElement(mscontents, "p")
    if not values["endDate"]:
        ET.SubElement(p_elem, "origDate", attrib={"when": values["startDate"]})
    else:
        ET.SubElement(p_elem, "origDate", attrib={"from": values["startDate"], "to": values["endDate"]})
    p_elem = ET.SubElement(mscontents, "p").text = values["toc"]
    doc.xpath(".//tei:msDesc/tei:physDesc/tei:objectDesc/tei:supportDesc/tei:extent",
              namespaces=nsmap)[0].text = values["pages"]
    p_elem = doc.xpath(".//tei:msDesc/tei:physDesc/tei:accMat", namespaces=nsmap)[0]
    if values["desc2"]:
        ET.SubElement(p_elem, "p").text = values["desc2"]
    p_elem = doc.xpath(".//tei:fileDesc/tei:notesStmt", namespaces=nsmap)[0]
    if values["note"]:
        ET.SubElement(p_elem, "note").text = values["note"]
    doc.xpath(".//tei:fileDesc/tei:sourceDesc/tei:msDesc/tei:msIdentifier/tei:idno[@type='shelfmark']",
              namespaces=nsmap)[0] = values["idno"]

def hodie(doc):
    dates = doc.xpath(".//tei:date[@when='2024-08-19']", namespaces=nsmap)
    for date in dates:
        date.set("when", today)
        date.text = today

df = pd.read_json(source_table, orient="index").fillna("")
for input_file in glob.glob(os.path.join(source_directory, "*.xml")):
    print(f"Parsing {input_file}")
    teifile = TeiReader(input_file)
    header = teifile.any_xpath(".//tei:teiHeader")[0]
    hodie(header)
    filename = teifile.any_xpath(".//tei:fileDesc/tei:titleStmt/tei:title[@type='desc' and @level='a']")[0].text

    # Find and replace the existing teiHeader with the template teiHeader
    existing_header = teifile.any_xpath(".//tei:teiHeader")[0]
    root = teifile.tree.getroot()
    print(f"Processing filename: {filename}")
    values = extract_from_table(df, filename)

    if values is None:
        print(f"Skipping {input_file} - no matching metadata found")
        continue

    listperson = teifile.any_xpath(".//tei:standOff/tei:listPerson")[0]
    resp_list = populate_people(listperson, values["oberkaemmerer"])

    # Populate other metadata fields
    populate_others(header, values)

    # Add respStmt elements to titleStmt after the last existing respStmt
    titleStmt = teifile.any_xpath(".//tei:fileDesc/tei:titleStmt")[0]
    existing_respStmts = titleStmt.xpath(".//tei:respStmt", namespaces={"tei": "http://www.tei-c.org/ns/1.0"})

    if existing_respStmts:
        # Insert after the last respStmt
        last_respStmt = existing_respStmts[-1]
        parent = last_respStmt.getparent()
        insert_index = list(parent).index(last_respStmt) + 1

        # Insert each respStmt element from the list
        for i, resp in enumerate(resp_list):
            parent.insert(insert_index + i, resp)
    else:
        # If no respStmt exists, append each one to titleStmt
        for resp in resp_list:
            titleStmt.append(resp)

    # Clean up formatting for the entire document
    clean_formatting(teifile.tree.getroot())

    # Save the modified file
    teifile.tree.write(input_file, encoding="utf-8", xml_declaration=True, pretty_print=True)
    print(f"\t\tUpdated teiHeader in {input_file}")

print("Completed processing files. All teiHeaders have been replaced with the template.")
