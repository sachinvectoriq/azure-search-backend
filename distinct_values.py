# distinct_values.py
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


async def get_distinct_values():
    query = """
        SELECT DISTINCT user_name 
        FROM azaisearch_logging 
        WHERE user_name NOT IN (
            '{"Sachin Bhusanurmath"}', 'HardCodedUser', '{"Jain, Anshuman"}', '{"Chanbasava Koti"}', 
            '{"Sachin Bhusanurmath"}', 'Test User', 'Sai Charan Kumbham', 
            'John Doe', 'Solomon Bhaskar', 'Harsh Aneppanavar', 'Sachin Ksr', 
            'Gaston Chan', 'John Doe1', 'Chanbasava Koti', 'Jain, Anshuman',
            'Sachin Bhusanurmath', 'Anonymous', 'Vinayak Inamadar', 'Raqib Rasheed'
        );
    """

    conn = await get_db_connection()
    rows = await conn.fetch(query)
    await conn.close()

    # Convert asyncpg record result to list of strings
    usernames = [row['user_name'] for row in rows]

    return jsonify({"distinct_user_name": usernames})