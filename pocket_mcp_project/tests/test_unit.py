import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pocket_server.engine import PocketTTSEngine

class TestPocketTTSEngine(unittest.TestCase):
    
    def setUp(self):
        # Reset singleton for testing
        PocketTTSEngine._instance = None
        
    @patch('pocket_server.engine.TTSModel')
    def test_singleton(self, mock_tts_model):
        """Verify that the engine uses a singleton pattern."""
        engine1 = PocketTTSEngine()
        engine2 = PocketTTSEngine()
        self.assertIs(engine1, engine2)
        
    @patch('pocket_server.engine.TTSModel')
    def test_voice_mapping(self, mock_tts_model):
        """Verify that scenarios map to correct voices."""
        engine = PocketTTSEngine()
        
        # Verify mapping logic
        expected_mapping = {
            "answer": "alba",
            "permission": "jean",
            "error": "javert",
            "success": "fantine"
        }
        
        self.assertEqual(engine.SCENARIO_VOICE_MAP, expected_mapping)
        
    @patch('pocket_server.engine.TTSModel')
    @patch('pocket_server.engine.wavfile.write')
    def test_generate_logic(self, mock_wav_write, mock_tts_model):
        """Verify generation calls correct model methods."""
        # Setup mock model
        mock_model_instance = MagicMock()
        mock_tts_model.load_model.return_value = mock_model_instance
        mock_model_instance.sample_rate = 24000
        
        # Mock generate output
        mock_audio_tensor = MagicMock()
        mock_audio_tensor.numpy.return_value = "fake_numpy_array"
        mock_model_instance.generate_audio.return_value = mock_audio_tensor
        
        engine = PocketTTSEngine()
        
        # Test "answer" scenario
        result = engine.generate("Hello", "answer", "test_output.wav")
        
        # Check if get_state_for_audio_prompt was called with correct voice
        mock_model_instance.get_state_for_audio_prompt.assert_any_call("alba")
        
        # Check generate_audio called
        mock_model_instance.generate_audio.assert_called()
        
        # Check output
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["scenario"], "answer")
        self.assertEqual(result["voice"], "alba")

if __name__ == '__main__':
    unittest.main()
