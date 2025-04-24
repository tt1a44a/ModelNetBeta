#!/usr/bin/env python3
"""
PostgreSQL Connection Pool for Ollama Scanner
Handles connection management and provides a centralized interface for database operations.
"""

import os
import logging
import time
import threading
from typing import Any, Dict, List, Tuple, Optional, Union
import psycopg2
from psycopg2 import pool
from psycopg2.extras import DictCursor, execute_values
from dotenv import load_dotenv

# Added by migration script
from database import Database, init_database

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("db_pool.log")
    ]
)
logger = logging.getLogger('db_pool')

# Load environment variables
load_dotenv()

# Default connection parameters
DEFAULT_DB_NAME = "ollama_scanner"
DEFAULT_DB_USER = "ollama"
DEFAULT_DB_PASSWORD = "ollama_scanner_password"
DEFAULT_DB_HOST = "localhost"
DEFAULT_DB_PORT = "5432"

# Get connection parameters from environment or use defaults
DB_NAME = os.getenv("POSTGRES_DB", DEFAULT_DB_NAME)
DB_USER = os.getenv("POSTGRES_USER", DEFAULT_DB_USER)
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", DEFAULT_DB_PASSWORD)
DB_HOST = os.getenv("POSTGRES_HOST", DEFAULT_DB_HOST)
DB_PORT = os.getenv("POSTGRES_PORT", DEFAULT_DB_PORT)

# Pool configuration
MIN_CONNECTIONS = int(os.getenv("DB_MIN_CONNECTIONS", "5"))
MAX_CONNECTIONS = int(os.getenv("DB_MAX_CONNECTIONS", "50"))
CONNECTION_TIMEOUT = int(os.getenv("DB_CONNECTION_TIMEOUT", "30"))

# Singleton pattern for the connection pool
class DatabasePool:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabasePool, cls).__new__(cls)
                cls._instance._initialize_pool()
            return cls._instance
    
    def _initialize_pool(self):
        """Initialize the connection pool"""
        logger.info(f"Initializing database connection pool (min={MIN_CONNECTIONS}, max={MAX_CONNECTIONS})")
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=MIN_CONNECTIONS,
                maxconn=MAX_CONNECTIONS,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                host=DB_HOST,
                port=DB_PORT
            )
            logger.info("Database connection pool initialized successfully")
            
            # Test the connection
            conn = self._pool.getconn()
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            logger.info(f"Connected to PostgreSQL: {version}")
            self._pool.putconn(conn)
            
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {str(e)}")
            raise
    
    def get_connection(self):
        """Get a connection from the pool with retry logic"""
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                connection = self._pool.getconn()
                return connection
            except psycopg2.pool.PoolError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Connection pool exhausted. Retrying in {retry_delay}s (attempt {attempt+1}/{max_retries})...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to get database connection after {max_retries} attempts: {str(e)}")
                    raise
    
    def return_connection(self, conn):
        """Return a connection to the pool"""
        self._pool.putconn(conn)
    
    def close_all(self):
        """Close all connections in the pool"""
        if hasattr(self, '_pool'):
            self._pool.closeall()
            logger.info("Closed all database connections")


# Context manager for database connections
class DatabaseConnection:
    def __init__(self, dict_cursor=False):
        self.pool = DatabasePool()
        self.dict_cursor = dict_cursor
        self.conn = None
        self.cursor = None
    
    def __enter__(self):
        self.conn = self.pool.get_connection()
        if self.dict_cursor:
            self.cursor = self.conn.cursor(cursor_factory=DictCursor)
        else:
            self.cursor = self.conn.cursor()
        return self.cursor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error(f"Database operation failed: {exc_val}")
            self.conn.rollback()
        else:
            self.conn.commit()
        
        self.cursor.close()
        self.pool.return_connection(self.conn)


# Utility functions for common database operations
def execute_query(query: str, params: tuple = None) -> None:
    """Execute a query without returning results"""
    with DatabaseConnection() as cursor:
        cursor.execute(query, params or ())


def fetch_one(query: str, params: tuple = None) -> Optional[tuple]:
    """Execute a query and return the first row"""
    with DatabaseConnection() as cursor:
        cursor.execute(query, params or ())
        return cursor.fetchone()


def fetch_all(query: str, params: tuple = None) -> List[tuple]:
    """Execute a query and return all rows"""
    with DatabaseConnection() as cursor:
        cursor.execute(query, params or ())
        return cursor.fetchall()


def fetch_dict(query: str, params: tuple = None) -> Optional[Dict]:
    """Execute a query and return the first row as a dictionary"""
    with DatabaseConnection(dict_cursor=True) as cursor:
        cursor.execute(query, params or ())
        return cursor.fetchone()


def fetch_dict_all(query: str, params: tuple = None) -> List[Dict]:
    """Execute a query and return all rows as dictionaries"""
    with DatabaseConnection(dict_cursor=True) as cursor:
        cursor.execute(query, params or ())
        return cursor.fetchall()


def execute_batch(query: str, params_list: List[tuple]) -> None:
    """Execute a batch of queries with different parameters"""
    with DatabaseConnection() as cursor:
        execute_values(cursor, query, params_list)


def execute_transaction(queries: List[Tuple[str, Optional[tuple]]]) -> None:
    """Execute multiple queries in a single transaction"""
    with DatabaseConnection() as cursor:
        for query, params in queries:
            cursor.execute(query, params or ())


# Test the connection pool
if __name__ == "__main__":
    try:
        logger.info("Testing database connection pool...")
        
        # Test basic query
        version = fetch_one("SELECT version();")
        logger.info(f"PostgreSQL version: {version[0]}")
        
        # Test concurrent connections
        def test_connection(i):
            result = fetch_one("SELECT %s AS test;", (f"Connection {i}",))
            logger.info(f"Thread {i} result: {result[0]}")
        
        threads = []
        for i in range(10):
            thread = threading.Thread(target=test_connection, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        logger.info("Database connection pool test completed successfully")
        
    except Exception as e:
        logger.error(f"Error testing database connection: {str(e)}")
    finally:
        # Clean up
        pool_instance = DatabasePool()
        pool_instance.close_all() 