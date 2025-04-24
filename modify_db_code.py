#!/usr/bin/env python3
"""
Database Code Modification Helper

This script helps identify and modify SQLite-specific code to use the new
database abstraction layer in the Ollama Scanner codebase.
"""

import os
import re
import sys
import argparse
from pathlib import Path


# Patterns to look for in code
SQLITE_PATTERNS = [
    r'sqlite3\.connect\(.*\)',
    r'conn\.cursor\(\)',
    r'conn\.commit\(\)',
    r'conn\.rollback\(\)',
    r'cursor\.execute\(.*\)',
    r'cursor\.executemany\(.*\)',
    r'cursor\.fetchone\(\)',
    r'cursor\.fetchall\(\)',
    # TODO: Replace SQLite-specific code: r'\.db',
    # TODO: Replace SQLite-specific code: r'PRAGMA'
]

# Replacements for common patterns
REPLACEMENTS = {
    r'import sqlite3': 'from database import Database, init_database',
    r'sqlite3\.connect\(.*\)': 'Database()',
    r'conn = sqlite3\.connect\(.*\)': '# Using Database abstraction instead of direct SQLite connection',
    r'conn\.cursor\(\)': '# Using Database methods instead of cursor',
    r'conn\.commit\(\)': '# Commit handled by Database methods',
    r'cursor\.execute\((.*?)\)': 'Database.execute(\\1)',
    r'cursor\.executemany\((.*?)\)': 'Database.execute_many(\\1)',
    r'cursor\.fetchone\(\)': 'Database.fetch_one(query, params)',
    r'cursor\.fetchall\(\)': 'Database.fetch_all(query, params)'
}


def find_sqlite_files(directory, extensions=None):
    """Find files that might contain SQLite code"""
    if extensions is None:
        extensions = ['.py']
    
    sqlite_files = []
    for ext in extensions:
        for path in Path(directory).rglob(f'*{ext}'):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'sqlite' in content.lower() or 'cursor' in content.lower():
                    sqlite_files.append(path)
    
    return sqlite_files


def analyze_file(file_path):
    """Analyze a file for SQLite usage patterns"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    findings = []
    for pattern in SQLITE_PATTERNS:
        matches = re.finditer(pattern, content)
        for match in matches:
            line_start = content[:match.start()].rfind('\n') + 1
            line_end = content[match.end():].find('\n')
            if line_end == -1:  # Handle EOF
                line_end = len(content) - match.end()
            line = content[line_start:match.end() + line_end].strip()
            
            findings.append({
                'pattern': pattern,
                'line': line,
                'position': match.start()
            })
    
    return sorted(findings, key=lambda x: x['position'])


def suggest_modifications(file_path, findings):
    """Suggest code modifications based on findings"""
    suggestions = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for finding in findings:
        pattern = finding['pattern']
        line = finding['line']
        
        for search_pattern, replacement in REPLACEMENTS.items():
            if re.search(search_pattern, line):
                new_line = re.sub(search_pattern, replacement, line)
                suggestions.append({
                    'original': line,
                    'modified': new_line,
                    'pattern': pattern
                })
                break
        else:
            # No specific replacement found
            suggestions.append({
                'original': line,
                'modified': f'# TODO: Replace SQLite-specific code: {line}',
                'pattern': pattern
            })
    
    return suggestions


def print_report(file_path, findings, suggestions):
    """Print analysis report for a file"""
    print(f"\n{'=' * 80}")
    print(f"File: {file_path}")
    print(f"{'=' * 80}")
    
    print(f"\nFound {len(findings)} SQLite patterns:")
    for i, finding in enumerate(findings, 1):
        print(f"{i}. {finding['line']}")
    
    print(f"\nSuggested modifications:")
    for i, suggestion in enumerate(suggestions, 1):
        print(f"{i}. Original: {suggestion['original']}")
        print(f"   Modified: {suggestion['modified']}")
        print()


def process_files(files, analyze_only=True):
    """Process multiple files"""
    total_findings = 0
    
    for file_path in files:
        findings = analyze_file(file_path)
        if findings:
            total_findings += len(findings)
            suggestions = suggest_modifications(file_path, findings)
            print_report(file_path, findings, suggestions)
            
            if not analyze_only:
                confirm = input(f"Apply suggested changes to {file_path}? (y/n): ")
                if confirm.lower() == 'y':
                    apply_changes(file_path, suggestions)
    
    print(f"\n{'=' * 80}")
    print(f"Total files analyzed: {len(files)}")
    print(f"Total SQLite usages found: {total_findings}")
    print(f"{'=' * 80}")


def apply_changes(file_path, suggestions):
    """Apply suggested changes to a file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Apply changes in reverse order to prevent position shifts
    for suggestion in sorted(suggestions, key=lambda x: x['original'], reverse=True):
        content = content.replace(suggestion['original'], suggestion['modified'])
    
    # Always add an import for the Database class if changes were made
    if 'from database import Database' not in content and suggestions:
        if 'import ' in content:
            # Find the last import statement
            import_match = list(re.finditer(r'^import .*$|^from .* import .*$', content, re.MULTILINE))
            if import_match:
                last_import = import_match[-1]
                pos = last_import.end()
                content = content[:pos] + '\n\n# Added by migration script\nfrom database import Database, init_database' + content[pos:]
        else:
            # Add to the top of the file
            content = '# Added by migration script\nfrom database import Database, init_database\n\n' + content
    
    # Add a call to init_database() in main functions
    if 'def main(' in content and 'init_database()' not in content:
        main_match = re.search(r'def main\([^)]*\):.*?(?=\S)', content, re.DOTALL)
        if main_match:
            indent = main_match.group(0).split('\n')[-1]
            pos = main_match.end()
            content = content[:pos] + f'\n{indent}# Initialize database schema\n{indent}init_database()' + content[pos:]
    
    # Write changes back to file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Changes applied to {file_path}")


def main():
    parser = argparse.ArgumentParser(description='Analyze and modify SQLite code to use database abstraction')
    parser.add_argument('directory', help='Directory to search for files')
    parser.add_argument('--extensions', nargs='+', default=['.py'], help='File extensions to search (default: .py)')
    parser.add_argument('--apply', action='store_true', help='Apply suggested changes')
    args = parser.parse_args()
    
    directory = args.directory
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a valid directory")
        sys.exit(1)
    
    print(f"Searching for SQLite usage in {directory}...")
    files = find_sqlite_files(directory, args.extensions)
    
    if not files:
        print("No files with SQLite usage found.")
        sys.exit(0)
    
    print(f"Found {len(files)} files with potential SQLite usage:")
    for file in files:
        print(f" - {file}")
    
    confirm = input("\nAnalyze these files? (y/n): ")
    if confirm.lower() != 'y':
        print("Operation cancelled")
        sys.exit(0)
    
    process_files(files, not args.apply)


if __name__ == "__main__":
    main() 