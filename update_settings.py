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




@app.route('/update_settings', methods=['POST'])
def update_settings():
    # Get admin_id from query parameters
    admin_id = request.args.get('admin_id')
    if not admin_id:
        return jsonify({'error': 'Missing admin_id in query parameters'}), 400

    # Get form data for columns to update
    update_fields = {}
    allowed_fields = [
    'current_index_name',
    'current_prompt',
    'azure_search_endpoint',
    'azure_search_api_key',
    'azure_search_index_filter',
    'openai_model',
    'openai_model_temperature',
    'openai_max_tokens',
    'openai_top_p'
    ]


    for field in allowed_fields:
        value = request.form.get(field)
        if value is not None:
            update_fields[field] = value

    if not update_fields:
        return jsonify({'error': 'No valid fields provided to update'}), 400

    # Connect to DB
    conn = connect_db()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        with conn.cursor() as cur:
            # Build SET clause dynamically
            set_clauses = []
            values = []
            for column, value in update_fields.items():
                set_clauses.append(sql.SQL("{} = %s").format(sql.Identifier(column)))
                values.append(value)

            # Add admin_id for WHERE clause
            values.append(admin_id)

            update_query = sql.SQL("""
                UPDATE azaisearch_ocm_settings
                SET {set_clause}
                WHERE admin_id = %s
            """).format(
                set_clause=sql.SQL(', ').join(set_clauses)
            )

            cur.execute(update_query, values)
            conn.commit()

            if cur.rowcount == 0:
                return jsonify({'message': f'No row found with admin_id={admin_id}'}), 404

        return jsonify({'message': f'Row with admin_id={admin_id} updated successfully'})

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        conn.rollback()
        return jsonify({'error': str(e)}), 500

    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)
