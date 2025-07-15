import os
from flask import Flask, request, jsonify
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Load environment variables from .env file (optional)
load_dotenv()

app = Flask(__name__)

# Database configuration
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def connect_db():
    """
    Establishes a connection to the database.
    """
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        return connection
    except psycopg2.Error as e:
        print(f"Error connecting to the database: {e}")
        return None





@app.route('/get_settings', methods=['GET'])
def get_settings():
    # Get admin_id from query parameters
    admin_id = request.args.get('admin_id')
    if not admin_id:
        return jsonify({'error': 'Missing admin_id in query parameters'}), 400

    # Connect to DB
    conn = connect_db()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        with conn.cursor() as cur:
            select_query = sql.SQL("""
                SELECT * FROM azaisearch_ocm_settings
                WHERE admin_id = %s
            """)
            cur.execute(select_query, (admin_id,))
            row = cur.fetchone()

            if row is None:
                return jsonify({'message': f'No row found with admin_id={admin_id}'}), 404

            # Get column names
            column_names = [desc[0] for desc in cur.description]
            result = dict(zip(column_names, row))

        return jsonify(result)

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        return jsonify({'error': str(e)}), 500

    finally:
        conn.close()
