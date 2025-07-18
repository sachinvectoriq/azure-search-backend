from flask import Flask, jsonify
from saml import saml_login, saml_callback, extract_token
import os


app = Flask(__name__)
app.config["SAML_PATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saml")
app.config["SECRET_KEY"] = os.getenv('JWT_SECRET_KEY')



@app.route('/')
def hello():
    return 'Hello!'




# SAML routes
@app.route('/saml/login')
def login():
    return saml_login(app.config["SAML_PATH"])

@app.route('/saml/callback', methods=['POST'])
def login_callback():
    return saml_callback(app.config["SAML_PATH"])

@app.route('/saml/token/extract', methods=['POST'])
def func_get_data_from_token():
    return extract_token()


from search_query import ask
@app.route('/ask', methods=['POST'])
def call_ask():
    return ask()

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



if __name__ == "__main__":
    app.run(debug=True)
