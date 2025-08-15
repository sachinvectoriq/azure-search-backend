
import base64
import json
import re
import os
import textwrap
from dotenv import load_dotenv
from quart import request, jsonify
import asyncpg

from azure.search.documents.aio import SearchClient as AsyncSearchClient
from azure.search.documents.models import VectorizableTextQuery
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from openai import AsyncAzureOpenAI

from load_settings_and_clients_from_db import load_settings_and_get_clients


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
    


def safe_base64_decode(data):
    if data.startswith("https"):
        return data
    try:
        valid_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
        data = data.rstrip()
        while data and data[-1] not in valid_chars:
            data = data[:-1]
        while len(data) % 4 == 1:
            data = data[:-1]
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        decoded = base64.b64decode(data).decode("utf-8", errors="ignore")
        decoded = decoded.strip().rstrip("\uFFFD").rstrip("?").strip()
        decoded = re.sub(r'\.(docx|pdf|pptx|xlsx)[0-9]+$', r'.\1', decoded, flags=re.IGNORECASE)
        return decoded
    except Exception as e:
        return f"[Invalid Base64] {data} - {str(e)}"

async def ask_query(user_query, user_id, conversation_store):
    # ✅ Load fresh settings and clients for each request
    try:
        config = await load_settings_and_get_clients()
    except Exception as e:
        print(f"❌ Failed to load settings: {e}")
        raise RuntimeError("Failed to initialize AI services")

    # Extract settings and clients from config
    current_prompt = config['current_prompt']
    openai_client = config['openai_client']
    search_client = config['search_client']
    deployment_name = config['deployment_name']
    openai_model_temperature = config['openai_model_temperature']
    semantic_configuration_name = config['semantic_configuration_name']

    
    user_data = conversation_store.get(user_id)
    if user_data:
        conversation_history = user_data.get("chat", "")
        history_list = user_data.get("history", [])
    else:
        conversation_history = ""
        history_list = []

    history_list.append(user_query)
    if len(history_list) > 3:
        history_list = history_list[-3:]

    history_queries = " ".join(history_list)

    async def fetch_chunks(query_text, k_value, start_index):
        vector_query = VectorizableTextQuery(text=query_text, k_nearest_neighbors=5, fields="text_vector")
        search_results = await search_client.search(
            search_text=query_text,
            vector_queries=[vector_query],
            select=["title", "chunk", "parent_id"],
            top=k_value,
            semantic_configuration_name=semantic_configuration_name,
            query_type="semantic"
        )
        chunks = []
        sources = []
        i = 0
        async for doc in search_results:
            title = doc.get("title", "N/A")
            chunk_content = doc.get("chunk", "N/A").replace("\n", " ").replace("\t", " ").strip()
            parent_id_encoded = doc.get("parent_id", "Unknown Document")
            parent_id_decoded = safe_base64_decode(parent_id_encoded)
            chunk_id = start_index + i
            chunk_obj = {
                "id": chunk_id,
                "title": title,
                "chunk": chunk_content,
                "parent_id": parent_id_decoded
            }
            chunks.append(chunk_obj)
            sources.append(
                f"Source ID: [{chunk_id}]\nContent: {chunk_content}\nDocument: {parent_id_decoded}"
            )
            i += 1
        return chunks, sources

    # Fetch chunks from both history and standalone query
    history_chunks, history_sources = await fetch_chunks(history_queries, 5, 1)
    standalone_chunks, standalone_sources = await fetch_chunks(user_query, 5, 6)

    # ✅ DEDUPLICATION STEP ADDED HERE
    combined_chunks = history_chunks + standalone_chunks
    seen_chunks = set()
    all_chunks = []
    for chunk in combined_chunks:
        identifier = chunk["chunk"]
        if identifier not in seen_chunks:
            seen_chunks.add(identifier)
            all_chunks.append(chunk)

    # Build sources from deduplicated chunks
    all_sources = []
    for chunk in all_chunks:
        all_sources.append(
            f"Source ID: [{chunk['id']}]\nContent: {chunk['chunk']}\nDocument: {chunk['parent_id']}"
        )
    sources_formatted = "\n\n---\n\n".join(all_sources)

    # ✅ Print all fetched chunks (citations) before sending to AI
    print("\n--- ALL CHUNKS RETURNED BY AZURE SEARCH ---")
    for chunk in all_chunks:
        print(f"[{chunk['id']}] Title: {chunk['title']}")
        print(f"Parent ID: {chunk['parent_id']}")
        print(f"Content: {chunk['chunk'][:300]}...")  # Truncate preview
        print("--------------------------------------------------")

    prompt_template = f"""{current_prompt}"""

    prompt = prompt_template.format(
        conversation_history=conversation_history,
        sources=sources_formatted,
        query=user_query
    )

    response = await openai_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=deployment_name,
        temperature=openai_model_temperature
    )

    full_reply = response.choices[0].message.content.strip()

    flat_ids = []
    for match in re.findall(r"\[(.*?)\]", full_reply):
        parts = match.split(",")
        for p in parts:
            if p.strip().isdigit():
                flat_ids.append(int(p.strip()))

    unique_original_ids = []
    for i in flat_ids:
        if i not in unique_original_ids:
            unique_original_ids.append(i)

    id_mapping = {old_id: new_id + 1 for new_id, old_id in enumerate(unique_original_ids)}

    def replace_citation_ids(text, mapping):
        def repl(match):
            nums = match.group(1).split(",")
            new_nums = sorted(set(mapping.get(int(n.strip()), int(n.strip())) for n in nums if n.strip().isdigit()))
            return f"[{', '.join(map(str, new_nums))}]"
        return re.sub(r"\[(.*?)\]", repl, text)

    ai_response = replace_citation_ids(full_reply, id_mapping)

    citations = []
    seen = set()
    for old_id in unique_original_ids:
        new_id = id_mapping[old_id]
        for chunk in all_chunks:
            if chunk["id"] == old_id and old_id not in seen:
                seen.add(old_id)
                updated_chunk = chunk.copy()
                updated_chunk["id"] = new_id
                citations.append(updated_chunk)

    conversation_store[user_id] = {
        "chat": conversation_history + f"\nUser: {user_query}\nAI: {ai_response}",
        "history": history_list
    }

    follow_up_prompt = f"""
Based only on the following chunks of source material, generate 3 follow-up questions the user might ask.
Only use the content in the sources. Do not invent new facts.

Format:
Q1: <question>
Q2: <question>
Q3: <question>

SOURCES:
{json.dumps(all_chunks, indent=2)}
    """

    follow_up_response = await openai_client.chat.completions.create(
        messages=[{"role": "user", "content": follow_up_prompt}],
        model=deployment_name
    )

    follow_ups_raw = follow_up_response.choices[0].message.content.strip()

    return {
        "query": user_query,
        "ai_response": ai_response,
        "citations": citations,
        "follow_ups": follow_ups_raw,
        "fetched_chunks": all_chunks  # ✅ Deduplicated chunks
    }
