#!/usr/bin/env python3
import glob
import os
from acdh_tei_pyutils.tei import ET
import re

directory = "./data/editions"


def checkfile(filename):
    parser = ET.XMLParser(recover=True)
    tree = False
    try:
        tree = ET.parse(filename)
    except Exception:
        try:
            tree = ET.parse(filename, parser=parser)
        except Exception as e:
            print(e)
    return tree.getroot()


def getname(root):
    name = False
    regex = re.compile(r'\d{4}_(WSTLA-OKA.*)')
    docid = root.xpath('//tei:teiHeader//tei:title[@type="main"]',
                       namespaces={"tei": "http://www.tei-c.org/ns/1.0"})[0].text
    name = re.sub(regex, r"\g<1>", docid).replace(" ", "")
    print(docid, '==>', name)
    return name


for current_filepath in glob.glob(os.path.join(directory, "*.xml")):
    filename = os.path.basename(current_filepath)
    try:
        xmltei = checkfile(current_filepath)
        current_file = f"{getname(xmltei)}.xml"
        if not filename.startswith('WSTLA'):
            new_filepath = os.path.join(directory, current_file)
            os.rename(current_filepath, new_filepath)
            print(f"{current_filepath}\t->\t{new_filepath}")
    except Exception as e:
        print(e)
