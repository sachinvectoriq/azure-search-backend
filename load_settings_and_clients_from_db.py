# db_settings.py
import os
import asyncpg
from dotenv import load_dotenv
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from azure.search.documents.aio import SearchClient as AsyncSearchClient
from openai import AsyncAzureOpenAI

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

# ========================
# DB Connection
# ========================
async def connect_db():
    try:
        return await asyncpg.connect(**DB_CONFIG)
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None

# ========================
# Load Settings from DB & Return Clients
# ========================
async def load_settings_and_get_clients():
    """
    Load settings from database and return configured clients.
    Returns a dictionary with all settings and initialized clients.
    """
    conn = await connect_db()
    if not conn:
        raise RuntimeError("❌ Could not connect to the database.")

    try:
        query = """
            SELECT * 
            FROM azaisearch_ocm_settings2
            WHERE update_id = (SELECT MAX(update_id) FROM azaisearch_ocm_settings2)
        """
        row = await conn.fetchrow(query)

        if not row:
            raise RuntimeError("⚠ No settings found in the database.")

        # Extract settings with decimal conversion
        settings = {
            'openai_api_key': row["openai_api_key"],
            'azure_search_endpoint': row["azure_search_endpoint"],
            'azure_search_index_name': row["azure_search_index_name"],
            'current_prompt': row["current_prompt"],
            'openai_api_version': row["openai_api_version"],
            'openai_endpoint': row["openai_endpoint"],
            'openai_model_deployment_name': row["openai_model_deployment_name"],
            'openai_model_temperature': float(row["openai_model_temperature"]),
            'semantic_configuration_name': row["semantic_configuration_name"]
        }

        print("✅ Settings loaded from DB:")
        print(f"openai_api_key: {settings['openai_api_key'][:6]}...")
        print(f"azure_search_endpoint: {settings['azure_search_endpoint']}")
        print(f"azure_search_index_name: {settings['azure_search_index_name']}")
        print(f"openai_model_temperature: {settings['openai_model_temperature']}")

    finally:
        await conn.close()

    # Initialize clients
    credential = AsyncDefaultAzureCredential()
    
    openai_client = AsyncAzureOpenAI(
        api_version=settings['openai_api_version'],
        azure_endpoint=settings['openai_endpoint'],
        api_key=settings['openai_api_key']
    )
    
    search_client = AsyncSearchClient(
        endpoint=settings['azure_search_endpoint'],
        index_name=settings['azure_search_index_name'],
        credential=credential
    )

    # Add clients to settings dictionary
    settings['openai_client'] = openai_client
    settings['search_client'] = search_client
    settings['deployment_name'] = settings['openai_model_deployment_name']

    print("✅ OpenAI client initialized:", openai_client is not None)
    print("✅ Azure Search client initialized:", search_client is not None)

    return settings


