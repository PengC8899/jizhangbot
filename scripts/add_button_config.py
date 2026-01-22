import aiosqlite
import asyncio

async def add_column():
    db_path = "./huiying.db"
    async with aiosqlite.connect(db_path) as db:
        try:
            await db.execute("ALTER TABLE bots ADD COLUMN button_config TEXT DEFAULT '{}'")
            await db.commit()
            print("Added button_config column")
        except Exception as e:
            print(f"Error (maybe column exists): {e}")

if __name__ == "__main__":
    asyncio.run(add_column())
