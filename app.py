from flask import Flask, request, jsonify
import base64
import json
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
import re

app = Flask(__name__)

# In-memory dictionary to hold the full conversation for each user
user_conversations = {}

import re

def is_contextual_query(openai_client, query, conversation_history, deployment_name):
    # Step 1: Quick check for context-dependent indicators
    contextual_keywords = r'\b(it|this|that|those|these|they|he|she|him|her|them|his|their|its|such)\b'
    if re.search(contextual_keywords, query, re.IGNORECASE):
        # Proceed to use LLM for confirmation
        classification_prompt = f"""
        Determine if the following query depends on previous conversation context or is self-sufficient.

        Conversation:
        {conversation_history}

        Query:
        {query}

        Respond with only one word: "Contextual" or "Independent"
        """
        classification_response = openai_client.chat.completions.create(
            messages=[{"role": "user", "content": classification_prompt}],
            model=deployment_name
        )
        result = classification_response.choices[0].message.content.strip()
        return result.lower() == "contextual"

    # If no contextual keywords, assume it's independent
    return False


# New function: Rephrase query if needed
def rephrase_query(openai_client, query, conversation_history, deployment_name):
    rephrase_prompt = f"""
Instruction:
To rewrite the user's latest query as a fully self-contained question, analyze the recent conversation. 

1. If the latest query contains a pronoun (e.g., it, this, that, those, these, they, he, she, him, her, them, his, their, its, such), examine the immediately **preceding user query** for context.
2. If that preceding query also contains a pronoun, continue going backward in the conversation history **until you find the most recent question without a pronoun**.
3. Use that question as context to resolve the pronoun and rewrite the latest query in a complete, standalone form.
4. If no previous context is needed (i.e., the latest query has no pronouns), simply return the query unchanged.

Conversation:
{conversation_history}

Original Query:
{query}

Rephrased Query:
"""

    rephrase_response = openai_client.chat.completions.create(
        messages=[{"role": "user", "content": rephrase_prompt}],
        model=deployment_name
    )
    return rephrase_response.choices[0].message.content.strip()

def generate_intent(openai_client, query, deployment_name):
    intent_prompt = [
        {"role": "system", "content": "You are an assistant that generates a concise intent phrase from user queries."},
        {"role": "user", "content": f"Generate a concise intent phrase summarizing this query:\n\n{query}"}
    ]
    intent_response = openai_client.chat.completions.create(
        messages=intent_prompt,
        model=deployment_name
    )
    intent = intent_response.choices[0].message.content.strip()
    return intent

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

    Dynamic_PROMPT = """
    You are an AI assistant that helps users learn from the information found in the source material.
    Answer the query using only the sources provided below.
    Use bullets if the answer has multiple points.
    If the answer is longer than 3 sentences, provide a summary.
    Answer ONLY with the facts listed in the list of sources below. Cite your source when you answer the question.
    If there isn't enough information below, say currently have insufficient information.
    Do not generate answers that don't use the sources below.

    Original Query: {query}
    Rephrased Query:{search_query}
    Sources:
    {sources}
    Conversation History:
    {conversation_history}
    """

    GROUNDED_PROMPT = Dynamic_PROMPT
    conversation_history = user_conversations.get(user_id, "")

    # Detect if the query is contextual
    if is_contextual_query(openai_client, user_query, conversation_history, deployment_name):
        search_query = rephrase_query(openai_client, user_query, conversation_history, deployment_name)
    else:
        search_query = user_query

    # Generate intent from the search_query
    intent = generate_intent(openai_client, search_query, deployment_name)
    print(f"[Intent Generated]: {intent}")

    # Create vector query using the intent
    vector_query = VectorizableTextQuery(text=intent, k_nearest_neighbors=5, fields="text_vector")
    search_results = search_client.search(
    search_text=search_query,
    vector_queries=[vector_query],
    select=["title", "chunk", "parent_id"],
    top=7,  # increase the number of results
    semantic_configuration_name="index-obe-semantic-configuration",
    query_type="semantic",          # enable semantic ranking          # enable extractive answers
)



    chunks_json = []
    sources_list = []

    for doc in search_results:
        title = doc.get("title", "N/A")
        chunk = doc.get("chunk", "N/A")
        parent_id_encoded = doc.get("parent_id", "Unknown Document")
        parent_id_decoded = safe_base64_decode(parent_id_encoded)
        
        cleaned_chunk = chunk.replace("\n", " ").replace("\t", " ").strip()
        chunks_json.append({
            "title": title,
            "chunk": cleaned_chunk,
            "parent_id": parent_id_decoded
        })

        sources_list.append(f"Document Title: {title}\nSource Link: {parent_id_decoded}\nContent:\n{chunk}\n")


    sources_formatted = "\n---\n".join(sources_list)


    prompt = GROUNDED_PROMPT.format(
        query=user_query,
        search_query=search_query,
        sources=sources_formatted,
        conversation_history=conversation_history
    )
    print(f"[Token count estimate]: {len(prompt.split())}")

    response = openai_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=deployment_name,
        temperature=0.8
    )

    ai_response = response.choices[0].message.content
    updated_conversation = conversation_history + f"\nUser: {user_query}\nAI: {ai_response}"
    user_conversations[user_id] = updated_conversation

    follow_up_prompt = f"""
    Based strictly on the following chunks of source material, generate 3 follow-up questions the user might ask.
    Only use the content in the sources. If info is missing, say "Not enough data".

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
