#!/usr/bin/env python3
"""
Database Schema Issues Check Script

This script performs a comprehensive check of the Ollama Scanner database schema
to identify potential issues, inconsistencies, or opportunities for optimization.
"""

import os
import sys
import logging
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from datetime import datetime
import tabulate
from typing import List, Dict, Any, Optional, Tuple

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("db_schema_check.log")
    ]
)
logger = logging.getLogger('db_schema_check')

# Load environment variables
load_dotenv()

# PostgreSQL connection details
PG_DB_NAME = os.getenv("POSTGRES_DB", "ollama_scanner")
PG_DB_USER = os.getenv("POSTGRES_USER", "ollama")
PG_DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ollama_scanner_password")
PG_DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_DB_PORT = os.getenv("POSTGRES_PORT", "5433")  # Default to 5433 (port forwarding)

class SchemaChecker:
    """Class to check database schema for issues and optimization opportunities"""
    
    def __init__(self):
        """Initialize the schema checker"""
        self.conn = None
        self.issues = []
        self.warnings = []
        self.info = []
        self.connect()
    
    def connect(self):
        """Connect to the PostgreSQL database"""
        try:
            logger.info(f"Connecting to PostgreSQL: {PG_DB_HOST}:{PG_DB_PORT}/{PG_DB_NAME}")
            self.conn = psycopg2.connect(
                dbname=PG_DB_NAME,
                user=PG_DB_USER,
                password=PG_DB_PASSWORD,
                host=PG_DB_HOST,
                port=PG_DB_PORT
            )
            logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL: {e}")
            sys.exit(1)
    
    def check_all(self):
        """Run all schema checks"""
        logger.info("Starting schema checks...")
        
        # Basic structure checks
        self.check_tables_exist()
        self.check_columns()
        self.check_constraints()
        self.check_indexes()
        
        # View checks
        self.check_views()
        
        # Data consistency checks
        self.check_data_consistency()
        
        # Performance checks
        self.check_table_bloat()
        self.check_index_usage()
        
        # Security checks
        self.check_permissions()
        
        logger.info("Schema checks completed")
        
        # Generate report
        return self.generate_report()
    
    def check_tables_exist(self):
        """Check that all expected tables exist"""
        expected_tables = [
            'endpoints', 'verified_endpoints', 'models', 
            'benchmark_results', 'metadata', 'schema_version'
        ]
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """)
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            # Check for missing tables
            missing_tables = [table for table in expected_tables if table not in existing_tables]
            if missing_tables:
                self.issues.append({
                    'type': 'Missing Tables',
                    'description': f"Tables not found: {', '.join(missing_tables)}",
                    'impact': 'High',
                    'recommendation': 'Create the missing tables using the schema definition'
                })
            
            # Check for unexpected tables
            extra_tables = [table for table in existing_tables if table not in expected_tables 
                           and not table.startswith('pg_') and table != 'servers']
            if extra_tables:
                self.info.append({
                    'type': 'Extra Tables',
                    'description': f"Unexpected tables found: {', '.join(extra_tables)}",
                    'impact': 'Low',
                    'recommendation': 'Review and determine if they are needed'
                })
                
        except Exception as e:
            logger.error(f"Error checking tables: {e}")
            self.issues.append({
                'type': 'Error',
                'description': f"Failed to check tables: {e}",
                'impact': 'High',
                'recommendation': 'Fix the database connection or permissions'
            })
    
    def check_columns(self):
        """Check table columns for issues"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Get all columns
            cursor.execute("""
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name IN ('endpoints', 'verified_endpoints', 'models', 'benchmark_results', 'metadata')
                ORDER BY table_name, ordinal_position
            """)
            
            columns = cursor.fetchall()
            
            # Check for NULL constraints on important columns
            critical_columns = [
                ('endpoints', 'ip'), ('endpoints', 'port'),
                ('verified_endpoints', 'endpoint_id'),
                ('models', 'name'), ('models', 'endpoint_id')
            ]
            
            for column in columns:
                table = column['table_name']
                col_name = column['column_name']
                nullable = column['is_nullable'] == 'YES'
                
                # Check if critical columns are nullable
                if (table, col_name) in critical_columns and nullable:
                    self.issues.append({
                        'type': 'Nullable Column',
                        'description': f"Critical column {table}.{col_name} is nullable",
                        'impact': 'Medium',
                        'recommendation': f"ALTER TABLE {table} ALTER COLUMN {col_name} SET NOT NULL"
                    })
                
                # Check for missing timestamp fields
                if col_name.endswith('_date') and table != 'metadata':
                    cursor.execute(f"""
                        SELECT count(*) FROM {table} 
                        WHERE {col_name} IS NULL AND id IS NOT NULL
                    """)
                    null_count = cursor.fetchone()[0]
                    if null_count > 0:
                        self.warnings.append({
                            'type': 'NULL Values',
                            'description': f"{null_count} NULL values in {table}.{col_name}",
                            'impact': 'Medium',
                            'recommendation': f"Update NULL values with CURRENT_TIMESTAMP"
                        })
                
        except Exception as e:
            logger.error(f"Error checking columns: {e}")
            self.issues.append({
                'type': 'Error',
                'description': f"Failed to check columns: {e}",
                'impact': 'High',
                'recommendation': 'Fix the database connection or permissions'
            })
    
    def check_constraints(self):
        """Check constraints for issues"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Check foreign key constraints
            cursor.execute("""
                SELECT
                    tc.constraint_name,
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name,
                    rc.delete_rule,
                    rc.update_rule
                FROM
                    information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                JOIN information_schema.referential_constraints AS rc
                    ON tc.constraint_name = rc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
            """)
            
            foreign_keys = cursor.fetchall()
            
            # Expected foreign key constraints
            expected_fks = [
                ('verified_endpoints', 'endpoint_id', 'endpoints', 'id'),
                ('models', 'endpoint_id', 'endpoints', 'id'),
                ('benchmark_results', 'endpoint_id', 'endpoints', 'id'),
                ('benchmark_results', 'model_id', 'models', 'id')
            ]
            
            # Check for missing foreign keys
            existing_fks = [(fk['table_name'], fk['column_name'], 
                           fk['foreign_table_name'], fk['foreign_column_name']) 
                          for fk in foreign_keys]
            
            missing_fks = [fk for fk in expected_fks if fk not in existing_fks]
            if missing_fks:
                for fk in missing_fks:
                    self.issues.append({
                        'type': 'Missing Foreign Key',
                        'description': f"Missing FK from {fk[0]}.{fk[1]} to {fk[2]}.{fk[3]}",
                        'impact': 'High',
                        'recommendation': f"ALTER TABLE {fk[0]} ADD CONSTRAINT fk_{fk[0]}_{fk[1]} " +
                                         f"FOREIGN KEY ({fk[1]}) REFERENCES {fk[2]}({fk[3]}) ON DELETE CASCADE"
                    })
            
            # Check DELETE rules for foreign keys (should be CASCADE for our schema)
            for fk in foreign_keys:
                if fk['delete_rule'] != 'CASCADE':
                    self.warnings.append({
                        'type': 'Foreign Key Rule',
                        'description': f"FK {fk['constraint_name']} has {fk['delete_rule']} instead of CASCADE",
                        'impact': 'Medium',
                        'recommendation': f"ALTER TABLE {fk['table_name']} DROP CONSTRAINT {fk['constraint_name']}, " +
                                         f"then add it back with ON DELETE CASCADE"
                    })
            
            # Check unique constraints
            cursor.execute("""
                SELECT tc.table_name, tc.constraint_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.constraint_type = 'UNIQUE'
                    AND tc.table_schema = 'public'
                ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position
            """)
            
            unique_constraints = cursor.fetchall()
            
            # Group unique constraints by table and constraint name
            constraint_dict = {}
            for uc in unique_constraints:
                key = (uc['table_name'], uc['constraint_name'])
                if key not in constraint_dict:
                    constraint_dict[key] = []
                constraint_dict[key].append(uc['column_name'])
            
            # Expected unique constraints
            expected_uniques = {
                'endpoints': [('ip', 'port')],
                'verified_endpoints': [('endpoint_id',)],
                'models': [('endpoint_id', 'name')]
            }
            
            # Check for missing unique constraints
            for table, constraints in expected_uniques.items():
                for constraint in constraints:
                    found = False
                    for key, columns in constraint_dict.items():
                        if key[0] == table and set(columns) == set(constraint):
                            found = True
                            break
                    
                    if not found:
                        self.issues.append({
                            'type': 'Missing Unique Constraint',
                            'description': f"Missing unique constraint on {table}({', '.join(constraint)})",
                            'impact': 'Medium',
                            'recommendation': f"ALTER TABLE {table} ADD CONSTRAINT {table}_{'_'.join(constraint)}_key " +
                                             f"UNIQUE ({', '.join(constraint)})"
                        })
                        
        except Exception as e:
            logger.error(f"Error checking constraints: {e}")
            self.issues.append({
                'type': 'Error',
                'description': f"Failed to check constraints: {e}",
                'impact': 'High',
                'recommendation': 'Fix the database connection or permissions'
            })
    
    def check_indexes(self):
        """Check indexes for issues or missing indexes"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Get all indexes
            cursor.execute("""
                SELECT
                    t.relname AS table_name,
                    i.relname AS index_name,
                    array_agg(a.attname) AS column_names,
                    ix.indisunique AS is_unique,
                    ix.indisprimary AS is_primary
                FROM
                    pg_class t,
                    pg_class i,
                    pg_index ix,
                    pg_attribute a
                WHERE
                    t.oid = ix.indrelid
                    AND i.oid = ix.indexrelid
                    AND a.attrelid = t.oid
                    AND a.attnum = ANY(ix.indkey)
                    AND t.relkind = 'r'
                    AND t.relname NOT LIKE 'pg_%'
                GROUP BY
                    t.relname,
                    i.relname,
                    ix.indisunique,
                    ix.indisprimary
                ORDER BY
                    t.relname,
                    i.relname;
            """)
            
            indexes = cursor.fetchall()
            index_dict = {}
            
            for idx in indexes:
                table = idx['table_name']
                if table not in index_dict:
                    index_dict[table] = []
                index_dict[table].append({
                    'name': idx['index_name'],
                    'columns': idx['column_names'],
                    'is_unique': idx['is_unique'],
                    'is_primary': idx['is_primary']
                })
            
            # Expected indexes (excluding primary keys and unique constraints which already have indexes)
            expected_indexes = {
                'endpoints': [('ip',), ('verified',), ('is_honeypot',), ('is_active',), 
                             ('verified', 'is_honeypot'), ('verified', 'is_active')],
                'verified_endpoints': [('endpoint_id',)],
                'models': [('endpoint_id',), ('name',)],
                'benchmark_results': [('endpoint_id',), ('model_id',), ('test_date',)],
                'metadata': [('key',)]
            }
            
            # Check for missing indexes
            for table, idx_list in expected_indexes.items():
                if table not in index_dict:
                    for columns in idx_list:
                        self.issues.append({
                            'type': 'Missing Index',
                            'description': f"Missing index on {table}({', '.join(columns)})",
                            'impact': 'Medium',
                            'recommendation': f"CREATE INDEX idx_{table}_{'_'.join(columns)} " +
                                             f"ON {table}({', '.join(columns)})"
                        })
                else:
                    table_indexes = index_dict[table]
                    for columns in idx_list:
                        found = False
                        for idx in table_indexes:
                            if set(idx['columns']) == set(columns):
                                found = True
                                break
                        
                        if not found:
                            self.warnings.append({
                                'type': 'Missing Index',
                                'description': f"Missing index on {table}({', '.join(columns)})",
                                'impact': 'Medium',
                                'recommendation': f"CREATE INDEX idx_{table}_{'_'.join(columns)} " +
                                                 f"ON {table}({', '.join(columns)})"
                            })
            
            # Check for redundant indexes
            for table, idx_list in index_dict.items():
                for i, idx1 in enumerate(idx_list):
                    for j, idx2 in enumerate(idx_list):
                        if i != j and not idx1['is_primary'] and not idx2['is_primary']:
                            # Check if one index is a subset of another
                            if set(idx1['columns']).issubset(set(idx2['columns'])):
                                if idx1['columns'][0] == idx2['columns'][0]:  # First column is the same
                                    self.info.append({
                                        'type': 'Redundant Index',
                                        'description': f"Index {idx1['name']} might be redundant with {idx2['name']}",
                                        'impact': 'Low',
                                        'recommendation': f"Consider dropping {idx1['name']} if queries use {idx2['name']}"
                                    })
                
        except Exception as e:
            logger.error(f"Error checking indexes: {e}")
            self.issues.append({
                'type': 'Error',
                'description': f"Failed to check indexes: {e}",
                'impact': 'High',
                'recommendation': 'Fix the database connection or permissions'
            })
    
    def check_views(self):
        """Check views for issues"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Get all views
            cursor.execute("""
                SELECT table_name, view_definition
                FROM information_schema.views
                WHERE table_schema = 'public'
            """)
            
            views = cursor.fetchall()
            
            for view in views:
                view_name = view['table_name']
                definition = view['view_definition']
                
                # Check for servers view INSTEAD OF triggers
                if view_name == 'servers':
                    cursor.execute("""
                        SELECT trigger_name
                        FROM information_schema.triggers
                        WHERE event_object_table = 'servers'
                        AND action_timing = 'INSTEAD OF'
                    """)
                    
                    triggers = cursor.fetchall()
                    expected_triggers = ['servers_insert_instead', 'servers_update_instead', 'servers_delete_instead']
                    
                    trigger_names = [t['trigger_name'] for t in triggers]
                    missing_triggers = [t for t in expected_triggers if t not in trigger_names]
                    
                    if missing_triggers:
                        self.issues.append({
                            'type': 'Missing View Triggers',
                            'description': f"View 'servers' is missing INSTEAD OF triggers: {', '.join(missing_triggers)}",
                            'impact': 'High',
                            'recommendation': "Run the fix_servers_view.sql script to add the missing triggers"
                        })
                    else:
                        self.info.append({
                            'type': 'View Triggers',
                            'description': "View 'servers' has all required INSTEAD OF triggers",
                            'impact': 'Low',
                            'recommendation': "No action needed"
                        })
                
        except Exception as e:
            logger.error(f"Error checking views: {e}")
            self.issues.append({
                'type': 'Error',
                'description': f"Failed to check views: {e}",
                'impact': 'High',
                'recommendation': 'Fix the database connection or permissions'
            })
    
    def check_data_consistency(self):
        """Check for data consistency issues across tables"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Check for verified=1 endpoints without corresponding verified_endpoints rows
            cursor.execute("""
                SELECT COUNT(*) 
                FROM endpoints e
                WHERE e.verified = 1
                AND NOT EXISTS (
                    SELECT 1 FROM verified_endpoints ve 
                    WHERE ve.endpoint_id = e.id
                )
            """)
            
            inconsistent_verified = cursor.fetchone()[0]
            if inconsistent_verified > 0:
                self.issues.append({
                    'type': 'Data Inconsistency',
                    'description': f"{inconsistent_verified} endpoints have verified=1 but no verified_endpoints record",
                    'impact': 'High',
                    'recommendation': """
                        INSERT INTO verified_endpoints (endpoint_id, verification_date)
                        SELECT id, COALESCE(verification_date, CURRENT_TIMESTAMP) 
                        FROM endpoints
                        WHERE verified = 1
                        AND NOT EXISTS (
                            SELECT 1 FROM verified_endpoints ve 
                            WHERE ve.endpoint_id = id
                        )
                    """
                })
            
            # Check for verified_endpoints rows without corresponding endpoints with verified=1
            cursor.execute("""
                SELECT COUNT(*)
                FROM verified_endpoints ve
                JOIN endpoints e ON ve.endpoint_id = e.id
                WHERE e.verified != 1
            """)
            
            inconsistent_ve = cursor.fetchone()[0]
            if inconsistent_ve > 0:
                self.issues.append({
                    'type': 'Data Inconsistency',
                    'description': f"{inconsistent_ve} verified_endpoints have corresponding endpoints with verified != 1",
                    'impact': 'High',
                    'recommendation': """
                        UPDATE endpoints
                        SET verified = 1,
                            verification_date = CURRENT_TIMESTAMP
                        WHERE id IN (
                            SELECT endpoint_id FROM verified_endpoints
                        )
                        AND verified != 1
                    """
                })
            
            # Check for orphaned models (models with no corresponding endpoint)
            cursor.execute("""
                SELECT COUNT(*)
                FROM models m
                WHERE NOT EXISTS (
                    SELECT 1 FROM endpoints e
                    WHERE e.id = m.endpoint_id
                )
            """)
            
            orphaned_models = cursor.fetchone()[0]
            if orphaned_models > 0:
                self.warnings.append({
                    'type': 'Orphaned Records',
                    'description': f"{orphaned_models} models have no corresponding endpoint",
                    'impact': 'Medium',
                    'recommendation': """
                        DELETE FROM models
                        WHERE NOT EXISTS (
                            SELECT 1 FROM endpoints e
                            WHERE e.id = models.endpoint_id
                        )
                    """
                })
            
            # Check for orphaned benchmark results
            cursor.execute("""
                SELECT COUNT(*)
                FROM benchmark_results br
                WHERE NOT EXISTS (
                    SELECT 1 FROM endpoints e
                    WHERE e.id = br.endpoint_id
                )
            """)
            
            orphaned_benchmarks = cursor.fetchone()[0]
            if orphaned_benchmarks > 0:
                self.warnings.append({
                    'type': 'Orphaned Records',
                    'description': f"{orphaned_benchmarks} benchmark results have no corresponding endpoint",
                    'impact': 'Medium',
                    'recommendation': """
                        DELETE FROM benchmark_results
                        WHERE NOT EXISTS (
                            SELECT 1 FROM endpoints e
                            WHERE e.id = benchmark_results.endpoint_id
                        )
                    """
                })
                
        except Exception as e:
            logger.error(f"Error checking data consistency: {e}")
            self.issues.append({
                'type': 'Error',
                'description': f"Failed to check data consistency: {e}",
                'impact': 'High',
                'recommendation': 'Fix the database connection or permissions'
            })
    
    def check_table_bloat(self):
        """Check for table bloat (tables that need vacuuming)"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Simple check for potential bloat
            cursor.execute("""
                SELECT schemaname, relname, n_dead_tup, n_live_tup,
                       round(n_dead_tup::numeric / NULLIF((n_live_tup + n_dead_tup), 0), 2) AS dead_ratio
                FROM pg_stat_user_tables
                WHERE n_dead_tup > 0
                ORDER BY dead_ratio DESC
            """)
            
            bloated_tables = cursor.fetchall()
            
            for table in bloated_tables:
                if table['dead_ratio'] > 0.2:  # More than 20% dead tuples
                    self.warnings.append({
                        'type': 'Table Bloat',
                        'description': f"Table {table['relname']} has {table['n_dead_tup']} dead tuples ({table['dead_ratio'] * 100:.1f}% of total)",
                        'impact': 'Medium',
                        'recommendation': f"VACUUM ANALYZE {table['relname']}"
                    })
                
        except Exception as e:
            logger.error(f"Error checking table bloat: {e}")
            self.info.append({
                'type': 'Info',
                'description': f"Could not check table bloat: {e}",
                'impact': 'Low',
                'recommendation': 'Run VACUUM ANALYZE periodically'
            })
    
    def check_index_usage(self):
        """Check for unused indexes"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Check for unused indexes
            cursor.execute("""
                SELECT
                    idxst.schemaname AS schema_name,
                    idxst.relname AS table_name,
                    indexrelname AS index_name,
                    idxst.idx_scan AS index_scans,
                    pg_size_pretty(pg_relation_size(idxst.indexrelid)) AS index_size
                FROM
                    pg_stat_user_indexes idxst
                JOIN
                    pg_index idx ON idx.indexrelid = idxst.indexrelid
                WHERE
                    idxst.idx_scan = 0      -- Index has never been scanned
                    AND idx.indisunique IS FALSE -- Not a unique index
                ORDER BY
                    pg_relation_size(idxst.indexrelid) DESC
            """)
            
            unused_indexes = cursor.fetchall()
            
            for idx in unused_indexes:
                self.info.append({
                    'type': 'Unused Index',
                    'description': f"Index {idx['index_name']} on {idx['table_name']} (size: {idx['index_size']}) has never been used",
                    'impact': 'Low',
                    'recommendation': f"Consider dropping: DROP INDEX {idx['index_name']}"
                })
                
        except Exception as e:
            logger.error(f"Error checking index usage: {e}")
            self.info.append({
                'type': 'Info',
                'description': f"Could not check index usage: {e}",
                'impact': 'Low',
                'recommendation': 'Review indexes manually'
            })
    
    def check_permissions(self):
        """Check database permissions"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Check if the ollama user has the right permissions
            cursor.execute("""
                SELECT grantee, table_name, privilege_type
                FROM information_schema.table_privileges
                WHERE table_schema = 'public'
                AND grantee = 'ollama'
            """)
            
            permissions = cursor.fetchall()
            
            # Group by table
            perm_by_table = {}
            for perm in permissions:
                table = perm['table_name']
                if table not in perm_by_table:
                    perm_by_table[table] = []
                perm_by_table[table].append(perm['privilege_type'])
            
            # Expected tables
            expected_tables = ['endpoints', 'verified_endpoints', 'models', 'benchmark_results', 'metadata', 'schema_version', 'servers']
            
            # Check for missing permissions
            for table in expected_tables:
                if table not in perm_by_table:
                    self.issues.append({
                        'type': 'Missing Permissions',
                        'description': f"User 'ollama' has no permissions on table {table}",
                        'impact': 'High',
                        'recommendation': f"GRANT ALL PRIVILEGES ON {table} TO ollama"
                    })
                else:
                    needed_perms = ['SELECT', 'INSERT', 'UPDATE', 'DELETE']
                    missing_perms = [p for p in needed_perms if p not in perm_by_table[table]]
                    
                    if missing_perms:
                        self.issues.append({
                            'type': 'Incomplete Permissions',
                            'description': f"User 'ollama' missing {', '.join(missing_perms)} on table {table}",
                            'impact': 'High',
                            'recommendation': f"GRANT {', '.join(missing_perms)} ON {table} TO ollama"
                        })
            
            # Check sequence permissions - using the correct column names in PostgreSQL 15
            cursor.execute("""
                SELECT grantee, object_name, privilege_type
                FROM information_schema.usage_privileges
                WHERE object_type = 'SEQUENCE'
                AND object_schema = 'public'
                AND grantee = 'ollama'
            """)
            
            seq_permissions = cursor.fetchall()
            
            if len(seq_permissions) == 0:
                self.issues.append({
                    'type': 'Missing Sequence Permissions',
                    'description': "User 'ollama' has no permissions on sequences",
                    'impact': 'High',
                    'recommendation': "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ollama"
                })
                
        except Exception as e:
            logger.error(f"Error checking permissions: {e}")
            self.issues.append({
                'type': 'Error',
                'description': f"Failed to check permissions: {e}",
                'impact': 'High',
                'recommendation': 'Fix the database connection or permissions'
            })
    
    def generate_report(self):
        """Generate a report of all issues found"""
        report_file = "db_schema_issues_report.md"
        logger.info(f"Generating report: {report_file}")
        
        with open(report_file, 'w') as f:
            f.write("# Database Schema Issues Report\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            if not self.issues and not self.warnings and not self.info:
                f.write("## No Issues Found\n\n")
                f.write("The database schema appears to be in good condition with no detected issues.\n")
            else:
                # Critical Issues
                if self.issues:
                    f.write(f"## Critical Issues ({len(self.issues)})\n\n")
                    headers = ['Type', 'Description', 'Impact', 'Recommendation']
                    table_data = [[i['type'], i['description'], i['impact'], i['recommendation']] for i in self.issues]
                    f.write(tabulate.tabulate(table_data, headers=headers, tablefmt="pipe") + "\n\n")
                
                # Warnings
                if self.warnings:
                    f.write(f"## Warnings ({len(self.warnings)})\n\n")
                    headers = ['Type', 'Description', 'Impact', 'Recommendation']
                    table_data = [[w['type'], w['description'], w['impact'], w['recommendation']] for w in self.warnings]
                    f.write(tabulate.tabulate(table_data, headers=headers, tablefmt="pipe") + "\n\n")
                
                # Info
                if self.info:
                    f.write(f"## Informational ({len(self.info)})\n\n")
                    headers = ['Type', 'Description', 'Impact', 'Recommendation']
                    table_data = [[i['type'], i['description'], i['impact'], i['recommendation']] for i in self.info]
                    f.write(tabulate.tabulate(table_data, headers=headers, tablefmt="pipe") + "\n\n")
                
                # Summary
                f.write("## Summary\n\n")
                f.write(f"- {len(self.issues)} critical issues\n")
                f.write(f"- {len(self.warnings)} warnings\n")
                f.write(f"- {len(self.info)} informational items\n\n")
                
                # Fix SQL
                if self.issues or self.warnings:
                    f.write("## Fix SQL\n\n")
                    f.write("The following SQL commands can be used to fix the identified issues:\n\n")
                    f.write("```sql\n")
                    
                    # Generate SQL for issues
                    for issue in self.issues:
                        if 'recommendation' in issue and issue['recommendation'].strip().startswith(("ALTER", "CREATE", "DROP", "INSERT", "UPDATE", "DELETE", "GRANT")):
                            f.write(f"-- Fix for: {issue['description']}\n")
                            f.write(f"{issue['recommendation']};\n\n")
                    
                    # Generate SQL for warnings
                    for warning in self.warnings:
                        if 'recommendation' in warning and warning['recommendation'].strip().startswith(("ALTER", "CREATE", "DROP", "INSERT", "UPDATE", "DELETE", "GRANT")):
                            f.write(f"-- Fix for: {warning['description']}\n")
                            f.write(f"{warning['recommendation']};\n\n")
                    
                    f.write("```\n")
        
        print(f"Report generated: {report_file}")
        
        # Also return summary of issues
        return {
            'critical': len(self.issues),
            'warnings': len(self.warnings),
            'info': len(self.info)
        }

    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()


if __name__ == "__main__":
    print("Starting database schema check...")
    
    # Add tabulate to requirements.txt if not already there
    try:
        import tabulate
    except ImportError:
        print("Installing missing dependency: tabulate")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tabulate"])
        import tabulate
    
    # Initialize and run the schema checker
    checker = SchemaChecker()
    try:
        summary = checker.check_all()
        print("\nCheck completed!")
        print(f"Found {summary['critical']} critical issues, {summary['warnings']} warnings, and {summary['info']} informational items.")
        print("See db_schema_issues_report.md for the full report.")
    finally:
        checker.close() 