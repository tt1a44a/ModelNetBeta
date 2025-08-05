# The Helvete Administration Suite - by Helvete Labs - Crafted with 💚 and THC in 🇨🇦

This suite consists of Discord bots each serving different purposes for server management and user interaction. These have NOT been tested!

## 🤖 Bot Overview

### 1. get-a-room.py
**Purpose**: On-demand text channel creation

Creates private text channels for users on request through an interactive button interface.

**Features:**
- Green button interface for room requests
- Automatic channel creation named after the user
- Private confirmation messages
- DM notifications to users
- Error handling for blocked DMs

**Usage:**
```
!setup  # Deploy the room request button
```

### 2. ghetto_union_bank.py
**Purpose**: Reference code generation system 

Generates alphanumeric reference codes for users with remote logging capabilities.

**Features:**
- Three profile types (A, B, C) with different button styles
- 8-character reference code generation
- One-time use per profile type per user
- DM delivery of reference codes
- Remote server logging of all requests

**Usage:**
```
!setup  # Deploy the profile request buttons
```

**Configuration:**
- Set `REMOTE_SERVER_ID` and `REMOTE_CHANNEL_ID` for logging destination

### 3. tattletale.py
**Purpose**: Cross-channel message forwarding

Automatically forwards messages from a source channel to a target channel.

**Features:**
- Real-time message monitoring
- Text and attachment forwarding
- Bot message filtering to prevent loops
- Cross-server relay capability

**Configuration:**
- Set `SOURCE_CHANNEL_ID` for the monitored channel
- Set `TARGET_CHANNEL_ID` for the destination channel

### 4. jeeves_but_wit_drugs.py
**Purpose**: Customer support ticket management

Comprehensive help desk system with persistent storage and search capabilities.

**Features:**
- Four ticket categories: Support, Sales, Partnerships, Other
- DM-based ticket creation workflow
- Sequential ticket numbering (001, 002, etc.)
- Persistent JSON database storage
- Ticket search by number or username
- Remote server notification system

**Usage:**
```
!ticket                    # Deploy ticket creation buttons
!findticket <search_term>  # Search tickets by number or username
```

**Files Created:**
- `ticket_counter.txt` - Tracks current ticket number
- `tickets.json` - Complete ticket database

### 5. gabagoolfiend.py
**Purpose**: Subscription payment management

Automated payment reminder and confirmation system with 30-day billing cycles.

**Features:**
- First purchase date logging
- Automatic 30-day payment cycles
- 5-day advance payment reminders
- Remote payment confirmation processing
- Persistent user payment status tracking
- Daily automated reminder checks

**Usage:**
```
!firstpurchase  # Log initial purchase and start payment cycle
```

**Files Created:**
- `user_data.json` - User payment status and dates

**Payment Confirmation Format:**
```
Payment Confirmed User: <user_id>
```

## 🛠️ Setup Instructions

### Prerequisites
```bash
pip install discord.py
```

### Configuration Steps

1. **Discord Bot Setup:**
   - Create a bot application at https://discord.com/developers/applications
   - Copy the bot token
   - Replace `"YOUR_BOT_TOKEN"` in each bot file

2. **Server/Channel IDs:**
   - Enable Developer Mode in Discord
   - Right-click servers/channels to copy IDs
   - Update the ID constants in each bot file

3. **Bot Permissions:**
   Required intents and permissions vary by bot:
   - `guilds`, `members`, `messages`, `dm_messages`, `message_content`
   - Channel management permissions for room creation
   - Send messages in target channels

### Running the Bots
```bash
python get_a_room.py
python ghetto_union_bank.py
python tattletale.py
python jeeves_but_with_drugs.py
python gabagoolfiend.py
```

## 📋 Bot Intents Required
| **Bot**          | **Guilds** | **Members** | **Messages** | **DM Messages** | **Message Content** | **Voice States** |
| ---------------- | ---------- | ----------- | ------------ | --------------- | ------------------- | ---------------- |
| get_a_room       |     ✅     |      ✅     |     ✅       |      ✅         |         -           |       ✅         |
| ghetto_union_bank|     ✅     |      ✅     |     ✅       |      ✅         |         -           |        -         |
| tattletale       |     ✅     |      -      |     ✅       |       -         |         ✅          |        -         |
| jeeves           |     ✅     |      ✅     |     ✅       |      ✅         |         ✅          |        -         |
| gabagoolfiend    |     ✅     |      ✅     |     ✅       |      ✅         |         ✅          |        -         |


## 🔧 Customization Options (though defaults are safe to use)

### Timing Adjustments
- **Gabagool Fiend**: Modify `timedelta(days=30)` for different billing cycles
- **Gabagool Fiend**: Change `timedelta(days=5)` for different reminder timing

### Reference Code Format
- **Ghetto Union Bank**: Adjust `length=8` in `generate_reference_code()` function
- **Ghetto Union Bank**: Modify character set in `string.ascii_uppercase + string.digits`

### Ticket Categories
- **Jeeves but with Drugs**: Add/remove buttons in `TicketButtonView` class
- **Jeeves but with Drugs**: Customize button labels and styles

## 📝 License
Licensed under the GNU General Public License v2.0.
