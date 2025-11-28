"""Interactive shell for file system operations."""

import os
import sys
from datetime import datetime

from file_system import FileSystem
from disk_emulator import DiskEmulator
from structures import Inode
from constants import BLOCK_SIZE, POINTERS_PER_BLOCK
import struct


class Shell:
    """Interactive shell for file system operations."""
    
    def __init__(self):
        self.fs = FileSystem()
        self.disk = None
        self.running = True
        self.gui_server = None
    
    # ... (all shell command methods)