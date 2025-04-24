#!/usr/bin/env python3

import os
import json
from CustomTools import CustomTools

# Create data directory if it doesn't exist
os.makedirs("./data", exist_ok=True)

def simulate_owui_command(command_str):
    """Simulate an OpenWebUI command execution."""
    print(f"Received command: {command_str}")
    
    # Parse the command
    parts = command_str.strip().split(' ', 2)
    if len(parts) < 3 or parts[0] != '/tool' or parts[1] != 'OllamaScanner':
        return {"error": "Invalid command format. Should be: /tool OllamaScanner method_name param1=value1 ..."}
    
    method_name = None
    params = {}
    
    # Extract method name and parameters
    method_and_params = parts[2].strip()
    method_parts = method_and_params.split(' ', 1)
    method_name = method_parts[0]
    
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
                    params['config_dict'] = config_dict
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
    
    print(f"Method: {method_name}")
    print(f"Parameters: {params}")
    
    # Initialize the tool
    tool = CustomTools()
    
    # Execute the method if it exists
    if hasattr(tool, method_name) and callable(getattr(tool, method_name)):
        method = getattr(tool, method_name)
        try:
            result = method(**params)
            print("\nCommand result:")
            print(json.dumps(result, indent=2, default=str))
            return result
        except Exception as e:
            print(f"Error executing command: {e}")
            return {"error": str(e)}
    else:
        print(f"Method {method_name} not found")
        return {"error": f"Method {method_name} not found"}

# Test with the user's command
print("=== SIMULATION OF OPENWEBUI COMMAND ===")
user_command = '/tool OllamaScanner set_configuration config_dict={"type": "some_type", "MAX_RESULTS": 20}'
simulate_owui_command(user_command)

# Test with another command
print("\n=== TESTING MODEL CAPABILITIES WITH EXAMPLE COMMAND ===")
test_command = '/tool OllamaScanner get_configuration'
simulate_owui_command(test_command)

print("\n=== SIMULATION COMPLETED ===") 