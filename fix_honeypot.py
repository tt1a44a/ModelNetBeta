#!/usr/bin/env python3
import sys
import logging
import os
from database import Database, init_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fix_honeypot')

def main():
    if len(sys.argv) < 3:
        print("Usage: python fix_honeypot.py <target_ip> <port>")
        sys.exit(1)

    target_ip = sys.argv[1]
    port = sys.argv[2]

    # Initialize the database
    init_database()

    # Check if the endpoint exists
    query = "SELECT id FROM endpoints WHERE ip = ? AND port = ?"
    result = Database.fetch_one(query, (target_ip, port))

    if result:
        endpoint_id = result[0]
        print(f"Found endpoint with ID {endpoint_id}")

        # Mark the endpoint as verified and not a honeypot
        update_query = "UPDATE endpoints SET is_honeypot = 0, is_verified = 1 WHERE id = ?"
        Database.execute(update_query, (endpoint_id,))
        print(f"Updated endpoint {endpoint_id} ({target_ip}:{port}) - marked as verified and not a honeypot")
    else:
        print(f"No endpoint found with IP {target_ip} and port {port}")

if __name__ == "__main__":
    main() 