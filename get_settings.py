# get_settings.py

import os
import asyncpg
from quart import request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Async DB config
DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

async def connect_db():
    try:
        return await asyncpg.connect(**DB_CONFIG)
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

async def get_settings():
    # admin_id = request.args.get('admin_id')
    admin_id = int(request.args.get('admin_id'))
    if not admin_id:
        return jsonify({'error': 'Missing admin_id in query parameters'}), 400

    conn = await connect_db()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        query = """
            SELECT * FROM azaisearch_ocm_settings
            WHERE admin_id = $1
        """
        row = await conn.fetchrow(query, admin_id)

        if row is None:
            return jsonify({'message': f'No row found with admin_id={admin_id}'}), 404

        result = dict(row)
        return jsonify(result)

    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({'error': str(e)}), 500

    finally:
        await conn.close()
