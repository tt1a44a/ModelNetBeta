#!/usr/bin/env python3
#
# query_c0mbined.py - h4ck t00l 2 query c0mbined AI endpoints database
#

import argparse
import os
import sqlite3
import sys
from datetime import datetime

# Added by migration script
from database import Database, init_database

def check_database():
    """Check if the combined database exists"""
    # TODO: Replace SQLite-specific code: if not os.path.exists('ai_endpoints.db'):
        print(f"[!] ERR0R: Combined database not found!")
        print(f"[*] Run combine_db.py first to create the database")
        return False
    return True

def list_servers(args):
    """List all servers in the combined database with filtering and sorting"""
    if not check_database():
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Build query with filters
    query = '''
    SELECT id, ip, port, type, version, country_code, country_name, 
           city, organization, model_count, last_seen 
    FROM servers
    '''
    
    filters = []
    params = []
    
    # Apply filters if provided
    if args.type:
        filters.append("type = ?")
        params.append(args.type)
    
    if args.country:
        filters.append("country_code = ?")
        params.append(args.country.upper())
    
    if args.organization:
        filters.append("organization LIKE ?")
        params.append(f"%{args.organization}%")
    
    if args.ip:
        filters.append("ip LIKE ?")
        params.append(f"%{args.ip}%")
    
    # Add WHERE clause if we have filters
    if filters:
        query += " WHERE " + " AND ".join(filters)
    
    # Apply sorting
    sort_field = args.sort if args.sort else "id"
    sort_order = "DESC" if args.desc else "ASC"
    query += f" ORDER BY {sort_field} {sort_order}"
    
    Database.execute(query, params)
    servers = Database.fetch_all(query, params)
    
    if not servers:
        print(f"[!] No servers found matching filters")
        conn.close()
        return
    
    print("\n" + "="*80)
    print("                       C0MBINED AI ENDPOINTS DATABASE")
    print("="*80)
    
    print(f"\n[+] Found {len(servers)} servers matching filters")
    print(f"\n{'ID':<5} {'IP':<15} {'PORT':<6} {'TYPE':<8} {'VERSION':<10} {'COUNTRY':<8} {'MODELS':<6} {'ORGANIZATION'}")
    print("-"*80)
    
    for server in servers:
        sid, ip, port, stype, version, country_code, country_name, city, org, model_count, last_seen = server
        print(f"{sid:<5} {ip:<15} {port:<6} {stype:<8} {version:<10} {country_code:<8} {model_count:<6} {org}")
    
    print("\n" + "="*80)
    conn.close()

def list_models(args):
    """List all models in the combined database with filtering and sorting"""
    if not check_database():
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Build query with joins for server info
    query = '''
    SELECT m.id, m.model_name, m.provider, m.parameters, m.quantization,
           s.ip, s.port, s.type, s.country_code, m.last_seen
    FROM models m
    JOIN servers s ON m.server_id = s.id
    '''
    
    filters = []
    params = []
    
    # Apply filters if provided
    if args.name:
        filters.append("m.model_name LIKE ?")
        params.append(f"%{args.name}%")
    
    if args.provider:
        filters.append("m.provider = ?")
        params.append(args.provider)
    
    if args.parameters:
        filters.append("m.parameters LIKE ?")
        params.append(f"%{args.parameters}%")
    
    if args.type:
        filters.append("s.type = ?")
        params.append(args.type)
    
    if args.country:
        filters.append("s.country_code = ?")
        params.append(args.country.upper())
    
    # Add WHERE clause if we have filters
    if filters:
        query += " WHERE " + " AND ".join(filters)
    
    # Apply sorting
    sort_field = args.sort if args.sort else "m.model_name"
    if sort_field == "name":
        sort_field = "m.model_name"
    elif sort_field == "params":
        sort_field = "m.parameters"
    elif sort_field == "provider":
        sort_field = "m.provider"
    
    sort_order = "DESC" if args.desc else "ASC"
    query += f" ORDER BY {sort_field} {sort_order}"
    
    Database.execute(query, params)
    models = Database.fetch_all(query, params)
    
    if not models:
        print(f"[!] No models found matching filters")
        conn.close()
        return
    
    print("\n" + "="*100)
    print("                               C0MBINED AI MODELS LIST")
    print("="*100)
    
    print(f"\n[+] Found {len(models)} models matching filters")
    print(f"\n{'MODEL NAME':<30} {'PROVIDER':<10} {'PARAMS':<10} {'QUANT':<8} {'SERVER':<22} {'TYPE':<8} {'COUNTRY'}")
    print("-"*100)
    
    for model in models:
        mid, name, provider, params, quant, ip, port, stype, country, last_seen = model
        server = f"{ip}:{port}"
        print(f"{name[:30]:<30} {provider[:10]:<10} {params[:10]:<10} {quant[:8]:<8} {server:<22} {stype:<8} {country}")
    
    print("\n" + "="*100)
    conn.close()

def search_model(args):
    """Search for a specific model across all servers"""
    if not check_database():
        return
    
    # Forward to list_models with name filter
    # Create a new namespace with the same attributes as args
    class NamespaceWithProvider:
        pass
    
    # Copy all attributes from args to the new namespace
    new_args = NamespaceWithProvider()
    for attr in vars(args):
        setattr(new_args, attr, getattr(args, attr))
    
    # Add the provider attribute if it doesn't exist
    if not hasattr(new_args, 'provider'):
        setattr(new_args, 'provider', None)
    if not hasattr(new_args, 'parameters'):
        setattr(new_args, 'parameters', None)
    if not hasattr(new_args, 'type'):
        setattr(new_args, 'type', None)
    if not hasattr(new_args, 'country'):
        setattr(new_args, 'country', None)
    
    # Set the name filter
    new_args.name = args.model
    
    list_models(new_args)

def show_server(args):
    """Show detailed information about a specific server"""
    if not check_database():
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Get server details
    cursor.execute('''
    SELECT id, ip, port, type, version, country_code, country_name, 
           city, organization, asn, model_count, last_seen
    FROM servers
    WHERE id = ?
    ''', (args.id,))
    
    server = Database.fetch_one(query, params)
    if not server:
        print(f"[!] Server with ID {args.id} not found")
        conn.close()
        return
    
    # Get models for this server
    cursor.execute('''
    SELECT id, model_name, provider, parameters, quantization, last_seen
    FROM models
    WHERE server_id = ?
    ORDER BY model_name
    ''', (args.id,))
    
    models = Database.fetch_all(query, params)
    
    # Display server information
    print("\n" + "="*80)
    print(f"                     SERVER DETAILS - ID: {args.id}")
    print("="*80)
    
    sid, ip, port, stype, version, country_code, country_name, city, org, asn, model_count, last_seen = server
    
    print(f"\n[+] Server Information:")
    print(f"    - IP Address:    {ip}")
    print(f"    - Port:          {port}")
    print(f"    - Type:          {stype.upper()}")
    print(f"    - Version:       {version}")
    print(f"    - Location:      {city}, {country_name} ({country_code})")
    print(f"    - Organization:  {org}")
    print(f"    - ASN:           {asn}")
    print(f"    - Last Seen:     {last_seen}")
    print(f"    - Model Count:   {model_count}")
    print(f"    - URL:           http://{ip}:{port}")
    
    if models:
        print(f"\n[+] Available Models ({len(models)}):")
        print(f"\n    {'MODEL NAME':<30} {'PROVIDER':<15} {'PARAMS':<10} {'QUANTIZATION'}")
        print(f"    {'-'*70}")
        
        for model in models:
            mid, name, provider, params, quant, model_last_seen = model
            print(f"    {name[:30]:<30} {provider[:15]:<15} {params[:10]:<10} {quant}")
    else:
        print(f"\n[!] No models available on this server")
    
    print("\n" + "="*80)
    conn.close()

def stats(args):
    """Show database statistics"""
    if not check_database():
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Get statistics
    Database.execute('SELECT COUNT(*) FROM servers')
    total_servers = Database.fetch_one(query, params)[0]
    
    Database.execute('SELECT type, COUNT(*) FROM servers GROUP BY type')
    server_types = Database.fetch_all(query, params)
    
    Database.execute('SELECT COUNT(*) FROM models')
    total_models = Database.fetch_one(query, params)[0]
    
    Database.execute('SELECT provider, COUNT(*) FROM models GROUP BY provider ORDER BY COUNT(*) DESC')
    providers = Database.fetch_all(query, params)
    
    Database.execute('SELECT country_code, country_name, COUNT(*) FROM servers GROUP BY country_code ORDER BY COUNT(*) DESC LIMIT 10')
    countries = Database.fetch_all(query, params)
    
    Database.execute('SELECT organization, COUNT(*) FROM servers GROUP BY organization ORDER BY COUNT(*) DESC LIMIT 10')
    organizations = Database.fetch_all(query, params)
    
    Database.execute('SELECT model_name, COUNT(*) FROM models GROUP BY model_name ORDER BY COUNT(*) DESC LIMIT 10')
    popular_models = Database.fetch_all(query, params)
    
    # Display statistics
    print("\n" + "="*80)
    print("                     C0MBINED DATABASE STAT1STICS")
    print("="*80)
    
    print(f"\n[+] Database Overview:")
    print(f"    - Total Servers: {total_servers}")
    print(f"    - Total Models:  {total_models}")
    
    print(f"\n[+] Server Types:")
    for stype, count in server_types:
        print(f"    - {stype.upper()}: {count} servers")
    
    print(f"\n[+] Top Model Providers:")
    for provider, count in providers:
        print(f"    - {provider}: {count} models")
    
    print(f"\n[+] Top 10 Countries:")
    for code, name, count in countries:
        print(f"    - {name} ({code}): {count} servers")
    
    print(f"\n[+] Top 10 Organizations:")
    for org, count in organizations:
        print(f"    - {org[:40]}: {count} servers")
    
    print(f"\n[+] Top 10 Popular Models:")
    for model, count in popular_models:
        print(f"    - {model[:40]}: {count} instances")
    
    print("\n" + "="*80)
    print(f"Database Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    conn.close()

def main():
    
    # Initialize database schema
    init_database()"""Main function to handle command-line arguments"""
    parser = argparse.ArgumentParser(description="Query the combined AI endpoints database")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # 'servers' command
    servers_parser = subparsers.add_parser("servers", help="List all servers")
    servers_parser.add_argument("-t", "--type", help="Filter by server type (ollama/litellm)")
    servers_parser.add_argument("-c", "--country", help="Filter by country code")
    servers_parser.add_argument("-o", "--organization", help="Filter by organization name")
    servers_parser.add_argument("-i", "--ip", help="Filter by IP address")
    servers_parser.add_argument("-s", "--sort", help="Sort field (id, ip, port, type, country_code, model_count)")
    servers_parser.add_argument("-d", "--desc", action="store_true", help="Sort in descending order")
    
    # 'models' command
    models_parser = subparsers.add_parser("models", help="List all models")
    models_parser.add_argument("-n", "--name", help="Filter by model name")
    models_parser.add_argument("-p", "--provider", help="Filter by provider")
    models_parser.add_argument("-r", "--parameters", help="Filter by parameter size")
    models_parser.add_argument("-t", "--type", help="Filter by server type (ollama/litellm)")
    models_parser.add_argument("-c", "--country", help="Filter by country code")
    models_parser.add_argument("-s", "--sort", help="Sort field (name, provider, params)")
    models_parser.add_argument("-d", "--desc", action="store_true", help="Sort in descending order")
    
    # 'search' command
    search_parser = subparsers.add_parser("search", help="Search for a specific model")
    search_parser.add_argument("model", help="Model name to search for")
    search_parser.add_argument("-t", "--type", help="Filter by server type (ollama/litellm)")
    search_parser.add_argument("-c", "--country", help="Filter by country code")
    search_parser.add_argument("-s", "--sort", help="Sort field (name, provider, params)")
    search_parser.add_argument("-d", "--desc", action="store_true", help="Sort in descending order")
    
    # 'server' command
    server_parser = subparsers.add_parser("server", help="Show server details")
    server_parser.add_argument("id", type=int, help="Server ID")
    
    # 'stats' command
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")
    
    args = parser.parse_args()
    
    # Execute the appropriate function based on the command
    commands = {
        "servers": list_servers,
        "models": list_models,
        "search": search_model,
        "server": show_server,
        "stats": stats
    }
    
    if args.command in commands:
        try:
            commands[args.command](args)
        except BrokenPipeError:
            # Handle broken pipe when output is piped to a pager
            sys.stderr.close()
    else:
        print("""
 ===================================================
   C0MBINED AI ENDPOINTS DATABASE QUERY T00L v1.0
 ===================================================

Usage examples:
  ./query_combined.py servers            - List all servers
  ./query_combined.py servers -t ollama  - List Ollama servers only
  ./query_combined.py models             - List all models
  ./query_combined.py search llama       - Search for models with 'llama' in name
  ./query_combined.py server 1           - Show details for server ID 1
  ./query_combined.py stats              - Show database statistics
  
More options available with -h for each command
""")

if __name__ == "__main__":
    main() 