import os
import asyncpg
from quart import request, jsonify

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


async def add_reports_access_user():
    try:
        data = await request.get_json()
        user_name = data.get("user_name")
        email = data.get("email")
        granted_by = data.get("granted_by")

        # Input validation
        if not user_name or not email or not granted_by:
            return jsonify({"error": "Missing required fields"}), 400

        query = """
            INSERT INTO azaisearch_obe_reports_access (name, email, granted_by)
            VALUES ($1, $2, $3)
            RETURNING id, name, email, permission_granted_at, granted_by;
        """

        conn = await get_db_connection()
        row = await conn.fetchrow(query, user_name, email, granted_by)
        await conn.close()

        # Convert record to dict
        return jsonify({"message": "User added successfully", "record": dict(row)}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
