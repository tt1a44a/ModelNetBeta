# Discord Developer Portal Setup Checklist

## OAuth2 Configuration Steps

1. **Go to the [Discord Developer Portal](https://discord.com/developers/applications)**

2. **Select Your Application:**
   - Application Name: (Your bot's name)
   - Application ID: `1361234219812126833`

3. **Check OAuth2 Settings:**
   - Go to the OAuth2 tab in the left sidebar
   - Ensure the following settings are correct:

4. **Verify Redirect URIs:**
   - Under "Redirects", make sure the following URI is listed:
     ```
     http://localhost:4466/callback
     ```
   - If it's not there, click "Add Redirect" and add it
   - Make sure there are no trailing slashes or extra characters
   - The URI must match EXACTLY what's in the code

5. **Verify Client ID and Secret:**
   - Client ID: `1361234219812126833`
   - Client Secret: Should be set to `MDe1ai2QRWGtHgr3jp0gT1dKeoPXSDGh`
   - If the client secret doesn't match, click "Reset Secret" and update your .env file

6. **Check Application Scopes:**
   - Under "OAuth2 URL Generator", make sure the following scopes are selected:
     - `bot`
     - `applications.commands`

7. **Check Bot Permissions:**
   - Make sure the following permissions are selected:
     - View Channels
     - Send Messages
     - Read Message History
     - Use Slash Commands

## Testing OAuth Flow

1. **Run the OAuth callback server:**
   ```bash
   cd /home/adam/Documents/Code/Ollama_Scanner/DiscordBot
   python oauth_server.py
   ```

2. **Generate and use the invite URL:**
   ```bash
   cd /home/adam/Documents/Code/Ollama_Scanner/DiscordBot
   python generate_invite.py
   ```

3. **Copy the URL and open it in your browser**

4. **If you get the "invalid_client" error:**
   - Run the token exchange test tool:
     ```bash
     python test_token_exchange.py
     ```
   - Follow the prompts to test the OAuth flow directly

## Common Issues

### "invalid_client" Error
This error usually means one of the following:

1. **Client ID is incorrect**
   - Verify it matches exactly what's in the Discord Developer Portal

2. **Client Secret is incorrect**
   - Reset your client secret in the Developer Portal and update your .env file

3. **Redirect URI mismatch**
   - The redirect URI in your code must match what's registered EXACTLY
   - Check for trailing slashes, http vs https, etc.

4. **Application not correctly configured**
   - Make sure the application is properly set up with the right scopes

### Other OAuth Issues

1. **"unauthorized_client" Error**
   - The application might not have the required scopes or permissions

2. **"invalid_grant" Error**
   - The authorization code might be expired or already used
   - These codes can only be used once and expire quickly

3. **"redirect_uri_mismatch" Error**
   - The redirect URI in the request doesn't match what's registered 