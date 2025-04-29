# Discord Message Formatting Guide

This document provides reference examples for formatting messages in the Discord bot.

## Basic Text Formatting

```
**Bold Text**                   -> Bold Text
*Italic Text* or _Italic Text_  -> Italic Text
__Underlined Text__             -> Underlined Text
~~Strikethrough Text~~          -> Strikethrough Text
`inline code`                   -> inline code
```python
# Code blocks with syntax highlighting
def hello():
    return "Hello, world!"
```
> Quote text                    -> Quote text
>>> Multi-line quotes           -> Multiple line quotes
```

## Emoji Use

Emojis help make messages more engaging and visually distinctive:

- 🤖 - For bot/AI related content
- 💬 - For chat/messages
- 📊 - For statistics/data
- ⚠️ - For warnings
- ❌ - For errors
- ✅ - For success
- 📋 - For lists/commands
- 🔍 - For search functions
- ⚙️ - For settings/configurations
- 🔄 - For updates/syncing
- 💾 - For saving/database
- 🖥️ - For server/endpoint operations

## Message Structure Patterns

### Standard Command Response

```
# Embed with title and description
title = "Command Result"
description = "Operation completed successfully."

# Add fields for structured data
fields = [
    {"name": "Status", "value": "✅ Completed", "inline": True},
    {"name": "Processed", "value": "42 items", "inline": True},
    {"name": "Time", "value": "3.5s", "inline": True},
    {"name": "Details", "value": "Additional information here...", "inline": False}
]
```

### Model List Entry

```
**llama3:8b-instruct** • 8B • Q4_K_M • 4.2 GB (ID: `123`)
```

### Error Pattern

```
# Error embed
title = "❌ Error Occurred"
description = "Failed to connect to the endpoint."
color = discord.Color.red()

# Add error details
fields = [
    {"name": "Error Type", "value": "ConnectionError", "inline": True},
    {"name": "Status", "value": "Timeout", "inline": True},
    {"name": "Details", "value": "```\nError details here...\n```", "inline": False}
]
```

### Bot Help Pattern

```
# Help categories with emoji prefixes
fields = [
    {"name": "📋 Model Commands", "value": "• `/command1` - Description\n• `/command2` - Description", "inline": False},
    {"name": "💬 Chat Commands", "value": "• `/chat` - Chat with a model\n• `/quickprompt` - Quick interaction", "inline": False}
]
```

## Best Practices

1. **Use Embeds for Most Responses**
   - Structured, visually appealing
   - Consistent coloring by response type
   - Supports fields for organized data

2. **Chunking Strategies for Long Content**
   - Split large responses across multiple messages
   - Use embeds for metadata, plain messages for content
   - Preserve code blocks when splitting

3. **Content Organization**
   - Use bullet points (•) for lists
   - Use headings (** for bolding) to organize sections
   - Group related information in fields
   - Use inline fields for related/comparable data

4. **Visual Consistency**
   - Use consistent colors for specific message types:
     - Blue (`discord.Color.blue()`) - Normal information
     - Green (`discord.Color.green()`) - Success
     - Red (`discord.Color.red()`) - Errors
     - Orange (`discord.Color.orange()`) - Warnings
     - Purple (`discord.Color.purple()`) - Processing/thinking

5. **Code vs Plain Text**
   - Use code blocks for:
     - Model output containing code
     - Command examples
     - Long text outputs (for monospace formatting)
   - Use plain text with markdown for:
     - Short responses
     - Navigation/instructional content
     - Lists of options

## Function Reference

The following utility functions are available for message formatting:

1. `format_embed_message()` - Creates consistently styled embeds
2. `format_list_as_pages()` - Creates paginated embeds for long lists
3. `format_model_details()` - Formats model information consistently
4. `format_code_or_text()` - Intelligently formats content as code/text

## Example Full Message Flow (Chat Command)

1. **Initial Response (Thinking)**
   - Purple embed with "Thinking..." title
   - Description showing what model is being used

2. **Response Header (Metadata)**
   - Green embed with model name in title
   - Fields for metrics (time, tokens, etc.)
   - Field with prompt used

3. **Response Content**
   - Follow-up message(s) with model's response
   - Properly formatted code blocks if present
   - Split into multiple messages if needed

4. **Optional Verbose Details**
   - Code block with JSON API details 