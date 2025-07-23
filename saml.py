import os
import json
import datetime
import jwt  # Import PyJWT for JWT operations
from quart import session, redirect, request, jsonify, run_sync # Changed from flask to quart, added run_sync
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError  # Import JWT exceptions

# SAML and JWT configuration
admin_group_id = os.getenv('ADMIN_GROUP_ID')
redirect_url = os.getenv('REDIRECT_URL')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')

# SAML functions
def init_saml_auth(req, saml_path):
    """
    Initializes the OneLogin SAML2 authentication object.
    This function itself doesn't directly use Quart's request context,
    but it's called within functions that do.
    """
    print('In init auth')
    auth = OneLogin_Saml2_Auth(req, custom_base_path=saml_path)
    return auth

async def prepare_quart_request(request):
    """
    Prepares the request dictionary for OneLogin_Saml2_Auth.
    This function is now async because request.args and request.form are awaitable.
    """
    print('In Prepare Quart Request')
    url_data = request.url.split('?')
    return {
        'https': 'on', # Assuming HTTPS in production
        'http_host': request.host,
        'script_name': request.path,
        # Safely get port, default to 443 for HTTPS if not specified
        'server_port': request.host.split(':')[1] if ':' in request.host else '443',
        'get_data': (await request.args).copy(), # Await request.args
        'post_data': (await request.form).copy(), # Await request.form
    }

async def saml_login(saml_path):
    """
    Handles the SAML login initiation, redirecting to the IdP.
    Now an async function.
    """
    try:
        print('In SAML Login')
        # Await the prepare_quart_request function
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

async def saml_callback(saml_path):
    """
    Handles the SAML callback from the IdP, processes the response,
    and creates a JWT token for the user.
    Now an async function.
    """
    print('In SAML Callback')
    # Await the prepare_quart_request function
    req = await prepare_quart_request(request)
    auth = init_saml_auth(req, saml_path)

    # Wrap the synchronous process_response call with run_sync to prevent blocking
    # and ensure it runs correctly within Quart's async context.
    await run_sync(auth.process_response)

    errors = auth.get_errors()
    group_name = 'user'

    if not errors:
        # Accessing session in Quart is an awaitable operation
        user_data_from_saml = auth.get_attributes()
        name_id_from_saml = auth.get_nameid()

        # Update session, remember session is an awaitable proxy in Quart
        await session.set('samlUserdata', user_data_from_saml)
        await session.set('samlNameId', name_id_from_saml)

        json_data = await session.get('samlUserdata') # Await session.get
        groups = json_data.get("http://schemas.microsoft.com/ws/2008/06/identity/claims/groups", [])

        # Check if the user belongs to the admin group
        if admin_group_id and admin_group_id in groups: # Added check for admin_group_id existence
            group_name = 'admin'

        user_data = {
            'name': json_data.get('http://schemas.microsoft.com/identity/claims/displayname'),
            'group': group_name
        }

        # Writing to file is a synchronous I/O operation.
        # It should be run in a separate thread to avoid blocking the event loop.
        # Quart provides run_sync for this.
        # Note: Writing to local file system in Azure App Service is temporary storage.
        # For persistent logs, use Azure Blob Storage or Application Insights.
        await run_sync(lambda:
            (lambda f: f.write(json.dumps(json_data, indent=4)))(
                open("session_data_from_backend.txt", "w")
            )
        )

        token = create_jwt_token(user_data)
        # Redirect to the React dashboard with the user data
        return redirect(f'{redirect_url}?token={token}')
    else:
        return f"Error in SAML Authentication: {errors}-{req}", 500

# JWT functions (these are CPU-bound, so they can remain synchronous unless they call async functions)
def create_jwt_token(user_data):
    """
    Creates a JWT token. This is a synchronous, CPU-bound operation.
    """
    expiration = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    payload = {
        'user_data': user_data,
        'exp': expiration
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')
    return token

def get_data_from_token(token):
    """
    Decodes and validates a JWT token. This is a synchronous, CPU-bound operation.
    """
    try:
        decoded_data = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        user_data = decoded_data.get('user_data')
        return user_data
    except ExpiredSignatureError:
        return 'Error: Token has expired'
    except InvalidTokenError:
        return 'Error: Invalid token'

async def extract_token():
    """
    Extracts and decodes the token from request arguments.
    Now an async function.
    """
    # request.args is an awaitable proxy in Quart
    token = (await request.args).get('token')
    if not token:
        return jsonify({"error": "Token is missing"}), 400

    # get_data_from_token is synchronous, so we can call it directly
    # if it's short-running and CPU-bound. If it were long-running or I/O-bound,
    # we'd wrap it with await run_sync(get_data_from_token, token)
    user_data = get_data_from_token(token)

    if isinstance(user_data, str) and user_data.startswith("Error"):
        return jsonify({"error": user_data}), 400

    return jsonify({"user_data": user_data}), 200
