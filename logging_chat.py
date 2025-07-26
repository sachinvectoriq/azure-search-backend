# logging_chat.py

import asyncpg
from quart import request, jsonify
import os
from dotenv import load_dotenv  

load_dotenv()

# Async DB config
DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG)

async def log_query():
    data = await request.get_json()

    required_fields = [
        "chat_session_id", "user_id", "user_name",
        "query", "ai_response", "citations", "login_session_id"
    ]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing one or more required fields."}), 400

    try:
        conn = await get_db_connection()

        insert_query = """
            INSERT INTO azaisearch_logging 
            (chat_session_id, user_id, user_name, query, ai_response, citations, login_session_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """

        await conn.execute(
            insert_query,
            data["chat_session_id"],
            data["user_id"],
            data["user_name"],
            data["query"],
            data["ai_response"],
            data["citations"],
            data["login_session_id"]
        )

        await conn.close()

        return jsonify({"message": "Log inserted successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
