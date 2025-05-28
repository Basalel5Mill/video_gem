import os
import re
import sys
import requests
import json
import time
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from datetime import datetime

# --- Debug: Print Python and environment info ---
print("\n=== DEBUG: Environment Information ===")
print(f"Python: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
env_path = find_dotenv()
print(f"Loading .env file from: {os.path.abspath(env_path) if env_path else 'Not found'}")
load_dotenv(override=True)
print("="*50 + "\n")

# --- Configuration ---
print("--- Loading Configuration ---")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LOCAL_FILE_PATH = os.getenv("VIDEO_FILE_PATH")
VIDEO_MIME_TYPE = os.getenv("VIDEO_MIME_TYPE", "video/mp4")
# ---> THIS NOW USES YOUR .ENV PROMPT! <---
DEFAULT_PROMPT_TO_USE = os.getenv("PROMPT", "Write a YouTube script reviewing the content of this video.")
UPLOAD_ENDPOINT = "https://generativelanguage.googleapis.com/upload/v1beta/files"
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
PROCESS_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_TTS_ENDPOINT = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}" if ELEVENLABS_VOICE_ID else None
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
print(f"Gemini Key Loaded: {'Yes' if GEMINI_API_KEY else 'No'}")
print(f"Video Path: {LOCAL_FILE_PATH}")
print(f"---> Using Prompt from .env: {DEFAULT_PROMPT_TO_USE[:80]}...") # Verify it's using yours
print("="*50 + "\n")

# --- Headers ---
gemini_upload_headers = {"x-goog-api-key": GEMINI_API_KEY}
gemini_process_headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
elevenlabs_headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY}

# --- Gemini Functions ---
def upload_video(file_path, mime_type):
    """Uploads a video file to the Gemini Files API."""
    print(f"Attempting to upload file: {file_path}")
    if not os.path.exists(file_path): print(f"Error: File not found: {file_path}"); return None
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, mime_type)}
            response = requests.post(UPLOAD_ENDPOINT, headers=gemini_upload_headers, files=files)
            response.raise_for_status()
            upload_response = response.json()
            print(f"Upload successful: {upload_response}")
            return upload_response['file']['uri']
    except requests.exceptions.RequestException as e:
        print(f"--- ERROR DURING FILE UPLOAD: {e} ---")
        if hasattr(e, 'response') and e.response is not None: print(f"Response: {e.response.text}")
        return None

def get_video_review_script(video_uri, prompt=DEFAULT_PROMPT_TO_USE):
    """Sends a request to Gemini API, expecting a TEXT review script."""
    print(f"Requesting TEXT review with prompt: '{prompt[:60]}...'")
    enhanced_prompt = f"{prompt}\n\nImportant: Please provide ONLY the script's spoken dialogue. Do not include any introductory phrases like 'Sure, here is...' or markdown like '(Music)' or speaker labels."

    payload = {
        "contents": [{"parts": [{"text": enhanced_prompt}, {"file_data": {"mime_type": VIDEO_MIME_TYPE, "file_uri": video_uri}}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8192}, # Creative temp
        "safetySettings": [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}]
    }
    try:
        response = requests.post(PROCESS_ENDPOINT, headers=gemini_process_headers, json=payload)
        response.raise_for_status()
        result = response.json()
        if 'candidates' in result and result['candidates']:
            text_content = result['candidates'][0]['content']['parts'][0]['text']
            print("--- Gemini Response (Raw) ---"); print(text_content[:500] + "..."); print("-----------------------------")
            return text_content
        return "ERROR: No valid candidates found."
    except requests.exceptions.RequestException as e:
        print(f"--- ERROR DURING VIDEO PROCESSING: {e} ---")
        if hasattr(e, 'response') and e.response is not None: print(f"Response: {e.response.text}")
        return f"Error: {e}"

# --- IMPROVED Cleaning Function ---
def clean_plain_script(script_text):
    """Removes common markdown, cues, and intros from a plain text script."""
    print("Cleaning script for TTS...")
    text = str(script_text)

    # 1. Remove "Sure, here is..." type intros (more aggressively)
    text = re.sub(r"^(Sure|Here's|Okay|Alright|Certainly)[\s\S]*?\n\s*\n", "", text, flags=re.IGNORECASE).strip()

    # 2. Remove speaker labels (like **Host:**)
    text = re.sub(r'\*\*(.*?)\*\*:', '', text)

    # 3. Remove cues (like **(Music)**)
    text = re.sub(r'\*\*\((.*?)\)\*\*', '', text)

    # 4. Remove tags
    text = re.sub(r'"', '', text)

    # 5. Replace newlines and multiple spaces with a single space
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    # ---> THIS IS WHERE THE BAD LINE WAS. IT IS NOW GONE. <---

    return text.strip()

# --- ElevenLabs Function ---
def generate_audio_elevenlabs(text_script, output_path):
    if not ELEVENLABS_TTS_ENDPOINT: print("Error: ELEVENLABS_VOICE_ID not set."); return False
    print(f"Generating audio using ElevenLabs (Voice ID: {ELEVENLABS_VOICE_ID})...");
    if not text_script or text_script.strip() == "": print("Error: Input script empty/invalid."); return False
    payload = {"text": text_script, "model_id": ELEVENLABS_MODEL, "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    try:
        response = requests.post(ELEVENLABS_TTS_ENDPOINT, headers=elevenlabs_headers, data=json.dumps(payload))
        response.raise_for_status()
        if response.content:
            with open(output_path, 'wb') as f: f.write(response.content)
            print(f"Audio saved: '{output_path}'"); return True
        else: print("Error: Empty response from ElevenLabs."); return False
    except requests.exceptions.RequestException as e:
        print(f"Error during ElevenLabs call: {e}");
        try: print(f"Response: {e.response.json()}")
        except: print(f"Response: {e.response.text}")
        return False

# --- Utility Functions ---
def create_safe_filename(name):
    safe_name = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
    return re.sub(r'_+', '_', safe_name)

def create_output_dirs(video_path):
    """Create output directories for the video WITH TIMESTAMPS."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    safe_name = create_safe_filename(video_name)
    timestamped_dir_name = f"{safe_name}_{timestamp}"
    output_dir = os.path.join(OUTPUT_DIR, timestamped_dir_name)
    os.makedirs(output_dir, exist_ok=True)
    progress_file = os.path.join(output_dir, f"progress_{timestamp}.log")
    with open(progress_file, 'w', encoding='utf-8') as f:
        f.write(f"Processing started: {datetime.now().isoformat()}\n")
    return {
        'base_dir': output_dir,
        'audio': os.path.join(output_dir, f"{safe_name}_{timestamp}.mp3"),
        'script_raw': os.path.join(output_dir, f"{safe_name}_{timestamp}_raw.txt"),
        'script_clean': os.path.join(output_dir, f"{safe_name}_{timestamp}_clean.txt"),
        'progress': progress_file
    }

def save_output(data, output_path, progress_file=None):
    try:
        with open(output_path, 'w', encoding='utf-8') as f: f.write(data)
        log_message = f"Output saved: {output_path}"
        print(log_message)
        if progress_file:
            with open(progress_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().isoformat()}] {log_message}\n")
        return True
    except Exception as e: print(f"Error saving output: {e}"); return False

# --- Workflow Function ---
def run_video_to_audio_workflow():
    """Runs video -> TEXT script -> Clean -> audio workflow."""
    print("--- Starting Video-to-Audio (Review Script) Workflow ---")
    if not GEMINI_API_KEY: print("Error: GEMINI_API_KEY not set."); return 1
    if not LOCAL_FILE_PATH or not os.path.exists(LOCAL_FILE_PATH): print(f"Error: Video file not found: {LOCAL_FILE_PATH}."); return 1

    output_paths = create_output_dirs(LOCAL_FILE_PATH)
    progress_file = output_paths['progress']

    def log_progress(message):
        log_msg = f"[{datetime.now().isoformat()}] {message}"
        print(log_msg)
        with open(progress_file, 'a', encoding='utf-8') as f: f.write(f"{log_msg}\n")

    log_progress(f"Output dir: {output_paths['base_dir']}")
    video_file_uri = upload_video(LOCAL_FILE_PATH, VIDEO_MIME_TYPE)

    if video_file_uri:
        log_progress(f"Video uploaded. URI: {video_file_uri}. Waiting..."); time.sleep(10)
        
        script_text = get_video_review_script(video_file_uri) # Uses .env prompt!
        
        if not script_text or "ERROR" in script_text:
            log_progress(f"ERROR: Failed to get script: {script_text}"); return 1

        save_output(script_text, output_paths['script_raw'], progress_file=progress_file)
        
        clean_text = clean_plain_script(script_text)
        log_progress(f"Cleaned Text (Preview): {clean_text[:200]}...")
        save_output(clean_text, output_paths['script_clean'], progress_file=progress_file)

        if ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID:
            log_progress("Generating audio...")
            generate_audio_elevenlabs(clean_text, output_paths['audio'])
        else:
            log_progress("Skipping audio generation (ElevenLabs keys/ID missing).")
            
        log_progress(f"Workflow completed. Outputs in: {output_paths['base_dir']}"); return 0
    else:
        log_progress("Error uploading video."); return 1

# --- Main Execution Block ---
if __name__ == "__main__":
    start_time = time.time()
    exit_code = 1
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY not set in .env file.")
    else:
        try:
            exit_code = run_video_to_audio_workflow()
        except Exception as e:
            print(f"\nAn unexpected error occurred: {str(e)}"); import traceback; traceback.print_exc(); exit_code = 1
    elapsed_time = time.time() - start_time
    print(f"\nProcess completed in {elapsed_time:.2f} seconds with exit code {exit_code}")
    exit(exit_code)