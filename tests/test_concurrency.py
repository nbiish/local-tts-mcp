import sys
import os
import time
import threading
from unittest.mock import MagicMock
import logging

# Add src to path
sys.path.append(os.path.abspath("src"))

# Mock dependencies to avoid loading heavy models or actual audio
sys.modules["scipy.io.wavfile"] = MagicMock()

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("local-tts")

# Mock Model
class MockModel:
    def __init__(self):
        self.sample_rate = 24000
        
    def generate_audio(self, voice_state, text):
        # Simulate generation time
        logging.info(f"[MockModel] Generating audio for: '{text}' (taking 0.5s)")
        time.sleep(0.5)
        import torch
        return torch.zeros(1, 24000)

    def get_state_for_audio_prompt(self, path):
        return None

# Mock server imports
import local_tts.server

# Inject mocks
local_tts.server.get_pocket = MagicMock(return_value=MockModel())
local_tts.server.wavfile.write = MagicMock()

# Mock subprocess.run to simulate playback duration
original_run = local_tts.server.subprocess.run
def mock_run(args, check=False):
    if args[0] in ["afplay", "aplay"]:
        # Extract speed if present (just for verification)
        speed = "1.0"
        if "-r" in args:
            speed = args[args.index("-r") + 1]
            
        logging.info(f"[MockPlayer] START playback for command: {' '.join(args)} (Speed: {speed}x)")
        time.sleep(1.0) # Simulate 1s audio
        logging.info(f"[MockPlayer] END playback")
    else:
        return original_run(args, check=check)

local_tts.server.subprocess.run = mock_run

def test_concurrency():
    print("--- Starting Concurrency Test ---")
    
    messages = ["Message One", "Message Two", "Message Three"]
    
    # Fire off 3 requests rapidly
    for msg in messages:
        logging.info(f"Calling speak('{msg}')...")
        result = local_tts.server.speak(msg)
        logging.info(f"Returned: {result}")
        time.sleep(0.1) # Slight delay to ensure order of calling
        
    # Wait for all background threads to finish
    # Since server.py threads are daemon, we need to manually wait or monitor
    # In a real app, the server runs forever. Here we just wait enough time.
    logging.info("Waiting for background tasks to complete...")
    time.sleep(6) # 3 messages * (0.5s gen + 1.0s play) = ~4.5s max serial time
    
    print("--- Test Complete ---")

if __name__ == "__main__":
    test_concurrency()
