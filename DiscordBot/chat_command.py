import logging
import discord
from discord import app_commands
import uuid
from datetime import datetime
import json
from typing import Dict, Any, List, Optional

from database import Database
from utils import format_embed_message, safe_defer
from ai_providers import get_ai_response

logger = logging.getLogger(__name__)

def register_chat_command(bot, safe_defer, safe_followup):
    """Register the chat command with the bot"""
    
    @bot.tree.command(name="chat", description="Chat with AI models")
    @app_commands.describe(
        model="Model to use (ID or name)",
        prompt="Your message to the AI",
        system_prompt="Optional system prompt to guide the AI's behavior",
        temperature="Temperature (0.0-2.0, higher = more creative)",
        max_tokens="Maximum response length in tokens",
        public="Make this conversation visible to everyone (default: only visible to you)",
        continue_last="Continue your last conversation with this model",
        quickprompt="Find and use any available model matching this name (like /quickprompt)"
    )
    async def chat_command(
        interaction: discord.Interaction,
        model: str,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        public: bool = False,
        continue_last: bool = False,
        quickprompt: bool = False
    ):
        """Handle chat requests to AI models"""
        await safe_defer(interaction, ephemeral=not public)
        
        try:
            # Validate parameters
            if not prompt or not prompt.strip():
                error_embed = await format_embed_message(
                    title="Missing Prompt",
                    description="Please provide a message to send to the AI.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                return
                
            if temperature is not None and (temperature < 0.0 or temperature > 2.0):
                error_embed = await format_embed_message(
                    title="Invalid Temperature",
                    description="Temperature must be between 0.0 and 2.0.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                return
                
            if max_tokens is not None and (max_tokens < 1 or max_tokens > 4096):
                error_embed = await format_embed_message(
                    title="Invalid Token Limit",
                    description="Token limit must be between 1 and 4096.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                return
            
            # Check if we're using quickprompt mode
            if quickprompt:
                # If using quickprompt mode, use process_model_chat function directly
                # This will find a matching model name and handle the conversation
                from discord_bot import process_model_chat
                
                await process_model_chat(
                    interaction=interaction,
                    model_name=model,
                    prompt=prompt,
                    system_prompt=system_prompt or "",
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return
            
            # Find the model (standard mode)
            model_info = find_model(model)
            
            if not model_info:
                error_embed = await format_embed_message(
                    title="Model Not Found",
                    description=f"Could not find model with ID or name '{model}'.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                return
                
            model_id, model_name, provider, category = model_info
            
            # Handle conversation context
            conversation_id = None
            previous_messages = []
            
            if continue_last:
                # Find the most recent conversation with this model
                last_conversation = get_last_conversation(interaction.user.id, model_id)
                
                if last_conversation:
                    conversation_id, previous_messages = last_conversation
                    
                    # Let the user know we're continuing a conversation
                    logger.info(f"Continuing conversation {conversation_id} for user {interaction.user.id} with model {model_id}")
                
            # Create new conversation if not continuing
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
            
            # Prepare message history for the AI provider
            message_history = previous_messages.copy()
            message_history.append({
                "role": "user",
                "content": prompt
            })
            
            # Create a typing indicator to show the bot is processing
            async with interaction.channel.typing():
                # Get response from AI model
                response, usage = await get_ai_response(
                    provider=provider,
                    model=model_name,
                    messages=message_history,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                # Save the conversation to the database
                save_conversation(
                    conversation_id=conversation_id,
                    user_id=interaction.user.id,
                    model_id=model_id,
                    prompt=prompt,
                    response=response,
                    system_prompt=system_prompt,
                    parameters={
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "public": public
                    },
                    usage=usage
                )
                
                # Format the response
                embed = create_chat_embed(
                    prompt=prompt,
                    response=response,
                    model_name=model_name,
                    provider=provider,
                    usage=usage,
                    public=public,
                    user=interaction.user,
                    conversation_id=conversation_id
                )
                
                # Send the response
                await safe_followup(interaction, embed=embed)
                
        except Exception as e:
            logger.error(f"Error in chat command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Chat",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
    
    return chat_command

def find_model(model_identifier: str) -> Optional[tuple]:
    """Find a model by ID or name"""
    try:
        # Try to find by ID first
        if model_identifier.isdigit():
            query = """
                SELECT id, name, provider, category
                FROM models
                WHERE id = %s AND is_available = TRUE
            """
            model = Database.fetch_one(query, (int(model_identifier),))
            
            if model:
                return model
        
        # If not found or not an ID, try to find by name
        query = """
            SELECT id, name, provider, category
            FROM models
            WHERE name LIKE %s AND is_available = TRUE
            LIMIT 1
        """
        model = Database.fetch_one(query, (f"%{model_identifier}%",))
        
        return model
    except Exception as e:
        logger.error(f"Error finding model: {str(e)}")
        return None

def get_last_conversation(user_id: int, model_id: int) -> Optional[tuple]:
    """Get the most recent conversation between a user and a model"""
    try:
        # Find the most recent conversation
        query = """
            SELECT conversation_id, messages
            FROM chat_history
            WHERE user_id = %s AND model_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """
        result = Database.fetch_one(query, (user_id, model_id))
        
        if not result:
            return None
            
        conversation_id, messages_json = result
        
        # Parse the messages
        try:
            messages = json.loads(messages_json) if messages_json else []
            return (conversation_id, messages)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in messages for conversation {conversation_id}")
            return (conversation_id, [])
            
    except Exception as e:
        logger.error(f"Error getting last conversation: {str(e)}")
        return None

def save_conversation(
    conversation_id: str,
    user_id: int,
    model_id: int,
    prompt: str,
    response: str,
    system_prompt: Optional[str],
    parameters: Dict[str, Any],
    usage: Dict[str, int]
) -> None:
    """Save a conversation to the database"""
    try:
        # Format the conversation messages
        messages = []
        
        # Add the user message
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        # Add the assistant response
        messages.append({
            "role": "assistant",
            "content": response
        })
        
        # Insert or update the conversation
        query = """
            INSERT INTO chat_history (
                conversation_id, user_id, model_id, prompt, response,
                system_prompt, parameters, messages, 
                prompt_tokens, completion_tokens, total_tokens
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        Database.execute(query, (
            conversation_id,
            user_id,
            model_id,
            prompt,
            response,
            system_prompt,
            json.dumps(parameters),
            json.dumps(messages),
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            usage.get("total_tokens", 0)
        ))
        
    except Exception as e:
        logger.error(f"Error saving conversation: {str(e)}")
        raise

def create_chat_embed(
    prompt: str,
    response: str,
    model_name: str,
    provider: str,
    usage: Dict[str, int],
    public: bool,
    user: discord.User,
    conversation_id: str
) -> discord.Embed:
    """Create an embed for a chat response"""
    # Create the embed
    embed = discord.Embed(
        title=f"Chat with {model_name}",
        color=discord.Color.blue()
    )
    
    # Add user info and prompt
    embed.add_field(
        name=f"{user.display_name}'s Prompt:",
        value=prompt[:1024],  # Discord has 1024 char limit for field values
        inline=False
    )
    
    # Add AI response
    # Split long responses into multiple fields if needed
    if len(response) <= 1024:
        embed.add_field(
            name="Response:",
            value=response,
            inline=False
        )
    else:
        # Split the response into chunks of 1024 characters
        chunks = [response[i:i+1024] for i in range(0, len(response), 1024)]
        
        embed.add_field(
            name="Response:",
            value=chunks[0],
            inline=False
        )
        
        for i, chunk in enumerate(chunks[1:], 1):
            embed.add_field(
                name=f"Response (continued {i}):",
                value=chunk,
                inline=False
            )
    
    # Add token usage info
    token_info = []
    
    if "prompt_tokens" in usage:
        token_info.append(f"Prompt: {usage['prompt_tokens']}")
    
    if "completion_tokens" in usage:
        token_info.append(f"Completion: {usage['completion_tokens']}")
    
    if "total_tokens" in usage:
        token_info.append(f"Total: {usage['total_tokens']}")
    
    if token_info:
        embed.add_field(
            name="Token Usage:",
            value=" | ".join(token_info),
            inline=True
        )
    
    # Add model info
    embed.add_field(
        name="Model Info:",
        value=f"{model_name} by {provider}",
        inline=True
    )
    
    # Add visibility info
    embed.add_field(
        name="Visibility:",
        value="Public" if public else "Private",
        inline=True
    )
    
    # Add conversation ID and timestamp
    embed.set_footer(text=f"Conversation ID: {conversation_id} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return embed 