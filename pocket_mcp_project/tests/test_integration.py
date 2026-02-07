import unittest
import sys
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pocket_server.server import generate_speech, engine

class TestPocketTTSIntegration(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        pass
        
    @classmethod
    def tearDownClass(cls):
        pass
            
    def test_e2e_answer_generation_and_cleanup(self):
        """Test generation, playback, and subsequent cleanup."""
        
        # We mock subprocess.run to simulate successful playback
        with patch('subprocess.run') as mock_run:
            # We also spy on os.remove to ensure cleanup happens
            with patch('os.remove', side_effect=os.remove) as mock_remove:
                
                result = generate_speech(
                    text="This is a test answer.",
                    context="answer"
                )
                
                self.assertIn("Successfully generated and played audio", result)
                self.assertIn("Audio played successfully", result)
                self.assertIn("Audio file has been deleted", result)
                
                mock_run.assert_called() # Ensure playback was attempted
                mock_remove.assert_called() # Ensure cleanup was attempted
        
    def test_e2e_error_generation(self):
        """Test generating error speech."""
        with patch('subprocess.run') as mock_run:
            result = generate_speech(
                text="This is a test error.",
                context="error"
            )
            
            self.assertIn("Successfully generated and played audio", result)
            mock_run.assert_called()
        
    def test_text_limit(self):
        """Test text length limit."""
        long_text = "a" * 1001
        result = generate_speech(
            text=long_text,
            context="answer"
        )
        self.assertIn("Error: Text is too long", result)

if __name__ == '__main__':
    unittest.main()
