#!/usr/bin/env python3
"""
OpenWebUI Helper Script for OllamaScanner Tool

This script helps to debug and fix issues with the OllamaScanner tool in OpenWebUI,
especially with the 'type' parameter.

Usage:
1. Deploy this script in the same directory as your OpenWebUI backend
2. Run it directly: python owui_helper.py
3. It provides options for testing commands and viewing logs

"""

import os
import sys
import json
import logging
import time
import argparse
import requests
from datetime import datetime
import subprocess

# Constants - adjust these for your specific deployment
DEFAULT_OPENWEBUI_LOGS = "/path/to/openwebui/logs"  # Update this
DEFAULT_CONFIG_PATH = "/app/backend/data/ollama_scanner_config.json"  # Default path in containerized OpenWebUI
LOCAL_CONFIG_PATH = "./data/ollama_scanner_config.json"  # Local path for testing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("owui_helper.log")
    ]
)
logger = logging.getLogger("owui_helper")

def test_owui_command(command_str):
    """Test an OpenWebUI command with proper handling of type parameter."""
    print(f"\nTesting command: {command_str}")
    
    # Parse the command
    parts = command_str.strip().split(' ', 2)
    if len(parts) < 3 or parts[0] != '/tool' or parts[1] != 'OllamaScanner':
        return {"error": "Invalid command format. Should be: /tool OllamaScanner method_name param1=value1 ..."}
    
    # Extract method name and parameters
    method_and_params = parts[2].strip()
    method_parts = method_and_params.split(' ', 1)
    method_name = method_parts[0]
    params = {}
    
    # Extract and process parameters
    if len(method_parts) > 1:
        param_str = method_parts[1].strip()
        
        # Handle special case for config_dict which is JSON
        if 'config_dict=' in param_str:
            before, json_part = param_str.split('config_dict=', 1)
            # Parse any parameters before config_dict
            for pair in before.strip().split():
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    params[k] = v
                    
            # Parse the JSON part
            try:
                json_str = json_part.strip()
                if json_str.startswith('{') and json_str.endswith('}'):
                    config_dict = json.loads(json_str)
                    
                    # Special handling for 'type' key if present
                    if 'type' in config_dict:
                        print(f"⚠️ WARNING: 'type' key found in config_dict with value: {config_dict['type']}")
                        print("ℹ️ This will be treated as an invalid parameter by the tool")
                        # Option to rename or remove the parameter
                        choice = input("Do you want to rename this key to 'profile_type' or remove it? (rename/remove/keep): ").strip().lower()
                        if choice == 'rename':
                            print("Renaming 'type' to 'profile_type'...")
                            config_dict['profile_type'] = config_dict.pop('type')
                        elif choice == 'remove':
                            print("Removing 'type' key...")
                            config_dict.pop('type')
                        else:
                            print("Keeping 'type' key as is (will be treated as invalid)")
                    
                    params['config_dict'] = config_dict
                else:
                    return {"error": "JSON string must start with { and end with }"}
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON in config_dict: {e}"}
        else:
            # Handle regular parameters
            for pair in param_str.split():
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    # Try to convert to appropriate types
                    if v.lower() == 'true':
                        params[k] = True
                    elif v.lower() == 'false':
                        params[k] = False
                    elif v.isdigit():
                        params[k] = int(v)
                    elif v.startswith('"') and v.endswith('"'):
                        params[k] = v[1:-1]
                    else:
                        params[k] = v
    
    # Print the processed command
    print(f"\nProcessed command:")
    print(f"  Method: {method_name}")
    print(f"  Parameters: {json.dumps(params, indent=2)}")
    
    # Format as it would be used in OpenWebUI
    formatted_cmd = f"/tool OllamaScanner {method_name}"
    for k, v in params.items():
        if k == 'config_dict':
            formatted_cmd += f" config_dict={json.dumps(v)}"
        else:
            if isinstance(v, str) and ' ' in v:
                formatted_cmd += f' {k}="{v}"'
            else:
                formatted_cmd += f" {k}={v}"
    
    print(f"\nUse this command in OpenWebUI:")
    print(f"  {formatted_cmd}")
    
    return {
        "success": True,
        "processed_command": formatted_cmd,
        "method": method_name,
        "params": params
    }


def check_openwebui_logs(log_path=DEFAULT_OPENWEBUI_LOGS, search_term="type"):
    """Check OpenWebUI logs for relevant errors."""
    if not os.path.exists(log_path):
        print(f"❌ Error: Log path does not exist: {log_path}")
        return
    
    print(f"\nSearching logs in: {log_path}")
    print(f"Looking for entries related to: '{search_term}'")
    
    try:
        # Use grep to search for relevant log entries
        grep_cmd = f"grep -i '{search_term}' {log_path}/*.log | tail -n 20"
        process = subprocess.Popen(grep_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if stdout:
            print("\nRelevant log entries found:")
            print(stdout.decode('utf-8'))
        else:
            print("\nNo relevant log entries found")
            
        if stderr:
            print("\nErrors when searching logs:")
            print(stderr.decode('utf-8'))
    except Exception as e:
        print(f"❌ Error searching logs: {e}")


def patch_openwebui_function():
    """Patch the OpenWebUI function to handle the 'type' parameter correctly."""
    config_path = LOCAL_CONFIG_PATH if os.path.exists(LOCAL_CONFIG_PATH) else DEFAULT_CONFIG_PATH
    
    if not os.path.exists(config_path):
        print(f"❌ Error: Configuration file not found at: {config_path}")
        alt_path = input("Enter the path to your ollama_scanner_config.json file: ").strip()
        if os.path.exists(alt_path):
            config_path = alt_path
        else:
            print("❌ Error: Configuration file not found")
            return
    
    print(f"\nPatching OpenWebUI function configuration at: {config_path}")
    
    try:
        # Read the current configuration
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Check if there's a type field in the configuration
        if 'type' in config:
            original_type = config['type']
            print(f"Found 'type' field with value: {original_type}")
            
            # Make a backup of the original file
            backup_path = f"{config_path}.bak.{int(time.time())}"
            with open(backup_path, 'w') as f:
                json.dump(config, f, indent=4)
            print(f"Created backup at: {backup_path}")
            
            # Create a patched version
            patched_config = config.copy()
            
            # If 'type' is a standard value like 'action', we'll keep it
            # Otherwise, rename it to something else
            if original_type != 'action':
                patched_config['function_type'] = patched_config.pop('type')
                patched_config['type'] = 'action'  # Set to standard value
            
            # Write the patched configuration
            with open(config_path, 'w') as f:
                json.dump(patched_config, f, indent=4)
            
            print("✅ Successfully patched the configuration")
            print("The original 'type' field has been renamed to 'function_type'")
            print("This should prevent conflicts with Python's built-in 'type' function")
        else:
            print("ℹ️ No 'type' field found in the configuration that would cause conflicts")
    except Exception as e:
        print(f"❌ Error patching configuration: {e}")


def diagnose_system():
    """Diagnose the system and provide recommendations."""
    print("\n📋 System Diagnosis")
    print("-" * 60)
    
    # Check Python version
    print(f"Python version: {sys.version}")
    
    # Check for important modules
    required_modules = ['pydantic', 'requests', 'shodan']
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ Module {module} is installed")
        except ImportError:
            print(f"❌ Module {module} is NOT installed")
    
    # Check file permissions for the data directory
    data_dir = os.path.dirname(LOCAL_CONFIG_PATH)
    if os.path.exists(data_dir):
        print(f"\nData directory exists: {data_dir}")
        try:
            test_file = os.path.join(data_dir, "permission_test.txt")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            print(f"✅ Data directory is writable")
        except Exception as e:
            print(f"❌ Data directory is NOT writable: {e}")
    else:
        print(f"❌ Data directory does NOT exist: {data_dir}")
    
    print("\n📋 Recommendation Summary")
    print("-" * 60)
    print("1. In OpenWebUI, use the command format:")
    print('   /tool OllamaScanner set_configuration config_dict={"ENABLE_BENCHMARKING": true, "SCAN_TIMEOUT": 60}')
    print("2. Avoid using 'type' as a key in config_dict - use 'profile_type' instead")
    print("3. If the issue persists, run the patch function in this helper")


def main():
    parser = argparse.ArgumentParser(description="OpenWebUI Helper for OllamaScanner Tool")
    parser.add_argument("--check-logs", action="store_true", help="Check OpenWebUI logs for errors")
    parser.add_argument("--log-path", help=f"Path to OpenWebUI logs (default: {DEFAULT_OPENWEBUI_LOGS})")
    parser.add_argument("--search", help="Term to search for in logs (default: type)")
    parser.add_argument("--patch", action="store_true", help="Patch OpenWebUI function configuration")
    parser.add_argument("--diagnose", action="store_true", help="Run system diagnosis")
    parser.add_argument("--test", action="store_true", help="Test a command")

    args = parser.parse_args()
    
    print("=" * 60)
    print("🛠️  OpenWebUI Helper for OllamaScanner Tool")
    print("=" * 60)
    
    if args.check_logs:
        log_path = args.log_path or DEFAULT_OPENWEBUI_LOGS
        search_term = args.search or "type"
        check_openwebui_logs(log_path, search_term)
    
    elif args.patch:
        patch_openwebui_function()
    
    elif args.diagnose:
        diagnose_system()
    
    elif args.test:
        print("Enter the command to test (type 'exit' to quit):")
        while True:
            command = input("> ").strip()
            if command.lower() == "exit":
                break
            if command:
                test_owui_command(command)
    
    else:
        print("Interactive Mode")
        print("-" * 60)
        print("1. Test a command")
        print("2. Check logs")
        print("3. Patch OpenWebUI function")
        print("4. Run system diagnosis")
        print("5. Exit")
        
        choice = input("\nSelect an option (1-5): ").strip()
        
        if choice == "1":
            print("\nEnter the command to test:")
            command = input("> ").strip()
            test_owui_command(command)
            
        elif choice == "2":
            log_path = input(f"\nEnter log path (default: {DEFAULT_OPENWEBUI_LOGS}): ").strip() or DEFAULT_OPENWEBUI_LOGS
            search_term = input("Enter search term (default: type): ").strip() or "type"
            check_openwebui_logs(log_path, search_term)
            
        elif choice == "3":
            patch_openwebui_function()
            
        elif choice == "4":
            diagnose_system()
            
        elif choice == "5":
            print("Exiting...")
        
        else:
            print("Invalid choice")

if __name__ == "__main__":
    main() 