# update_settings.py

import os
import asyncpg
from quart import request, jsonify
from dotenv import load_dotenv

# Load env variables
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
        print(f"Error connecting to the database: {e}")
        return None

async def update_settings():
    # Get admin_id from query parameters
    admin_id_str = request.args.get('admin_id')
    if not admin_id_str:
        return jsonify({'error': 'Missing admin_id in query parameters'}), 400
    
    try:
        admin_id = int(admin_id_str)
    except ValueError:
        return jsonify({'error': 'admin_id must be a valid integer'}), 400

    # Read form data
    form = await request.form
    update_fields = {}
    
    # Define field types for proper conversion
    field_types = {
        'azure_search_endpoint': str,
        'azure_search_index_name': str,
        'current_prompt': str,
        'openai_model_deployment_name': str,
        'openai_endpoint': str,
        'openai_api_version': str,
        'openai_model_temperature': float,  # This is likely the problem!
        'semantic_configuration_name': str
    }

    for field, field_type in field_types.items():
        if form.get(field) is not None:
            try:
                if field_type == float:
                    update_fields[field] = float(form.get(field))
                elif field_type == int:
                    update_fields[field] = int(form.get(field))
                else:
                    update_fields[field] = form.get(field)
            except ValueError:
                return jsonify({'error': f'Invalid {field_type.__name__} value for {field}'}), 400

    if not update_fields:
        return jsonify({'error': 'No valid fields provided to update'}), 400

    conn = await connect_db()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        # Build query dynamically
        set_clause = ', '.join(f"{key} = ${i+1}" for i, key in enumerate(update_fields.keys()))
        values = list(update_fields.values())
        values.append(admin_id)  # last param for WHERE

        query = f"""
            UPDATE azaisearch_ocm_settings
            SET {set_clause}
            WHERE admin_id = ${len(values)}
        """

        result = await conn.execute(query, *values)
        await conn.close()

        if result == "UPDATE 0":
            return jsonify({'message': f'No row found with admin_id={admin_id}'}), 404

        return jsonify({'message': f'Row with admin_id={admin_id} updated successfully'})

    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({'error': str(e)}), 500
