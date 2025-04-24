#!/usr/bin/env python3
"""
Ollama Scanner Status Dashboard
A simple dashboard to check the status of scanner/pruner operations
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from tabulate import tabulate
import time

# Load environment variables
load_dotenv()

# Database connection parameters
DB_TYPE = os.environ.get('DATABASE_TYPE', 'postgres')
DB_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
DB_PORT = os.environ.get('POSTGRES_PORT', '5432')
DB_NAME = os.environ.get('POSTGRES_DB', 'ollama_scanner')
DB_USER = os.environ.get('POSTGRES_USER', 'ollama')
DB_PASS = os.environ.get('POSTGRES_PASSWORD', '')

def get_db_connection():
    """Get a connection to the PostgreSQL database"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def get_metadata(conn):
    """Get all metadata entries from the database"""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT key, value, updated_at FROM metadata")
    metadata = {row['key']: {'value': row['value'], 'updated_at': row['updated_at']} for row in cursor.fetchall()}
    cursor.close()
    return metadata

def get_endpoint_stats(conn):
    """Get endpoint statistics from the database"""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Get verified/unverified counts
    cursor.execute("SELECT verified, COUNT(*) FROM endpoints GROUP BY verified")
    verified_counts = {row['verified']: row['count'] for row in cursor.fetchall()}
    
    # Get recent additions
    cursor.execute("""
        SELECT COUNT(*) FROM endpoints 
        WHERE scan_date > NOW() - INTERVAL '24 hours'
    """)
    recent_count = cursor.fetchone()[0]
    
    # Get recent verifications
    cursor.execute("""
        SELECT COUNT(*) FROM endpoints 
        WHERE verification_date IS NOT NULL AND verification_date > NOW() - INTERVAL '24 hours'
    """)
    recent_verified = cursor.fetchone()[0]
    
    # Get model counts
    cursor.execute("SELECT COUNT(*) FROM models")
    model_count = cursor.fetchone()[0]
    
    # Get unique model count
    cursor.execute("SELECT COUNT(DISTINCT name) FROM models")
    unique_model_count = cursor.fetchone()[0]
    
    cursor.close()
    
    return {
        'verified': verified_counts.get(1, 0),
        'unverified': verified_counts.get(0, 0),
        'recent_additions': recent_count,
        'recent_verifications': recent_verified,
        'model_count': model_count,
        'unique_model_count': unique_model_count
    }

def get_operation_status(metadata):
    """Analyze metadata to determine operation status"""
    operations = []
    
    # Scanner status
    scan_start = metadata.get('last_scan_start', {}).get('value')
    scan_end = metadata.get('last_scan_end', {}).get('value')
    
    if scan_start:
        scan_start_time = metadata.get('last_scan_start', {}).get('updated_at')
        status = "Completed" if scan_end else "In Progress"
        if status == "In Progress":
            duration = "Running since " + str(datetime.now() - scan_start_time)
        else:
            duration = str(metadata.get('last_scan_end', {}).get('updated_at') - scan_start_time)
        
        operations.append({
            'name': 'Scanner',
            'last_run': scan_start_time,
            'status': status,
            'duration': duration
        })
    
    # Pruner status
    prune_start = metadata.get('last_prune_start', {}).get('value')
    prune_end = metadata.get('last_prune_end', {}).get('value')
    
    if prune_start:
        prune_start_time = metadata.get('last_prune_start', {}).get('updated_at')
        status = "Completed" if prune_end else "In Progress"
        if status == "In Progress":
            duration = "Running since " + str(datetime.now() - prune_start_time)
        else:
            duration = str(metadata.get('last_prune_end', {}).get('updated_at') - prune_start_time)
        
        operations.append({
            'name': 'Pruner',
            'last_run': prune_start_time,
            'status': status,
            'duration': duration
        })
    
    # Maintenance status
    maintenance = metadata.get('last_maintenance', {}).get('value')
    if maintenance:
        operations.append({
            'name': 'Maintenance',
            'last_run': metadata.get('last_maintenance', {}).get('updated_at'),
            'status': 'Completed',
            'duration': 'N/A'
        })
    
    # Recovery status
    recovery = metadata.get('last_recovery', {}).get('value')
    if recovery:
        operations.append({
            'name': 'Recovery',
            'last_run': metadata.get('last_recovery', {}).get('updated_at'),
            'status': 'Completed',
            'duration': 'N/A'
        })
    
    return operations

def print_dashboard(metadata, stats, operations, continuous=False):
    """Print the dashboard to the console"""
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        
        # Print header
        print("\n" + "=" * 80)
        print("  OLLAMA SCANNER STATUS DASHBOARD")
        print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("=" * 80 + "\n")
        
        # Print operation status
        print("OPERATION STATUS:")
        if operations:
            headers = ["Operation", "Last Run", "Status", "Duration"]
            table_data = []
            for op in operations:
                table_data.append([
                    op['name'],
                    op['last_run'].strftime("%Y-%m-%d %H:%M:%S") if op['last_run'] else 'Never',
                    op['status'],
                    op['duration']
                ])
            print(tabulate(table_data, headers=headers, tablefmt="grid"))
        else:
            print("No operations have been recorded yet.")
        
        print("\n")
        
        # Print endpoint statistics
        print("ENDPOINT STATISTICS:")
        stats_table = [
            ["Verified Endpoints", stats['verified']],
            ["Unverified Endpoints", stats['unverified']],
            ["Total Endpoints", stats['verified'] + stats['unverified']],
            ["Added in last 24h", stats['recent_additions']],
            ["Verified in last 24h", stats['recent_verifications']],
            ["Total Models", stats['model_count']],
            ["Unique Models", stats['unique_model_count']]
        ]
        print(tabulate(stats_table, tablefmt="grid"))
        
        print("\n")
        
        # Print most recent metadata values
        print("RECENT METADATA VALUES:")
        metadata_table = []
        important_keys = [
            'scanned_count', 'verified_count', 'failed_count', 
            'model_count', 'last_scan_start', 'last_scan_end',
            'last_prune_start', 'last_prune_end'
        ]
        
        for key in important_keys:
            if key in metadata:
                value = metadata[key]['value']
                updated = metadata[key]['updated_at'].strftime("%Y-%m-%d %H:%M:%S")
                metadata_table.append([key, value, updated])
        
        print(tabulate(metadata_table, headers=["Key", "Value", "Updated At"], tablefmt="grid"))
        
        if not continuous:
            break
        
        # In continuous mode, refresh every 5 seconds
        print("\nRefreshing in 5 seconds... (Press Ctrl+C to exit)")
        try:
            time.sleep(5)
            
            # Refresh data
            conn = get_db_connection()
            metadata = get_metadata(conn)
            stats = get_endpoint_stats(conn)
            operations = get_operation_status(metadata)
            conn.close()
        except KeyboardInterrupt:
            print("\nExiting dashboard.")
            break

def main():
    parser = argparse.ArgumentParser(description="Ollama Scanner Status Dashboard")
    parser.add_argument('--continuous', '-c', action='store_true', help='Run in continuous mode, refreshing every 5 seconds')
    args = parser.parse_args()
    
    conn = get_db_connection()
    metadata = get_metadata(conn)
    stats = get_endpoint_stats(conn)
    operations = get_operation_status(metadata)
    conn.close()
    
    print_dashboard(metadata, stats, operations, args.continuous)

if __name__ == "__main__":
    main() 