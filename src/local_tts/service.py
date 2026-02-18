"""
Heavy Inference Service for Local TTS MCP.

This service runs as a background process (daemon) and holds the Pocket TTS model in memory.
It communicates with lightweight MCP clients via a Unix Domain Socket (UDS).
"""

import gc
import json
import logging
import os
import queue
import random
import re
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Optional

import psutil
import scipy.io.wavfile as wavfile
import torch

# Heavy imports only in this service
from pocket_tts import TTSModel

from local_tts.resource_manager import ResourceManager
from local_tts.system_lock import SystemTTSCoordinator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Service] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/tmp/local-tts-mcp/service.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("local-tts-service")

# Constants
SOCKET_PATH = "/tmp/local-tts-mcp/inference.sock"
VOICES = ['alba', 'marius', 'javert', 'jean', 'fantine', 'cosette', 'eponine', 'azelma']

class ThreadingUnixServer(ThreadingMixIn, HTTPServer):
    address_family = socket.AF_UNIX

class TTSRequestHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_POST(self):
        if self.path == '/generate':
            self.handle_generate()
        elif self.path == '/status':
            self.handle_status()
        elif self.path == '/shutdown':
            self.handle_shutdown()
        else:
            self.send_error(404)

    def handle_status(self):
        rm = ResourceManager()
        status = rm.get_status()
        proc = rm.get_process_memory_info()
        
        resp = {
            "status": "running",
            "model_loaded": ServiceState.model is not None,
            "ram_percent": status.memory_percent,
            "rss_mb": proc["rss_mb"]
        }
        self.send_json(resp)

    def handle_shutdown(self):
        self.send_json({"status": "shutting_down"})
        logger.info("Received shutdown request via API.")
        # Schedule shutdown
        threading.Thread(target=ServiceState.shutdown_server).start()

    def handle_generate(self):
        length = int(self.headers.get('content-length', 0))
        if length == 0:
            self.send_error(400, "Empty body")
            return
            
        try:
            body = self.rfile.read(length)
            data = json.loads(body)
            
            text = data.get("text")
            voice_path = data.get("voice_path")
            voice_name = data.get("voice_name", "random")
            
            if not text:
                self.send_error(400, "Missing text")
                return

            # Queue the task
            ServiceState.last_activity = time.time()
            ticket = ServiceState.coordinator.get_ticket()
            ServiceState.queue.put((text, voice_path, voice_name, ticket))
            
            self.send_json({"status": "queued", "ticket": ticket})
            
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            self.send_error(500, str(e))

    def send_json(self, data):
        resp = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, format, *args):
        # Silence default HTTP logs to keep console clean
        pass

class PlaybackCoordinator:
    def __init__(self):
        self.current_ticket = 0
        self.next_ticket = 0
        self.condition = threading.Condition()

    def get_ticket(self):
        with self.condition:
            ticket = self.next_ticket
            self.next_ticket += 1
            return ticket

    def wait_for_turn(self, ticket):
        with self.condition:
            while ticket != self.current_ticket:
                self.condition.wait()

    def finish_turn(self):
        with self.condition:
            self.current_ticket += 1
            self.condition.notify_all()

class ServiceState:
    server: Optional[ThreadingUnixServer] = None
    model: Optional[TTSModel] = None
    queue = queue.Queue()
    coordinator = PlaybackCoordinator()
    last_activity = time.time()
    running = True

    @staticmethod
    def shutdown_server():
        logger.info("Shutting down service...")
        ServiceState.running = False
        if ServiceState.server:
            ServiceState.server.shutdown()
            ServiceState.server.server_close()
        # Clean up socket
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
        sys.exit(0)

def load_model():
    if ServiceState.model is None:
        logger.info("Loading Pocket TTS model...")
        ServiceState.model = TTSModel.load_model()

def unload_model():
    if ServiceState.model is not None:
        logger.info("Unloading model due to inactivity...")
        ServiceState.model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        elif torch.backends.mps.is_available():
            torch.mps.empty_cache()

def split_text(text: str, max_length: int = 200) -> list[str]:
    # Reuse existing split logic
    if not text: return []
    text = " ".join(text.split())
    chunks = []
    current_chunk = ""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for sentence in sentences:
        if not sentence.strip(): continue
        if len(current_chunk) + len(sentence) + 1 <= max_length:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            if len(sentence) > max_length:
                words = sentence.split(' ')
                temp_chunk = ""
                for word in words:
                    if len(word) > max_length:
                        for i in range(0, len(word), max_length):
                            sub_word = word[i:i+max_length]
                            if len(temp_chunk) + len(sub_word) + 1 <= max_length:
                                temp_chunk += sub_word + " "
                            else:
                                if temp_chunk: chunks.append(temp_chunk.strip())
                                temp_chunk = sub_word + " "
                    else:
                        if len(temp_chunk) + len(word) + 1 <= max_length:
                            temp_chunk += word + " "
                        else:
                            if temp_chunk: chunks.append(temp_chunk.strip())
                            temp_chunk = word + " "
                current_chunk = temp_chunk
            else:
                current_chunk = sentence + " "
    if current_chunk: chunks.append(current_chunk.strip())
    return chunks

def prepare_voice_file(voice_path: str) -> str:
    try:
        if not os.path.exists(voice_path): return voice_path
        sr, data = wavfile.read(voice_path)
        duration = len(data) / sr
        if duration > 10.0:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                temp_wav_path = temp_wav.name
            max_samples = int(10.0 * sr)
            trimmed_data = data[:max_samples]
            wavfile.write(temp_wav_path, sr, trimmed_data)
            return temp_wav_path
    except Exception as e:
        logger.warning(f"Voice prep error: {e}")
    return voice_path

def play_audio(temp_wav_path: str, ticket: int, start_time: float, text_preview: str, voice_name: str):
    try:
        ServiceState.coordinator.wait_for_turn(ticket)
        if sys.platform == "darwin":
            subprocess.run(["afplay", "-r", "1.2", temp_wav_path], check=True)
        else:
            subprocess.run(["aplay", temp_wav_path], check=False)
        duration = time.time() - start_time
        logger.info(f"Spoken: '{text_preview}...' ({voice_name}) in {duration:.2f}s")
    except Exception as e:
        logger.error(f"Playback error: {e}")
    finally:
        ServiceState.coordinator.finish_turn()
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)

def worker_loop():
    logger.info("Worker thread started.")
    rm = ResourceManager()
    rm.start()
    
    while ServiceState.running:
        try:
            # Wait for task with timeout to check idle status
            try:
                task = ServiceState.queue.get(timeout=5.0)
            except queue.Empty:
                if ServiceState.model is not None and (time.time() - ServiceState.last_activity > 60.0):
                    unload_model()
                continue

            text, voice_path, voice_name, ticket = task
            ServiceState.last_activity = time.time()

            # Resource check
            estimated_mb = 500.0 + (len(text) / 1000.0 * 50.0)
            if not rm.check_allocation_feasibility(estimated_mb):
                logger.warning("Low memory, waiting...")
                time.sleep(2.0)

            load_model()
            model = ServiceState.model
            if not model: continue # Failed to load

            # Voice setup
            voice_state = None
            if voice_path:
                try:
                    proc_path = prepare_voice_file(voice_path)
                    voice_state = model.get_state_for_audio_prompt(proc_path)
                    if proc_path != voice_path and os.path.exists(proc_path):
                        os.remove(proc_path)
                except Exception as e:
                    logger.error(f"Voice error: {e}")
            else:
                if not voice_name or voice_name == "random":
                    voice_name = random.choice(VOICES)
                clean = voice_name.split(" (")[0]
                if clean not in VOICES: clean = "alba"
                voice_state = model.get_state_for_audio_prompt(clean)

            # Generate
            start_time = time.time()
            chunks = split_text(text)
            audio_segments = []
            
            for chunk in chunks:
                if not chunk.strip(): continue
                try:
                    seg = model.generate_audio(voice_state, chunk)
                    if seg.dim() == 1: seg = seg.unsqueeze(0)
                    audio_segments.append(seg)
                except Exception as e:
                    logger.error(f"Gen error: {e}")

            if not audio_segments:
                ServiceState.coordinator.finish_turn()
                continue

            try:
                if len(audio_segments) > 1:
                    audio = torch.cat(audio_segments, dim=1)
                else:
                    audio = audio_segments[0]
                
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    tpath = tf.name
                    wavfile.write(tpath, model.sample_rate, audio.squeeze().numpy())
                
                # Play in separate thread (but serialized by coordinator)
                threading.Thread(
                    target=play_audio,
                    args=(tpath, ticket, start_time, text[:30], voice_name)
                ).start()
                
            except Exception as e:
                logger.error(f"Save error: {e}")
                ServiceState.coordinator.finish_turn()

        except Exception as e:
            logger.error(f"Worker error: {e}")

def main():
    if os.path.exists(SOCKET_PATH):
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            if os.path.exists(SOCKET_PATH):
                logger.error(f"Socket {SOCKET_PATH} already exists and cannot be removed.")
                sys.exit(1)

    server = ThreadingUnixServer(SOCKET_PATH, TTSRequestHandler)
    ServiceState.server = server
    
    # Start worker
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
    
    logger.info(f"Service listening on {SOCKET_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ServiceState.shutdown_server()

if __name__ == "__main__":
    main()
