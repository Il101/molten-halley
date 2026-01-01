import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from pathlib import Path
import sys

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))
from utils.config import get_config

async def generate_session():
    """
    Utility to generate a Telethon StringSession.
    Usage: python utils/gen_session.py
    """
    print("\n--- Telegram StringSession Generator ---\n")
    
    # Try to get credentials from config/env
    config = get_config()
    api_id = config.get('telegram', {}).get('api_id')
    api_hash = config.get('telegram', {}).get('api_hash')
    
    if not api_id or not api_hash:
        print("API credentials not found in config or environment.")
        api_id = input("Enter your API_ID: ").strip()
        api_hash = input("Enter your API_HASH: ").strip()
    else:
        print(f"Using API_ID: {api_id} (from config/env)")

    if not api_id or not api_hash:
        print("Error: API_ID and API_HASH are required.")
        return

    # Use StringSession() as the first argument to create a new session
    # which we'll save after logging in.
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    
    try:
        await client.start()
        
        session_string = client.session.save()
        
        print("\n" + "="*60)
        print("SUCCESS! Your Telegram StringSession is:")
        print("="*60)
        print(f"\n{session_string}\n")
        print("="*60)
        print("\nCopy the long string above and set it as TELEGRAM_SESSION_STRING\nin your Railway environment variables.")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(generate_session())
