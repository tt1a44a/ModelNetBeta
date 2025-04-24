#!/usr/bin/env python3
"""
Test script for demonstrating the enhanced dynamic timeout and timeout flag features
"""

import argparse
import requests
import time
import re
import json

# Import the timeout calculation function directly
# This is a copy of what we added to the ollama_scanner files
def calculate_dynamic_timeout(model_name="", prompt="", max_tokens=1000, timeout_flag=None):
    """
    Calculate a dynamic timeout based on model size, prompt length, and max tokens.
    
    Args:
        model_name (str): Name of the model, used to estimate size (e.g., "deepseek-r1:70b")
        prompt (str): The prompt text, longer prompts need more time
        max_tokens (int): Maximum tokens to generate, more tokens need more time
        timeout_flag (int, optional): If provided, overrides the calculated timeout.
                                    Use 0 for no timeout (None or inf).
    
    Returns:
        float or None: Timeout in seconds, or None for no timeout
    """
    # If timeout_flag is explicitly set to 0, return None for no timeout
    if timeout_flag == 0:
        print("🔄 Using NO TIMEOUT (will wait indefinitely)")
        return None
    
    # If timeout_flag is provided and not 0, use that value
    if timeout_flag is not None:
        print(f"🔄 Using manual timeout: {timeout_flag} seconds")
        return float(timeout_flag)
    
    # Base timeout value
    base_timeout = 180  # 3 minutes
    
    # Factor in model size
    param_factor = 1.0
    model_name_lower = model_name.lower()
    
    # Extract parameter size from model name (e.g., "13b" from "deepseek-r1:13b")
    size_match = re.search(r'(\d+)b', model_name_lower)
    if size_match:
        try:
            size_num = float(size_match.group(1))
            # Special handling for very large models (50B+)
            if size_num >= 50:
                param_factor = 2.5 + (size_num / 20)  # Much more time for 70B models
            else:
                param_factor = 1.0 + (size_num / 10)  # Standard scaling for smaller models
        except ValueError:
            # If we can't parse it, use default factor
            pass
    elif "70b" in model_name_lower:
        param_factor = 6.0  # Special case for 70B models
    elif "14b" in model_name_lower or "13b" in model_name_lower:
        param_factor = 2.4  # Special case for 13-14B models
    elif "7b" in model_name_lower or "8b" in model_name_lower:
        param_factor = 1.7  # Special case for 7-8B models
    
    # Factor in prompt length
    prompt_length = len(prompt) if prompt else 0
    prompt_factor = 1.0 + (prompt_length / 1000)  # Add factor for each 1000 chars
    
    # Factor in max_tokens
    max_tokens = max(1, max_tokens)  # Ensure positive value
    token_factor = max(1.0, max_tokens / 1000)  # Add factor for each 1000 tokens
    
    # Calculate final timeout with minimum and maximum bounds
    final_timeout = max(60, min(1800, base_timeout * param_factor * prompt_factor * token_factor))
    
    # Display the factors
    print(f"⚙️ Dynamic timeout calculation:")
    print(f"  • Base timeout:  {base_timeout:.1f}s")
    print(f"  • Model factor:  {param_factor:.2f}x (based on {model_name})")
    print(f"  • Prompt factor: {prompt_factor:.2f}x (for {prompt_length} chars)")
    print(f"  • Token factor:  {token_factor:.2f}x (for {max_tokens} tokens)")
    print(f"🔄 Final timeout:  {final_timeout:.1f} seconds")
    
    return final_timeout

def test_ollama_endpoint(ip, port, model, prompt, max_tokens, timeout_flag=None):
    """Test API request with dynamic timeout"""
    print(f"\n=== Testing API request with model: {model} ===")
    print(f"Endpoint: {ip}:{port}")
    print(f"Prompt: \"{prompt}\"")
    print(f"Max tokens: {max_tokens}")
    
    url = f"http://{ip}:{port}/api/generate"
    
    data = {
        "model": model,
        "prompt": prompt,
        "system": "You are a helpful assistant.",
        "stream": False,
        "max_tokens": max_tokens
    }
    
    # Calculate timeout using our dynamic function
    timeout = calculate_dynamic_timeout(
        model_name=model,
        prompt=prompt,
        max_tokens=max_tokens,
        timeout_flag=timeout_flag
    )
    
    print("\n=== Sending API request ===")
    start_time = time.time()
    
    try:
        response = requests.post(url, json=data, timeout=timeout)
        elapsed = time.time() - start_time
        
        print(f"✅ Request completed in {elapsed:.2f} seconds")
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            response_text = result.get("response", "")
            print("\n=== Response ===")
            print(response_text[:200] + ("..." if len(response_text) > 200 else ""))
            print(f"\n✅ Generation successful (response length: {len(response_text)} chars)")
            return True
        else:
            print(f"❌ Error: Status code {response.status_code}")
            print(f"Response: {response.text[:100]}")
            return False
            
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"❌ Request timed out after {elapsed:.2f} seconds")
        print("Recommendation: Try increasing the timeout or using timeout=0 for no timeout")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Test Ollama API with dynamic timeout")
    parser.add_argument("--ip", default="99.178.157.123", help="Ollama server IP")
    parser.add_argument("--port", type=int, default=11434, help="Ollama server port")
    parser.add_argument("--model", default="deepseek-r1:7b", help="Model name to use")
    parser.add_argument("--prompt", default="Explain what LLMs are in one sentence", help="Prompt to send")
    parser.add_argument("--max-tokens", type=int, default=100, help="Maximum tokens to generate")
    parser.add_argument("--timeout", "-t", type=int, default=None, 
                       help="Timeout in seconds. Use 0 for no timeout, or omit for dynamic timeout.")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("DYNAMIC TIMEOUT TESTER")
    print("=" * 60)
    print("This script demonstrates the new dynamic timeout and timeout flag features")
    print("=" * 60)
    
    # First check if the endpoint/model is available
    check_url = f"http://{args.ip}:{args.port}/api/tags"
    try:
        print(f"Checking if endpoint is available: {check_url}")
        response = requests.get(check_url, timeout=5)
        
        if response.status_code == 200:
            models = [m.get("name") for m in response.json().get("models", [])]
            print(f"✅ Endpoint is available with {len(models)} models")
            
            if args.model in models:
                print(f"✅ Requested model '{args.model}' is available")
            else:
                print(f"⚠️ Requested model '{args.model}' not found. Available models:")
                for model in models:
                    print(f"  - {model}")
                print("\nPlease select a model from the list above using --model.")
                return
        else:
            print(f"❌ Endpoint returned status code {response.status_code}")
            return
            
    except Exception as e:
        print(f"❌ Could not connect to endpoint: {str(e)}")
        return
    
    # Test with the specified parameters
    test_ollama_endpoint(
        ip=args.ip,
        port=args.port,
        model=args.model,
        prompt=args.prompt,
        max_tokens=args.max_tokens,
        timeout_flag=args.timeout
    )
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("To use the enhanced timeout features in the ollama_scanner command:")
    print("\n1. Dynamic timeout (based on model, prompt length, tokens):")
    print("   python ollama_scanner.py [other args]")
    print("\n2. Fixed timeout (specific number of seconds):")
    print("   python ollama_scanner.py --timeout 300 [other args]")
    print("\n3. No timeout (wait indefinitely):")
    print("   python ollama_scanner.py --timeout 0 [other args]")
    
if __name__ == "__main__":
    main() 