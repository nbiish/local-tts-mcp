"""
Tests for the Resource Manager.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import psutil
import pytest

from local_tts.resource_manager import ResourceManager, SystemStatus

class TestResourceManager:
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        # Reset the singleton instance before each test
        ResourceManager._instance = None
        yield
        ResourceManager._instance = None

    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    def test_initialization(self, mock_cpu, mock_mem):
        mock_mem.return_value = MagicMock(percent=50.0, available=8*1024*1024*1024, total=16*1024*1024*1024)
        mock_cpu.return_value = 10.0
        
        rm = ResourceManager()
        status = rm.get_status()
        
        assert status.memory_percent == 50.0
        assert status.memory_available_mb == 8192.0
        assert status.is_critical is False

    @patch("psutil.virtual_memory")
    def test_critical_status(self, mock_mem):
        mock_mem.return_value = MagicMock(percent=90.0, available=100*1024*1024, total=16*1024*1024*1024)
        
        rm = ResourceManager(memory_threshold_percent=85.0)
        status = rm.get_status()
        
        assert status.is_critical is True
        assert rm.is_safe_to_run() is False

    @patch("psutil.virtual_memory")
    def test_allocation_feasibility(self, mock_mem):
        # 50% used of 1000MB total = 500MB used
        mock_mem.return_value = MagicMock(percent=50.0, available=500*1024*1024, total=1000*1024*1024)
        
        rm = ResourceManager(memory_threshold_percent=80.0)
        
        # Allocate 100MB -> 600MB used (60%) -> OK
        assert rm.check_allocation_feasibility(100) is True
        
        # Allocate 400MB -> 900MB used (90%) -> Fail
        assert rm.check_allocation_feasibility(400) is False

    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    def test_monitoring_thread(self, mock_cpu, mock_mem):
        mock_mem.return_value = MagicMock(percent=50.0, available=8192*1024*1024, total=16384*1024*1024)
        mock_cpu.return_value = 10.0
        
        rm = ResourceManager(check_interval=0.1)
        rm.start()
        
        time.sleep(0.2)
        assert rm._thread.is_alive()
        
        rm.stop()
        assert not rm._monitoring
