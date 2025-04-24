#!/usr/bin/env python3

from Toolv2 import Tools
from pydantic import BaseModel, Field
import os

class CustomTools(Tools):
    """Customized version of Tools class for testing with local paths."""
    
    def __init__(self):
        # Create a local directory for databases
        os.makedirs("./data", exist_ok=True)
        
        # Override default initialization
        self.valves = self.Valves(
            DB_PATH="./data/ollama_scanner.db",
            OPENWEBUI_DB_PATH="./data/openwebui.db"
        )
        self._setup_logging()
        self._setup_database()

if __name__ == "__main__":
    # Test the custom tools
    try:
        print("Creating CustomTools instance...")
        tool = CustomTools()
        
        # Test configuration with a 'type' key
        print("\nTesting set_configuration with 'type' key...")
        test_config = {
            "type": "test_type",
            "MAX_RESULTS": 20,
            "SHODAN_API_KEY": "test_key"
        }
        result = tool.set_configuration(test_config)
        
        print(f"\nConfiguration result: {'Success' if result['success'] else 'Failed'}")
        print(f"Updated keys: {', '.join(result['updated_keys'])}")
        print(f"Invalid keys: {', '.join(result['invalid_keys'])}")
        
        # Get current configuration
        print("\nGetting current configuration...")
        config = tool.get_configuration()
        print(f"Configuration successful: {config['success']}")
        
        # Print some config values
        if config['success']:
            print("\nSome configuration values:")
            print(f"SHODAN_API_KEY: {config['config']['SHODAN_API_KEY']}")
            print(f"MAX_RESULTS: {config['config']['MAX_RESULTS']}")
            print(f"DB_PATH: {config['config']['DB_PATH']}")
        
        print("\nTest completed!")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc() 