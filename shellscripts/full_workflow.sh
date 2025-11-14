#!/bin/bash
. ./.secret.env
rm -rf data/editions/* data/mets/* tei_headers/*
./pyscripts/01_download.py
./pyscripts/02_fix_tkb.py
./pyscripts/03_transform.py
./pyscripts/04_rename_files.py
./pyscripts/05_fix_xml.py
# ./pyscripts/06_add_missing_initial_page.py
./pyscripts/07_generate_headers.py
./pyscripts/08_fill_headers.py
