import os
import json
import datetime
import jwt  # PyJWT
import asyncio
from quart import redirect, request, jsonify
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

# Configuration
admin_group_id = os.getenv('ADMIN_GROUP_ID')
redirect_url = os.getenv('REDIRECT_URL')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')

# Initialize SAML Auth
def init_saml_auth(req, saml_path):
    print('In init auth')
    return OneLogin_Saml2_Auth(req, custom_base_path=saml_path)

# Prepare request for OneLogin SAML
async def prepare_quart_request(request):
    print('In Prepare Quart Request')
    return {
        'https': 'on',
        'http_host': request.host,
        'script_name': request.path,
        'server_port': request.host.split(':')[1] if ':' in request.host else '443',
        'get_data': request.args.copy(),                    # sync
        'post_data': (await request.form).copy()            # async
    }

# JWT creation
def create_jwt_token(user_data):
    expiration = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    payload = {
        'user_data': user_data,
        'exp': expiration
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')
    return token

# JWT decoding
def get_data_from_token(token):
    try:
        decoded_data = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        return decoded_data.get('user_data')
    except ExpiredSignatureError:
        return 'Error: Token has expired'
    except InvalidTokenError:
        return 'Error: Invalid token'

# SAML login route
async def saml_login(saml_path):
    try:
        print('In SAML Login')
        req = await prepare_quart_request(request)
        print(f'Request Prepared: {req}')
        auth = init_saml_auth(req, saml_path)
        print('SAML Auth Initialized')
        login_url = auth.login()
        print(f'Redirecting to: {login_url}')
        return redirect(login_url)
    except Exception as e:
        print(f'Error during SAML login: {str(e)}')
        return f'Internal Server Error: {str(e)}', 500

# SAML callback route
async def saml_callback(saml_path):
    print('In SAML Callback')
    req = await prepare_quart_request(request)
    auth = init_saml_auth(req, saml_path)

    await asyncio.to_thread(auth.process_response)
    errors = auth.get_errors()
    group_name = 'user'

    if not errors:
        user_data_from_saml = auth.get_attributes()
        name_id_from_saml = auth.get_nameid()

        from quart import session
        session['samlUserdata'] = user_data_from_saml
        session['samlNameId'] = name_id_from_saml

        json_data = session.get('samlUserdata', {})
        groups = json_data.get("http://schemas.microsoft.com/ws/2008/06/identity/claims/groups", [])

        if admin_group_id and admin_group_id in groups:
            group_name = 'admin'

        user_data = {
            'name': json_data.get('http://schemas.microsoft.com/identity/claims/displayname'),
            'group': group_name,
            'job_title': json_data.get('http://schemas.xmlsoap.org/ws/2005/05/identity/claims/jobtitle')
        }

        await asyncio.to_thread(
            lambda: (lambda f: f.write(json.dumps(json_data, indent=4)))(open("session_data_from_backend.txt", "w"))
        )

        token = create_jwt_token(user_data)
        return redirect(f'{redirect_url}?token={token}')
    else:
        return f"Error in SAML Authentication: {errors}-{req}", 500

# Token extractor
async def extract_token():
    token = request.args.get('token')
    if not token:
        return jsonify({"error": "Token is missing"}), 400

    user_data = get_data_from_token(token)

    if isinstance(user_data, str) and user_data.startswith("Error"):
        return jsonify({"error": user_data}), 400

    return jsonify({"user_data": user_data}), 200
