#!/usr/bin/env python
# Executable file that calls library maketei
import glob
import os
import re
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
tei = "{http://www.tei-c.org/ns/1.0}"
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


def slugify_xmlid(*parts):
    """Create a stable xml:id-friendly token from the provided strings."""
    base = "-".join(filter(None, (re.sub(r"[^0-9A-Za-z]+", "-", (part or "").strip()) for part in parts)))
    base = base.strip("-").lower()
    return base or "person"


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
        title = row[f"Creator{i}/Title"].strip()
        if title:
            surname = " ".join((row[f"Creator{i}/LastName"].strip(), row[f"Creator{i}/LastName2"].strip())).strip()
            forename = row[f"Creator{i}/FirstName"].strip()
            role_name = row[f"Creator{i}/PersonalName"].strip() or title
            xmlid_candidate = slugify_xmlid(surname, forename, title)
            oberkaemmerer[role_name] = {
                "idno": row[f"Creator{i}/Identifier"].strip(),
                "title": title,
                "forename": forename,
                "surname": surname,
                "role": role_name,
                "note": row[f"Creator{i}/Note"].strip(),
                "xmlid": xmlid_candidate,
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


def ensure_listperson(root):
    standoff = root.xpath(".//tei:standOff", namespaces=nsmap)
    if standoff:
        stand_off_node = standoff[0]
    else:
        stand_off_node = ET.SubElement(root, f"{tei}standOff")
    list_person = stand_off_node.find(f"{tei}listPerson")
    if list_person is None:
        list_person = ET.SubElement(stand_off_node, f"{tei}listPerson")
    return list_person


def populate_people(listperson, people):
    resps = []
    if not people:
        return resps
    previous_ids = {}
    protected_ids = set()
    for person in listperson.xpath("./tei:person", namespaces=nsmap):
        pid = person.get(f"{xml}id")
        role = (person.get("role") or "").strip()
        if role and pid:
            previous_ids[role] = pid
            protected_ids.add(pid)
        elif pid:
            protected_ids.add(pid)
        listperson.remove(person)
    assigned_ids = set()
    for role, entry in people.items():
        base_id = entry.get("xmlid") or slugify_xmlid(entry.get("surname"), entry.get("forename"), entry.get("title"))
        preferred_id = previous_ids.get(role)
        candidate = preferred_id or base_id
        counter = 1
        while candidate in assigned_ids or (candidate in protected_ids and candidate != preferred_id):
            counter += 1
            candidate = f"{base_id}-{counter}"
        assigned_ids.add(candidate)
        person = ET.SubElement(listperson, f"{tei}person", attrib={f"{xml}id": candidate, "role": role})
        persname_norm = ET.SubElement(person, f"{tei}persName", attrib={"type": "norm"})
        if entry["forename"]:
            ET.SubElement(persname_norm, f"{tei}forename").text = entry["forename"]
        if entry["surname"]:
            ET.SubElement(persname_norm, f"{tei}surname").text = entry["surname"]
        ET.SubElement(person, f"{tei}persName", attrib={"type": "orig"}).text = entry["title"]
        ET.SubElement(person, f"{tei}occupation").text = role
        if entry["idno"]:
            ET.SubElement(person, f"{tei}idno", attrib={"type": "URI", "subtype": "WienGeschichteWiki"}).text = entry["idno"]
        if entry["note"]:
            ET.SubElement(person, f"{tei}note").text = entry["note"]
        respstmt = ET.Element(f"{tei}respStmt")
        ET.SubElement(respstmt, f"{tei}resp").text = role
        ET.SubElement(respstmt, f"{tei}persName", attrib={"ref": f"#{candidate}", "role": role}).text = entry["title"]
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
    shelfmark = doc.xpath(".//tei:fileDesc/tei:sourceDesc/tei:msDesc/tei:msIdentifier/tei:idno[@type='shelfmark']",
                          namespaces=nsmap)
    if shelfmark:
        shelfmark[0].text = values["idno"]

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

    listperson = ensure_listperson(root)
    resp_list = populate_people(listperson, values["oberkaemmerer"])

    # Populate other metadata fields
    populate_others(header, values)

    # Add respStmt elements to titleStmt after the last existing respStmt
    titleStmt = teifile.any_xpath(".//tei:fileDesc/tei:titleStmt")[0]
    roles_to_replace = set(values["oberkaemmerer"].keys())
    existing_respStmts = titleStmt.xpath("./tei:respStmt", namespaces=nsmap)
    for resp_stmt in list(existing_respStmts):
        resp_role = (resp_stmt.xpath("./tei:resp/text()", namespaces=nsmap) or [""])[0].strip()
        pers_roles = { (node.get("role") or "").strip() for node in resp_stmt.xpath(".//tei:persName", namespaces=nsmap)}
        if resp_role in roles_to_replace or any(role in roles_to_replace for role in pers_roles):
            parent = resp_stmt.getparent()
            if parent is not None:
                parent.remove(resp_stmt)

    existing_respStmts = titleStmt.xpath("./tei:respStmt", namespaces=nsmap)
    if existing_respStmts:
        last_respStmt = existing_respStmts[-1]
        parent = last_respStmt.getparent()
        insert_index = list(parent).index(last_respStmt) + 1
        for offset, resp in enumerate(resp_list):
            parent.insert(insert_index + offset, resp)
    else:
        for resp in resp_list:
            titleStmt.append(resp)

    # Clean up formatting for the entire document
    clean_formatting(teifile.tree.getroot())

    # Save the modified file
    teifile.tree.write(input_file, encoding="utf-8", xml_declaration=True, pretty_print=True)
    print(f"\t\tUpdated teiHeader in {input_file}")

print("Completed processing files. All teiHeaders have been replaced with the template.")
