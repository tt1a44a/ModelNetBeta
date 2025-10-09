#!/usr/bin/env python3
"""
Consolidate all IPs from various files into the PostgreSQL database
"""

import re
import os
from database import Database, init_database

def parse_ollama_instances_txt(filename):
    """Parse ollama_instances.txt format"""
    ips = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                # Match format: [+] IP:PORT
                match = re.search(r'\[\+\]\s+(\d+\.\d+\.\d+\.\d+):(\d+)', line)
                if match:
                    ip = match.group(1)
                    port = match.group(2)
                    ips.append((ip, int(port)))
    except FileNotFoundError:
        print(f"File not found: {filename}")
    return ips

def parse_masscan_results(filename):
    """Parse masscan grepable output format"""
    ips = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                # Match format: Host: IP () Ports: PORT/open/tcp////
                match = re.search(r'Host:\s+(\d+\.\d+\.\d+\.\d+)\s+.*Ports:\s+(\d+)/open', line)
                if match:
                    ip = match.group(1)
                    port = match.group(2)
                    ips.append((ip, int(port)))
    except FileNotFoundError:
        print(f"File not found: {filename}")
    return ips

def parse_simple_ip_list(filename):
    """Parse simple IP:PORT or just IP format"""
    ips = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Try IP:PORT format
                match = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)', line)
                if match:
                    ip = match.group(1)
                    port = match.group(2)
                    ips.append((ip, int(port)))
                else:
                    # Try just IP format (assume port 11434)
                    match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                    if match:
                        ip = match.group(1)
                        ips.append((ip, 11434))
    except FileNotFoundError:
        print(f"File not found: {filename}")
    return ips

def insert_ips_to_db(ips, source_file):
    """Insert IPs into PostgreSQL database"""
    added = 0
    duplicates = 0
    errors = 0
    
    for ip, port in ips:
        try:
            # Check if already exists
            existing = Database.fetch_one(
                "SELECT id FROM endpoints WHERE ip = %s AND port = %s",
                (ip, port)
            )
            
            if existing:
                duplicates += 1
                continue
            
            # Insert new endpoint
            Database.execute(
                """INSERT INTO endpoints (ip, port, scan_date, verified, is_active)
                   VALUES (%s, %s, NOW(), 0, TRUE)
                   ON CONFLICT (ip, port) DO NOTHING""",
                (ip, port)
            )
            added += 1
            
        except Exception as e:
            print(f"Error inserting {ip}:{port}: {e}")
            errors += 1
    
    return added, duplicates, errors

def main():
    print("=" * 70)
    print("        IP Consolidation to PostgreSQL Database")
    print("=" * 70)
    print()
    
    # Initialize database
    init_database()
    
    # Define files to process
    files_to_process = [
        ('ollama_instances.txt', parse_ollama_instances_txt),
        ('ips_to_verify.txt', parse_simple_ip_list),
        ('test_ips.txt', parse_simple_ip_list),
        ('masscan_results.txt', parse_masscan_results),
        ('res.txt', parse_masscan_results),
        ('DiscordBot/res.txt', parse_masscan_results),
    ]
    
    total_added = 0
    total_duplicates = 0
    total_errors = 0
    
    for filename, parser in files_to_process:
        if not os.path.exists(filename):
            print(f"⊘ Skipping {filename} (not found)")
            continue
        
        print(f"Processing {filename}...")
        ips = parser(filename)
        
        if not ips:
            print(f"  ⊘ No IPs found in {filename}")
            continue
        
        print(f"  Found {len(ips)} IPs")
        
        added, duplicates, errors = insert_ips_to_db(ips, filename)
        
        print(f"  ✓ Added: {added}, Duplicates: {duplicates}, Errors: {errors}")
        
        total_added += added
        total_duplicates += duplicates
        total_errors += errors
    
    print()
    print("=" * 70)
    print("                        SUMMARY")
    print("=" * 70)
    print(f"Total IPs Added:      {total_added}")
    print(f"Total Duplicates:     {total_duplicates}")
    print(f"Total Errors:         {total_errors}")
    print()
    
    # Show current database stats
    try:
        total_endpoints = Database.fetch_one("SELECT COUNT(*) FROM endpoints")[0]
        verified = Database.fetch_one("SELECT COUNT(*) FROM endpoints WHERE verified > 0")[0]
        unverified = Database.fetch_one("SELECT COUNT(*) FROM endpoints WHERE verified = 0")[0]
        honeypots = Database.fetch_one("SELECT COUNT(*) FROM endpoints WHERE is_honeypot=true")[0]
        active = Database.fetch_one("SELECT COUNT(*) FROM endpoints WHERE is_active=true")[0]
        
        print("Current Database Statistics:")
        print(f"  Total Endpoints:    {total_endpoints}")
        print(f"  Verified:           {verified}")
        print(f"  Unverified:         {unverified}")
        print(f"  Honeypots:          {honeypots}")
        print(f"  Active:             {active}")
        print()
        
    except Exception as e:
        print(f"Error getting database stats: {e}")
    
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Run the pruner to verify these endpoints:")
    print("     ./run_pruner.sh --workers 10 --force")
    print()
    print("  2. Query the database:")
    print("     python query_models_fixed.py servers")
    print()

if __name__ == "__main__":
    main()

