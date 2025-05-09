from flask import Flask, request, jsonify
import base64
import json
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

app = Flask(__name__)

# In-memory dictionary to hold the full conversation for each user
user_conversations = {}

def safe_base64_decode(data):
    try:
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        return base64.b64decode(data).decode("utf-8")
    except Exception:
        return f"[Invalid Base64] {data}"

def search_and_answer_query(user_query, user_id):
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    
    AZURE_SEARCH_SERVICE = "https://aiconciergeserach.search.windows.net"
    index_name = "index-obe"
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

    # The prompt template for generating the AI response
    GROUNDED_PROMPT = """
    You are an AI assistant that helps users learn from the information found in the source material.
    Answer the query using only the sources provided below.
    Use bullets if the answer has multiple points.
    If the answer is longer than 3 sentences, provide a summary.
    Answer ONLY with the facts listed in the list of sources below. Cite your source when you answer the question.
    If there isn't enough information below, say you don't know.
    Do not generate answers that don't use the sources below.

    Query: {query}
    Sources:
    {sources}
    Conversation History:
    {conversation_history}
    """

    # Prepending the conversation history to the query
    conversation_history = user_conversations.get(user_id, "")
    extended_query = conversation_history + "\nUser: " + user_query if conversation_history else user_query

    # Azure Search query
    vector_query = VectorizableTextQuery(text=extended_query, k_nearest_neighbors=50, fields="text_vector")
    search_results = search_client.search(
        search_text=extended_query,  # We now send the extended query for more context
        vector_queries=[vector_query],
        select=["title", "chunk", "parent_id"],
        top=5
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

    # Prepare the prompt for OpenAI with the conversation history included
    prompt = GROUNDED_PROMPT.format(
        query=user_query,
        sources=sources_formatted,
        conversation_history=conversation_history
    )

    # Call to OpenAI API to generate the response
    response = openai_client.chat.completions.create(
        messages=[{
            "role": "user",
            "content": prompt
        }],
        model=deployment_name
    )

    # Capture AI response and append it to the conversation history
    ai_response = response.choices[0].message.content
    updated_conversation = conversation_history + f"\nUser: {user_query}\nAI: {ai_response}"

    # Store the full conversation for this user
    user_conversations[user_id] = updated_conversation

    return {
        "query": user_query,
        "chunks": chunks_json,
        "ai_response": ai_response
    }

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    if not data or "query" not in data:
        return jsonify({"error": "Missing 'query' in request body"}), 400

    user_id = data.get("user_id", "default_user")  # Default user if no user_id is provided
    try:
        result = search_and_answer_query(data["query"], user_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
