#!/usr/bin/env python3
"""
Enhanced Timeout Handling for Ollama Commands
Adds dynamic timeout calculation and a timeout flag where 0 means no timeout.
"""

import os
import sys
import re
import glob
import shutil
from datetime import datetime

def backup_file(file_path):
    """Create a backup of the file before modifying it"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.bak.{timestamp}"
    shutil.copy2(file_path, backup_path)
    print(f"✅ Created backup: {backup_path}")
    return backup_path

def find_ollama_scanner_files():
    """Find files related to the ollama_scanner command"""
    # Define potential file patterns to search for
    patterns = [
        "ollama_scanner.py",
        "DiscordBot/ollama_scanner.py",
        "OpenWebui/backend/ollama_scanner_function.py",
        "**/ollama_scanner*.py"
    ]
    
    found_files = []
    
    for pattern in patterns:
        # Use glob to find files matching the pattern
        matches = glob.glob(pattern, recursive=True)
        for match in matches:
            if os.path.isfile(match) and match not in found_files:
                found_files.append(match)
    
    return found_files

def add_dynamic_timeout_function(file_path):
    """Add the calculate_dynamic_timeout function to the file"""
    with open(file_path, 'r') as file:
        content = file.read()
    
    # Check if the function already exists
    if "def calculate_dynamic_timeout(" in content:
        print(f"⚠️ calculate_dynamic_timeout function already exists in {file_path}")
        return False
    
    # Find a good place to insert the function
    # Look for common points like imports, other functions, etc.
    # Here's a simple heuristic: after imports but before the first function
    import_end = 0
    for match in re.finditer(r'import\s+[\w\s,]+|from\s+[\w.]+\s+import\s+[\w\s,]+', content):
        import_end = max(import_end, match.end())
    
    if import_end == 0:
        # No imports found, try to find a different insertion point
        # Maybe before the first function definition
        function_match = re.search(r'def\s+\w+\s*\(', content)
        if function_match:
            import_end = function_match.start()
        else:
            # Just insert at the beginning as a fallback
            import_end = 0
    
    # Add two newlines after the imports
    insertion_point = import_end
    
    # Define the dynamic timeout calculation function
    dynamic_timeout_function = """

# Dynamic timeout calculation function
def calculate_dynamic_timeout(model_name="", prompt="", max_tokens=1000, timeout_flag=None):
    \"\"\"
    Calculate a dynamic timeout based on model size, prompt length, and max tokens.
    
    Args:
        model_name (str): Name of the model, used to estimate size (e.g., "deepseek-r1:70b")
        prompt (str): The prompt text, longer prompts need more time
        max_tokens (int): Maximum tokens to generate, more tokens need more time
        timeout_flag (int, optional): If provided, overrides the calculated timeout.
                                     Use 0 for no timeout (None or inf).
    
    Returns:
        float or None: Timeout in seconds, or None for no timeout
    \"\"\"
    # If timeout_flag is explicitly set to 0, return None for no timeout
    if timeout_flag == 0:
        return None
    
    # If timeout_flag is provided and not 0, use that value
    if timeout_flag is not None:
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
    
    return final_timeout
"""
    
    # Insert the function
    modified_content = content[:insertion_point] + dynamic_timeout_function + content[insertion_point:]
    
    # Write the modified content back to the file
    with open(file_path, 'w') as file:
        file.write(modified_content)
    
    print(f"✅ Added calculate_dynamic_timeout function to {file_path}")
    return True

def add_timeout_flag_to_parser(file_path):
    """Add a timeout flag to the argument parser"""
    with open(file_path, 'r') as file:
        content = file.read()
    
    # Find the argument parser setup
    parser_match = re.search(r'parser\s*=\s*argparse\.ArgumentParser\(', content)
    if not parser_match:
        print(f"⚠️ Could not find argument parser in {file_path}")
        return False
    
    # Check if the timeout flag already exists
    if "add_argument('--timeout'" in content or "add_argument('-t'" in content:
        print(f"⚠️ Timeout flag already exists in {file_path}")
        return False
    
    # Look for the end of parser arguments - usually right before parser.parse_args()
    parser_end_match = re.search(r'parser\.parse_args\(', content)
    if not parser_end_match:
        print(f"⚠️ Could not find parser.parse_args() in {file_path}")
        return False
    
    # Find a suitable place to insert the timeout flag
    insertion_point = parser_end_match.start()
    
    # Search backward for the last add_argument call
    last_arg_match = re.search(r'parser\.add_argument\(.*?\)(?:\s*\n)+(?=\s*parser\.parse_args\()', content, re.DOTALL)
    if last_arg_match:
        insertion_point = last_arg_match.end()
    
    # Define the timeout flag argument
    timeout_flag_arg = """
    # Add timeout flag - 0 means no timeout
    parser.add_argument('--timeout', '-t', type=int, default=None,
                      help='Timeout in seconds for API requests. Use 0 for no timeout.')
"""
    
    # Insert the timeout flag
    modified_content = content[:insertion_point] + timeout_flag_arg + content[insertion_point:]
    
    # Write the modified content back to the file
    with open(file_path, 'w') as file:
        file.write(modified_content)
    
    print(f"✅ Added timeout flag argument to {file_path}")
    return True

def update_request_timeouts(file_path):
    """Update request timeout usage to use the dynamic calculation"""
    with open(file_path, 'r') as file:
        content = file.read()
    
    # Look for requests calls with timeout parameters
    # This pattern might need to be adjusted based on the actual code
    request_patterns = [
        r'requests\.get\((.*?)timeout\s*=\s*([^,\)]+)(.*?)\)',
        r'requests\.post\((.*?)timeout\s*=\s*([^,\)]+)(.*?)\)',
        r'session\.get\((.*?)timeout\s*=\s*([^,\)]+)(.*?)\)',
        r'session\.post\((.*?)timeout\s*=\s*([^,\)]+)(.*?)\)',
        r'request\((.*?)timeout\s*=\s*([^,\)]+)(.*?)\)'
    ]
    
    modified_content = content
    replace_count = 0
    
    for pattern in request_patterns:
        # Find and replace timeout parameters
        matches = list(re.finditer(pattern, modified_content, re.DOTALL))
        # Process matches in reverse to avoid offset issues
        for match in reversed(matches):
            full_match = match.group(0)
            prefix = match.group(1)
            timeout_val = match.group(2)
            suffix = match.group(3)
            
            # Skip if it already uses calculate_dynamic_timeout
            if "calculate_dynamic_timeout" in timeout_val:
                continue
            
            # Skip specific cases we don't want to modify
            if "timeout=5" in full_match and ("/api/tags" in full_match or "healthcheck" in full_match):
                # Don't modify quick health checks or tag listing endpoints
                continue
            
            # Extract model and prompt if possible for better timeout calculation
            model_extract = ""
            prompt_extract = ""
            max_tokens_extract = "1000"
            
            # Try to extract model name from nearby context
            model_context = modified_content[max(0, match.start() - 200):match.start()]
            model_name_match = re.search(r'model["\']?\s*[:=]\s*["\']([^"\']+)["\']', model_context, re.IGNORECASE)
            if model_name_match:
                model_extract = f', model_name="{model_name_match.group(1)}"'
            
            # Try to extract prompt
            prompt_match = re.search(r'prompt["\']?\s*[:=]\s*["\']([^"\']{1,50})["\']', model_context, re.IGNORECASE)
            if prompt_match:
                prompt_extract = f', prompt="{prompt_extract}"'
            
            # Try to extract max_tokens
            max_tokens_match = re.search(r'max_tokens["\']?\s*[:=]\s*(\d+)', model_context, re.IGNORECASE)
            if max_tokens_match:
                max_tokens_extract = max_tokens_match.group(1)
            
            # Create the replacement with dynamic timeout
            replacement = f'requests.post({prefix}timeout=calculate_dynamic_timeout(max_tokens={max_tokens_extract}{model_extract}{prompt_extract}, timeout_flag=args.timeout if "args" in locals() else None){suffix})'
            
            # Handle different request types
            if "requests.get" in full_match:
                replacement = f'requests.get({prefix}timeout=calculate_dynamic_timeout(timeout_flag=args.timeout if "args" in locals() else None){suffix})'
            elif "session.get" in full_match:
                replacement = f'session.get({prefix}timeout=calculate_dynamic_timeout(timeout_flag=args.timeout if "args" in locals() else None){suffix})'
            elif "session.post" in full_match:
                replacement = f'session.post({prefix}timeout=calculate_dynamic_timeout(max_tokens={max_tokens_extract}{model_extract}{prompt_extract}, timeout_flag=args.timeout if "args" in locals() else None){suffix})'
            
            # Apply the replacement
            modified_content = modified_content[:match.start()] + replacement + modified_content[match.end():]
            replace_count += 1
    
    # Only write if changes were made
    if replace_count > 0:
        with open(file_path, 'w') as file:
            file.write(modified_content)
        print(f"✅ Updated {replace_count} request timeout calls in {file_path}")
        return True
    else:
        print(f"⚠️ No request timeout calls were updated in {file_path}")
        return False

def update_command_help(file_path):
    """Update command help text to document the new timeout flag"""
    with open(file_path, 'r') as file:
        content = file.read()
    
    # Find command help text or documentation sections
    help_sections = [
        r'"""[^"]*?command[^"]*?"""',
        r"'''[^']*?command[^']*?'''",
        r"USAGE\s*=\s*(?:f?'''|\"\"\")[^'\"]*?(?:''',\"\"\")",
        r"help_text\s*=\s*(?:f?'''|\"\"\")[^'\"]*?(?:''',\"\"\")"
    ]
    
    modified_content = content
    updated = False
    
    for pattern in help_sections:
        matches = list(re.finditer(pattern, modified_content, re.DOTALL))
        for match in matches:
            section = match.group(0)
            
            # Check if the help already mentions timeout
            if "--timeout" in section or "-t" in section:
                continue
            
            # Add timeout information to the help text
            timeout_help = "\n    --timeout, -t: Timeout in seconds for API requests. Use 0 for no timeout."
            
            # Try to find a good place to insert (after other arguments)
            insertion_match = re.search(r'(-[-\w]+,\s*)?-[\w],.*?\n', section)
            if insertion_match:
                insertion_point = insertion_match.end()
                updated_section = section[:insertion_point] + timeout_help + section[insertion_point:]
                modified_content = modified_content.replace(section, updated_section)
                updated = True
            else:
                # If no good insertion point, try to add it before the closing quotes
                close_match = re.search(r'(?:"""|\'\'\')$', section)
                if close_match:
                    insertion_point = close_match.start()
                    updated_section = section[:insertion_point] + timeout_help + "\n    " + section[insertion_point:]
                    modified_content = modified_content.replace(section, updated_section)
                    updated = True
    
    if updated:
        with open(file_path, 'w') as file:
            file.write(modified_content)
        print(f"✅ Updated command help text in {file_path}")
        return True
    else:
        print(f"⚠️ No command help text was updated in {file_path}")
        return False

def main():
    """Main function to enhance timeout handling"""
    print("=" * 60)
    print("ENHANCED TIMEOUT HANDLING IMPLEMENTATION")
    print("=" * 60)
    print("This script will update timeout handling to:")
    print("1. Add dynamic timeout calculation based on model, prompt length, and max_tokens")
    print("2. Add a timeout flag where 0 means no timeout")
    print("=" * 60)
    
    # Find relevant files
    scanner_files = find_ollama_scanner_files()
    
    if not scanner_files:
        print("❌ No ollama_scanner files found")
        return False
    
    print(f"Found {len(scanner_files)} relevant files:")
    for file in scanner_files:
        print(f"  - {file}")
    
    print("\nApplying changes...")
    
    success_count = 0
    for file in scanner_files:
        print(f"\nProcessing {file}:")
        
        # Create a backup
        backup_file(file)
        
        # Apply changes
        func1 = add_dynamic_timeout_function(file)
        func2 = add_timeout_flag_to_parser(file)
        func3 = update_request_timeouts(file)
        func4 = update_command_help(file)
        
        if any([func1, func2, func3, func4]):
            success_count += 1
    
    print("\n" + "=" * 60)
    if success_count > 0:
        print(f"✅ Successfully enhanced timeout handling in {success_count} files")
        print("\nChanges made:")
        print("1. Added dynamic timeout calculation function")
        print("2. Added timeout flag (--timeout or -t) to command arguments")
        print("3. Updated request timeouts to use dynamic calculation")
        print("4. Updated command help text")
        print("\nUsage:")
        print("- Run with default dynamic timeout: python ollama_scanner.py [other args]")
        print("- Run with specific timeout: python ollama_scanner.py --timeout 300 [other args]")
        print("- Run with no timeout: python ollama_scanner.py --timeout 0 [other args]")
    else:
        print("❌ No changes were applied")
    
    return success_count > 0

if __name__ == "__main__":
    main() 