from flask import Flask, request, jsonify
import base64
import json
import re
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

app = Flask(__name__)

# In-memory dictionary to hold conversation context per user
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

    # Initialize user context
    if user_id not in user_conversations:
        user_conversations[user_id] = {"history": [], "chat": ""}

    # Maintain last 3 queries for search
    user_conversations[user_id]["history"].append(user_query)
    if len(user_conversations[user_id]["history"]) > 3:
        user_conversations[user_id]["history"] = user_conversations[user_id]["history"][-3:]

    # Use last 3 queries combined for search query
    search_query = " ".join(user_conversations[user_id]["history"])

    # Full conversation history for prompt context
    conversation_history = user_conversations[user_id]["chat"]

    Dynamic_PROMPT = """
You are an AI assistant helping users by answering their questions based only on the content in the sources below.

Instructions:
- Extract only factual and relevant information from the provided sources.
- Cite each fact clearly using the document title (e.g., [Document Title]).
- After each answer or section, include the exact piece(s) of raw source text used to derive the answer.
- Always wrap raw text excerpts in a clearly marked section titled "Referenced Source Excerpts".
- Use bullet points for lists or multiple facts.
- If the answer is long, start with a short summary followed by details.

Citation Format:
- Use square brackets to cite sources: [Document Title].
- If the source has a link, include it like this: [Document Title](https://example.com).
- Do NOT use numeric citations like [1], [2] unless documents are explicitly numbered.

Constraints:
- Do NOT use prior knowledge or assumptions unrelated to the sources.
- Do NOT fabricate or guess any information.
- Do NOT cite sources that were not used.
- Do NOT modify raw source text excerpts; quote them exactly as they appear.

Format Example:

Answer:
- Fact or insight A [Document Title]
- Fact or insight B [Document Title]

Referenced Source Excerpts:
- "Quoted raw text related to A" – [Document Title]
- "Quoted raw text related to B" – [Document Title]

Conversation History:
{conversation_history}
---
Sources:
{sources}
---
User Question: {query}


    """
    GROUNDED_PROMPT = Dynamic_PROMPT

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

    for doc in search_results:
        title = doc.get("title", "N/A")
        chunk = doc.get("chunk", "N/A")
        parent_id_encoded = doc.get("parent_id", "Unknown Document")
        parent_id_decoded = safe_base64_decode(parent_id_encoded)

        chunks_json.append({
            "title": title,
            "chunk": chunk,
            "parent_id": parent_id_decoded
        })

        sources_list.append(f'DOCUMENT: {parent_id_decoded}, TITLE: {title}, CONTENT: {chunk}')

    sources_formatted = "\n=================\n".join(sources_list)

    # Format final prompt
    prompt = GROUNDED_PROMPT.format(
        query=user_query,
        search_query=search_query,
        sources=sources_formatted,
        conversation_history=conversation_history
    )

    # Get answer from Azure OpenAI
    response = openai_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=deployment_name,
        temperature=0.8
    )

    ai_response = response.choices[0].message.content
    user_conversations[user_id]["chat"] += f"\nUser: {user_query}\nAI: {ai_response}"

    # Generate follow-up questions
    follow_up_prompt = f"""
Based strictly on the following chunks of source material, generate 3 follow-up questions the user might ask.
Only use the content in the sources. Do not invent new facts, but you must generate 3 questions based on any content available. If the source is completely empty or irrelevant, then and only then say "Not enough data" for all questions.

Format the response as:
Q1: <question>
Q2: ...

SOURCES:
{sources_formatted}
    """

    follow_up_response = openai_client.chat.completions.create(
        messages=[{"role": "user", "content": follow_up_prompt}],
        model=deployment_name
    )

    follow_ups_raw = follow_up_response.choices[0].message.content

    return {
        "query": search_query,
        "chunks": chunks_json,
        "ai_response": ai_response,
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
