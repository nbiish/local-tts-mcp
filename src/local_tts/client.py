"""
Lightweight Client for Local TTS Service.

Handles communication with the background inference service via Unix Domain Socket.
Starts the service if it's not running.
"""

import json
import logging
import os
import socket
import subprocess
import sys
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("local-tts-client")

SOCKET_PATH = "/tmp/local-tts-mcp/inference.sock"
SERVICE_SCRIPT = "local_tts.service"

class TTSClient:
    def __init__(self):
        pass

    def _connect(self) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(SOCKET_PATH)
        return sock

    def is_service_running(self) -> bool:
        if not os.path.exists(SOCKET_PATH):
            return False
        try:
            with self._connect() as sock:
                pass
            return True
        except (ConnectionRefusedError, FileNotFoundError):
            return False

    def start_service(self):
        """Start the background service process."""
        if self.is_service_running():
            return

        logger.info("Starting Local TTS Service...")
        
        # Use the same python interpreter
        python_exe = sys.executable
        
        # Launch as detached process
        subprocess.Popen(
            [python_exe, "-m", SERVICE_SCRIPT],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Wait for socket
        start = time.time()
        while time.time() - start < 10.0:
            if self.is_service_running():
                logger.info("Service started successfully.")
                return
            time.sleep(0.5)
            
        raise RuntimeError("Timed out waiting for TTS Service to start.")

    def _send_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        if not self.is_service_running():
            self.start_service()

        with self._connect() as sock:
            body = json.dumps(data).encode('utf-8') if data else b""
            
            request = (
                f"{method} {endpoint} HTTP/1.1\r\n"
                f"Host: localhost\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"\r\n"
            ).encode('utf-8') + body
            
            sock.sendall(request)
            
            # Read response (simple HTTP parser)
            response_data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                
            # Parse headers/body
            header_end = response_data.find(b"\r\n\r\n")
            if header_end == -1:
                raise ValueError("Invalid response from service")
                
            body = response_data[header_end+4:]
            return json.loads(body)

    def speak(self, text: str, voice_path: Optional[str] = None, voice_name: Optional[str] = None) -> Dict[str, Any]:
        """Send a speech generation request."""
        # Ensure we only send the request if we can connect
        if not self.is_service_running():
            self.start_service()
            
        return self._send_request("POST", "/generate", {
            "text": text,
            "voice_path": voice_path,
            "voice_name": voice_name
        })

    def get_status(self) -> Dict[str, Any]:
        try:
            return self._send_request("POST", "/status")
        except Exception:
            return {"status": "stopped"}

    def shutdown(self):
        try:
            self._send_request("POST", "/shutdown")
        except Exception:
            pass
