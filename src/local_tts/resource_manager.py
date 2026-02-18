"""
Resource Manager for Local TTS MCP Server.

Handles system monitoring, memory tracking, and resource-based decision making
to prevent system overload during concurrent TTS operations.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

import psutil

logger = logging.getLogger("local-tts")

@dataclass
class SystemStatus:
    memory_percent: float
    memory_available_mb: float
    memory_total_mb: float
    cpu_percent: float
    is_critical: bool
    
    def __str__(self):
        return (
            f"RAM: {self.memory_percent:.1f}% ({self.memory_available_mb:.0f}MB free), "
            f"CPU: {self.cpu_percent:.1f}%"
        )

class ResourceManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ResourceManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, memory_threshold_percent: float = 85.0, check_interval: float = 2.0):
        if hasattr(self, "_initialized") and self._initialized:
            return
            
        self.memory_threshold = memory_threshold_percent
        self.check_interval = check_interval
        self._monitoring = False
        self._thread: Optional[threading.Thread] = None
        # Initialize with current state
        mem = psutil.virtual_memory()
        self._status = SystemStatus(
            memory_percent=mem.percent,
            memory_available_mb=mem.available / (1024 * 1024),
            memory_total_mb=mem.total / (1024 * 1024),
            cpu_percent=0.0,
            is_critical=mem.percent > memory_threshold_percent
        )
        self._status_lock = threading.Lock()
        self._initialized = True

    def start(self):
        """Start background monitoring thread."""
        if self._monitoring:
            return
        self._monitoring = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("ResourceManager started monitoring system resources.")

    def stop(self):
        """Stop background monitoring thread."""
        self._monitoring = False
        if self._thread:
            self._thread.join(timeout=1.0)
            logger.info("ResourceManager stopped.")

    def _monitor_loop(self):
        while self._monitoring:
            try:
                mem = psutil.virtual_memory()
                cpu = psutil.cpu_percent(interval=None)
                
                with self._status_lock:
                    self._status = SystemStatus(
                        memory_percent=mem.percent,
                        memory_available_mb=mem.available / (1024 * 1024),
                        memory_total_mb=mem.total / (1024 * 1024),
                        cpu_percent=cpu,
                        is_critical=mem.percent > self.memory_threshold
                    )
                
                if self._status.is_critical:
                    logger.warning(
                        f"High memory usage detected: {self._status.memory_percent:.1f}% used. "
                        f"Available: {self._status.memory_available_mb:.0f}MB"
                    )
                    
            except Exception as e:
                logger.error(f"Error in resource monitor: {e}")
            
            time.sleep(self.check_interval)

    def get_status(self) -> SystemStatus:
        """Get the latest system status."""
        with self._status_lock:
            return self._status

    def is_safe_to_run(self) -> bool:
        """Check if system resources are sufficient to start a new task."""
        with self._status_lock:
            return not self._status.is_critical

    def get_process_memory_info(self) -> dict:
        """Get current process memory info."""
        try:
            process = psutil.Process()
            mem = process.memory_info()
            return {
                "rss_mb": mem.rss / (1024 * 1024),
                "vms_mb": mem.vms / (1024 * 1024),
                "percent": process.memory_percent()
            }
        except Exception:
            return {"rss_mb": 0, "vms_mb": 0, "percent": 0}

    def check_allocation_feasibility(self, estimated_mb: float) -> bool:
        """
        Check if allocating 'estimated_mb' would push system over threshold.
        """
        with self._status_lock:
            # Simple check: do we have enough available memory?
            # And will using it push us over the threshold?
            
            # Calculate what percent would be used if we allocate this
            current_used_mb = (self._status.memory_total_mb * (self._status.memory_percent / 100))
            new_used_mb = current_used_mb + estimated_mb
            new_percent = (new_used_mb / self._status.memory_total_mb) * 100
            
            if new_percent > self.memory_threshold:
                logger.warning(
                    f"Allocation rejected: {estimated_mb}MB would push RAM to {new_percent:.1f}% "
                    f"(Threshold: {self.memory_threshold}%)"
                )
                return False
                
            return True
