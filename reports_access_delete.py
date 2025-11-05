import os
import asyncpg
from quart import jsonify, request

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


async def delete_reports_access():
    try:
        data = await request.get_json()
        record_id = data.get("id")
        email = data.get("email")

        if not record_id and not email:
            return jsonify({"error": "Provide either 'id' or 'email' to delete."}), 400

        conn = await get_db_connection()

        # Build query dynamically
        if record_id:
            query = "DELETE FROM azaisearch_obe_reports_access WHERE id = $1 RETURNING *;"
            params = (record_id,)
        else:
            query = "DELETE FROM azaisearch_obe_reports_access WHERE email = $1 RETURNING *;"
            params = (email,)

        deleted_row = await conn.fetchrow(query, *params)
        await conn.close()

        if deleted_row:
            return jsonify({
                "message": "Record deleted successfully",
                "deleted_record": dict(deleted_row)
            }), 200
        else:
            return jsonify({"message": "No matching record found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500
