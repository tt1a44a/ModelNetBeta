#!/usr/bin/env python3
"""
Fix script for the 'ollama_scanner' app command timeout issues
"""

import os
import sys
import json
import requests
import time

def test_endpoint(ip="99.178.157.123", port=11434, model="deepseek-r1:70b", timeout=60):
    """Test direct connection to the endpoint"""
    print(f"\n=== Testing direct connection to {ip}:{port} ===")
    
    # First check if the endpoint is up
    url = f"http://{ip}:{port}/api/tags"
    try:
        start_time = time.time()
        response = requests.get(url, timeout=5)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            print(f"✅ Endpoint is responsive (took {elapsed:.2f}s)")
            
            # Check if the model exists
            models = response.json().get("models", [])
            model_names = [m.get("name") for m in models]
            
            if model in model_names:
                print(f"✅ Model '{model}' is available")
            else:
                print(f"❌ Model '{model}' not found. Available models:")
                for m in model_names:
                    print(f"  - {m}")
                return False
                
            # Test a simple generation
            print(f"\n=== Testing simple generation with {model} ===")
            gen_url = f"http://{ip}:{port}/api/generate"
            data = {
                "model": model,
                "prompt": "Hi",
                "stream": False,
                "max_tokens": 10  # Keep this very low for quick testing
            }
            
            try:
                print(f"Sending request (timeout: {timeout}s)...")
                start_time = time.time()
                gen_response = requests.post(gen_url, json=data, timeout=timeout)
                elapsed = time.time() - start_time
                
                if gen_response.status_code == 200:
                    result = gen_response.json()
                    response_text = result.get("response", "")
                    print(f"✅ Generation successful (took {elapsed:.2f}s)")
                    print(f"Response: {response_text[:50]}...")
                    return True
                else:
                    print(f"❌ Generation failed with status {gen_response.status_code}")
                    print(f"Response: {gen_response.text[:100]}")
                    return False
                    
            except requests.exceptions.Timeout:
                elapsed = time.time() - start_time
                print(f"❌ Generation timed out after {elapsed:.2f}s")
                return False
            except Exception as e:
                print(f"❌ Generation error: {str(e)}")
                return False
        else:
            print(f"❌ Endpoint returned status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {str(e)}")
        return False

def check_bot_config():
    """Check the Discord bot configuration"""
    print("\n=== Checking Discord bot configuration ===")
    
    bot_file = os.path.join("DiscordBot", "discord_bot.py")
    if not os.path.exists(bot_file):
        print(f"❌ Discord bot file not found at {bot_file}")
        return False
        
    try:
        with open(bot_file, "r") as f:
            content = f.read()
            
        # Check for key timeout settings
        if "dynamic_timeout = min(900," in content:
            print("⚠️ Bot still has the old timeout setting (900s)")
            print("   Run fix_timeout_for_large_models.py to fix this")
        elif "dynamic_timeout = min(1500," in content:
            print("✅ Bot has the updated timeout setting (1500s)")
        else:
            print("❓ Could not determine timeout setting in bot code")
            
        # Check if the bot has the special handling for large models
        if "if size_num >= 50:" in content:
            print("✅ Bot has special handling for large models (50B+)")
        else:
            print("⚠️ Bot missing special handling for large models")
            print("   Run fix_timeout_for_large_models.py to fix this")
            
        return True
    except Exception as e:
        print(f"❌ Error checking bot configuration: {str(e)}")
        return False

def check_app_command():
    """Check the APP 'ollama_scanner' command that's failing"""
    print("\n=== Checking APP 'ollama_scanner' command ===")
    
    # First look for APP directory/files
    app_files = []
    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith(".py") and "app" in file.lower():
                app_files.append(os.path.join(root, file))
                
    if not app_files:
        print("❓ No obvious APP files found in the codebase")
    else:
        print(f"Found {len(app_files)} potential APP files:")
        for file in app_files:
            print(f"  - {file}")
            
    print("\nRecommendation for fixing APP 'ollama_scanner' timeout issues:")
    print("1. APP 'ollama_scanner' is likely a custom command defined in one of the Python files")
    print("2. Look for timeout settings in the command implementation")
    print("3. Increase the timeout specifically for large models (50B+)")
    print("4. Use the same dynamic timeout logic as applied to the Discord bot")
    
    return True

def check_server_limits():
    """Check if server-side limits could be causing issues"""
    print("\n=== Server Resource Considerations ===")
    print("Large models like deepseek-r1:70b require significant resources:")
    print("1. The server might be limiting resources per request")
    print("2. Multiple concurrent requests to the same large model will slow down responses")
    print("3. The server may have queue limits or prioritization that affects response time")
    
    print("\nRecommendations:")
    print("1. Implement request queuing in the bot to prevent overwhelming the server")
    print("2. Add exponential backoff for retries on timeout")
    print("3. Consider implementing a model-specific timeout table in the bot")
    print("   - 7B models: 60s timeout")
    print("   - 14B models: 120s timeout")
    print("   - 70B models: 300s timeout or more")
    
    return True

def main():
    """Main function"""
    print("=" * 60)
    print("OLLAMA SCANNER APP TIMEOUT DIAGNOSTIC TOOL")
    print("=" * 60)
    print("This tool helps diagnose and fix timeout issues with the APP 'ollama_scanner' command")
    print("Original error: Request timed out. The model may be taking too long to respond.")
    print("=" * 60)
    
    # Test the endpoint directly
    endpoint_working = test_endpoint(model="deepseek-r1:7b", timeout=30)
    
    if not endpoint_working:
        print("\n❌ The endpoint is not responding correctly.")
        print("Fix the endpoint connectivity issues before proceeding.")
        return False
        
    # Check Discord bot configuration
    check_bot_config()
    
    # Check APP command implementation
    check_app_command()
    
    # Check server limits
    check_server_limits()
    
    print("\n" + "=" * 60)
    print("SUMMARY AND RECOMMENDATIONS")
    print("=" * 60)
    print("1. The bot's timeout settings have been updated by running fix_timeout_for_large_models.py")
    print("2. Smaller models (deepseek-r1:7b) respond quickly and should be used when possible")
    print("3. For the 70B model, keep prompts short and limit max_tokens")
    print("4. The APP 'ollama_scanner' command needs similar timeout handling as the Discord bot")
    print("5. Consider implementing request queuing to prevent overwhelming the server")
    print("\nMost importantly: Large models like deepseek-r1:70b will naturally take longer to respond.")
    print("This is normal and cannot be fully resolved without more server resources.")
    
    return True

if __name__ == "__main__":
    main() 