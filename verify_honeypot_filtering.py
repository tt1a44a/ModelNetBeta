#!/usr/bin/env python3
"""
Verify honeypot filtering and check for other potentially missed honeypots
"""

from database import Database, init_database, DATABASE_TYPE
import json

# Initialize database
init_database()

def check_endpoint_in_results(endpoint_ip, endpoint_port):
    """Check if a specific endpoint would be returned by find_model"""
    # This simulates the find_model function's query logic
    if DATABASE_TYPE == "postgres":
        query = """
            SELECT m.id, m.name, e.ip, e.port, m.parameter_size, m.quantization_level
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE e.verified = 1
            AND e.is_honeypot = FALSE
            AND e.is_active = TRUE
            AND e.ip = %s AND e.port = %s
            ORDER BY m.name, m.parameter_size
        """
    else:
        query = """
            SELECT m.id, m.name, e.ip, e.port, m.parameter_size, m.quantization_level
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE e.verified = 1
            AND e.is_honeypot = 0
            AND e.is_active = 1
            AND e.ip = %s AND e.port = %s
            ORDER BY m.name, m.parameter_size
        """
    
    results = Database.fetch_all(query, (endpoint_ip, endpoint_port))
    
    print(f"Checking if endpoint {endpoint_ip}:{endpoint_port} would be returned by find_model...")
    if results:
        print(f"WARNING: Endpoint {endpoint_ip}:{endpoint_port} would still be returned by find_model!")
        print(f"Found {len(results)} models for this endpoint:")
        for result in results:
            print(f"  Model: {result[1]}, ID: {result[0]}")
        return True
    else:
        print(f"Success: Endpoint {endpoint_ip}:{endpoint_port} would NOT be returned by find_model.")
        return False

def find_potential_honeypots():
    """Find endpoints that might be honeypots but aren't marked as such"""
    
    # Check for endpoints that are verified but have suspicious patterns
    print("\nChecking for potential unmarked honeypots...\n")
    
    # 1. Check for endpoints with future last_check_date
    future_date_query = """
        SELECT id, ip, port, verified, is_honeypot, is_active, last_check_date 
        FROM endpoints 
        WHERE last_check_date > NOW() + INTERVAL '1 day'
        AND is_honeypot = FALSE
        AND verified = 1
    """
    
    future_results = Database.fetch_all(future_date_query)
    if future_results:
        print(f"Found {len(future_results)} endpoints with future check dates (potential issue):")
        for result in future_results:
            print(f"  ID: {result[0]}, IP: {result[1]}:{result[2]}, verified: {result[3]}, is_honeypot: {result[4]}, is_active: {result[5]}, last_check: {result[6]}")
    else:
        print("No endpoints with future check dates found.")
    
    # 2. Check for endpoints with unusual port numbers (non-standard Ollama ports)
    unusual_port_query = """
        SELECT id, ip, port, verified, is_honeypot
        FROM endpoints
        WHERE verified = 1
        AND is_honeypot = FALSE
        AND port NOT IN (11434, 8000, 8080, 443, 80, 8888)
        ORDER BY port
    """
    
    port_results = Database.fetch_all(unusual_port_query)
    if port_results:
        print(f"\nFound {len(port_results)} verified endpoints with unusual ports (check these manually):")
        for result in port_results:
            print(f"  ID: {result[0]}, IP: {result[1]}:{result[2]}, verified: {result[3]}, is_honeypot: {result[4]}")
    else:
        print("\nNo endpoints with unusual ports found.")
    
    # 3. Check for inconsistencies - honeypots that are still verified
    inconsistent_query = """
        SELECT id, ip, port, verified, is_honeypot, is_active
        FROM endpoints
        WHERE is_honeypot = TRUE
        AND verified = 1
    """
    
    inconsistent_results = Database.fetch_all(inconsistent_query)
    if inconsistent_results:
        print(f"\nWARNING: Found {len(inconsistent_results)} honeypot endpoints that are still marked as verified:")
        for result in inconsistent_results:
            print(f"  ID: {result[0]}, IP: {result[1]}:{result[2]}, verified: {result[3]}, is_honeypot: {result[4]}, is_active: {result[5]}")
            
        print("\nFIXING inconsistent honeypot endpoints...")
        for result in inconsistent_results:
            endpoint_id = result[0]
            ip = result[1]
            port = result[2]
            
            # Update endpoint to be unverified
            Database.execute("UPDATE endpoints SET verified = 0 WHERE id = %s", (endpoint_id,))
            
            # Remove from verified_endpoints
            Database.execute("DELETE FROM verified_endpoints WHERE endpoint_id = %s", (endpoint_id,))
            
            print(f"  Fixed endpoint {ip}:{port} (ID: {endpoint_id})")
    else:
        print("\nNo inconsistent honeypot endpoints found (good).")

if __name__ == "__main__":
    # Verify our fix for the specific endpoint
    check_endpoint_in_results("63.178.23.6", 5523)
    
    # Find other potential honeypots
    find_potential_honeypots() 