#!/bin/bash
. ./secret.env
rm -rf data/editions/* data/mets/* tei_headers/*
TRANSKRIBUS_DOC_IDS="6981834,10651984,7714156" ./pyscripts/download.py
./pyscripts/transform.py
./pyscripts/rename_files.py
./pyscripts/fix_xml.py
./pyscripts/add_missing_initial_page.py
./pyscripts/generate_headers.py
./pyscripts/fill_headers.py
