#!/usr/bin/env python

import csv
import json
import sys
import os

def extract_document_id(filename):
    """
    Extract document ID from filename.
    From WSTLA_OKA_B1_1_096_1_00001 extract WSTLA_OKA_B1_1_096_1
    """
    if not filename or not filename.startswith('WSTLA_'):
        return filename
    
    # Split by underscore and take all parts except the last one (the page index)
    parts = filename.split('_')
    if len(parts) < 2:
        return filename
    
    # Join all parts except the last one
    document_id = '_'.join(parts[:-1])
    return document_id

def transform_filename(filename):
    """
    Transform filename from WSTLA_OKA_B1_1_096_1_00001 to WSTLA-OKA-B1-1-096-1_00001
    Replace underscores with hyphens except for the last underscore before the index.
    """
    if not filename or not filename.startswith('WSTLA_'):
        return filename
    
    # Split by underscore
    parts = filename.split('_')
    if len(parts) < 2:
        return filename
    
    # Join all parts except the last one with hyphens
    # Keep the last part separated by underscore
    main_part = '-'.join(parts[:-1])
    index_part = parts[-1]
    
    return f"{main_part}_{index_part}"

def process_csv_to_json(csv_file_path):
    """
    Process CSV file to generate JSON structure with file references and folio data.
    
    The CSV has metadata rows at the top, followed by a header row starting with 'Dateiname'.
    Each file reference (WSTLA_OKA_B1_1_XXX_X_XXXXX) appears in the first column,
    and subsequent rows with empty first column cells contain data related to that file.
    """
    
    result = {}
    current_file = None
    current_document_id = None
    
    with open(csv_file_path, 'r', encoding='utf-8') as file:
        csv_reader = csv.reader(file)
        
        # Skip metadata rows until we find the header row
        header_found = False
        for row in csv_reader:
            if len(row) > 0 and row[0] == 'Dateiname':
                header_found = True
                break
        
        if not header_found:
            raise ValueError("Header row with 'Dateiname' not found")
        
        # Process data rows
        for row in csv_reader:
            # Ensure we have exactly 6 columns (Dateiname, Folio, Kategorie 1-4)
            while len(row) < 6:
                row.append("")
            
            # If first column has content, it's a new file reference
            if row[0].strip():
                original_filename = row[0].strip()
                current_file = transform_filename(original_filename)
                
                # Extract document ID and transform it
                original_doc_id = extract_document_id(original_filename)
                current_document_id = transform_filename(original_doc_id + "_dummy").replace("_dummy", "")
                
                # Initialize document structure if it doesn't exist
                if current_document_id not in result:
                    result[current_document_id] = {}
                
                # Initialize file structure if it doesn't exist
                if current_file not in result[current_document_id]:
                    result[current_document_id][current_file] = {}
                
                # Check if this row also has folio data
                if row[1].strip():  # Folio column
                    folio = row[1].strip()
                    # Always create exactly 4 elements for the categories
                    categories = [
                        row[2] if len(row) > 2 else "",
                        row[3] if len(row) > 3 else "",
                        row[4] if len(row) > 4 else "",
                        row[5] if len(row) > 5 else ""
                    ]
                    result[current_document_id][current_file][folio] = categories
            
            # If first column is empty but we have a current file and folio data
            elif current_file and current_document_id and row[1].strip():  # Has folio data
                folio = row[1].strip()
                # Always create exactly 4 elements for the categories
                categories = [
                    row[2] if len(row) > 2 else "",
                    row[3] if len(row) > 3 else "",
                    row[4] if len(row) > 4 else "",
                    row[5] if len(row) > 5 else ""
                ]
                result[current_document_id][current_file][folio] = categories
    
    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: python csv2json.py <csv_file_path> [csv_file_path2] [...]")
        print("       python csv2json.py extern/csv/*")
        sys.exit(1)
    
    csv_file_paths = sys.argv[1:]
    all_results = {}
    
    for csv_file_path in csv_file_paths:
        if not os.path.exists(csv_file_path):
            print(f"Warning: File '{csv_file_path}' not found, skipping...")
            continue
            
        if not csv_file_path.lower().endswith('.csv'):
            print(f"Warning: File '{csv_file_path}' is not a CSV file, skipping...")
            continue
        
        try:
            print(f"Processing: {csv_file_path}", file=sys.stderr)
            result = process_csv_to_json(csv_file_path)
            
            # Merge results from this file into the main results
            for doc_id, doc_data in result.items():
                if doc_id in all_results:
                    # If document already exists, merge the page data
                    all_results[doc_id].update(doc_data)
                else:
                    all_results[doc_id] = doc_data
            
            print(f"✓ Processed {len(result)} documents from {csv_file_path}", file=sys.stderr)
            
        except Exception as e:
            print(f"Error processing '{csv_file_path}': {e}", file=sys.stderr)
            continue
    
    if not all_results:
        print("No valid CSV files were processed successfully.")
        sys.exit(1)
    
    try:
        # Output JSON with proper formatting
        json_output = json.dumps(all_results, indent=2, ensure_ascii=False)
        print(json_output)
        
        # Also save to a combined file
        output_file = "combined_output.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(json_output)
        
        print(f"\nCombined JSON output saved to: {output_file}", file=sys.stderr)
        print(f"Total documents processed: {len(all_results)}", file=sys.stderr)
        
    except Exception as e:
        print(f"Error writing output: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()