#!/usr/bin/env python
# Executable file that calls library maketei
import glob
import os
from sys import argv
from acdh_tei_pyutils.tei import TeiReader, ET

xml = "{http://www.w3.org/XML/1998/namespace}"
os.makedirs("tmp", exist_ok=True)
source_directory = "./data/editions2"
source_table = os.path.join("tmp", "Metadata.json")
schema_file = "tei_ms.xsd"
output_directory = "./data/indices"
template = "./data/constants/template.xml"

templatetei = TeiReader(template)

teiheader = templatetei.any_xpath(".//tei:teiHeader")[0]
standoff = templatetei.any_xpath(".//tei:standOff")[0]
i = 1

for input_file in glob.glob(os.path.join(source_directory, "*.xml")):
    print(f"{i}\t\tParsing {input_file}")
    teifile = TeiReader(input_file)
    
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
    
    # Save the modified file
    teifile.tree.write(input_file, encoding="utf-8", xml_declaration=True, pretty_print=True)
    print(f"\t\tUpdated teiHeader in {input_file}")
    i += 1

print(f"Completed processing {i - 1} files. All teiHeaders have been replaced with the template.")