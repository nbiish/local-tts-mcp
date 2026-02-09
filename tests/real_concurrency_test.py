import sys
import os
import time
import logging

# Add src to path
sys.path.append(os.path.abspath("src"))

# Import server directly
import local_tts.server

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def test_real_concurrency():
    print("--- Starting REAL Audio Concurrency Test ---")
    print("You should hear 3 distinct sentences played one after another.")
    print("Loading model first (this might take a moment)...")
    
    # Pre-load model to avoid timeout on first call
    local_tts.server.get_pocket()
    print("Model loaded.")
    
    messages = [
        "First message. Testing concurrency.",
        "Second message. This should play after the first.",
        "Third message. Finally, this completes the sequence."
    ]
    
    print("Firing off 3 speak requests...")
    for msg in messages:
        # Call the tool function directly. 
        # Since it launches a thread, these should return immediately.
        result = local_tts.server.speak(msg)
        print(f"Request sent for: '{msg[:15]}...' -> Result: {result}")
        # Small sleep to ensure we don't hit any weird race conditions in thread spawning,
        # though the lock handles the playback serialization.
        time.sleep(0.1)
        
    print("All requests sent. Waiting for playback to finish...")
    print("(This script will stay alive for 15 seconds to allow playback to complete)")
    
    # Keep main thread alive long enough for background threads to finish
    time.sleep(15)
    print("--- Test Complete ---")

if __name__ == "__main__":
    test_real_concurrency()
