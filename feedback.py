# feedback.py

import asyncpg
from quart import request, jsonify
import os
from dotenv import load_dotenv  

load_dotenv()

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

async def submit_feedback():
    try:
        data = await request.get_json()

        chat_session_id = data.get("chat_session_id")
        user_name = data.get("user_name")
        query = data.get("query")
        ai_response = data.get("ai_response")
        citations = data.get("citations")
        feedback_type = data.get("feedback_type")
        feedback = data.get("feedback")
        login_session_id = data.get("login_session_id")
        user_id = data.get("user_id")

        conn = await get_db_connection()

        insert_query = """
            INSERT INTO azaisearch_feedback 
            (chat_session_id, user_name, date_and_time, query, ai_response, citations, feedback_type, feedback, login_session_id, user_id)
            VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7, $8, $9)
        """

        await conn.execute(insert_query,
            chat_session_id, user_name, query, ai_response,
            citations, feedback_type, feedback, login_session_id, user_id
        )

        await conn.close()

        return jsonify({"status": "success", "message": "Feedback submitted successfully"}), 201

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
