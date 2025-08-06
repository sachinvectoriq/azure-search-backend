from flask import Flask, jsonify
from saml import saml_login, saml_callback, extract_token
import os


app = Flask(__name__)
app.config["SAML_PATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saml")
app.config["SECRET_KEY"] = os.getenv('JWT_SECRET_KEY')



@app.route('/')
def hello():
    return 'Hello!'







from search_query import ask
@app.route('/ask', methods=['POST'])
def call_ask():
    return ask()






if __name__ == "__main__":
    app.run(debug=True)
