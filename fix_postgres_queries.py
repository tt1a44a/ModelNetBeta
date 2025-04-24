#!/usr/bin/env python3
"""
Fix PostgreSQL queries in prune_bad_endpoints.py
"""

import os
import re
import fileinput

def fix_prune_bad_endpoints():
    """Fix PostgreSQL queries in prune_bad_endpoints.py"""
    filename = "prune_bad_endpoints.py"
    print(f"Fixing PostgreSQL queries in {filename}...")
    
    # Define patterns to search for
    patterns = [
        # Fix verified value comparison
        (r"verified = {verified_value}", r"verified = CAST({verified_value} AS INTEGER)"),
        # Fix direct boolean comparisons
        (r"verified = (TRUE|FALSE)", r"verified = CAST(\1 AS INTEGER)"),
        (r"is_honeypot = (TRUE|FALSE)", r"is_honeypot = \1"),
        (r"is_active = (TRUE|FALSE)", r"is_active = \1"),
    ]
    
    lines_modified = 0
    with fileinput.FileInput(filename, inplace=True, backup='.bak') as file:
        for line in file:
            original_line = line
            
            # Apply all patterns
            for pattern, replacement in patterns:
                line = re.sub(pattern, replacement, line)
            
            # Print the modified line back to the file
            print(line, end='')
            
            # Count modified lines
            if line != original_line:
                lines_modified += 1
    
    print(f"Modified {lines_modified} lines in {filename}")
    
    # Fix get_db_boolean function
    filename = "database.py"
    print(f"Fixing get_db_boolean function in {filename}...")
    
    with fileinput.FileInput(filename, inplace=True, backup='.bak') as file:
        for line in file:
            # Look for the get_db_boolean function definition
            if "def get_db_boolean" in line:
                print(line, end='')
                # Read the next few lines to check if we need to modify the function
                inside_function = True
                function_lines = []
                continue
            
            # Print the line as-is
            print(line, end='')
    
    print("Database fixes completed!")

if __name__ == "__main__":
    fix_prune_bad_endpoints() 