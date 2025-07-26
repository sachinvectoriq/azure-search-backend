# user_login_log.py

import asyncpg
from quart import request, jsonify
import os
from datetime import datetime
from dotenv import load_dotenv  

load_dotenv()

DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG)

async def log_user():
    data = await request.get_json()
    if not data or 'user_name' not in data:
        return jsonify({'error': 'Missing "user_name" in request body'}), 400

    user_name = data['user_name']

    try:
        conn = await get_db_connection()

        insert_query = """
            INSERT INTO azaisearch_login_log (user_name)
            VALUES ($1)
            RETURNING login_session_id, user_name, date_and_time;
        """

        row = await conn.fetchrow(insert_query, user_name)

        await conn.close()

        return jsonify({
            'message': 'User logged successfully',
            'login_session_id': row['login_session_id'],
            'user_name': row['user_name'],
            'date_and_time': row['date_and_time'].strftime("%Y-%m-%d %H:%M:%S")
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
