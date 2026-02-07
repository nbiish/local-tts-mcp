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
os.environ["HF_HOME"] = os.path.join(BASE_DIR, "hf_cache")
os.environ["LHOTSE_TOOLS_DIR"] = os.path.join(BASE_DIR, "lhotse_tools")
os.makedirs(os.environ["HF_HOME"], exist_ok=True)
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
def speak(text: str) -> str:
    """
    Generate speech from text using a random voice and play it immediately.
    
    Args:
        text: Text to speak.
    """
    start_time = time.time()
    
    # Always use pocket
    model = get_pocket()
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
