import os
import time
import logging

# Set HF_HOME before importing heavy libraries
# This ensures we use a local cache directory to avoid permission issues
os.environ["HF_HOME"] = os.path.abspath("hf_cache")
os.makedirs(os.environ["HF_HOME"], exist_ok=True)

import scipy.io.wavfile as wavfile
import torch
from pocket_tts import TTSModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pocket_server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PocketEngine")

class PocketTTSEngine:
    """
    Wrapper for Pocket TTS engine with scenario-based voice mapping.
    """
    
    # Mapping scenarios to specific voices in Pocket TTS catalog
    SCENARIO_VOICE_MAP = {
        "answer": "alba",      # Friendly, default response
        "permission": "jean",  # Authoritative, polite request
        "error": "javert",     # Stern, serious for errors
        "success": "fantine"   # Pleasant, happy for success
    }
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PocketTTSEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.model = None
        self.voice_states = {}
        self._load_model()
        self._initialized = True
        
    def _load_model(self):
        """Lazy load the model and prepare voice states."""
        try:
            logger.info("Loading Pocket TTS model...")
            start_time = time.time()
            self.model = TTSModel.load_model()
            duration = time.time() - start_time
            logger.info(f"Model loaded in {duration:.2f}s")
            
            # Pre-load voice states for our scenarios
            for scenario, voice_name in self.SCENARIO_VOICE_MAP.items():
                logger.info(f"Loading voice state for scenario '{scenario}' (Voice: {voice_name})...")
                # Use get_state_for_audio_prompt as discovered in benchmark
                self.voice_states[scenario] = self.model.get_state_for_audio_prompt(voice_name)
                
        except Exception as e:
            logger.error(f"Failed to load Pocket TTS model: {e}")
            raise RuntimeError(f"Engine initialization failed: {e}")

    def generate(self, text: str, scenario: str, output_path: str) -> dict:
        """
        Generate audio for the given text and scenario.
        
        Args:
            text: Text to speak
            scenario: One of ["answer", "permission", "error", "success"]
            output_path: Path to write the WAV file
            
        Returns:
            dict: Metadata about the generation (duration, file_path, etc.)
        """
        if not self.model:
            raise RuntimeError("Model not initialized")
            
        if scenario not in self.SCENARIO_VOICE_MAP:
            logger.warning(f"Unknown scenario '{scenario}', defaulting to 'answer'")
            scenario = "answer"
            
        voice_state = self.voice_states.get(scenario)
        if not voice_state:
            # Should not happen if init worked, but fallback just in case
            voice_name = self.SCENARIO_VOICE_MAP[scenario]
            voice_state = self.model.get_state_for_audio_prompt(voice_name)
            self.voice_states[scenario] = voice_state
            
        try:
            logger.info(f"Generating audio for scenario '{scenario}'...")
            start_time = time.time()
            
            # Generate
            audio = self.model.generate_audio(voice_state, text)
            
            # Save
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                
            wavfile.write(output_path, self.model.sample_rate, audio.numpy())
            
            duration = time.time() - start_time
            logger.info(f"Generated audio in {duration:.2f}s at {output_path}")
            
            return {
                "status": "success",
                "output_path": output_path,
                "duration_seconds": duration,
                "scenario": scenario,
                "voice": self.SCENARIO_VOICE_MAP[scenario]
            }
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise RuntimeError(f"Audio generation failed: {e}")
