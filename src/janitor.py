import asyncio
import time
import logging
from pyrogram import Client
from src.config import LEAVE_DELAY
from src.database import get_active_subscriptions, mark_subscription_left

logger = logging.getLogger(__name__)

async def janitor_task(app: Client):
    """
    Background task to leave channels after LEAVE_DELAY.
    """
    logger.info("Janitor task started.")
    while True:
        try:
            # Calculate cutoff time
            cutoff_time = time.time() - LEAVE_DELAY
            
            # Get channels to leave
            channels_to_leave = await get_active_subscriptions(min_joined_time=cutoff_time)
            
            if channels_to_leave:
                logger.info(f"Janitor found {len(channels_to_leave)} channels to leave.")
                
            for chat_id in channels_to_leave:
                try:
                    await app.leave_chat(chat_id)
                    logger.info(f"Janitor left channel {chat_id}")
                    await mark_subscription_left(chat_id)
                    
                    # Sleep to avoid flood limits
                    await asyncio.sleep(5) 
                    
                except Exception as e:
                    logger.error(f"Janitor failed to leave {chat_id}: {e}")
                    # If we aren't in the chat anymore, mark as left anyway?
                    if "USER_NOT_PARTICIPANT" in str(e) or "Chat not found" in str(e):
                         await mark_subscription_left(chat_id)
            
            # Run check every minute
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.info("Janitor task cancelled.")
            break
        except Exception as e:
            logger.error(f"Janitor loop error: {e}")
            await asyncio.sleep(60)


