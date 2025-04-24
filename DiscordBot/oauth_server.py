#!/usr/bin/env python3
"""
OAuth2 callback server for Discord bot authentication
"""

from flask import Flask, request, redirect
import os
from dotenv import load_dotenv
import requests
import socket
import sys
import json
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('oauth_server')

app = Flask(__name__)
app.debug = False  # Explicitly disable debug mode
load_dotenv()

# Load and log credentials (first 5 chars only for security)
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
REDIRECT_URI = 'http://localhost:4466/callback'
PORT = 4466

# Log credential info (partial) for debugging
if CLIENT_ID and CLIENT_SECRET:
    client_id_prefix = CLIENT_ID[:5] if len(CLIENT_ID) > 5 else CLIENT_ID
    client_secret_prefix = CLIENT_SECRET[:5] if len(CLIENT_SECRET) > 5 else CLIENT_SECRET
    logger.info(f"Loaded credentials - Client ID: {client_id_prefix}... (length: {len(CLIENT_ID)})")
    logger.info(f"Client Secret: {client_secret_prefix}... (length: {len(CLIENT_SECRET)})")
else:
    logger.error("Missing CLIENT_ID or CLIENT_SECRET in environment variables")
    logger.error(f"CLIENT_ID present: {CLIENT_ID is not None}")
    logger.error(f"CLIENT_SECRET present: {CLIENT_SECRET is not None}")

@app.route('/')
def index():
    return """
    <html>
        <body>
            <h1>OAuth2 Callback Server</h1>
            <p>This server is running and ready to handle Discord OAuth2 callbacks.</p>
            <p>You can close this window after the authentication is complete.</p>
        </body>
    </html>
    """

@app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('guild_id')
    
    if not code:
        logger.error("No code received in callback")
        return "Authentication failed: No code received", 400
    
    logger.info(f"Received auth code: {code[:5]}... for guild: {guild_id}")
    
    try:
        # Format the data as application/x-www-form-urlencoded
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        logger.info("Sending token request to Discord...")
        response = requests.post(
            'https://discord.com/api/oauth2/token',
            data=data,
            headers=headers
        )
        
        logger.info(f"Discord API response: Status {response.status_code}")
        
        if response.status_code == 200:
            logger.info("Authentication successful")
            return """
            <html>
                <body>
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window and return to Discord.</p>
                    <p>The bot has been added to your server.</p>
                </body>
            </html>
            """
        else:
            error_text = response.text
            logger.error(f"Auth failed: {error_text}")
            
            # For troubleshooting invalid_client error
            if '"error": "invalid_client"' in error_text:
                logger.error("Invalid client error detected. This usually means:")
                logger.error("1. Client ID or Secret is incorrect")
                logger.error("2. Application settings may be misconfigured")
                logger.error(f"Using Client ID: {CLIENT_ID}")
                
            return f"""
            <html>
                <body>
                    <h1>Authentication Failed</h1>
                    <p>Error: {error_text}</p>
                    <p>Please check the server logs for more information.</p>
                </body>
            </html>
            """, 400
            
    except Exception as e:
        logger.exception("Error in authentication process")
        return f"Authentication failed: {str(e)}", 500

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

if __name__ == '__main__':
    print("Starting OAuth2 callback server...")
    print("Make sure to keep this window open while authenticating the bot.")
    print(f"The server will be available at http://localhost:{PORT}/callback")
    
    # Check environment variables
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Missing CLIENT_ID or CLIENT_SECRET in environment variables.")
        print("Please update your .env file with the correct Discord application credentials.")
        sys.exit(1)
    
    # Check if port is already in use
    if is_port_in_use(PORT):
        print(f"Error: Port {PORT} is already in use. Please choose a different port or close the application using it.")
        sys.exit(1)
    
    try:
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Error starting server: {str(e)}")
        sys.exit(1) 