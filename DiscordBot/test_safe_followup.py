#!/usr/bin/env python3
"""
Test script to verify the fix for safe_followup function
"""

import asyncio
import discord
from discord import Embed

# Mock Discord interaction
class MockInteraction:
    class MockFollowup:
        async def send(self, content=None, embed=None, embeds=None, ephemeral=False):
            print(f"Sending followup with content: {content}")
            if embed:
                print(f"Embed title: {embed.title}")
                print(f"Embed description: {embed.description}")
            if embeds:
                for i, e in enumerate(embeds):
                    print(f"Embed {i+1} title: {e.title}")
                    print(f"Embed {i+1} description: {e.description}")
            print(f"Ephemeral: {ephemeral}")
            return "Mock response"
    
    def __init__(self):
        self.followup = self.MockFollowup()

# Define our fixed safe_followup function
async def safe_followup_wrapper(interaction, content=None, embed=None, ephemeral=False):
    print("Using safe_followup_wrapper")
    if embed:
        await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)
    else:
        await interaction.followup.send(content=content, ephemeral=ephemeral)

# Define function similar to handle_db_info
async def test_db_info(interaction, safe_followup):
    print("Running test_db_info with provided safe_followup function")
    
    # Create test embeds
    main_embed = Embed(title="Test Main Embed", description="This is the main embed")
    second_embed = Embed(title="Test Second Embed", description="This is the second embed")
    
    # Use the provided safe_followup function
    await safe_followup(interaction, content=None, embed=main_embed)
    await safe_followup(interaction, content=None, embed=second_embed)
    await safe_followup(interaction, content="Test message without embed")

async def main():
    # Create mock interaction
    interaction = MockInteraction()
    
    print("=== Testing with our wrapper function ===")
    await test_db_info(interaction, safe_followup_wrapper)

if __name__ == "__main__":
    # Run the async test
    asyncio.run(main()) 