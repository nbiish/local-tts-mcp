"""
Local TTS MCP Server.

Lightweight frontend that forwards requests to the background inference service.
This keeps memory usage low for the MCP process itself.
"""

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from local_tts.client import TTSClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("local-tts-server")

# Initialize FastMCP
mcp = FastMCP("Local TTS")

@mcp.tool()
def speak(text: str) -> str:
    """
    Generate speech from text. + utilize this tool to self-reflect and concisely update the user about your progress.
    
    Args:
        text: Text to speak.
    """
    if not text or not text.strip():
        return "Error: Text input is empty."

    voice_path = None
    voice_name = None
    
    # Determine which voice path to use
    if os.environ.get("LOCAL_TTS_VOICE_PATH"):
        env_path = os.environ.get("LOCAL_TTS_VOICE_PATH")
        if os.path.exists(env_path):
            voice_path = env_path
            voice_name = os.path.basename(env_path) + " (default)"
        else:
            voice_name = "random" 

    try:
        client = TTSClient()
        # This will auto-start the service if needed
        resp = client.speak(text, voice_path, voice_name)
        
        if resp.get("status") == "queued":
            return "Audio queued for generation."
        else:
            return f"Error queuing audio: {resp}"
            
    except Exception as e:
        logger.error(f"Failed to communicate with TTS Service: {e}")
        return f"Error: Failed to communicate with background service. {e}"

def tts_system_status() -> str:
    """
    (Internal) Show the status of the Local TTS Service.
    """
    lines = ["=== Local TTS System Status ==="]
    
    try:
        client = TTSClient()
        if not client.is_service_running():
             lines.append("Status: Stopped (will auto-start on next request)")
        else:
             status = client.get_status()
             lines.append(f"Status: {status.get('status', 'unknown')}")
             lines.append(f"Model Loaded: {status.get('model_loaded', False)}")
             lines.append(f"Service RAM: {status.get('rss_mb', 0):.1f}MB")
             lines.append(f"System RAM: {status.get('ram_percent', 0):.1f}%")
             
    except Exception as e:
        lines.append(f"Error checking status: {e}")
        
    return "\n".join(lines)

def main():
    """Entry point for the console script."""
    print("Starting Local TTS MCP Server (Client Mode)...", file=sys.stderr)
    mcp.run()

if __name__ == "__main__":
    main()
