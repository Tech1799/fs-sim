"""Disk emulator for block-level I/O operations."""

import os
from typing import Optional
from constants import BLOCK_SIZE


class DiskEmulator:
    """Emulates a disk by dividing a file into fixed-size blocks."""
    
    def __init__(self, path: str, blocks: int):
        self.path = path
        self.blocks = blocks
        self.reads = 0
        self.writes = 0
        self.fd = None
        
    def open(self) -> bool:
        """Open or create the disk image."""
        try:
            if not os.path.exists(self.path):
                with open(self.path, 'wb') as f:
                    f.write(b'\x00' * (self.blocks * BLOCK_SIZE))
            
            self.fd = open(self.path, 'r+b')
            return True
        except Exception as e:
            print(f"Error opening disk: {e}")
            return False
    
    def close(self):
        """Close the disk image."""
        if self.fd:
            self.fd.close()
            self.fd = None
    
    def read(self, block_num: int) -> Optional[bytes]:
        """Read a block from disk."""
        if block_num < 0 or block_num >= self.blocks:
            print(f"Error: Invalid block number {block_num}")
            return None
        
        try:
            self.fd.seek(block_num * BLOCK_SIZE)
            data = self.fd.read(BLOCK_SIZE)
            if len(data) < BLOCK_SIZE:
                data += b'\x00' * (BLOCK_SIZE - len(data))
            self.reads += 1
            return data
        except Exception as e:
            print(f"Error reading block {block_num}: {e}")
            return None
    
    def write(self, block_num: int, data: bytes) -> bool:
        """Write a block to disk."""
        if block_num < 0 or block_num >= self.blocks:
            print(f"Error: Invalid block number {block_num}")
            return False
        
        if len(data) != BLOCK_SIZE:
            print(f"Error: Data must be exactly {BLOCK_SIZE} bytes")
            return False
        
        try:
            self.fd.seek(block_num * BLOCK_SIZE)
            self.fd.write(data)
            self.fd.flush()
            self.writes += 1
            return True
        except Exception as e:
            print(f"Error writing block {block_num}: {e}")
            return False