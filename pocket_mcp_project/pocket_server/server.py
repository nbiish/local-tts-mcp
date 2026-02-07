from mcp.server.fastmcp import FastMCP
from pydantic import Field
from typing import Literal
import os
import sys
import uuid
import subprocess
import datetime
import tempfile

# Ensure we can import engine
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pocket_server.engine import PocketTTSEngine

# Initialize the MCP server
mcp = FastMCP("Pocket TTS Contextual Server")

# Initialize engine singleton
engine = PocketTTSEngine()

@mcp.tool()
def generate_speech(
    text: str = Field(
        ..., 
        description="The text content to be spoken. Must be concise and clear."
    ),
    context: Literal["answer", "permission", "error", "success"] = Field(
        ..., 
        description="The context/scenario for the speech generation. Determines the voice tone and style. Options: 'answer' (general response), 'permission' (asking user), 'error' (reporting issues), 'success' (task completion)."
    )
) -> str:
    """
    Instructs the backend to generate concise TTS audio output tailored to a specific context.
    
    The audio is generated internally, played back immediately, and then deleted (ephemeral).
    
    Use this tool when you need to verbally communicate with the user in one of the following scenarios:
    1. Responding to questions (context='answer')
    2. Requesting permission (context='permission')
    3. Reporting errors (context='error')
    4. Confirming success (context='success')
    """
    
    try:
        # Validate input length for "concise" requirement (soft limit)
        if len(text) > 1000:
            return "Error: Text is too long. Please provide concise text (under 1000 characters)."
            
        # Create a temporary file
        # We use mkstemp to ensure we have a file path compatible with subprocess
        # and delete=False so we can close it before playback (avoiding file lock issues on some OSs)
        # though on Mac/Unix open files are fine, explicit management is cleaner.
        fd, output_path = tempfile.mkstemp(suffix=".wav", prefix=f"pocket_{context}_")
        os.close(fd)
        
        try:
            # Generate Audio
            result = engine.generate(text, context, output_path)
            
            # Play Audio
            try:
                subprocess.run(["afplay", output_path], check=True)
                playback_status = "Audio played successfully."
            except Exception as e:
                playback_status = f"Audio generated but playback failed: {e}"
            
            return (
                f"Successfully generated and played audio for context '{context}'.\n"
                f"Voice: {result['voice']}\n"
                f"Duration: {result['duration_seconds']:.2f}s\n"
                f"Status: {playback_status}\n"
                f"Note: Audio file has been deleted after playback."
            )
            
        finally:
            # Ensure cleanup happens even if generation or playback fails
            if os.path.exists(output_path):
                os.remove(output_path)
        
    except Exception as e:
        return f"Error generating speech: {str(e)}"

if __name__ == "__main__":
    mcp.run()
