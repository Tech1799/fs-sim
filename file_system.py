"""Core file system implementation."""

import time
import struct
from typing import Dict, List, Optional, Tuple, Any

from constants import (
    BLOCK_SIZE, MAGIC_NUMBER, POINTERS_PER_INODE,
    POINTERS_PER_BLOCK, INODES_PER_BLOCK, INODE_SIZE
)
from structures import SuperBlock, Inode, DirEntry
from disk_emulator import DiskEmulator


class FileSystem:
    """Main file system implementation."""
    
    def __init__(self):
        self.disk = None
        self.mounted = False
        self.free_blocks = []
        self.superblock = SuperBlock()
        self.current_dir_inode = 0
        self.gui_update_callback = None
    
    def set_gui_callback(self, callback):
        """Set callback for GUI updates."""
        self.gui_update_callback = callback
    
    def _notify_gui(self):
        """Notify GUI of changes."""
        if self.gui_update_callback:
            self.gui_update_callback()
    
    # ... (rest of FileSystem methods - format, mount, create_file, etc.)