from mcp.server.fastmcp import FastMCP
import os
import torch
import scipy.io.wavfile as wavfile
import time
import numpy as np
import random
import sys
import tempfile
import subprocess

# Set environment variables for cache
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Use HF_HUB_CACHE to redirect model downloads while preserving HF_HOME for auth token
os.environ["HF_HUB_CACHE"] = os.path.join(BASE_DIR, "hf_cache")
os.environ["LHOTSE_TOOLS_DIR"] = os.path.join(BASE_DIR, "lhotse_tools")
os.makedirs(os.environ["HF_HUB_CACHE"], exist_ok=True)
os.makedirs(os.environ["LHOTSE_TOOLS_DIR"], exist_ok=True)

# Initialize FastMCP
mcp = FastMCP("Local TTS")

# Global model cache
MODELS = {
    "pocket": None
}

VOICES = ['alba', 'marius', 'javert', 'jean', 'fantine', 'cosette', 'eponine', 'azelma']

def get_pocket():
    if MODELS["pocket"] is None:
        from pocket_tts import TTSModel
        print("Loading Pocket TTS...", file=sys.stderr)
        MODELS["pocket"] = TTSModel.load_model()
    return MODELS["pocket"]

@mcp.tool()
def speak(text: str, voice_path: str = None) -> str:
    """
    Generate speech from text. Uses a random voice by default, or clones a voice if provided.
    
    Args:
        text: Text to speak.
        voice_path: Optional path to a WAV file for voice cloning.
    """
    start_time = time.time()
    
    # Always use pocket
    model = get_pocket()
    
    if voice_path:
        try:
            if not os.path.exists(voice_path):
                return f"Error: Voice file not found at {voice_path}"
            
            print(f"Cloning voice from: {voice_path}", file=sys.stderr)
            voice_state = model.get_state_for_audio_prompt(voice_path)
            voice = os.path.basename(voice_path)
        except Exception as e:
            return f"Error loading custom voice: {str(e)}"
    elif os.environ.get("LOCAL_TTS_VOICE_PATH"):
        voice_path = os.environ.get("LOCAL_TTS_VOICE_PATH")
        try:
            if not os.path.exists(voice_path):
                # If configured default is missing, log it but fall back to random? 
                # Or return error? User said "we will always generate a cloned voice... based on the audio file designated"
                # So error is probably better to alert misconfiguration.
                return f"Error: Configured default voice file not found at {voice_path}"
            
            print(f"Cloning voice from configured default: {voice_path}", file=sys.stderr)
            voice_state = model.get_state_for_audio_prompt(voice_path)
            voice = os.path.basename(voice_path) + " (default)"
        except Exception as e:
             return f"Error loading configured default voice: {str(e)}"
    else:
        voice = random.choice(VOICES)
        
        try:
            voice_state = model.get_state_for_audio_prompt(voice)
        except Exception:
             # Fallback to catalog check just in case
             voice_state = model.get_state_for_audio_prompt("alba")
         
    audio = model.generate_audio(voice_state, text)
    
    # Create a temporary file to save the audio
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
        temp_wav_path = temp_wav.name
        wavfile.write(temp_wav_path, model.sample_rate, audio.numpy())
    
    try:
        # Play the audio using afplay (macOS)
        if sys.platform == "darwin":
            subprocess.run(["afplay", temp_wav_path], check=True)
        else:
            # Fallback for Linux (aplay) - assuming 'aplay' exists, otherwise this might fail or we could try to detect
            # For this specific project (macOS focused), afplay is sufficient.
            subprocess.run(["aplay", temp_wav_path], check=False)
            
    except Exception as e:
        print(f"Error playing audio: {e}", file=sys.stderr)
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)
        
    duration = time.time() - start_time
    return f"Spoken: '{text}' (voice: {voice}) in {duration:.2f}s"

if __name__ == "__main__":
    print("Starting Local TTS MCP Server...", file=sys.stderr)
    mcp.run()

def main():
    """Entry point for the console script."""
    print("Starting Local TTS MCP Server...", file=sys.stderr)
    mcp.run()
