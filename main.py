
import functions_framework
import os
import requests
import noisereduce as nr
import numpy as np
from pydub import AudioSegment
from flask import request, jsonify
from scipy.io import wavfile
import firebase_admin
from firebase_admin import credentials, auth
from google.cloud import secretmanager







@functions_framework.http
def transcribe_audio(request):
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
        decoded_token = verify_firebase_token(id_token)



        if not decoded_token:
            return jsonify({'error': 'Invalid Firebase ID Token'}), 401

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
        cleaned_audio_path = clean_audio(temp_file_path)
        transcription = send_to_openai(cleaned_audio_path)

        # Step 6: Clean up temporary files
        os.remove(temp_file_path)
        os.remove(cleaned_audio_path)


        return jsonify({'transcription': transcription}), 200

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



def clean_audio(file_path):
    """
    Convert the audio to WAV (if needed) and apply noise reduction.

    Args:
        file_path (str): Path to the local audio file.
    
    Returns:
        str: Path to the cleaned WAV file.
    """
    # Load the audio file using pydub
    audio = AudioSegment.from_file(file_path)

    # Convert to WAV format (required for noise reduction)
    wav_path = f'/tmp/cleaned_audio.wav'
    audio.export(wav_path, format='wav')

    # Apply noise reduction using noisereduce
    rate, data = wavfile.read(wav_path)

    # Noise reduction: reduce background noise in the audio signal
    reduced_noise = nr.reduce_noise(y=data, sr=rate)

    # Save the cleaned audio file
    cleaned_wav_path = f'/tmp/cleaned_audio_processed.wav'
    wavfile.write(cleaned_wav_path, rate, reduced_noise.astype(np.int16))

    return cleaned_wav_path


def verify_firebase_token(id_token):
    """
    Verify Firebase ID token using Firebase Admin SDK.
    
    Args:
        id_token (str): Firebase ID token sent from the client.
    
    Returns:
        dict: Decoded Firebase token if valid, None otherwise.
    """
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        print(f"Error verifying Firebase ID token: {e}")
        return None
    

def get_secret():
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/104499888600/secrets/OPENAI_API_KEY/versions/latest"
    response = client.access_secret_version(name=name)
    return response.payload.data.decode("UTF-8")






def extract_other_persons_names(transcribed_text,request):
    """
    Combined Google Cloud Function to extract names from a conversation using the OpenAI API, excluding the current user's name.
    """

    # Parse the request body
    request_json = request.get_json()

   

    # Step 1: Call OpenAI API with the generated prompt
    prompt = generate_openai_prompt(transcribed_text, request)

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
   Extract the names of all individuals introduced in the following conversation and return them in an array. If no names are mentioned, return an array with 'Name not mentioned'.Text: "{text}"
    """
    return prompt

def call_openai_api(prompt,api_key):
    """
    Call the OpenAI API with the generated prompt and return the API response.
    """
    openai_url = "https://api.openai.com/v1/chat/completions"
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




