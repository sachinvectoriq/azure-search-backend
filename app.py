# app.py
from quart import Quart, request, jsonify
from saml import saml_login, saml_callback, extract_token
import os

# Import the refactored function
from search_query import ask_query  # Renamed to avoid conflict with route name

# --- In-memory store for conversation history (TEMPORARY - NOT for production) ---
# This will not persist across restarts or multiple Flask processes/instances.
user_conversations = {}  # Define the single source of truth here

# Initialize Quart app
app = Quart(__name__)
app.config["SAML_PATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saml")
app.config["SECRET_KEY"] = os.getenv('JWT_SECRET_KEY')  # Replace with hardcoded key or securely read it, as you prefer.

# ---- Basic route ----
@app.route('/')
async def hello():
    return 'Hello!'

# ---- SAML routes ----
@app.route('/saml/login')
def login():
    return saml_login(app.config["SAML_PATH"])

@app.route('/saml/callback', methods=['POST'])
def login_callback():
    return saml_callback(app.config["SAML_PATH"])

@app.route('/saml/token/extract', methods=['POST'])
def func_get_data_from_token():
    return extract_token()

# ---- Async ask route ----
@app.route('/ask', methods=['POST'])
async def call_ask():
    try:
        data = await request.get_json()
        user_id = data.get("user_id", "default_user")
        user_query = data.get("query")
        if not user_query:
            return jsonify({"error": "Missing 'query' in request body"}), 400

        # Call the refactored function, passing the shared conversation store
        result = await ask_query(user_query, user_id, user_conversations)
        return jsonify(result)
    except Exception as e:
        print(f"Error processing request for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500

# ---- All other sync routes ----
from user_login_log import log_user
@app.route('/log/user', methods=['POST'])
def call_log_user():
    return log_user()

from feedback import submit_feedback
@app.route('/feedback', methods=['POST'])
def call_submit_feedback():
    return submit_feedback()

from logging_chat import log_query
@app.route('/log', methods=['POST'])
def call_log_query():
    return log_query()

from get_settings import get_settings
@app.route('/get_settings', methods=['GET'])
def call_get_settings():
    return get_settings()

from update_settings import update_settings
@app.route('/update_settings', methods=['POST'])
def call_update_settings():
    return update_settings()

# ---- Optional sync test route ----
@app.route("/ping", methods=["GET"])
def ping():
    return "pong"

# ---- Main Entry Point ----
if __name__ == "__main__":
    # For local development, use uvicorn directly
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)  # Removed workers=1 for local dev simplicity
