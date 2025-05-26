from flask import Flask, request, jsonify
import base64
import json
import re
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

app = Flask(__name__)
user_conversations = {}

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

def search_and_answer_query(user_query, user_id):
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")

    AZURE_SEARCH_SERVICE = "https://aiconciergeserach.search.windows.net"
    index_name = "index-obe-final"
    deployment_name = "ocm-gpt-4o"

    openai_client = AzureOpenAI(
        api_version="2025-01-01-preview",
        azure_endpoint="https://ai-hubdevaiocm273154123411.cognitiveservices.azure.com/",
        azure_ad_token_provider=token_provider
    )

    search_client = SearchClient(
        endpoint=AZURE_SEARCH_SERVICE,
        index_name=index_name,
        credential=credential
    )

    if user_id not in user_conversations:
        user_conversations[user_id] = {"history": [], "chat": ""}

    user_conversations[user_id]["history"].append(user_query)
    if len(user_conversations[user_id]["history"]) > 3:
        user_conversations[user_id]["history"] = user_conversations[user_id]["history"][-3:]

    search_query = " ".join(user_conversations[user_id]["history"])
    conversation_history = user_conversations[user_id]["chat"]

    # Perform vector search
    vector_query = VectorizableTextQuery(text=search_query, k_nearest_neighbors=5, fields="text_vector")
    search_results = search_client.search(
        search_text=search_query,
        vector_queries=[vector_query],
        select=["title", "chunk", "parent_id"],
        top=7,
        semantic_configuration_name="index-obe-final-semantic-configuration",
        query_type="semantic"
    )

    chunks_json = []
    sources_list = []

    for i, doc in enumerate(search_results, start=1):
        title = doc.get("title", "N/A")
        chunk = doc.get("chunk", "N/A")
        parent_id_encoded = doc.get("parent_id", "Unknown Document")
        parent_id_decoded = safe_base64_decode(parent_id_encoded)
        cleaned_chunk = chunk.replace("\n", " ").replace("\t", " ").strip()
        chunks_json.append({
            "id": i,
            "title": title,
            "chunk": cleaned_chunk,
            "parent_id": parent_id_decoded
        })

        # Make source formatting clear for AI and user
        sources_list.append(f"[{i}] {chunk.strip()} (Source: {parent_id_decoded})")

    sources_formatted = "\n\n".join(sources_list)

    prompt_template = """
You are an AI assistant. Answer the user query using only the sources listed below.

Guidelines:
- Extract only factual information from the chunks.
- Each fact must be followed immediately by the citation in square brackets, e.g., [1]. Only use a number if it corresponds exactly to the chunk containing that fact.
- Do not guess or cite a number that doesn't directly support the fact.
- Do not add information not present in the sources.
- Summarize briefly if needed, followed by details.
- Only cite sources that directly contributed to the answer.

Conversation History:
{conversation_history}

Sources:
{sources}

User Question: {query}

Respond with:
- An answer citing sources inline like [1], [2].
    """

    prompt = prompt_template.format(
        conversation_history=conversation_history,
        sources=sources_formatted,
        query=user_query
    )

    response = openai_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=deployment_name,
        temperature=0.7
    )

    full_reply = response.choices[0].message.content.strip()

    # Extract used citation IDs by finding all [number] patterns in AI's response
    used_ids = list(set(map(int, re.findall(r"\[(\d+)\]", full_reply))))
    # Remove citations from answer text if you want clean answer without trailing citation list
    ai_response = full_reply

    citations = [chunk for chunk in chunks_json if chunk["id"] in used_ids]

    # Append this Q&A to conversation chat history for context in next queries
    user_conversations[user_id]["chat"] += f"\nUser: {user_query}\nAI: {ai_response}"

    # Generate follow-up questions strictly based on source chunks
    follow_up_prompt = f"""
Based strictly on the following chunks of source material, generate 3 follow-up questions the user might ask.
Only use the content in the sources. Do not invent new facts, but generate 3 questions based on any content available.
If the source is completely empty or irrelevant, respond "Not enough data" for all questions.

Format:
Q1: <question>
Q2: <question>
Q3: <question>

SOURCES:
{sources_formatted}
    """

    follow_up_response = openai_client.chat.completions.create(
        messages=[{"role": "user", "content": follow_up_prompt}],
        model=deployment_name
    )
    follow_ups_raw = follow_up_response.choices[0].message.content.strip()

    return {
        "query": search_query,
        "ai_response": ai_response,
        "citations": citations,
        "follow_ups": follow_ups_raw
    }

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    if not data or "query" not in data:
        return jsonify({"error": "Missing 'query' in request body"}), 400

    user_id = data.get("user_id", "default_user")
    try:
        result = search_and_answer_query(data["query"], user_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
