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

import re

def split_text(text: str, max_length: int = 200) -> list[str]:
    """Split text into chunks ensuring no chunk exceeds max_length."""
    chunks = []
    current_chunk = ""
    
    # Split by common sentence terminators while keeping them
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) < max_length:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
            
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

def prepare_voice_file(voice_path: str) -> str:
    """
    Prepare voice file for cloning. Trims if too long to prevent context window issues.
    Returns path to use (either original or temp trimmed).
    """
    try:
        # Check duration
        sr, data = wavfile.read(voice_path)
        duration = len(data) / sr
        
        # If longer than 10 seconds, trim it
        if duration > 10.0:
            print(f"Voice file {os.path.basename(voice_path)} is {duration:.1f}s long. Trimming to 10s.", file=sys.stderr)
            # Create temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                temp_wav_path = temp_wav.name
                
            # Trim data (handling potential multi-channel)
            max_samples = int(10.0 * sr)
            trimmed_data = data[:max_samples]
            wavfile.write(temp_wav_path, sr, trimmed_data)
            return temp_wav_path
            
    except Exception as e:
        print(f"Warning: Failed to process voice file {voice_path}: {e}", file=sys.stderr)
        
    return voice_path

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
    
    voice_file_to_use = None
    voice_name = None
    
    # Determine which voice path to use
    if voice_path:
        if os.path.exists(voice_path):
            voice_file_to_use = voice_path
            voice_name = os.path.basename(voice_path)
        else:
            return f"Error: Voice file not found at {voice_path}"
    elif os.environ.get("LOCAL_TTS_VOICE_PATH"):
        env_path = os.environ.get("LOCAL_TTS_VOICE_PATH")
        if os.path.exists(env_path):
            voice_file_to_use = env_path
            voice_name = os.path.basename(env_path) + " (default)"
        else:
            return f"Error: Configured default voice file not found at {env_path}"

    if voice_file_to_use:
        try:
            # Prepare file (trim if needed)
            processed_voice_path = prepare_voice_file(voice_file_to_use)
            
            print(f"Cloning voice from: {voice_name}", file=sys.stderr)
            voice_state = model.get_state_for_audio_prompt(processed_voice_path)
            
            # Clean up temp file if we created one
            if processed_voice_path != voice_file_to_use and os.path.exists(processed_voice_path):
                os.remove(processed_voice_path)
                
        except Exception as e:
            return f"Error loading custom voice: {str(e)}"
    else:
        voice_name = random.choice(VOICES)
        try:
            voice_state = model.get_state_for_audio_prompt(voice_name)
        except Exception:
             voice_state = model.get_state_for_audio_prompt("alba")
    
    # Process text in chunks to avoid tensor size mismatch errors with long text
    chunks = split_text(text)
    audio_segments = []
    
    for chunk in chunks:
        if not chunk.strip():
            continue
        try:
            # Generate audio for each chunk
            segment = model.generate_audio(voice_state, chunk)
            audio_segments.append(segment)
        except Exception as e:
            print(f"Error generating audio for chunk '{chunk[:20]}...': {e}", file=sys.stderr)
            continue
            
    if not audio_segments:
        return "Error: No audio generated."
        
    # Concatenate all audio segments
    if len(audio_segments) > 1:
        audio = torch.cat(audio_segments, dim=1)
    else:
        audio = audio_segments[0]
         
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
    return f"Spoken: '{text}' (voice: {voice_name}) in {duration:.2f}s"

if __name__ == "__main__":
    print("Starting Local TTS MCP Server...", file=sys.stderr)
    mcp.run()

def main():
    """Entry point for the console script."""
    print("Starting Local TTS MCP Server...", file=sys.stderr)
    mcp.run()
