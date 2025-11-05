import os
import asyncpg
from quart import jsonify

# Database configuration
DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG)


async def get_reports_access():
    query = "SELECT * FROM azaisearch_obe_reports_access ORDER BY id;"
    conn = await get_db_connection()
    rows = await conn.fetch(query)
    await conn.close()

    # Convert asyncpg records into a list of dicts
    data = [dict(row) for row in rows]

    return jsonify({"records": data})
