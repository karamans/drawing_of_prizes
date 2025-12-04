import asyncio
import hashlib
import logging
import re
import os
import glob
import random
from typing import Optional, List

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, UserAlreadyParticipant, PeerIdInvalid

from src.config import (
    API_ID, API_HASH, SESSION_NAME, SOURCE_CHAT, 
    TARGET_CHANNEL_ID, KEYWORDS, LEAVE_DELAY
)
from src.database import (
    init_db, add_post, is_post_exists, 
    add_subscription
)
from src.janitor import janitor_task

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ensure data directory exists
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Global lists for clients
clients: List[Client] = []
master_app: Optional[Client] = None
worker_index = 0

def get_next_client() -> Client:
    """Round-robin selection of clients (including master) for tasks."""
    global worker_index
    if not clients:
        raise Exception("No clients initialized")
    
    client = clients[worker_index]
    worker_index = (worker_index + 1) % len(clients)
    return client

def get_content_hash(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def extract_links(text: str, entities: list) -> list[str]:
    """Extracts t.me links from text and entities."""
    links = []
    if not text:
        return links
    regex_links = re.findall(r'(https?://t\.me/[a-zA-Z0-9_/+]+)', text)
    links.extend(regex_links)
    if entities:
        for entity in entities:
            if entity.type.name == "TEXT_LINK":
                if "t.me" in entity.url:
                    links.append(entity.url)
    return list(set(links)) 

def matches_keywords(text: str) -> bool:
    if not KEYWORDS or (len(KEYWORDS) == 1 and KEYWORDS[0] == ""):
        return True 
    text_lower = text.lower()
    return any(k.strip().lower() in text_lower for k in KEYWORDS)

async def process_public_post(client: Client, link: str) -> Optional[Message]:
    """
    Fetches public post using the specific client.
    """
    try:
        parts = link.split('/')
        if 't.me' not in parts:
            return None
            
        if 'c' in parts:
            # Private link format t.me/c/chat_id/msg_id
            try:
                chat_id_idx = parts.index('c') + 1
                msg_id_idx = chat_id_idx + 1
                chat_id = int("-100" + parts[chat_id_idx])
                msg_id = int(parts[msg_id_idx])
                return await client.get_messages(chat_id, msg_id)
            except Exception as e:
                logger.error(f"Failed to parse private link {link}: {e}")
                return None
        else:
            # Username format
            username = parts[-2]
            msg_id = int(parts[-1])
            return await client.get_messages(username, msg_id)
            
    except FloodWait as e:
        logger.warning(f"[{client.name}] FloodWait fetching post {link}: {e.value}s wait required.")
        if e.value > 300:
             # If wait is too long, return None so we might try another client or skip?
             # Actually, we should sleep inside this client context or just fail this attempt.
             logger.error(f"FloodWait too long, skipping on this client.")
             return None
        await asyncio.sleep(e.value + 2)
        try:
            username = parts[-2]
            msg_id = int(parts[-1])
            return await client.get_messages(username, msg_id)
        except Exception:
             return None
    except Exception as e:
        logger.error(f"[{client.name}] Error fetching public post {link}: {e}")
        return None

async def process_private_invite(client: Client, link: str) -> Optional[Message]:
    """
    Joins private channel using specific client.
    """
    try:
        chat_id = None
        try:
            joined_chat = await client.join_chat(link)
            chat_id = joined_chat.id
            logger.info(f"[{client.name}] Joined chat: {joined_chat.title} ({chat_id})")
            await add_subscription(chat_id)
        except UserAlreadyParticipant:
            try:
                chat = await client.get_chat(link)
                chat_id = chat.id
            except Exception:
                 return None
        except FloodWait as e:
            logger.warning(f"[{client.name}] FloodWait joining {link}: {e.value}s")
            return None
        except Exception as e:
            logger.error(f"[{client.name}] Failed to join {link}: {e}")
            return None

        if not chat_id:
            return None

        await asyncio.sleep(2) 
        
        async for message in client.get_chat_history(chat_id, limit=5):
            if message.text or message.caption:
                content = message.text or message.caption
                if matches_keywords(content):
                    return message
        return None

    except Exception as e:
        logger.error(f"Error processing private invite {link}: {e}")
        return None

async def publish_post(target_message: Message, link: str, content_hash: str, is_private_source: bool):
    """
    Publishes the post using Master App.
    If source was public -> Forward.
    If source was private (fetched by worker) -> Copy.
    """
    try:
        # If we can forward (public channel and Master has access), we prefer forward.
        # If 'is_private_source' is True, it means a worker fetched it from a private channel 
        # where Master might not be a member.
        
        if not is_private_source:
            try:
                await master_app.forward_messages(
                    chat_id=TARGET_CHANNEL_ID,
                    from_chat_id=target_message.chat.id,
                    message_ids=target_message.id
                )
                logger.info(f"Forwarded post from {link}")
                await add_post(link, content_hash)
                return
            except Exception as e:
                logger.warning(f"Forward failed (maybe Master not in chat?), falling back to Copy: {e}")
        
        # Fallback: Copy (for private sources or failed forwards)
        # Note: If target_message comes from a Worker client, Master cannot forward/copy it directly 
        # using message_id because message_id is specific to that user's view? 
        # No, message_id in channel is global.
        # BUT Master must have access to the chat to Copy/Forward from it.
        
        # CRITICAL: If Worker joined a private channel, Master CANNOT copy/forward from it 
        # unless Master is also in it.
        # Since only Worker joined, Master cannot access `from_chat_id`.
        
        # Solution for Private Channels found by Workers:
        # The Worker must download media and send it? Or Worker must Copy it to Master?
        # Or we just accept that for private channels, we only support text/link forwarding if Master isn't in.
        
        # Workaround: Worker copies message to Target Channel?
        # Problem: Worker is not Admin of Target Channel.
        
        # User Requirement: "Only Main account posts".
        # This creates a deadlock for private channels where only Worker is member.
        
        # Option A: Worker copies message to Master (Saved Messages), Master copies to Channel.
        # Option B: We make all Workers admins (User rejected this impliedly).
        # Option C: We ignore private channel content copying and just send text/link.
        
        # Let's try Option A (Worker -> Master -> Channel).
        
        # 1. Worker copies to Master's username (or 'me' if it's same, but they are diff accounts).
        # We need Master's username or ID.
        master_me = await master_app.get_me()
        
        # Worker copies to Master
        # Note: target_message is bound to the client that fetched it.
        worker_client = target_message._client
        
        sent_to_master = None
        if target_message.media:
             # Copy
             sent_to_master = await worker_client.copy_message(
                 chat_id=master_me.username or master_me.id,
                 from_chat_id=target_message.chat.id,
                 message_id=target_message.id,
                 caption=target_message.caption
             )
        else:
             # Text
             sent_to_master = await worker_client.send_message(
                 chat_id=master_me.username or master_me.id,
                 text=target_message.text
             )
             
        # 2. Master copies from Saved Messages to Channel
        if sent_to_master:
            # We need to wait a bit or fetch it?
            # Master needs to receive it. 
            # But we can't easily get the message object for Master without listening.
            
            # Alternative: Worker sends FILE (download/upload).
            # This is heavy.
            
            # Let's assume for now that for Private channels we just send the Link and Text attribution
            # because full content proxying between userbots is complex without a shared storage.
            
            # Wait, if we used `copy_message` above, it sends it to Master.
            # Master can see it in his history with Worker?
            pass
            
        # For now, to keep it simple and robust:
        # If private source and Master not in it -> Send Text Summary + Link.
        # If User really wants content, we need all bots to be admins or Master to join everything.
        
        # Let's try to have Master join if it's a public link, 
        # but here we are in `is_private_source` block.
        
        logger.info(f"Posting content from private source {link} via Copy text")
        
        # Construct a rich text message
        text = target_message.text or target_message.caption or ""
        attribution = f"\n\n🔗 [Ссылка на пост]({link})"
        
        await master_app.send_message(
             chat_id=TARGET_CHANNEL_ID,
             text=text + attribution,
             disable_web_page_preview=False
        )
        await add_post(link, content_hash)

    except FloodWait as e:
        logger.warning(f"FloodWait publishing: {e.value}s")
        await asyncio.sleep(e.value + 2)
    except Exception as e:
        logger.error(f"Publish failed: {e}")


from pyrogram.handlers import MessageHandler

async def source_monitor(client, message: Message):
    """This handler is attached to Master only."""
    # DEBUG LOGGING
    chat_info = f"{message.chat.id}"
    if message.chat.username:
        chat_info += f" (@{message.chat.username})"
    if message.chat.title:
        chat_info += f" title='{message.chat.title}'"
        
    logger.info(f"DEBUG: Received message from {chat_info} | Text len: {len(message.text or message.caption or '')}")
    
    # Check if it matches source (try both ID and Username matching manually)
    is_source = False
    if str(message.chat.id) == str(SOURCE_CHAT):
        is_source = True
    elif message.chat.username and message.chat.username.lower() == str(SOURCE_CHAT).lower().replace("@", ""):
        is_source = True
        
    if not is_source:
        logger.info(f"IGNORING message from {chat_info} (Not {SOURCE_CHAT})")
        return

    logger.info(f"MATCH! Processing message from {SOURCE_CHAT}: {message.id}")
    
    text = message.text or message.caption or ""
    links = extract_links(text, message.entities)
    
    if not links:
        return

    for link in links:
        if await is_post_exists(original_link=link):
            logger.info(f"Link {link} already processed. Skipping.")
            continue
            
        # Rotate client
        worker = get_next_client()
        logger.info(f"Assigning {link} to {worker.name}")
        
        # Small delay for safety
        await asyncio.sleep(2)
        
        target_message = None
        is_private = False
        
        if "+" in link or "joinchat" in link:
            is_private = True
            target_message = await process_private_invite(worker, link)
        elif re.match(r'https?://t\.me/[\w\d_]+/\d+', link):
            target_message = await process_public_post(worker, link)
        else:
            logger.info(f"Unknown link format: {link}")
            continue
            
        if target_message:
            content = target_message.text or target_message.caption or ""
            if not content:
                continue
            content_hash = get_content_hash(content)
            
            if await is_post_exists(content_hash=content_hash):
                logger.info(f"Content duplicate {link}. Skipping.")
                await add_post(link, content_hash)
                continue

            # Publish using Master
            await publish_post(target_message, link, content_hash, is_private)

async def main():
    global master_app, clients
    
    # Load sessions
    session_files = glob.glob(os.path.join(DATA_DIR, "*.session"))
    if not session_files:
        logger.error("No session files found in data/! Run auth.py first.")
        return

    logger.info(f"Found {len(session_files)} sessions.")
    
    # Initialize clients
    for i, session_path in enumerate(session_files):
        # Determine name (filename without extension)
        name = os.path.basename(session_path).replace(".session", "")
        
        client = Client(
            os.path.join(DATA_DIR, name),
            api_id=API_ID,
            api_hash=API_HASH
        )
        # Manually set name attribute for logging purposes if needed, 
        # though Pyrogram sets it to session_name usually.
        client.name = name 
        clients.append(client)
        
        # Assume the session matching SESSION_NAME in env is master, or first one
        if name == SESSION_NAME or (not master_app and i == 0):
            master_app = client
            
    if not master_app:
        master_app = clients[0]
        
    # Register handler only on Master
    master_app.add_handler(MessageHandler(source_monitor, filters.incoming))

    # Start all clients nicely
    valid_clients = []
    for client in clients:
        try:
            await client.start()
            valid_clients.append(client)
            logger.info(f"Started client: {client.name}")
        except Exception as e:
            logger.error(f"Failed to start client {client.name}: {e}")
            # If master failed, we have a problem unless we can reassign master
            if client == master_app:
                logger.critical("Master client failed to start!")
    
    clients = valid_clients
    
    if not clients:
        logger.critical("No clients started successfully. Exiting.")
        return

    # Re-check master
    if not master_app.is_connected:
         # Try to find another master?
         # If master failed, we can't listen.
         # Unless we assign new master from valid_clients
         if valid_clients:
             master_app = valid_clients[0]
             logger.warning(f"Original master failed. New master is: {master_app.name}")
             # Re-register handler
             master_app.add_handler(source_monitor)
         else:
             return

    try:
        me = await master_app.get_me()
        logger.info(f"Master client is: {master_app.name} (ID: {me.id})")
    except Exception as e:
        logger.error(f"Failed to get master info: {e}")

    logger.info(f"Listening for messages from: {SOURCE_CHAT}")
    
    logger.info(f"Total {len(clients)} clients running. Listening...")
    
    # Start Janitor
    for c in clients:
        asyncio.create_task(janitor_task(c))
    
    from pyrogram import idle
    await idle()
    
    # Stop all
    await asyncio.gather(*[c.stop() for c in clients if c.is_connected])

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    loop.run_until_complete(main())
