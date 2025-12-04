import aiosqlite
import time
import logging
from typing import Optional, List

DB_PATH = "data/bot_db.sqlite"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_link TEXT UNIQUE,
                content_hash TEXT,
                created_at REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                channel_id INTEGER PRIMARY KEY,
                joined_at REAL,
                status TEXT
            )
        """)
        await db.commit()

async def add_post(original_link: str, content_hash: str):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO posts (original_link, content_hash, created_at) VALUES (?, ?, ?)",
                (original_link, content_hash, time.time())
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def is_post_exists(original_link: str = None, content_hash: str = None) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        if original_link:
            async with db.execute("SELECT 1 FROM posts WHERE original_link = ?", (original_link,)) as cursor:
                if await cursor.fetchone():
                    return True
        
        if content_hash:
            async with db.execute("SELECT 1 FROM posts WHERE content_hash = ?", (content_hash,)) as cursor:
                if await cursor.fetchone():
                    return True
        
        return False

async def add_subscription(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO subscriptions (channel_id, joined_at, status) VALUES (?, ?, ?)",
            (channel_id, time.time(), 'active')
        )
        await db.commit()

async def get_active_subscriptions(min_joined_time: float = 0) -> List[int]:
    """
    Returns list of channel_ids that are 'active' and joined before min_joined_time.
    If min_joined_time is 0, returns all active subscriptions.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        query = "SELECT channel_id FROM subscriptions WHERE status = 'active'"
        params = []
        
        if min_joined_time > 0:
            query += " AND joined_at < ?"
            params.append(min_joined_time)
            
        async with db.execute(query, tuple(params)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def mark_subscription_left(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET status = 'left' WHERE channel_id = ?",
            (channel_id,)
        )
        await db.commit()


