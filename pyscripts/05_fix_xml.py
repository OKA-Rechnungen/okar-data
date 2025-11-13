#!/usr/bin/env python3
# Run just once from the top directory to add a xml:id attrib to  the TEI
# files in data/editions. It uses the file name without extension
import os
from acdh_tei_pyutils.tei import TeiReader, ET
import re

BASENAME = "/"
xml_path = "./data/editions"
xml_files = [f for f in os.listdir(xml_path) if
             f.startswith("WSTLA-OKA") and f.endswith(".xml")]


prev_file = ""
for current_file in xml_files:
    print(f"Fixing {current_file}")
    volume_name = re.sub(r"(WSTLA-OKA-B1-\d+-\d+-\d).*", r"\1", current_file)
    current_filepath = os.path.join(xml_path, current_file)
    xml_current = TeiReader(current_filepath)
    tei_ns = xml_current.ns_tei
    xml_current_root = xml_current.tree.getroot()
    xml_current_root.attrib[f'{{{xml_current.ns_xml.get("xml")}}}id'] = "".join(os.path.splitext(current_file))
    xml_current_root.attrib[f'{{{xml_current.ns_xml.get("xml")}}}base'] = BASENAME
    for graphic in xml_current.any_xpath('//tei:graphic'):
        url = graphic.get('url')
        if re.match(r'^\d+\.tif$', url):
            # Navigate to parent <surface> and extract @xml:id
            surface = graphic.getparent()
            xml_id = surface.get('{http://www.w3.org/XML/1998/namespace}id')
            if xml_id:
                id_suffix = xml_id.split('_')[1] if '_' in xml_id else xml_id
                new_url = f"{volume_name}_{id_suffix}.tif"
                graphic.set('url', new_url)
    if prev_file:
        xml_current_root.attrib['prev'] = prev_file
        prev_filepath = os.path.join(xml_path, prev_file)
        xml_prev = TeiReader(prev_filepath)
        xml_prev_root = xml_prev.tree.getroot()
        xml_prev_root.attrib['next'] = current_file
        with open(prev_filepath, "wb") as f:
            f.write(ET.tostring(xml_prev_root, pretty_print=True))
    prev_file = current_file

    with open(current_filepath, "wb") as f:
        f.write(ET.tostring(xml_current_root, pretty_print=True))
