import aiosqlite
from bot.config import DB_PATH

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def fetchone(query, params=()):
    db = await get_db()
    async with db.execute(query, params) as cur:
        row = await cur.fetchone()
    await db.close()
    return row

async def fetchall(query, params=()):
    db = await get_db()
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    await db.close()
    return rows

async def execute(query, params=()):
    db = await get_db()
    await db.execute(query, params)
    await db.commit()
    await db.close()