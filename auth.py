import asyncio
import os
import glob
from pyrogram import Client
from src.config import API_ID, API_HASH

DATA_DIR = "data"

async def main():
    print("=== Telegram Multi-Account Manager ===")
    
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # List existing sessions
    sessions = glob.glob(os.path.join(DATA_DIR, "*.session"))
    print(f"Found {len(sessions)} existing sessions:")
    for s in sessions:
        print(f" - {os.path.basename(s)}")
    
    # If no sessions, force create one
    if not sessions:
        print("\nNo sessions found. Let's create the first one.")
        await create_session()
    
    # Loop to add more
    while True:
        choice = input("\nDo you want to add a NEW account? (y/n): ").lower().strip()
        if choice == 'y':
            await create_session()
        else:
            break
            
    print("\nAuthentication setup complete.")

async def create_session():
    # Generate unique name
    existing = glob.glob(os.path.join(DATA_DIR, "session_*.session"))
    next_idx = len(existing) + 1
    
    # Allow custom name or auto
    name_input = input(f"Enter session name (default: session_{next_idx}): ").strip()
    if not name_input:
        session_name = f"session_{next_idx}"
    else:
        session_name = name_input
        
    session_path = os.path.join(DATA_DIR, session_name)
    
    print(f"Initializing {session_name}...")
    
    # We use a temporary client just to auth and save session
    app = Client(
        session_path,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=DATA_DIR # Important to keep .session in data/
    )
    
    try:
        await app.start()
        me = await app.get_me()
        print(f"✅ Successfully logged in as: {me.first_name} (@{me.username})")
        print(f"Saved to {session_path}.session")
        await app.stop()
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
