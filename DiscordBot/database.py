#!/usr/bin/env python3
"""
Database Abstraction Module for Ollama Scanner
Provides a unified interface for working with PostgreSQL databases
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Union
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

# Database libraries
import psycopg2
import psycopg2.pool
import psycopg2.extras
from psycopg2 import sql

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("database.log")
    ]
)
logger = logging.getLogger('database')

# Load environment variables
load_dotenv()

# Database configuration
DATABASE_TYPE = "postgres"  # Force PostgreSQL
logger.info(f"Database configured to use: {DATABASE_TYPE}")

# PostgreSQL package is only imported if we're using PostgreSQL
if DATABASE_TYPE == "postgres":
    try:
        from psycopg2 import pool
        from psycopg2.extras import DictCursor, execute_values
    except ImportError:
        logger.error("psycopg2 package is required for PostgreSQL connectivity.")
        logger.error("Install it using: pip install psycopg2-binary")
        sys.exit(1)
    
    # PostgreSQL connection details
    PG_DB_NAME = os.getenv("POSTGRES_DB", "ollama_scanner")
    PG_DB_USER = os.getenv("POSTGRES_USER", "ollama")
    PG_DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ollama_scanner_password")
    PG_DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
    PG_DB_PORT = os.getenv("POSTGRES_PORT", "5432")
    
    # Connection pool configuration
    MIN_CONNECTIONS = int(os.getenv("DB_MIN_CONNECTIONS", "5"))
    MAX_CONNECTIONS = int(os.getenv("DB_MAX_CONNECTIONS", "50"))
    
    logger.info(f"PostgreSQL configuration: {PG_DB_USER}@{PG_DB_HOST}:{PG_DB_PORT}/{PG_DB_NAME}")
else:
    # For backward compatibility, log warning and exit - we only support PostgreSQL now
    logger.error("PostgreSQL is required. Please set DATABASE_TYPE=postgres in your .env file.")
    sys.exit(1)


class PostgreSQLManager:
    """PostgreSQL database manager with connection pooling for Ollama Scanner"""
    _instance = None
    _lock = threading.Lock()
    _active_connections = set()  # Track active connections
    _active_connections_lock = threading.Lock()
    _is_closing = False  # Flag to indicate pool is being closed
    _is_initialized = False  # Flag to track if pool is successfully initialized
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(PostgreSQLManager, cls).__new__(cls)
                cls._instance._initialize_pool()
            return cls._instance
    
    def _initialize_pool(self):
        """Initialize the connection pool"""
        logger.info(f"Initializing PostgreSQL connection pool (min={MIN_CONNECTIONS}, max={MAX_CONNECTIONS})")
        try:
            # If we're reinitializing, clean up any old pool first
            if hasattr(self, '_pool') and self._pool:
                try:
                    self._is_closing = True
                    self._pool.closeall()
                    logger.info("Closed existing pool before reinitializing")
                except Exception as e:
                    logger.warning(f"Error closing existing pool during reinitialization: {e}")
            
            self._is_closing = False
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=MIN_CONNECTIONS,
                maxconn=MAX_CONNECTIONS,
                dbname=PG_DB_NAME,
                user=PG_DB_USER,
                password=PG_DB_PASSWORD,
                host=PG_DB_HOST,
                port=PG_DB_PORT,
                # Add connection timeout parameters
                connect_timeout=int(os.getenv("DB_CONNECTION_TIMEOUT", "5")),  # Reduced from 10 to 5 seconds
                # Add additional connection parameters for better behavior
                options="-c statement_timeout=10000",  # 10 seconds statement timeout
                keepalives=1,  # Enable TCP keepalives
                keepalives_idle=60,  # Idle time after which to send keepalive (seconds)
                keepalives_interval=10,  # Interval between keepalives (seconds)
                keepalives_count=3  # Number of keepalives before considering connection dead
            )
            # Test the connection
            conn = self._pool.getconn()
            cursor = conn.cursor()
            # Set a short timeout for the test query
            cursor.execute("SET statement_timeout = 5000")  # 5 seconds
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            logger.info(f"Connected to PostgreSQL: {version}")
            self._pool.putconn(conn)
            
            # Mark as successfully initialized
            self._is_initialized = True
            
        except Exception as e:
            self._is_initialized = False
            logger.error(f"Failed to initialize PostgreSQL connection pool: {str(e)}")
            raise
    
    def reinitialize(self):
        """Reinitialize the database connection pool"""
        try:
            logger.info("Reinitializing database connection pool")
            
            # Close existing pool if it exists
            if self._is_initialized and not self._is_closing:
                logger.info("Closing existing connection pool")
                self._pool.closeall()
                
            # Reset status flags
            self._is_initialized = False
            self._is_closing = False
            
            # Create a new connection pool
            self._create_pool()
            
            # Test connection
            conn = self._pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                    conn.commit()
                    self._is_initialized = True
                    logger.info("Database connection pool successfully reinitialized")
                    return True
            except Exception as e:
                logger.error(f"Failed to verify new connection pool: {str(e)}")
                return False
            finally:
                self._pool.putconn(conn)
        except Exception as e:
            logger.error(f"Failed to reinitialize database connection pool: {str(e)}")
            return False
            
    def _create_pool(self):
        """Create a new connection pool"""
        logger.info(f"Initializing PostgreSQL connection pool (min={MIN_CONNECTIONS}, max={MAX_CONNECTIONS})")
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=MIN_CONNECTIONS,
                maxconn=MAX_CONNECTIONS,
                dbname=PG_DB_NAME,
                user=PG_DB_USER,
                password=PG_DB_PASSWORD,
                host=PG_DB_HOST,
                port=PG_DB_PORT,
                # Add connection timeout parameters
                connect_timeout=int(os.getenv("DB_CONNECTION_TIMEOUT", "5")),  # Reduced from 10 to 5 seconds
                # Add additional connection parameters for better behavior
                options="-c statement_timeout=10000",  # 10 seconds statement timeout
                keepalives=1,  # Enable TCP keepalives
                keepalives_idle=60,  # Idle time after which to send keepalive (seconds)
                keepalives_interval=10,  # Interval between keepalives (seconds)
                keepalives_count=3  # Number of keepalives before considering connection dead
            )
            # Test the connection
            conn = self._pool.getconn()
            cursor = conn.cursor()
            # Set a short timeout for the test query
            cursor.execute("SET statement_timeout = 5000")  # 5 seconds
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            logger.info(f"Connected to PostgreSQL: {version}")
            self._pool.putconn(conn)
            
            # Mark as successfully initialized
            self._is_initialized = True
            
        except Exception as e:
            self._is_initialized = False
            logger.error(f"Failed to initialize PostgreSQL connection pool: {str(e)}")
            raise
    
    def get_connection(self):
        """Get a connection from the pool with retry logic"""
        # Check if pool needs reinitialization
        if self._is_closing or not self._is_initialized:
            with self._lock:
                if self._is_closing or not self._is_initialized:
                    logger.warning("Pool is closing or not initialized. Attempting to reinitialize.")
                    self.reinitialize()
            
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                connection = self._pool.getconn()
                with self._active_connections_lock:
                    self._active_connections.add(connection)
                return connection
            except psycopg2.pool.PoolError as e:
                logger.warning(f"Connection pool exhausted, retry {attempt+1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # exponential backoff
                else:
                    logger.error(f"Failed to get database connection: {e}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error obtaining connection: {e}")
                raise
    
    def return_connection(self, conn):
        """Return a connection to the pool"""
        if conn is None:
            return
            
        if self._is_closing:
            # Pool is closing, just close the connection
            try:
                conn.close()
                logger.debug("Connection closed directly (pool is closing)")
            except Exception as e:
                logger.debug(f"Error closing connection: {e}")
            return
            
        try:
            self._pool.putconn(conn)
            with self._active_connections_lock:
                if conn in self._active_connections:
                    self._active_connections.remove(conn)
        except Exception as e:
            logger.error(f"Error returning connection to pool: {e}")
            # Try to close it anyway
            try:
                conn.close()
            except:
                pass
    
    def execute(self, query, params=None):
        """Execute a query with optional parameters and return cursor"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            # Replace ? placeholders with %s for PostgreSQL
            query = query.replace('?', '%s')
            cursor.execute(query, params or ())
            conn.commit()
            return cursor
        except psycopg2.Error as e:
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            logger.error(f"Error executing PostgreSQL query: {e}")
            logger.debug(f"Query: {query}")
            logger.debug(f"Params: {params}")
            raise
        finally:
            if conn:
                self.return_connection(conn)
    
    def execute_many(self, query, params_list):
        """Execute many operations with the same query but different parameters"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            execute_values(cursor, query, params_list)
            conn.commit()
            return cursor
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"Error executing PostgreSQL batch query: {e}")
            raise
        finally:
            self.return_connection(conn)
    
    def fetch_one(self, query, params=None):
        """Execute a query and fetch one result with a timeout"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Replace ? placeholders with %s for PostgreSQL
            query = query.replace('?', '%s')
            # Set a statement timeout to prevent hanging queries (10 seconds)
            cursor.execute("SET statement_timeout = 10000")  # 10 seconds in milliseconds
            cursor.execute(query, params or ())
            return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error fetching from PostgreSQL: {e}")
            raise
        finally:
            self.return_connection(conn)
    
    def fetch_all(self, query, params=None):
        """Execute a query and fetch all results with a timeout"""
        conn = self.get_connection()
        try:
            # Use regular cursor to get results as tuples (consistent with fetch_one)
            cursor = conn.cursor()
            # Replace ? placeholders with %s for PostgreSQL
            query = query.replace('?', '%s')
            # Set a statement timeout to prevent hanging queries (10 seconds)
            cursor.execute("SET statement_timeout = 10000")  # 10 seconds in milliseconds
            
            # Debug logging
            logger.debug(f"Executing query with params type: {type(params)}, params: {params}")
            
            cursor.execute(query, params or ())
            results = cursor.fetchall()
            return results
        except Exception as e:
            logger.error(f"Error in fetch_all PostgreSQL: {type(e).__name__}: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            logger.error(f"Params type: {type(params)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
        finally:
            self.return_connection(conn)
    
    def transaction(self, queries_params):
        """Execute multiple queries in a transaction"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            for query, params in queries_params:
                # Replace ? placeholders with %s for PostgreSQL
                query = query.replace('?', '%s')
                cursor.execute(query, params or ())
            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"Error in PostgreSQL transaction: {e}")
            raise
        finally:
            self.return_connection(conn)
    
    def close_all(self):
        """Close all connections in the pool"""
        with self._lock:
            if hasattr(self, '_pool'):
                # Mark as closing to prevent new connections
                self._is_closing = True
                
                # Close all tracked active connections first
                with self._active_connections_lock:
                    active_count = len(self._active_connections)
                    if active_count > 0:
                        logger.warning(f"Closing pool with {active_count} active connections")
                    
                    # Try to close each active connection cleanly
                    for conn in list(self._active_connections):
                        try:
                            conn.close()
                        except Exception as e:
                            logger.debug(f"Error closing active connection: {e}")
                    
                    # Clear the set
                    self._active_connections.clear()
                
                # Now close the pool
                try:
                    self._pool.closeall()
                    logger.info("Closed all PostgreSQL database connections")
                except Exception as e:
                    logger.error(f"Error closing connection pool: {e}")
                    
                # Mark as not initialized
                self._is_initialized = False


# Factory function to get the appropriate database manager
def get_db_manager():
    """Get the database manager based on configuration"""
    return PostgreSQLManager()


# Simplified interface for database operations
class Database:
    """High-level database abstraction for application code"""
    
    @staticmethod
    def ensure_pool_initialized():
        """Ensure the database pool is initialized"""
        return get_db_manager()._is_initialized
        
    @staticmethod
    def reconnect():
        """Force reconnection to the database by reinitializing the connection pool"""
        try:
            logger.info("Attempting to reconnect to database...")
            db_manager = get_db_manager()
            result = db_manager.reinitialize()
            if result:
                logger.info("Database connection pool successfully reinitialized")
            else:
                logger.error("Failed to reinitialize database connection pool")
            return result
        except Exception as e:
            logger.error(f"Error reconnecting to database: {str(e)}")
            return False
            
    @staticmethod
    def execute(query, params=None):
        """Execute a query and return cursor"""
        Database.ensure_pool_initialized()
        db_manager = get_db_manager()
        # Convert dict parameters to JSON strings if using PostgreSQL
        if params:
            params = Database._process_params(params)
        return db_manager.execute(query, params)
    
    @staticmethod
    def execute_many(query, params_list):
        """Execute many operations with the same query"""
        Database.ensure_pool_initialized()
        db_manager = get_db_manager()
        # Convert dict parameters to JSON strings
        if params_list:
            processed_params = []
            for params in params_list:
                processed_params.append(Database._process_params(params))
            params_list = processed_params
        return db_manager.execute_many(query, params_list)
    
    @staticmethod
    def fetch_one(query, params=None):
        """Execute a query and fetch one result"""
        Database.ensure_pool_initialized()
        # Add detailed logging
        params_str = str(params) if params else "None"
        logger.info(f"fetch_one query: {query}")
        logger.info(f"fetch_one params (before processing): {params_str}")
        processed_params = Database._process_params(params)
        logger.info(f"fetch_one params (after processing): {processed_params}")
        try:
            result = get_db_manager().fetch_one(query, processed_params)
            logger.info(f"fetch_one result: {result}")
            return result
        except Exception as e:
            logger.error(f"Error in fetch_one: {str(e)}")
            raise
    
    @staticmethod
    def fetch_all(query, params=None):
        """Execute a query and fetch all results"""
        Database.ensure_pool_initialized()
        # Add detailed logging
        params_str = str(params) if params else "None"
        logger.info(f"fetch_all query: {query}")
        logger.info(f"fetch_all params (before processing): {params_str}")
        processed_params = Database._process_params(params)
        logger.info(f"fetch_all params (after processing): {processed_params}")
        try:
            results = get_db_manager().fetch_all(query, processed_params)
            logger.info(f"fetch_all returned {len(results) if results else 0} rows")
            if results and len(results) > 0:
                logger.info(f"First row sample: {results[0]}")
            return results
        except Exception as e:
            logger.error(f"Error in fetch_all: {str(e)}")
            raise
    
    @staticmethod
    def transaction(queries_params):
        """Execute multiple queries in a transaction"""
        Database.ensure_pool_initialized()
        db_manager = get_db_manager()
        # Convert dict parameters to JSON strings
        processed_queries_params = []
        for query, params in queries_params:
            if params:
                params = Database._process_params(params)
            processed_queries_params.append((query, params))
        queries_params = processed_queries_params
        return db_manager.transaction(queries_params)
    
    @staticmethod
    def _process_params(params):
        """Process parameters for PostgreSQL compatibility
        Convert dictionaries to JSON strings"""
        import json
        
        if isinstance(params, dict):
            # Convert entire dict to JSON string
            return json.dumps(params)
        elif isinstance(params, (list, tuple)):
            # Process each item in the sequence
            processed = []
            for item in params:
                if isinstance(item, dict):
                    processed.append(json.dumps(item))
                else:
                    processed.append(item)
            return tuple(processed)
        return params
    
    # Add a static close method for convenience
    @staticmethod
    def close():
        """Close connection if appropriate for the database manager"""
        db_manager = get_db_manager()
        if hasattr(db_manager, 'close_all'):
            db_manager.close_all()

    @staticmethod
    def keep_alive():
        """Check database connection and reconnect if needed"""
        try:
            # First try a simple query to check connection status
            logger.debug("Database keep_alive check starting")
            result = Database.fetch_one("SELECT 1")
            if result:
                logger.debug("Database connection is healthy")
                return True
        except Exception as e:
            logger.warning(f"Database keep_alive check failed: {str(e)}")
            
            # If the query failed, attempt to reconnect
            try:
                logger.info("Attempting database reconnection")
                manager = get_db_manager()
                if manager and hasattr(manager, 'reinitialize'):
                    success = manager.reinitialize()
                    if success:
                        logger.info("Database reconnection successful")
                        return True
                    else:
                        logger.error("Database reconnection failed after reinitialize")
                        return False
                else:
                    logger.error("Database manager not available or doesn't support reinitialize")
                    return False
            except Exception as reconnect_error:
                logger.error(f"Database reconnection failed with error: {str(reconnect_error)}")
                return False
        
        return True


# Initialize database schema if needed
def init_database():
    """Initialize the database schema based on the configured database type"""
    db_manager = get_db_manager()
    
    # PostgreSQL - schema is initialized via postgres_init.sql in Docker
    # This just tests the connection
    try:
        version = db_manager.fetch_one("SELECT version();")
        logger.info(f"PostgreSQL schema already initialized: {version[0]}")
    except psycopg2.Error as e:
        logger.error(f"Error connecting to PostgreSQL: {e}")


# Test the database connection
if __name__ == "__main__":
    print(f"Testing PostgreSQL database connection...")
    
    try:
        # Initialize database
        init_database()
        
        # Test basic queries
        db = Database()
        
        # PostgreSQL test
        result = db.fetch_one("SELECT version();")
        print(f"PostgreSQL version: {result[0]}")
        
        print("Database connection test successful!")
        
    except Exception as e:
        print(f"Database connection test failed: {e}")
        sys.exit(1) 