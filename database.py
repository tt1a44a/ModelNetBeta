#!/usr/bin/env python3
"""
Database Abstraction Module for Ollama Scanner
Provides a unified interface for working with both SQLite and PostgreSQL databases
"""

import os
import sys
import time
import sqlite3
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Union
from dotenv import load_dotenv

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
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite").lower()
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "ollama_instances.db")

# PostgreSQL package is only imported if we're using PostgreSQL
if DATABASE_TYPE == "postgres":
    try:
        import psycopg2
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


class SQLiteManager:
    """SQLite database manager for Ollama Scanner"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SQLiteManager, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance
    
    def _initialize(self):
        """Initialize the SQLite connection"""
        self.db_path = SQLITE_DB_PATH
        logger.info(f"Initializing SQLite database: {self.db_path}")
        
        # Ensure the database file exists and has correct permissions
        db_file = Path(self.db_path)
        if not db_file.exists():
            logger.warning(f"Database file not found: {self.db_path}")
            # We'll create it when we connect
        
        # Check if database directory exists
        db_dir = db_file.parent
        if not db_dir.exists():
            logger.info(f"Creating database directory: {db_dir}")
            db_dir.mkdir(parents=True, exist_ok=True)
    
    def get_connection(self):
        """Get a new SQLite connection"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Allow dict-like access to rows
            return conn
        except sqlite3.Error as e:
            logger.error(f"Error connecting to SQLite database: {e}")
            raise
    
    def execute(self, query, params=None):
        """Execute a query with optional parameters and return cursor"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
            return cursor
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error executing SQLite query: {e}")
            logger.debug(f"Query: {query}")
            logger.debug(f"Params: {params}")
            raise
        finally:
            conn.close()
    
    def execute_many(self, query, params_list):
        """Execute many operations with the same query but different parameters"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error executing SQLite batch query: {e}")
            raise
        finally:
            conn.close()
    
    def fetch_one(self, query, params=None):
        """Execute a query and fetch one result"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            return cursor.fetchone()
        except sqlite3.Error as e:
            logger.error(f"Error fetching from SQLite: {e}")
            raise
        finally:
            conn.close()
    
    def fetch_all(self, query, params=None):
        """Execute a query and fetch all results"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching from SQLite: {e}")
            raise
        finally:
            conn.close()
    
    def transaction(self, queries_params):
        """Execute multiple queries in a transaction"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            for query, params in queries_params:
                cursor.execute(query, params or ())
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error in SQLite transaction: {e}")
            raise
        finally:
            conn.close()


class PostgreSQLManager:
    """PostgreSQL database manager with connection pooling for Ollama Scanner"""
    _instance = None
    _lock = threading.Lock()
    
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
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=MIN_CONNECTIONS,
                maxconn=MAX_CONNECTIONS,
                dbname=PG_DB_NAME,
                user=PG_DB_USER,
                password=PG_DB_PASSWORD,
                host=PG_DB_HOST,
                port=PG_DB_PORT
            )
            # Test the connection
            conn = self._pool.getconn()
            with conn.cursor() as cursor:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]
                logger.info(f"Connected to PostgreSQL: {version}")
            self._pool.putconn(conn)
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection pool: {str(e)}")
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
                logger.warning(f"Connection pool exhausted, retry {attempt+1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # exponential backoff
                else:
                    logger.error(f"Failed to get database connection: {e}")
                    raise
    
    def return_connection(self, conn):
        """Return a connection to the pool"""
        self._pool.putconn(conn)
    
    def execute(self, query, params=None):
        """Execute a query with optional parameters and return cursor"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Replace SQLite parameter style with PostgreSQL
            query = query.replace('?', '%s')
            cursor.execute(query, params or ())
            conn.commit()
            return cursor
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"Error executing PostgreSQL query: {e}")
            logger.debug(f"Query: {query}")
            logger.debug(f"Params: {params}")
            raise
        finally:
            self.return_connection(conn)
    
    def execute_many(self, query, params_list):
        """Execute many operations with the same query but different parameters"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Replace SQLite parameter style with PostgreSQL
            query = query.replace('?', '%s')
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
        """Execute a query and fetch one result"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(cursor_factory=DictCursor)
            # Replace SQLite parameter style with PostgreSQL
            query = query.replace('?', '%s')
            cursor.execute(query, params or ())
            return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error fetching from PostgreSQL: {e}")
            raise
        finally:
            self.return_connection(conn)
    
    def fetch_all(self, query, params=None):
        """Execute a query and fetch all results"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(cursor_factory=DictCursor)
            # Replace SQLite parameter style with PostgreSQL
            query = query.replace('?', '%s')
            cursor.execute(query, params or ())
            return cursor.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Error fetching from PostgreSQL: {e}")
            raise
        finally:
            self.return_connection(conn)
    
    def transaction(self, queries_params):
        """Execute multiple queries in a transaction"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            for query, params in queries_params:
                # Replace SQLite parameter style with PostgreSQL
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
        if hasattr(self, '_pool'):
            self._pool.closeall()
            logger.info("Closed all PostgreSQL database connections")


# Factory function to get the appropriate database manager
def get_db_manager():
    """Get the database manager based on configuration"""
    if DATABASE_TYPE == "postgres":
        return PostgreSQLManager()
    else:
        return SQLiteManager()


# Simplified interface for database operations
class Database:
    """High-level database abstraction for application code"""
    
    @staticmethod
    def execute(query, params=None):
        """Execute a query and return cursor"""
        db_manager = get_db_manager()
        # Convert dict parameters to JSON strings if using PostgreSQL
        if DATABASE_TYPE == "postgres" and params:
            params = Database._process_params(params)
        return db_manager.execute(query, params)
    
    @staticmethod
    def execute_many(query, params_list):
        """Execute many operations with the same query"""
        db_manager = get_db_manager()
        # Convert dict parameters to JSON strings if using PostgreSQL
        if DATABASE_TYPE == "postgres" and params_list:
            processed_params = []
            for params in params_list:
                processed_params.append(Database._process_params(params))
            params_list = processed_params
        return db_manager.execute_many(query, params_list)
    
    @staticmethod
    def fetch_one(query, params=None):
        """Execute a query and fetch one result"""
        db_manager = get_db_manager()
        # Convert dict parameters to JSON strings if using PostgreSQL
        if DATABASE_TYPE == "postgres" and params:
            params = Database._process_params(params)
        return db_manager.fetch_one(query, params)
    
    @staticmethod
    def fetch_all(query, params=None):
        """Execute a query and fetch all results"""
        db_manager = get_db_manager()
        # Convert dict parameters to JSON strings if using PostgreSQL
        if DATABASE_TYPE == "postgres" and params:
            params = Database._process_params(params)
        return db_manager.fetch_all(query, params)
    
    @staticmethod
    def transaction(queries_params):
        """Execute multiple queries in a transaction"""
        db_manager = get_db_manager()
        # Convert dict parameters to JSON strings if using PostgreSQL
        if DATABASE_TYPE == "postgres":
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
        
    @staticmethod
    def ensure_pool_initialized():
        """Ensure that the database connection pool is initialized
        This is a no-op for SQLite, but required for PostgreSQL"""
        if DATABASE_TYPE == "postgres":
            # Make sure the connection pool is initialized
            db_manager = get_db_manager()
            # Just getting the manager will initialize the pool
            return True
        return True


# Initialize database schema if needed
def init_database():
    """Initialize the database schema based on the configured database type"""
    db_manager = get_db_manager()
    
    if DATABASE_TYPE == "sqlite":
        # SQLite schema initialization
        queries = [
            # Create endpoints table
            ("""
            CREATE TABLE IF NOT EXISTS endpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                port INTEGER NOT NULL,
                scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified INTEGER DEFAULT 0,
                verification_date TIMESTAMP,
                is_honeypot INTEGER DEFAULT 0,
                honeypot_reason TEXT,
                is_active INTEGER DEFAULT 1,
                inactive_reason TEXT,
                last_check_date TIMESTAMP,
                UNIQUE(ip, port)
            );
            """, None),
            
            # Create verified_endpoints table
            ("""
            CREATE TABLE IF NOT EXISTS verified_endpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_id INTEGER NOT NULL,
                verification_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (endpoint_id) REFERENCES endpoints (id) ON DELETE CASCADE,
                UNIQUE(endpoint_id)
            );
            """, None),
            
            # Create models table
            ("""
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                parameter_size TEXT,
                quantization_level TEXT,
                size_mb REAL,
                FOREIGN KEY (endpoint_id) REFERENCES endpoints (id) ON DELETE CASCADE,
                UNIQUE(endpoint_id, name)
            );
            """, None),
            
            # Create benchmark_results table
            ("""
            CREATE TABLE IF NOT EXISTS benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_id INTEGER NOT NULL,
                model_id INTEGER,
                test_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                avg_response_time REAL,
                tokens_per_second REAL,
                first_token_latency REAL,
                throughput_tokens REAL,
                throughput_time REAL,
                context_500_tps REAL,
                context_1000_tps REAL,
                context_2000_tps REAL,
                max_concurrent_requests INTEGER,
                concurrency_success_rate REAL,
                concurrency_avg_time REAL,
                success_rate REAL,
                FOREIGN KEY (endpoint_id) REFERENCES endpoints (id) ON DELETE CASCADE,
                FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE SET NULL
            );
            """, None),
            
            # Create a servers view for backward compatibility
            ("""
            CREATE VIEW IF NOT EXISTS servers AS
            SELECT 
                e.id, 
                e.ip, 
                e.port, 
                e.scan_date
            FROM 
                endpoints e
            JOIN
                verified_endpoints ve ON e.id = ve.endpoint_id;
            """, None)
        ]
        
        # Execute all schema queries
        for query, params in queries:
            try:
                db_manager.execute(query, params)
            except sqlite3.Error as e:
                logger.error(f"Error initializing SQLite schema: {e}")
                logger.error(f"Query: {query}")
    
    elif DATABASE_TYPE == "postgres":
        # PostgreSQL - schema is initialized via postgres_init.sql in Docker
        # This just tests the connection
        try:
            version = db_manager.fetch_one("SELECT version();")
            logger.info(f"PostgreSQL schema already initialized: {version[0]}")
        except Exception as e:
            if DATABASE_TYPE == "postgres":
                logger.error(f"Error connecting to PostgreSQL: {e}")


# Test the database connection
if __name__ == "__main__":
    db_type = "SQLite" if DATABASE_TYPE == "sqlite" else "PostgreSQL"
    print(f"Testing {db_type} database connection...")
    
    try:
        # Initialize database
        init_database()
        
        # Test basic queries
        db = Database()
        
        if DATABASE_TYPE == "sqlite":
            # SQLite test
            result = db_manager = get_db_manager()
            result = db_manager.fetch_one("SELECT sqlite_version();")
            print(f"SQLite version: {result[0]}")
        else:
            # PostgreSQL test
            db_manager = get_db_manager()
            result = db_manager.fetch_one("SELECT version();")
            print(f"PostgreSQL version: {result[0]}")
        
        print("Database connection test successful!")
        
    except Exception as e:
        print(f"Database connection test failed: {e}")
        sys.exit(1) 