#!/usr/bin/env python
# Executable file that calls library maketei
import glob
import os
from sys import argv
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
source_directory = "./data/editions2"
source_table = os.path.join("tmp", "Metadata.json")
schema_file = "tei_ms.xsd"
output_directory = "./data/indices"
template = "./data/constants/template.xml"


def get_info(doc):
    date, ttltitle = doc.xpath(".//tei:fileDesc/tei:titleStmt/tei:title", namespaces=nsmap)[0].text.split("_")
    srctitle = doc.xpath(".//tei:fileDesc/tei:sourceDesc/tei:bibl/tei:title", namespaces=nsmap)[0].text
    srcidno = doc.xpath(".//tei:fileDesc/tei:sourceDesc/tei:bibl/tei:idno", namespaces=nsmap)[0].text
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
    print( existing_info[0])
    
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