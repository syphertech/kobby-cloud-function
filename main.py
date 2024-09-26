import functions_framework
import os
import requests
from flask import jsonify
from google.cloud import secretmanager
import requests
import jwt
from jwt.algorithms import RSAAlgorithm
import json


# URL to fetch Apple's public keys
APPLE_KEYS_URL = 'https://appleid.apple.com/auth/keys'

# Your app's bundle ID, this is the "aud" claim in the token
YOUR_APP_BUNDLE_ID = "com.mexamie.kobby"

# Apple's issuer
APPLE_ISSUER = "https://appleid.apple.com"

@functions_framework.http
def transcribe(request):
    """
    Cloud Function to transcribe an audio file using OpenAI API.
    Input (Multipart form-data):
        - 'file': The audio file uploaded by the user.
        - Authorization: Bearer <Firebase ID Token>
    
    Output:
        - JSON response containing the transcription or an error message.
    """
    try:
        # Step 1: Verify Firebase ID token
        id_token = request.headers.get('Authorization')

        if not id_token or not id_token.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401

        id_token = id_token.split(' ')[1]  # Remove 'Bearer' part
        decoded_token = verify_apple_token(id_token)
        

        if not decoded_token:
            return jsonify({'error': 'Invalid Apple ID Token'}), 401

        # Step 2: Check for uploaded file in request
        if 'file' not in request.files:
            return jsonify({'error': 'No file part in the request.'}), 400

        file = request.files['file']

        # Step 3: Ensure the file is uploaded
        if file.filename == '':
            return jsonify({'error': 'No file selected for uploading.'}), 400

        # Step 4: Save the file temporarily to the /tmp directory
        temp_file_path = f'/tmp/{file.filename}'
        file.save(temp_file_path)

        # Step 5: Clean audio and send to OpenAI for transcription
       # cleaned_audio_path = clean_audio(temp_file_path)
        transcription = send_to_openai(temp_file_path)

        # Step 6: Clean up temporary files
        os.remove(temp_file_path)
        # os.remove(cleaned_audio_path)

        prompt = generate_openai_prompt(transcription)
        results = call_openai_api(prompt)
        names = extract_name_from_response(results)


        return jsonify({'name': names}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def send_to_openai(file_path):
    """
    Send the audio file to OpenAI API for transcription.
    
    Args:
        file_path (str): Path to the local file.
    
    Returns:
        str: Transcription of the audio file.
    """

    api_key = get_secret()
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    # Read the file and send it to OpenAI API
    with open(file_path, 'rb') as audio_file:
        files = {
            'file': (audio_file.name, audio_file, 'multipart/form-data'),
            'model': (None, 'whisper-1')  # Specify the OpenAI model (e.g., whisper-1)
        }

        response = requests.post(url, headers=headers, files=files)

        if response.status_code != 200:
            raise Exception(f"OpenAI API error: {response.text}")

        return response.json().get('text', '')






# def verify_firebase_token(id_token):
#     """
#     Verify Firebase ID token using Firebase Admin SDK.
    
#     Args:
#         id_token (str): Firebase ID token sent from the client.
    
#     Returns:
#         dict: Decoded Firebase token if valid, None otherwise.
#     """
#     try:
#         decoded_token = auth.verify_id_token(id_token)
#         return decoded_token
#     except Exception as e:
#         print(f"Error verifying Firebase ID token: {e}")
#         return None
    

def get_secret():
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/104499888600/secrets/OPENAI_API_KEY/versions/latest"
    response = client.access_secret_version(name=name)
    return response.payload.data.decode("UTF-8")




def extract_other_persons_names(transcribed_text):
    """
    Combined Google Cloud Function to extract names from a conversation using the OpenAI API, excluding the current user's name.
    """



    # Step 1: Call OpenAI API with the generated prompt
    prompt = generate_openai_prompt(transcribed_text)

    try:
        openai_response = call_openai_api(prompt)
       
        return {
            "names": openai_response
        }
    except Exception as e:
        return jsonify({"error": f"Failed to connect to OpenAI API: {str(e)}"}), 500



def generate_openai_prompt(text):
    """
    Generate the prompt for the OpenAI API to extract names from the conversation.
    """
    prompt = f"""
   Extract the names of all individuals introduced in the following conversation and return them in an array. If no names are mentioned, return an array with 'Name not mentioned'.Conversation: "{text}"
    """
    return prompt

def call_openai_api(prompt):
    """
    Call the OpenAI API with the generated prompt and return the API response.
    """
    openai_url = "https://api.openai.com/v1/chat/completions"
    api_key = get_secret()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-4",  # You can use gpt-3.5-turbo or another suitable model
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0
    }

    response = requests.post(openai_url, headers=headers, json=data)
    response.raise_for_status()  # Raise an error for bad responses
    return response.json()


def extract_name_from_response(response):
    # Parse the input string as JSON

    
    # Extract the content from the response
    try:
        content = response['choices'][0]['message']['content']
        return json.loads(content) 
    except (KeyError, IndexError) as e:
        return f"Error extracting content: {e}"


def get_apple_public_key(kid):
    response = requests.get(APPLE_KEYS_URL)
    apple_keys = response.json().get('keys')
    
    # Find the key that matches the key ID (kid) from the token's header
    key = next((k for k in apple_keys if k['kid'] == kid), None)
    
    if not key:
        raise ValueError("Key not found")
    
    return RSAAlgorithm.from_jwk(json.dumps(key))



# Function to verify the ID token
def verify_apple_token(id_token):
    # Decode the token header to extract key ID (kid)
    unverified_header = jwt.get_unverified_header(id_token)
    kid = unverified_header['kid']
    
    # Get the public key corresponding to the kid
    public_key = get_apple_public_key(kid)
    
    try:
        # Verify the token using Apple's public key
        decoded_token = jwt.decode(
            id_token,
            public_key,
            algorithms=['RS256'],
            audience=YOUR_APP_BUNDLE_ID,
            issuer=APPLE_ISSUER
        )
        
        # If successful, the token is valid
        return decoded_token
    except jwt.ExpiredSignatureError:
        print("expired token ")
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as e:
        print("invalid token ")
        raise ValueError(jsonify(e))

