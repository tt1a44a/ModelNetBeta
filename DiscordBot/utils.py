import discord
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Union, Optional

logger = logging.getLogger("utils")

async def format_embed_message(
    title: str = None,
    description: str = None,
    fields: List[Dict[str, str]] = None,
    color: discord.Color = discord.Color.blue(),
    footer_text: str = None,
    thumbnail_url: str = None,
    image_url: str = None,
    timestamp: bool = False
) -> discord.Embed:
    """
    Format a Discord embed message with various components.
    
    Args:
        title (str, optional): The title of the embed.
        description (str, optional): The description of the embed.
        fields (List[Dict[str, str]], optional): List of fields to add to the embed.
                                               Each field is a dict with 'name', 'value', and optional 'inline' keys.
        color (discord.Color, optional): The color of the embed. Defaults to blue.
        footer_text (str, optional): Text to display in the footer.
        thumbnail_url (str, optional): URL for thumbnail image.
        image_url (str, optional): URL for main image.
        timestamp (bool, optional): Whether to include current timestamp.
        
    Returns:
        discord.Embed: The formatted embed object.
    """
    embed = discord.Embed(color=color)
    
    if title:
        embed.title = title
        
    if description:
        embed.description = description
        
    if fields:
        for field in fields:
            inline = field.get('inline', False)
            embed.add_field(
                name=field.get('name', 'Field'),
                value=field.get('value', 'No value'),
                inline=inline
            )
            
    if footer_text:
        embed.set_footer(text=footer_text)
        
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
        
    if image_url:
        embed.set_image(url=image_url)
        
    if timestamp:
        embed.timestamp = datetime.utcnow()
        
    return embed

async def safe_defer(interaction: discord.Interaction, ephemeral: bool = False) -> bool:
    """
    Safely defer a Discord interaction response.
    
    Args:
        interaction (discord.Interaction): The interaction to defer.
        ephemeral (bool, optional): Whether to make the response ephemeral. Defaults to False.
        
    Returns:
        bool: True if deferred successfully, False otherwise.
    """
    try:
        await interaction.response.defer(ephemeral=ephemeral)
        return True
    except Exception as e:
        logger.error(f"Error deferring interaction: {str(e)}")
        try:
            await interaction.followup.send(
                "I'm having trouble processing your request. Please try again.",
                ephemeral=True
            )
        except:
            pass
        return False

async def safe_followup(
    interaction: discord.Interaction,
    content: str = None,
    embed: discord.Embed = None,
    embeds: List[discord.Embed] = None,
    ephemeral: bool = False,
    suppress_errors: bool = False
) -> Optional[discord.Message]:
    """
    Safely send a followup message to a Discord interaction.
    
    Args:
        interaction (discord.Interaction): The interaction to send a followup to.
        content (str, optional): Text content of the message.
        embed (discord.Embed, optional): Single embed to send.
        embeds (List[discord.Embed], optional): List of embeds to send.
        ephemeral (bool, optional): Whether to make the response ephemeral. Defaults to False.
        suppress_errors (bool, optional): Whether to suppress error messages. Defaults to False.
        
    Returns:
        Optional[discord.Message]: The sent message if successful, None otherwise.
    """
    try:
        if embeds:
            return await interaction.followup.send(
                content=content,
                embeds=embeds,
                ephemeral=ephemeral
            )
        elif embed:
            return await interaction.followup.send(
                content=content,
                embed=embed,
                ephemeral=ephemeral
            )
        else:
            return await interaction.followup.send(
                content=content,
                ephemeral=ephemeral
            )
    except Exception as e:
        if not suppress_errors:
            logger.error(f"Error sending followup: {str(e)}")
            try:
                error_embed = await format_embed_message(
                    title="Error",
                    description=f"Failed to send the response: {str(e)}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            except:
                pass
        return None

def truncate_string(text: str, max_length: int = 1024, add_ellipsis: bool = True) -> str:
    """
    Truncate a string to a maximum length.
    
    Args:
        text (str): The string to truncate.
        max_length (int, optional): Maximum length of the string. Defaults to 1024.
        add_ellipsis (bool, optional): Whether to add "..." at the end of truncated strings. Defaults to True.
        
    Returns:
        str: The truncated string.
    """
    if not text:
        return ""
        
    if len(text) <= max_length:
        return text
        
    if add_ellipsis:
        return text[:max_length-3] + "..."
    else:
        return text[:max_length] 