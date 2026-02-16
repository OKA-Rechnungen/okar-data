#!/usr/bin/env python
# Executable file that calls library maketei
import glob
import os
import re
from acdh_tei_pyutils.tei import TeiReader, ET
import copy


nsmap = {
    "tei": "http://www.tei-c.org/ns/1.0",
    "mets": "http://www.loc.gov/METS/",
    "mods": "http://www.loc.gov/mods/v3",
    "dv": "http://dfg-viewer.de/",
    "default": "http://www.tei-c.org/ns/1.0",
}
xml = "{http://www.w3.org/XML/1998/namespace}"
os.makedirs("tmp", exist_ok=True)
source_directory = "./data/editions"
source_table = os.path.join("tmp", "Metadata.json")
schema_file = "tei_ms.xsd"
template = "./data/constants/template.xml"


def extract_year(*candidates):
    for candidate in candidates:
        if not candidate:
            continue
        match = re.search(r"\b(\d{4})\b", str(candidate))
        if match:
            return match.group(1)
    return None


def get_info(doc):
    title_elems = doc.xpath(".//tei:fileDesc/tei:titleStmt/tei:title", namespaces=nsmap)
    first_title_text = (title_elems[0].text or "").strip() if title_elems else ""

    ttltitle = ""
    date = ""
    if "_" in first_title_text:
        date_part, title_part = first_title_text.split("_", 1)
        date = (date_part or "").strip()
        ttltitle = (title_part or "").strip()
    else:
        desc_titles = doc.xpath(
            ".//tei:fileDesc/tei:titleStmt/tei:title[@type='desc' and @level='a']",
            namespaces=nsmap,
        )
        ttltitle = ((desc_titles[0].text or "").strip() if desc_titles else "")

        bibl_date = doc.xpath(".//tei:fileDesc/tei:sourceDesc/tei:bibl/tei:date", namespaces=nsmap)
        bibl_date_text = ((bibl_date[0].text or "").strip() if bibl_date else "")
        date = extract_year(first_title_text, bibl_date_text) or ""

    srctitle_elem = doc.xpath(".//tei:fileDesc/tei:sourceDesc/tei:bibl/tei:title", namespaces=nsmap)
    srctitle = ((srctitle_elem[0].text or "").strip() if srctitle_elem else "")

    srcidno_elem = doc.xpath(".//tei:fileDesc/tei:sourceDesc/tei:bibl/tei:idno", namespaces=nsmap)
    srcidno = ((srcidno_elem[0].text or "").strip() if srcidno_elem else "")
    return (ttltitle, date, srctitle, srcidno)


templatetei = TeiReader(template)

teiheader = templatetei.any_xpath(".//tei:teiHeader")[0]
standoff = templatetei.any_xpath(".//tei:standOff")[0]
i = 1

for input_file in glob.glob(os.path.join(source_directory, "*.xml")):
    print(f"{i}\t\tParsing {input_file}")
    teifile = False
    teifile = TeiReader(input_file)

    # Find and replace the existing teiHeader with the template teiHeader
    existing_header = teifile.any_xpath(".//tei:teiHeader")[0]
    existing_info = get_info(existing_header)
    root = teifile.tree.getroot()

    # Remove the existing header
    root.remove(existing_header)

    # Create a deep copy of the template header for this file
    new_header = copy.deepcopy(teiheader)
    new_standoff = copy.deepcopy(standoff)

    # Insert the new header from template at the beginning
    root.insert(0, new_header)
    titleStmt = root.xpath(".//tei:teiHeader/tei:fileDesc/tei:titleStmt", namespaces=nsmap)[0]
    bibl = root.xpath(".//tei:sourceDesc/tei:bibl", namespaces=nsmap)[0]
    print(existing_info[0])

    year = extract_year(existing_info[1], existing_info[0])
    main_title_de = root.xpath(
        ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title[@level='a' and @type='main' and @xml:lang='de']",
        namespaces=nsmap,
    )
    if main_title_de:
        main_title_de[0].text = f"Oberkammeramtstrechnung | {year}" if year else "Oberkammeramtstrechnung"

    # Create the desc title element and insert it at the top of titleStmt, after existing titles
    titleStmttitle = ET.Element("title", attrib={"level": "a", "type": "desc"})
    titleStmttitle.text = existing_info[0]

    # Find existing title elements to determine insertion position
    existing_titles = titleStmt.xpath(".//tei:title", namespaces=nsmap)
    if existing_titles:
        # Insert after the last existing title
        insert_position = len(existing_titles)
        titleStmt.insert(insert_position, titleStmttitle)
    else:
        # If no titles exist, insert at the beginning
        titleStmt.insert(0, titleStmttitle)

    ET.SubElement(bibl, "title", attrib={"type": "main"}).text = existing_info[2]
    ET.SubElement(bibl, "date").text = existing_info[1]
    ET.SubElement(bibl, "idno", attrib={"type": "Transkribus"}).text = existing_info[3]

    # Add standOff after teiHeader (check if it doesn't already exist)
    existing_standoff = teifile.any_xpath(".//tei:standOff")
    if not existing_standoff:
        root.insert(1, new_standoff)
        print(f"\t\tAdded standOff section to {input_file}")

    # Save the modified file
    teifile.tree.write(input_file, encoding="utf-8", xml_declaration=True, pretty_print=True)
    print(f"\t\tUpdated teiHeader in {input_file}")
    i += 1

print(f"Completed processing {i - 1} files. All teiHeaders have been replaced with the template.")
