import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

async def main():
    uri = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME")

    print("URI:", uri)
    print("DB:", db_name)

    client = AsyncIOMotorClient(uri)
    db = client[db_name]

    collections = await db.list_collection_names()
    print("✅ Connected. Collections:", collections)

    client.close()

asyncio.run(main())
