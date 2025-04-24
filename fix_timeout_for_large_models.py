#!/usr/bin/env python3
"""
Fix script for large model timeout issues in the Discord bot
"""

import re
import sys
import os
import shutil
import datetime

def backup_file(file_path):
    """Create a backup of the original file"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.bak.{timestamp}"
    shutil.copy2(file_path, backup_path)
    print(f"Created backup at: {backup_path}")
    return backup_path

def update_timeout_settings(file_path):
    """Update the dynamic timeout calculation for large models"""
    try:
        with open(file_path, 'r') as file:
            content = file.read()
        
        # Pattern to match the dynamic timeout line
        timeout_pattern = r'dynamic_timeout = min\(900, max\(180, base_timeout \* prompt_factor \* param_factor \* token_factor\)\)'
        
        # Check if the pattern exists in the file
        if not re.search(timeout_pattern, content):
            print("Error: Could not find the dynamic timeout calculation in the file.")
            return False
        
        # Apply the fix
        modified_content = re.sub(
            timeout_pattern,
            'dynamic_timeout = min(1500, max(180, base_timeout * prompt_factor * param_factor * token_factor))',
            content
        )
        
        # Look for param_factor calculation for large models
        param_factor_pattern = r'if "B" in param_size:\s+size_num = float\(param_size\.replace\("B", ""\)\.strip\(\)\)\s+param_factor = 1\.0 \+ \(size_num / 10\)'
        
        # Adjust param_factor for very large models
        if re.search(param_factor_pattern, modified_content):
            modified_param_factor = (
                'if "B" in param_size:\n'
                '                    size_num = float(param_size.replace("B", "").strip())\n'
                '                    # Special handling for very large models (50B+)\n'
                '                    if size_num >= 50:\n'
                '                        param_factor = 2.5 + (size_num / 20)  # Much more time for 70B models\n'
                '                    else:\n'
                '                        param_factor = 1.0 + (size_num / 10)  # Standard scaling for smaller models'
            )
            modified_content = re.sub(param_factor_pattern, modified_param_factor, modified_content)
        
        # Write the modified content back to the file
        with open(file_path, 'w') as file:
            file.write(modified_content)
        
        print(f"Updated timeout settings in {file_path}")
        print("Changes made:")
        print("1. Increased maximum dynamic timeout from 900s (15min) to 1500s (25min)")
        print("2. Added special handling for very large models (50B+) with larger timeout multipliers")
        return True
        
    except Exception as e:
        print(f"Error updating file: {str(e)}")
        return False

def main():
    """Main function to apply the fix"""
    # Path to the Discord bot file
    bot_file = os.path.join("DiscordBot", "discord_bot.py")
    
    if not os.path.exists(bot_file):
        print(f"Error: Discord bot file not found at {bot_file}")
        return False
    
    # Create a backup
    backup_path = backup_file(bot_file)
    
    # Apply the fix
    success = update_timeout_settings(bot_file)
    
    if success:
        print("\nTimeout fix applied successfully!")
        print(f"Original file was backed up to: {backup_path}")
        print("\nRecommendations:")
        print("1. Restart the Discord bot to apply the changes")
        print("2. When using large models (50B+), try to keep prompts short")
        print("3. Consider setting max_tokens to lower values (e.g., 500) for faster responses")
        return True
    else:
        print("\nFailed to apply timeout fix.")
        print(f"You can restore the backup from: {backup_path}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 