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
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("local-tts")

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
        logger.info("Loading Pocket TTS...")
        MODELS["pocket"] = TTSModel.load_model()
    return MODELS["pocket"]

def split_text(text: str, max_length: int = 200) -> list[str]:
    """
    Split text into chunks ensuring no chunk exceeds max_length.
    Handles long sentences by splitting on commas or spaces, and forces split if words are too long.
    """
    if not text:
        return []

    # Normalize whitespace: replace newlines/tabs with spaces and collapse multiple spaces
    text = " ".join(text.split())
    
    chunks = []
    current_chunk = ""
    
    # Split by common sentence terminators while keeping them
    # This regex looks for punctuation followed by space
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    for sentence in sentences:
        if not sentence.strip():
            continue
            
        # Check if adding this sentence exceeds max_length
        if len(current_chunk) + len(sentence) + 1 <= max_length:
            current_chunk += sentence + " "
        else:
            # If current chunk has content, push it
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # If the sentence itself is too long, we need to break it down further
            if len(sentence) > max_length:
                words = sentence.split(' ')
                temp_chunk = ""
                for word in words:
                    # Check if word itself is too long
                    if len(word) > max_length:
                        # Split very long word into pieces
                        for i in range(0, len(word), max_length):
                            sub_word = word[i:i+max_length]
                            if len(temp_chunk) + len(sub_word) + 1 <= max_length:
                                temp_chunk += sub_word + " "
                            else:
                                if temp_chunk:
                                    chunks.append(temp_chunk.strip())
                                temp_chunk = sub_word + " "
                    else:
                        if len(temp_chunk) + len(word) + 1 <= max_length:
                            temp_chunk += word + " "
                        else:
                            if temp_chunk:
                                chunks.append(temp_chunk.strip())
                            temp_chunk = word + " "
                current_chunk = temp_chunk # Start next chunk with remainder
            else:
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
        if not os.path.exists(voice_path):
             logger.error(f"Voice file not found: {voice_path}")
             return voice_path

        # Check duration
        sr, data = wavfile.read(voice_path)
        duration = len(data) / sr
        
        # If longer than 10 seconds, trim it
        if duration > 10.0:
            logger.info(f"Voice file {os.path.basename(voice_path)} is {duration:.1f}s long. Trimming to 10s.")
            # Create temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                temp_wav_path = temp_wav.name
                
            # Trim data (handling potential multi-channel)
            max_samples = int(10.0 * sr)
            trimmed_data = data[:max_samples]
            wavfile.write(temp_wav_path, sr, trimmed_data)
            return temp_wav_path
            
    except Exception as e:
        logger.warning(f"Failed to process voice file {voice_path}: {e}")
        
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
    
    if not text or not text.strip():
        return "Error: Text input is empty."

    # Always use pocket
    try:
        model = get_pocket()
    except Exception as e:
        return f"Error loading TTS model: {e}"
    
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
            # Fallback if env var points to invalid file
            voice_name = "random" 

    voice_state = None
    if voice_file_to_use:
        try:
            # Prepare file (trim if needed)
            processed_voice_path = prepare_voice_file(voice_file_to_use)
            
            logger.info(f"Cloning voice from: {voice_name}")
            voice_state = model.get_state_for_audio_prompt(processed_voice_path)
            
            # Clean up temp file if we created one
            if processed_voice_path != voice_file_to_use and os.path.exists(processed_voice_path):
                os.remove(processed_voice_path)
                
        except Exception as e:
            logger.error(f"Error loading custom voice: {str(e)}")
            return f"Error loading custom voice: {str(e)}"
    else:
        if not voice_name:
            voice_name = random.choice(VOICES)
        try:
            # If voice_name is not in VOICES (e.g. from failed env var), fallback to alba
            if voice_name not in VOICES and "default" not in voice_name:
                 voice_name = "alba"
            
            clean_name = voice_name.split(" (")[0]
            if clean_name in VOICES:
                 voice_state = model.get_state_for_audio_prompt(clean_name)
            else:
                 voice_state = model.get_state_for_audio_prompt("alba")
                 voice_name = "alba (fallback)"
        except Exception as e:
             logger.error(f"Error setting voice state: {e}")
             voice_state = model.get_state_for_audio_prompt("alba")
    
    # Process text in chunks to avoid tensor size mismatch errors with long text
    chunks = split_text(text)
    audio_segments = []
    errors = []
    
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        try:
            # Generate audio for each chunk
            segment = model.generate_audio(voice_state, chunk)
            
            # Validation: Ensure segment is a valid tensor
            if not isinstance(segment, torch.Tensor):
                 logger.warning(f"Chunk {i} generated non-tensor output: {type(segment)}")
                 continue
                 
            if segment.dim() == 0 or segment.numel() == 0:
                 logger.warning(f"Chunk {i} generated empty tensor.")
                 continue
                 
            # Ensure 2D [1, T] or 1D [T] -> 2D [1, T]
            if segment.dim() == 1:
                segment = segment.unsqueeze(0)
                
            audio_segments.append(segment)
        except Exception as e:
            msg = f"Error generating audio for chunk '{chunk[:20]}...': {e}"
            logger.error(msg)
            errors.append(msg)
            continue
            
    if not audio_segments:
        if errors:
            return f"Error: Failed to generate audio. Details: {'; '.join(errors[:3])}"
        return "Error: No audio generated (empty text or filtering)."
        
    # Concatenate all audio segments
    try:
        if len(audio_segments) > 1:
            audio = torch.cat(audio_segments, dim=1)
        else:
            audio = audio_segments[0]
            
        # Final shape check
        if audio.dim() != 2 or audio.size(0) != 1:
             logger.warning(f"Unexpected audio shape: {audio.shape}, attempting to fix.")
             if audio.dim() == 1:
                 audio = audio.unsqueeze(0)
             # If it's something else, wavfile.write might fail or work depending on numpy conversion
             
        # Create a temporary file to save the audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = temp_wav.name
            wavfile.write(temp_wav_path, model.sample_rate, audio.squeeze().numpy())
        
        # Play the audio using afplay (macOS)
        if sys.platform == "darwin":
            subprocess.run(["afplay", temp_wav_path], check=True)
        else:
            subprocess.run(["aplay", temp_wav_path], check=False)
            
    except Exception as e:
        logger.error(f"Error playing/saving audio: {e}")
        return f"Error playing audio: {e}"
        
    finally:
        # Clean up the temporary file
        if 'temp_wav_path' in locals() and os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)
        
    duration = time.time() - start_time
    status_msg = f"Spoken: '{text[:50]}...' (voice: {voice_name}) in {duration:.2f}s"
    if errors:
        status_msg += f" (Note: {len(errors)} chunks failed to generate)"
    return status_msg

def main():
    """Entry point for the console script."""
    print("Starting Local TTS MCP Server...", file=sys.stderr)
    mcp.run()

if __name__ == "__main__":
    main()
