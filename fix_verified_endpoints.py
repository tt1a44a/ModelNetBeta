#!/usr/bin/env python3
import logging
from database import Database, init_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fix_verified_endpoints')

def main():
    # Initialize database connection
    init_database()
    
    # Find honeypots in verified_endpoints table
    query = """
    SELECT ve.endpoint_id, e.ip, e.port 
    FROM verified_endpoints ve 
    JOIN endpoints e ON ve.endpoint_id = e.id 
    WHERE e.is_honeypot = TRUE
    """
    
    honeypots = Database.fetch_all(query)
    
    if not honeypots:
        logger.info("No honeypots found in verified_endpoints table.")
        return
    
    logger.info(f"Found {len(honeypots)} honeypot(s) in verified_endpoints table.")
    
    for honeypot in honeypots:
        endpoint_id, ip, port = honeypot
        logger.info(f"Found honeypot in verified_endpoints: Endpoint ID: {endpoint_id}, IP: {ip}:{port}")
        
        # Remove from verified_endpoints
        delete_query = "DELETE FROM verified_endpoints WHERE endpoint_id = %s"
        Database.execute(delete_query, (endpoint_id,))
        
        logger.info(f"Removed endpoint ID {endpoint_id} from verified_endpoints table")
    
    # Verify the fix
    check_query = """
    SELECT COUNT(*) 
    FROM verified_endpoints ve 
    JOIN endpoints e ON ve.endpoint_id = e.id 
    WHERE e.is_honeypot = TRUE
    """
    
    remaining = Database.fetch_one(check_query)[0]
    
    if remaining == 0:
        logger.info("Successfully removed all honeypots from verified_endpoints table.")
    else:
        logger.warning(f"There are still {remaining} honeypots in verified_endpoints table.")

if __name__ == "__main__":
    main() 