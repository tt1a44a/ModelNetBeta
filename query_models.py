#!/usr/bin/env python3
"""
Query tool for searching the Ollama Scanner database
"""

import os
import sys
import sqlite3
import argparse

# Added by migration script
from database import Database, init_database

# TODO: Replace SQLite-specific code: dbFile = 'ollama_instances.db'  # the database file

def checkDB():
    # Initialize database connection
    db = Database()
    
    # how many servers do we have?
    count = db.fetch_one("SELECT COUNT(*) FROM servers")[0]
    
    db.close()
    
    if count == 0:
        print("No data found in the database.")
        print("Run ollama_scanner.py first to collect data.")
        return False
    
    return True  # database is good to go

def removeDuplicates():
    """Remove duplicate entries from the database"""
    # Check if database exists
    if not checkDB():
        return
    
    print("\n=== Removing Duplicate Entries From Database ===")
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Find duplicate servers
    cursor.execute("""
        SELECT ip, port, COUNT(*), GROUP_CONCAT(id) as ids
        FROM servers
        GROUP BY ip, port
        HAVING COUNT(*) > 1
    """)
    
    dupes = Database.fetch_all(query, params)
    
    # did we find any?
    if len(dupes) == 0:
        print("No duplicate servers found!")
    else:
        print("Found " + str(len(dupes)) + " duplicate server entries - fixing now...")
        
        # go through each set of duplicates
        for dupe in dupes:
            ip, port, count, ids = dupe
            id_list = ids.split(',')
            # keep first one, remove others
            keep_id = id_list[0]  # keep this one
            remove_ids = id_list[1:]  # get rid of these
            
            print("  Will keep server: " + ip + ":" + str(port) + " (ID " + keep_id + ")")
            print("  Will remove: " + str(len(remove_ids)) + " duplicates with same IP/port")
            
            # Update models to point to the ID we're keeping
            for remove_id in remove_ids:
                cursor.execute("""
                    UPDATE models
                    SET server_id = ?
                    WHERE server_id = ?
                """, (keep_id, remove_id))
                
                # Now delete the duplicate server
                Database.execute("DELETE FROM servers WHERE id = ?", (remove_id,))
    
    # Find duplicate models
    cursor.execute("""
        SELECT server_id, name, COUNT(*), GROUP_CONCAT(id) as ids
        FROM models
        GROUP BY server_id, name
        HAVING COUNT(*) > 1
    """)
    
    dupe_models = Database.fetch_all(query, params)
    
    # did we find any?
    if len(dupe_models) == 0:
        print("No duplicate models found!")
    else:
        print("Found " + str(len(dupe_models)) + " duplicate model entries - fixing now...")
        
        # go through each set of duplicates
        for dupe in dupe_models:
            server_id, name, count, ids = dupe
            id_list = ids.split(',')
            # keep first one, remove others
            keep_id = id_list[0]  # keep this one
            remove_ids = id_list[1:]  # get rid of these
            
            # get server info
            Database.execute("SELECT ip, port FROM servers WHERE id = ?", (server_id,))
            server = Database.fetch_one(query, params)
            if server:
                server_info = server[0] + ":" + str(server[1])
            else:
                server_info = "Unknown server"
            
            print("  Will keep model: " + name + " on " + server_info + " (ID " + keep_id + ")")
            print("  Will remove: " + str(len(remove_ids)) + " duplicates of same model on same server")
            
            # Delete the duplicate models
            for remove_id in remove_ids:
                Database.execute("DELETE FROM models WHERE id = ?", (remove_id,))
    
    # Save all our changes
    # Commit handled by Database methods
    conn.close()
    
    print("Database cleanup complete!")

def showAllServers(sortby=None, desc=False):
    # check if database exists
    if checkDB() == False:
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # what order should we show them in?
    orderby = "s.scan_date DESC"  # default sorting
    
    if sortby == "models":
        if desc == True:
            orderby = "model_count DESC"
        else: 
            orderby = "model_count ASC"
    elif sortby == "ip":
        if desc == True:
            orderby = "s.ip DESC"
        else:
            orderby = "s.ip ASC"
    elif sortby == "date":
        if desc == True:
            orderby = "s.scan_date DESC"
        else:
            orderby = "s.scan_date ASC"
    
    # query for all servers
    query = """
        SELECT s.ip, s.port, s.scan_date, COUNT(m.id) as model_count
        FROM servers s
        LEFT JOIN models m ON s.id = m.server_id
        GROUP BY s.id
        ORDER BY """ + orderby
    
    Database.execute(query)
    
    allservers = Database.fetch_all(query, params)
    
    print("\n=== All Ollama Servers ===")
    print("Total servers: " + str(len(allservers)))
    print("IP:Port                  Scan Date                  Models Count")
    print("------------------------------------------------------------")
    
    for s in allservers:
        ip, port, scan_date, num_models = s
        print(ip + ":" + str(port) + " " * (25-len(ip+str(port))) + scan_date + " " * (25-len(scan_date)) + str(num_models))
    
    conn.close()

def showAllModels(sortby=None, desc=False):
    # check if database exists
    if checkDB() == False:
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # default sorting
    orderby = "server_count DESC"
    
    if sortby == "name":
        if desc:
            orderby = "name DESC"
        else:
            orderby = "name ASC"
    elif sortby == "params":
        if desc:
            orderby = """
            CASE 
                WHEN parameter_size LIKE '%B' THEN 
                    CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                ELSE 0
            END DESC"""
        else:
            orderby = """
            CASE 
                WHEN parameter_size LIKE '%B' THEN 
                    CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                ELSE 0
            END ASC"""
    elif sortby == "quant":
        if desc:
            orderby = "quantization_level DESC"
        else:
            orderby = "quantization_level ASC"
    elif sortby == "count":
        if desc:
            orderby = "server_count DESC"
        else:
            orderby = "server_count ASC"
    
    # get all models
    query = """
        SELECT 
            name, 
            parameter_size, 
            quantization_level, 
            COUNT(*) as server_count
        FROM models
        GROUP BY name, parameter_size, quantization_level
        ORDER BY """ + orderby
    
    Database.execute(query)
    
    all_models = Database.fetch_all(query, params)
    
    print("\n=== All Unique Models ===")
    print("Total unique models: " + str(len(all_models)))
    print("Model Name                      Parameters      Quantization   Count    Example Servers")
    print("------------------------------------------------------------------------------------------")
    
    for model in all_models:
        name, params, quant, cnt = model
        
        # get some example servers
        cursor.execute("""
            SELECT s.ip, s.port
            FROM models m
            JOIN servers s ON m.server_id = s.id
            WHERE m.name = ? AND m.parameter_size = ? AND m.quantization_level = ?
            LIMIT 3
        """, (name, params, quant))
        
        servers = Database.fetch_all(query, params)
        servers_text = ""
        
        for i in range(len(servers)):
            s_ip, s_port = servers[i]
            if i > 0:
                servers_text = servers_text + ", "
            servers_text = servers_text + s_ip + ":" + str(s_port)
        
        if cnt > 3:
            servers_text = servers_text + " (+" + str(cnt-3) + " more)"
        
        # trim long names
        namestr = name
        if len(namestr) > 29:
            namestr = name[:26] + "..."
        
        print(namestr + " " * (30-len(namestr)) + 
              str(params) + " " * (15-len(str(params))) + 
              str(quant) + " " * (15-len(str(quant))) + 
              str(cnt) + " " * (8-len(str(cnt))) + 
              servers_text)
    
    conn.close()

def findModel(model_name, sortby=None, desc=False):
    # check if database exists
    if checkDB() == False:
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # default sorting
    orderby = "server_count DESC"
    
    if sortby == "name":
        if desc:
            orderby = "name DESC"
        else:
            orderby = "name ASC"
    elif sortby == "params":
        if desc:
            orderby = """
            CASE 
                WHEN parameter_size LIKE '%B' THEN 
                    CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                ELSE 0
            END DESC"""
        else:
            orderby = """
            CASE 
                WHEN parameter_size LIKE '%B' THEN 
                    CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                ELSE 0
            END ASC"""
    elif sortby == "quant":
        if desc:
            orderby = "quantization_level DESC"
        else:
            orderby = "quantization_level ASC"
    
    # add wildcards to search
    search = "%" + model_name + "%"
    
    # search for models
    query = """
        SELECT 
            m.name, 
            m.parameter_size, 
            m.quantization_level, 
            COUNT(*) as server_count
        FROM models m
        WHERE m.name LIKE ?
        GROUP BY m.name, m.parameter_size, m.quantization_level
        ORDER BY """ + orderby
    
    Database.execute(query, (search,))
    
    results = Database.fetch_all(query, params)
    
    print("\n=== Models containing '" + model_name + "' ===")
    print("Found " + str(len(results)) + " unique models")
    
    if len(results) > 0:
        print("Model Name                      Parameters      Quantization   Count    Example Servers")
        print("------------------------------------------------------------------------------------------")
        
        for model in results:
            name, params, quant, cnt = model
            
            # get example servers
            cursor.execute("""
                SELECT s.ip, s.port
                FROM models m
                JOIN servers s ON m.server_id = s.id
                WHERE m.name = ? AND m.parameter_size = ? AND m.quantization_level = ?
                LIMIT 3
            """, (name, params, quant))
            
            servers = Database.fetch_all(query, params)
            servers_text = ""
            
            for i in range(len(servers)):
                s_ip, s_port = servers[i]
                if i > 0:
                    servers_text = servers_text + ", "
                servers_text = servers_text + s_ip + ":" + str(s_port)
            
            if cnt > 3:
                servers_text = servers_text + " (+" + str(cnt-3) + " more)"
            
            # trim long names
            namestr = name
            if len(namestr) > 29:
                namestr = name[:26] + "..."
            
            print(namestr + " " * (30-len(namestr)) + 
                str(params) + " " * (15-len(str(params))) + 
                str(quant) + " " * (15-len(str(quant))) + 
                str(cnt) + " " * (8-len(str(cnt))) + 
                servers_text)
    
    conn.close()

def findParamSize(param_size, sortby=None, desc=False):
    # check if database exists
    if checkDB() == False:
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # default sorting
    orderby = "server_count DESC"
    
    if sortby == "name":
        if desc:
            orderby = "name DESC"
        else:
            orderby = "name ASC"
    elif sortby == "params":
        if desc:
            orderby = """
            CASE 
                WHEN parameter_size LIKE '%B' THEN 
                    CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                ELSE 0
            END DESC"""
        else:
            orderby = """
            CASE 
                WHEN parameter_size LIKE '%B' THEN 
                    CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                ELSE 0
            END ASC"""
    elif sortby == "quant":
        if desc:
            orderby = "quantization_level DESC"
        else:
            orderby = "quantization_level ASC"
    
    # add wildcards
    search = "%" + param_size + "%"
    
    # search for models with this param size
    query = """
        SELECT 
            m.name, 
            m.parameter_size, 
            m.quantization_level, 
            COUNT(*) as server_count
        FROM models m
        WHERE m.parameter_size LIKE ?
        GROUP BY m.name, m.parameter_size, m.quantization_level
        ORDER BY """ + orderby
    
    Database.execute(query, (search,))
    
    results = Database.fetch_all(query, params)
    
    print("\n=== Models with parameter size containing '" + param_size + "' ===")
    print("Found " + str(len(results)) + " unique models")
    
    if len(results) > 0:
        print("Model Name                      Parameters      Quantization   Count    Example Servers")
        print("------------------------------------------------------------------------------------------")
        
        for model in results:
            name, params, quant, cnt = model
            
            # get example servers
            cursor.execute("""
                SELECT s.ip, s.port
                FROM models m
                JOIN servers s ON m.server_id = s.id
                WHERE m.name = ? AND m.parameter_size = ? AND m.quantization_level = ?
                LIMIT 3
            """, (name, params, quant))
            
            servers = Database.fetch_all(query, params)
            servers_text = ""
            
            for i in range(len(servers)):
                s_ip, s_port = servers[i]
                if i > 0:
                    servers_text = servers_text + ", "
                servers_text = servers_text + s_ip + ":" + str(s_port)
            
            if cnt > 3:
                servers_text = servers_text + " (+" + str(cnt-3) + " more)"
            
            # trim long names
            namestr = name
            if len(namestr) > 29:
                namestr = name[:26] + "..."
            
            print(namestr + " " * (30-len(namestr)) + 
                str(params) + " " * (15-len(str(params))) + 
                str(quant) + " " * (15-len(str(quant))) + 
                str(cnt) + " " * (8-len(str(cnt))) + 
                servers_text)
    
    conn.close()

def seeServerDetails(ip, port=None, sortby=None, desc=False):
    # check if database exists
    if checkDB() == False:
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # look for server by IP and maybe port
    if port:
        Database.execute("SELECT id, scan_date FROM servers WHERE ip = ? AND port = ?", (ip, port))
    else:
        Database.execute("SELECT id, port, scan_date FROM servers WHERE ip = ?", (ip,))
    
    servers = Database.fetch_all(query, params)
    
    if not servers:
        if port:
            print("No server found with IP " + ip + " and port " + str(port))
        else:
            print("No server found with IP " + ip)
        conn.close()
        return
    
    if port:
        print("\n=== Server Details: " + ip + ":" + str(port) + " ===")
    else:
        print("\n=== Server Details: " + ip + " ===")
    
    for server in servers:
        if port:
            server_id, scan_date = server
            server_port = port
        else:
            server_id, server_port, scan_date = server
        
        print("IP:Port: " + ip + ":" + str(server_port))
        print("Last Scan: " + scan_date)
        
        # default sorting
        orderby = "name ASC"
        
        if sortby == "name":
            if desc:
                orderby = "name DESC"
            else:
                orderby = "name ASC"
        elif sortby == "params":
            if desc:
                orderby = """
                CASE 
                    WHEN parameter_size LIKE '%B' THEN 
                        CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                    ELSE 0
                END DESC"""
            else:
                orderby = """
                CASE 
                    WHEN parameter_size LIKE '%B' THEN 
                        CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                    ELSE 0
                END ASC"""
        elif sortby == "quant":
            if desc:
                orderby = "quantization_level DESC"
            else:
                orderby = "quantization_level ASC"
        elif sortby == "size":
            if desc:
                orderby = "size_mb DESC"
            else:
                orderby = "size_mb ASC"
        
        # get models on this server
        query = """
            SELECT name, parameter_size, quantization_level, size_mb
            FROM models
            WHERE server_id = ?
            ORDER BY """ + orderby
        
        Database.execute(query, (server_id,))
        
        models = Database.fetch_all(query, params)
        
        print("Models available (" + str(len(models)) + "):")
        print("  Model Name                      Parameters      Quantization      Size (MB)")
        print("  " + "-" * 75)
        
        for model in models:
            name, params, quant, size = model
            
            # trim long names
            namestr = name
            if len(namestr) > 29:
                namestr = name[:26] + "..."
                
            size_str = str(round(size, 2))
            
            print("  " + namestr + " " * (30-len(namestr)) + 
                  str(params) + " " * (15-len(str(params))) + 
                  str(quant) + " " * (15-len(str(quant))) + 
                  size_str)
        
        print("\n")
    
    conn.close()

def showModelsWithServers(sortby=None, desc=False):
    # check if database exists
    if checkDB() == False:
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # default sorting
    orderby = "m.name ASC"
    
    if sortby == "name":
        if desc:
            orderby = "m.name DESC"
        else:
            orderby = "m.name ASC"
    elif sortby == "params":
        if desc:
            orderby = """
            CASE 
                WHEN m.parameter_size LIKE '%B' THEN 
                    CAST(REPLACE(REPLACE(m.parameter_size, 'B', ''), '.', '') AS REAL)
                ELSE 0
            END DESC"""
        else:
            orderby = """
            CASE 
                WHEN m.parameter_size LIKE '%B' THEN 
                    CAST(REPLACE(REPLACE(m.parameter_size, 'B', ''), '.', '') AS REAL)
                ELSE 0
            END ASC"""
    elif sortby == "quant":
        if desc:
            orderby = "m.quantization_level DESC"
        else:
            orderby = "m.quantization_level ASC"
    elif sortby == "size":
        if desc:
            orderby = "m.size_mb DESC"
        else:
            orderby = "m.size_mb ASC"
    elif sortby == "ip":
        if desc:
            orderby = "s.ip DESC"
        else:
            orderby = "s.ip ASC"
    
    # get all models and their servers
    query = """
        SELECT m.name, m.parameter_size, m.quantization_level, m.size_mb, s.ip, s.port
        FROM models m
        JOIN servers s ON m.server_id = s.id
        ORDER BY """ + orderby
    
    Database.execute(query)
    
    all_models = Database.fetch_all(query, params)
    
    print("\n=== All Models with Server IPs ===")
    print("Total model instances: " + str(len(all_models)))
    print("Model Name                      Parameters      Quantization   Size (MB)     Server IP:Port")
    print("------------------------------------------------------------------------------------------")
    
    for model in all_models:
        name, params, quant, size, ip, port = model
        
        # trim long names
        namestr = name
        if len(namestr) > 29:
            namestr = name[:26] + "..."
            
        size_str = str(round(size, 2))
        
        print(namestr + " " * (30-len(namestr)) + 
              str(params) + " " * (15-len(str(params))) + 
              str(quant) + " " * (15-len(str(quant))) + 
              size_str + " " * (12-len(size_str)) + 
              ip + ":" + str(port))
    
    conn.close()

def mainFunc():
    # set up command line arguments
    parser = argparse.ArgumentParser(description='Query tool for Ollama Scanner database')
    
    # Add subparsers for different commands
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # All servers command
    servers_parser = subparsers.add_parser('servers', help='List all servers in the database')
    servers_parser.add_argument('--sort', choices=['ip', 'date', 'models'], 
                               help='Field to sort results by')
    servers_parser.add_argument('--desc', action='store_true', help='Sort in descending order')
    
    # All models command
    models_parser = subparsers.add_parser('models', help='List all models in the database')
    models_parser.add_argument('--sort', choices=['name', 'params', 'quant', 'count'], 
                              help='Field to sort results by')
    models_parser.add_argument('--desc', action='store_true', help='Sort in descending order')
    
    # Models with servers command
    models_servers_parser = subparsers.add_parser('models-servers', 
                                                 help='List all models with their server IPs')
    models_servers_parser.add_argument('--sort', choices=['name', 'params', 'quant', 'size', 'ip'], 
                                      help='Field to sort results by')
    models_servers_parser.add_argument('--desc', action='store_true', help='Sort in descending order')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search for a specific model')
    search_parser.add_argument('model_name', help='Name of model to search for')
    search_parser.add_argument('--sort', choices=['name', 'params', 'quant', 'count'], 
                              help='Field to sort results by')
    search_parser.add_argument('--desc', action='store_true', help='Sort in descending order')
    
    # Parameter size command
    param_parser = subparsers.add_parser('params', help='Find models with specific parameter size')
    param_parser.add_argument('parameter_size', help='Parameter size to search for (e.g., 7B, 13B)')
    param_parser.add_argument('--sort', choices=['name', 'params', 'quant', 'size'], 
                              help='Field to sort results by')
    param_parser.add_argument('--desc', action='store_true', help='Sort in descending order')
    
    # Server details command
    server_parser = subparsers.add_parser('server', help='Show details of a specific server')
    server_parser.add_argument('ip', help='IP address of the server')
    server_parser.add_argument('--port', type=int, help='Port of the server (optional)')
    server_parser.add_argument('--sort', choices=['name', 'params', 'quant', 'size'], 
                               help='Field to sort results by')
    server_parser.add_argument('--desc', action='store_true', help='Sort in descending order')
    
    # Prune duplicates command 
    prune_parser = subparsers.add_parser('prune', help='Remove duplicate entries from the database')
    
    # parse arguments
    args = parser.parse_args()
    
    # if no command was given, show help
    if not args.command:
        parser.print_help()
        return
    
    # figure out which command to run
    if args.command == 'servers':
        showAllServers(args.sort, args.desc)
    elif args.command == 'models':
        showAllModels(args.sort, args.desc)
    elif args.command == 'models-servers':
        showModelsWithServers(args.sort, args.desc)
    elif args.command == 'search':
        findModel(args.model_name, args.sort, args.desc)
    elif args.command == 'params':
        findParamSize(args.parameter_size, args.sort, args.desc)
    elif args.command == 'server':
        seeServerDetails(args.ip, args.port, args.sort, args.desc)
    elif args.command == 'prune':
        removeDuplicates()

# This is where the program starts running
if __name__ == "__main__":
    try:
        # Call our main function
        mainFunc()
    except KeyboardInterrupt:
        # User hit Ctrl+C
        print("\nProgram interrupted by user. Exiting...")
    except Exception as e:
        # Some other error happened
        print("ERROR: " + str(e))
        sys.exit(1) 