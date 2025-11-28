#!/usr/bin/env python3
"""
File System Simulator with Interactive Shell and Real-Time GUI Visualization
A comprehensive educational tool for understanding file system internals.

Authors: Based on requirements by Bhupinder Bhattarai, Vidyabharathi Ramachandran, Yathish Karkera
"""

import os
import sys
import struct
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
try:
    import tkinter as tk
    from tkinter import ttk
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    print("Warning: tkinter not available. GUI visualization will be disabled.")

# Constants
BLOCK_SIZE = 4096  # 4KB blocks
MAGIC_NUMBER = 0xF0F03410
POINTERS_PER_INODE = 5  # Direct pointers
POINTERS_PER_BLOCK = 1024  # Pointers in indirect block
INODE_SIZE = 44  # Size of each inode in bytes
INODES_PER_BLOCK = BLOCK_SIZE // INODE_SIZE  # 93 inodes per block
MAX_FILENAME = 255


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


class SuperBlock:
    """Represents the file system superblock."""
    
    def __init__(self):
        self.magic_number = MAGIC_NUMBER
        self.blocks = 0
        self.inode_blocks = 0
        self.inodes = 0
        self.root_inode = 0
    
    def pack(self) -> bytes:
        """Pack superblock into bytes."""
        data = struct.pack('<5I', 
                          self.magic_number,
                          self.blocks,
                          self.inode_blocks,
                          self.inodes,
                          self.root_inode)
        # Pad to exactly BLOCK_SIZE (4096 bytes)
        padding_size = BLOCK_SIZE - len(data)
        return data + (b'\x00' * padding_size)
    
    @staticmethod
    def unpack(data: bytes) -> 'SuperBlock':
        """Unpack superblock from bytes."""
        sb = SuperBlock()
        values = struct.unpack('<5I', data[:20])
        sb.magic_number = values[0]
        sb.blocks = values[1]
        sb.inode_blocks = values[2]
        sb.inodes = values[3]
        sb.root_inode = values[4]
        return sb


class Inode:
    """Represents an inode structure."""
    
    TYPE_FILE = 0
    TYPE_DIR = 1
    
    def __init__(self):
        self.valid = 0
        self.inode_type = self.TYPE_FILE
        self.size = 0
        self.created = 0
        self.modified = 0
        self.direct = [0] * POINTERS_PER_INODE
        self.indirect = 0
    
    def pack(self) -> bytes:
        """Pack inode into bytes (44 bytes total)."""
        # Pack: valid, type, size, created, modified, 5 direct pointers, 1 indirect pointer
        # Total: 11 unsigned ints = 44 bytes
        packed = struct.pack('<11I',
                            self.valid,
                            self.inode_type,
                            self.size,
                            self.created,
                            self.modified,
                            self.direct[0],
                            self.direct[1],
                            self.direct[2],
                            self.direct[3],
                            self.direct[4],
                            self.indirect)
        return packed
    
    @staticmethod
    def unpack(data: bytes) -> 'Inode':
        """Unpack inode from bytes."""
        if len(data) < 44:
            data = data + b'\x00' * (44 - len(data))
        
        inode = Inode()
        # Unpack: valid, type, size, created, modified, 5 direct pointers, 1 indirect pointer
        # Total: 11 unsigned ints = 44 bytes
        values = struct.unpack('<11I', data[:44])
        inode.valid = values[0]
        inode.inode_type = values[1]
        inode.size = values[2]
        inode.created = values[3]
        inode.modified = values[4]
        inode.direct = [values[5], values[6], values[7], values[8], values[9]]
        inode.indirect = values[10]
        return inode


class DirEntry:
    """Represents a directory entry."""
    
    ENTRY_SIZE = 264  # 256 bytes for name + 4 bytes for inode + 4 padding
    
    def __init__(self, name: str = "", inode_num: int = 0):
        self.name = name[:MAX_FILENAME]
        self.inode_num = inode_num
    
    def pack(self) -> bytes:
        """Pack directory entry."""
        name_bytes = self.name.encode('utf-8')[:MAX_FILENAME]
        name_bytes = name_bytes.ljust(256, b'\x00')
        return name_bytes + struct.pack('<I', self.inode_num) + b'\x00' * 4
    
    @staticmethod
    def unpack(data: bytes) -> 'DirEntry':
        """Unpack directory entry."""
        if len(data) < DirEntry.ENTRY_SIZE:
            return DirEntry("", 0)
        name = data[:256].rstrip(b'\x00').decode('utf-8', errors='ignore')
        inode_num = struct.unpack('<I', data[256:260])[0]
        return DirEntry(name, inode_num)


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
    
    def format(self, disk: DiskEmulator) -> bool:
        """Format the disk with a new file system."""
        if self.mounted:
            print("Error: Cannot format mounted file system")
            return False
        
        print("Formatting file system...")
        
        # Calculate inode blocks (10% of total, minimum 1)
        inode_blocks = max(1, (disk.blocks + 9) // 10)
        inodes = inode_blocks * INODES_PER_BLOCK
        
        # Setup superblock
        self.superblock.magic_number = MAGIC_NUMBER
        self.superblock.blocks = disk.blocks
        self.superblock.inode_blocks = inode_blocks
        self.superblock.inodes = inodes
        self.superblock.root_inode = 0
        
        # Write superblock
        if not disk.write(0, self.superblock.pack()):
            return False
        
        # Clear inode blocks
        empty_block = b'\x00' * BLOCK_SIZE
        for i in range(1, inode_blocks + 1):
            disk.write(i, empty_block)
        
        # Create root directory inode
        root = Inode()
        root.valid = 1
        root.inode_type = Inode.TYPE_DIR
        root.size = 0
        root.created = int(time.time())
        root.modified = root.created
        
        if not self._save_inode(disk, 0, root):
            return False
        
        print(f"Format complete: {disk.blocks} blocks, {inodes} inodes, {inode_blocks} inode blocks")
        return True
    
    def mount(self, disk: DiskEmulator) -> bool:
        """Mount a file system."""
        if self.mounted:
            print("Error: File system already mounted")
            return False
        
        # Read superblock
        data = disk.read(0)
        if not data:
            return False
        
        self.superblock = SuperBlock.unpack(data)
        
        # Verify magic number
        if self.superblock.magic_number != MAGIC_NUMBER:
            print(f"Error: Invalid file system (bad magic number: 0x{self.superblock.magic_number:08x})")
            return False
        
        self.disk = disk
        self.mounted = True
        self.current_dir_inode = self.superblock.root_inode
        
        # Build free block bitmap
        self._build_free_block_map()
        
        print(f"Mounted file system: {self.superblock.blocks} blocks, "
              f"{self.superblock.inodes} inodes")
        
        self._notify_gui()
        return True
    
    def unmount(self):
        """Unmount the file system."""
        if self.mounted:
            self.disk = None
            self.mounted = False
            self.free_blocks = []
            print("File system unmounted")
            self._notify_gui()
    
    def debug(self) -> bool:
        """Print file system debug information."""
        if not self.disk:
            print("Error: No disk loaded")
            return False
        
        # Read and display superblock
        data = self.disk.read(0)
        if not data:
            return False
        
        sb = SuperBlock.unpack(data)
        
        print("\n=== File System Debug ===")
        print(f"SuperBlock:")
        print(f"  Magic Number: 0x{sb.magic_number:08x} "
              f"({'valid' if sb.magic_number == MAGIC_NUMBER else 'INVALID'})")
        print(f"  Total Blocks: {sb.blocks}")
        print(f"  Inode Blocks: {sb.inode_blocks}")
        print(f"  Total Inodes: {sb.inodes}")
        print(f"  Root Inode: {sb.root_inode}")
        
        # Display valid inodes
        print(f"\nValid Inodes:")
        valid_count = 0
        for i in range(sb.inodes):
            inode = self._load_inode(self.disk, i)
            if inode and inode.valid:
                valid_count += 1
                inode_type = "DIR" if inode.inode_type == Inode.TYPE_DIR else "FILE"
                print(f"  Inode {i} ({inode_type}):")
                print(f"    Size: {inode.size} bytes")
                print(f"    Created: {datetime.fromtimestamp(inode.created)}")
                print(f"    Modified: {datetime.fromtimestamp(inode.modified)}")
                
                # Show direct blocks
                direct_blocks = [b for b in inode.direct if b != 0]
                if direct_blocks:
                    print(f"    Direct blocks: {direct_blocks}")
                
                # Show indirect block
                if inode.indirect != 0:
                    print(f"    Indirect block: {inode.indirect}")
        
        if valid_count == 0:
            print("  (no valid inodes)")
        
        # Show free block statistics
        if self.mounted:
            free_count = sum(1 for b in self.free_blocks if b)
            used_count = len(self.free_blocks) - free_count
            print(f"\nBlock Usage:")
            print(f"  Free blocks: {free_count}")
            print(f"  Used blocks: {used_count}")
            print(f"  Disk reads: {self.disk.reads}")
            print(f"  Disk writes: {self.disk.writes}")
        
        return True
    
    def create_file(self, name: str) -> int:
        """Create a new file in current directory."""
        if not self.mounted:
            print("Error: File system not mounted")
            return -1
        
        # Check if file already exists
        if self._find_dir_entry(self.current_dir_inode, name) >= 0:
            print(f"Error: File '{name}' already exists")
            return -1
        
        # Find free inode
        inode_num = self._allocate_inode()
        if inode_num < 0:
            print("Error: No free inodes")
            return -1
        
        # Create new file inode
        inode = Inode()
        inode.valid = 1
        inode.inode_type = Inode.TYPE_FILE
        inode.size = 0
        inode.created = int(time.time())
        inode.modified = inode.created
        
        if not self._save_inode(self.disk, inode_num, inode):
            return -1
        
        # Add to current directory
        if not self._add_dir_entry(self.current_dir_inode, name, inode_num):
            # Cleanup on failure
            inode.valid = 0
            self._save_inode(self.disk, inode_num, inode)
            return -1
        
        self._notify_gui()
        return inode_num
    
    def remove_file(self, inode_num: int) -> bool:
        """Remove a file by inode number."""
        if not self.mounted:
            print("Error: File system not mounted")
            return False
        
        inode = self._load_inode(self.disk, inode_num)
        if not inode or not inode.valid:
            print(f"Error: Invalid inode {inode_num}")
            return False
        
        # Free all data blocks
        for block in inode.direct:
            if block != 0:
                self._free_block(block)
        
        # Free indirect blocks
        if inode.indirect != 0:
            indirect_data = self.disk.read(inode.indirect)
            if indirect_data:
                pointers = struct.unpack('<' + 'I' * POINTERS_PER_BLOCK, indirect_data)
                for ptr in pointers:
                    if ptr != 0:
                        self._free_block(ptr)
            self._free_block(inode.indirect)
        
        # Mark inode as invalid
        inode.valid = 0
        result = self._save_inode(self.disk, inode_num, inode)
        
        self._notify_gui()
        return result
    
    def stat(self, inode_num: int) -> int:
        """Get file size by inode number."""
        if not self.mounted:
            print("Error: File system not mounted")
            return -1
        
        inode = self._load_inode(self.disk, inode_num)
        if not inode or not inode.valid:
            return -1
        
        return inode.size
    
    def read(self, inode_num: int, length: int, offset: int = 0) -> Optional[bytes]:
        """Read data from a file."""
        if not self.mounted:
            print("Error: File system not mounted")
            return None
        
        inode = self._load_inode(self.disk, inode_num)
        if not inode or not inode.valid:
            print(f"Error: Invalid inode {inode_num}")
            return None
        
        # Adjust length if beyond file size
        if offset >= inode.size:
            return b''
        
        length = min(length, inode.size - offset)
        result = bytearray()
        bytes_read = 0
        
        while bytes_read < length:
            # Calculate block and offset within block
            file_offset = offset + bytes_read
            block_index = file_offset // BLOCK_SIZE
            block_offset = file_offset % BLOCK_SIZE
            
            # Get the block number
            block_num = self._get_block_pointer(inode, block_index)
            if block_num == 0:
                break
            
            # Read from block
            block_data = self.disk.read(block_num)
            if not block_data:
                break
            
            # Copy data
            bytes_to_copy = min(BLOCK_SIZE - block_offset, length - bytes_read)
            result.extend(block_data[block_offset:block_offset + bytes_to_copy])
            bytes_read += bytes_to_copy
        
        return bytes(result)
    
    def write(self, inode_num: int, data: bytes, offset: int = 0) -> int:
        """Write data to a file."""
        if not self.mounted:
            print("Error: File system not mounted")
            return -1
        
        inode = self._load_inode(self.disk, inode_num)
        if not inode or not inode.valid:
            print(f"Error: Invalid inode {inode_num}")
            return -1
        
        bytes_written = 0
        data_len = len(data)
        
        while bytes_written < data_len:
            # Calculate block and offset
            file_offset = offset + bytes_written
            block_index = file_offset // BLOCK_SIZE
            block_offset = file_offset % BLOCK_SIZE
            
            # Get or allocate block
            block_num = self._get_block_pointer(inode, block_index)
            if block_num == 0:
                block_num = self._allocate_block()
                if block_num < 0:
                    print("Error: Disk full")
                    break
                
                if not self._set_block_pointer(inode, block_index, block_num):
                    self._free_block(block_num)
                    break
            
            # Read existing block data if we're doing partial write
            if block_offset != 0 or (data_len - bytes_written) < BLOCK_SIZE:
                block_data = bytearray(self.disk.read(block_num) or b'\x00' * BLOCK_SIZE)
            else:
                block_data = bytearray(BLOCK_SIZE)
            
            # Write new data
            bytes_to_write = min(BLOCK_SIZE - block_offset, data_len - bytes_written)
            block_data[block_offset:block_offset + bytes_to_write] = \
                data[bytes_written:bytes_written + bytes_to_write]
            
            # Write block back
            if not self.disk.write(block_num, bytes(block_data)):
                break
            
            bytes_written += bytes_to_write
        
        # Update inode size and modification time
        inode.size = max(inode.size, offset + bytes_written)
        inode.modified = int(time.time())
        self._save_inode(self.disk, inode_num, inode)
        
        self._notify_gui()
        return bytes_written
    
    def mkdir(self, name: str) -> int:
        """Create a new directory."""
        if not self.mounted:
            print("Error: File system not mounted")
            return -1
        
        # Check if directory already exists
        if self._find_dir_entry(self.current_dir_inode, name) >= 0:
            print(f"Error: Directory '{name}' already exists")
            return -1
        
        # Allocate inode for directory
        inode_num = self._allocate_inode()
        if inode_num < 0:
            print("Error: No free inodes")
            return -1
        
        # Create directory inode
        inode = Inode()
        inode.valid = 1
        inode.inode_type = Inode.TYPE_DIR
        inode.size = 0
        inode.created = int(time.time())
        inode.modified = inode.created
        
        if not self._save_inode(self.disk, inode_num, inode):
            return -1
        
        # Add . and .. entries
        self._add_dir_entry(inode_num, ".", inode_num)
        self._add_dir_entry(inode_num, "..", self.current_dir_inode)
        
        # Add to parent directory
        if not self._add_dir_entry(self.current_dir_inode, name, inode_num):
            self.remove_file(inode_num)
            return -1
        
        self._notify_gui()
        return inode_num
    
    def ls(self) -> List[Tuple[str, int, str, int]]:
        """List files in current directory."""
        if not self.mounted:
            return []
        
        entries = []
        dir_inode = self._load_inode(self.disk, self.current_dir_inode)
        if not dir_inode or not dir_inode.valid:
            return []
        
        # Read directory data
        if dir_inode.size == 0:
            return []
        
        data = self.read(self.current_dir_inode, dir_inode.size)
        if not data:
            return []
        
        # Parse directory entries
        entry_size = DirEntry.ENTRY_SIZE
        for i in range(0, len(data), entry_size):
            if i + entry_size > len(data):
                break
            
            entry = DirEntry.unpack(data[i:i+entry_size])
            if entry.name and entry.inode_num < self.superblock.inodes:
                inode = self._load_inode(self.disk, entry.inode_num)
                if inode and inode.valid:
                    inode_type = "DIR" if inode.inode_type == Inode.TYPE_DIR else "FILE"
                    entries.append((entry.name, entry.inode_num, inode_type, inode.size))
        
        return entries
    
    def cd(self, path: str) -> bool:
        """Change current directory."""
        if not self.mounted:
            print("Error: File system not mounted")
            return False
        
        # Handle absolute path (root)
        if path == "/":
            self.current_dir_inode = self.superblock.root_inode
            return True
        
        # Find directory entry
        target_inode = self._find_dir_entry(self.current_dir_inode, path)
        if target_inode < 0:
            print(f"Error: Directory '{path}' not found")
            return False
        
        # Verify it's a directory
        inode = self._load_inode(self.disk, target_inode)
        if not inode or not inode.valid or inode.inode_type != Inode.TYPE_DIR:
            print(f"Error: '{path}' is not a directory")
            return False
        
        self.current_dir_inode = target_inode
        return True
    
    def get_visualization_data(self) -> Dict[str, Any]:
        """Get data for visualization."""
        if not self.mounted:
            return {}
        
        total_blocks = self.superblock.blocks
        
        # Categorize blocks
        superblock_blocks = [0]
        inode_blocks = list(range(1, self.superblock.inode_blocks + 1))
        data_blocks_used = []
        data_blocks_free = []
        
        data_start = self.superblock.inode_blocks + 1
        for i in range(data_start, total_blocks):
            if i < len(self.free_blocks):
                if self.free_blocks[i]:
                    data_blocks_free.append(i)
                else:
                    data_blocks_used.append(i)
        
        return {
            'total_blocks': total_blocks,
            'superblock_blocks': superblock_blocks,
            'inode_blocks': inode_blocks,
            'data_blocks_used': data_blocks_used,
            'data_blocks_free': data_blocks_free,
            'disk_reads': self.disk.reads if self.disk else 0,
            'disk_writes': self.disk.writes if self.disk else 0,
        }
    
    def _build_free_block_map(self):
        """Build free block bitmap by scanning inodes."""
        self.free_blocks = [True] * self.superblock.blocks
        
        # Mark superblock and inode blocks as used
        for i in range(self.superblock.inode_blocks + 1):
            if i < len(self.free_blocks):
                self.free_blocks[i] = False
        
        # Scan all inodes and mark used blocks
        for i in range(self.superblock.inodes):
            inode = self._load_inode(self.disk, i)
            if inode and inode.valid:
                # Mark direct blocks
                for block in inode.direct:
                    if 0 < block < self.superblock.blocks:
                        self.free_blocks[block] = False
                
                # Mark indirect blocks
                if 0 < inode.indirect < self.superblock.blocks:
                    self.free_blocks[inode.indirect] = False
                    
                    # Mark blocks pointed to by indirect block
                    indirect_data = self.disk.read(inode.indirect)
                    if indirect_data:
                        pointers = struct.unpack('<' + 'I' * POINTERS_PER_BLOCK, indirect_data)
                        for ptr in pointers:
                            if 0 < ptr < self.superblock.blocks:
                                self.free_blocks[ptr] = False
    
    def _allocate_inode(self) -> int:
        """Find and allocate a free inode."""
        for i in range(self.superblock.inodes):
            inode = self._load_inode(self.disk, i)
            if inode and not inode.valid:
                return i
        return -1
    
    def _allocate_block(self) -> int:
        """Find and allocate a free block."""
        for i in range(self.superblock.inode_blocks + 1, self.superblock.blocks):
            if i < len(self.free_blocks) and self.free_blocks[i]:
                self.free_blocks[i] = False
                return i
        return -1
    
    def _free_block(self, block_num: int):
        """Free a block."""
        if 0 <= block_num < len(self.free_blocks):
            self.free_blocks[block_num] = True
    
    def _load_inode(self, disk: DiskEmulator, inode_num: int) -> Optional[Inode]:
        """Load an inode from disk."""
        if inode_num < 0 or inode_num >= self.superblock.inodes:
            return None
        
        # Calculate block and offset
        block_num = 1 + (inode_num // INODES_PER_BLOCK)
        block_offset = (inode_num % INODES_PER_BLOCK) * INODE_SIZE
        
        # Read block
        data = disk.read(block_num)
        if not data:
            return None
        
        return Inode.unpack(data[block_offset:block_offset + INODE_SIZE])
    
    def _save_inode(self, disk: DiskEmulator, inode_num: int, inode: Inode) -> bool:
        """Save an inode to disk."""
        if inode_num < 0 or inode_num >= self.superblock.inodes:
            return False
        
        # Calculate block and offset
        block_num = 1 + (inode_num // INODES_PER_BLOCK)
        block_offset = (inode_num % INODES_PER_BLOCK) * INODE_SIZE
        
        # Read block
        block_data = bytearray(disk.read(block_num) or b'\x00' * BLOCK_SIZE)
        
        # Update inode data
        inode_data = inode.pack()
        block_data[block_offset:block_offset + INODE_SIZE] = inode_data
        
        # Write back
        return disk.write(block_num, bytes(block_data))
    
    def _get_block_pointer(self, inode: Inode, block_index: int) -> int:
        """Get block pointer from inode."""
        if block_index < POINTERS_PER_INODE:
            return inode.direct[block_index]
        
        # Use indirect block
        if inode.indirect == 0:
            return 0
        
        indirect_data = self.disk.read(inode.indirect)
        if not indirect_data:
            return 0
        
        indirect_index = block_index - POINTERS_PER_INODE
        if indirect_index >= POINTERS_PER_BLOCK:
            return 0
        
        pointers = struct.unpack('<' + 'I' * POINTERS_PER_BLOCK, indirect_data)
        return pointers[indirect_index]
    
    def _set_block_pointer(self, inode: Inode, block_index: int, block_num: int) -> bool:
        """Set block pointer in inode."""
        if block_index < POINTERS_PER_INODE:
            inode.direct[block_index] = block_num
            return True
        
        # Use indirect block
        if inode.indirect == 0:
            inode.indirect = self._allocate_block()
            if inode.indirect < 0:
                return False
            
            # Initialize indirect block
            empty_pointers = struct.pack('<' + 'I' * POINTERS_PER_BLOCK, *([0] * POINTERS_PER_BLOCK))
            self.disk.write(inode.indirect, empty_pointers)
        
        # Update indirect block
        indirect_data = bytearray(self.disk.read(inode.indirect))
        indirect_index = block_index - POINTERS_PER_INODE
        
        if indirect_index >= POINTERS_PER_BLOCK:
            return False
        
        # Update pointer
        struct.pack_into('<I', indirect_data, indirect_index * 4, block_num)
        return self.disk.write(inode.indirect, bytes(indirect_data))
    
    def _find_dir_entry(self, dir_inode_num: int, name: str) -> int:
        """Find a directory entry by name. Returns inode number or -1."""
        dir_inode = self._load_inode(self.disk, dir_inode_num)
        if not dir_inode or not dir_inode.valid or dir_inode.size == 0:
            return -1
        
        # Read directory data
        data = self.read(dir_inode_num, dir_inode.size)
        if not data:
            return -1
        
        # Search for entry
        entry_size = DirEntry.ENTRY_SIZE
        for i in range(0, len(data), entry_size):
            if i + entry_size > len(data):
                break
            
            entry = DirEntry.unpack(data[i:i+entry_size])
            if entry.name == name:
                return entry.inode_num
        
        return -1
    
    def _add_dir_entry(self, dir_inode_num: int, name: str, inode_num: int) -> bool:
        """Add an entry to a directory."""
        entry = DirEntry(name, inode_num)
        entry_data = entry.pack()
        
        dir_inode = self._load_inode(self.disk, dir_inode_num)
        if not dir_inode or not dir_inode.valid:
            return False
        
        # Append entry to directory
        bytes_written = self.write(dir_inode_num, entry_data, dir_inode.size)
        return bytes_written == len(entry_data)


# Global reference to file system for GUI
global_fs = None


class BlockVisualizationGUI:
    """Tkinter GUI for real-time block allocation visualization."""
    
    def __init__(self, fs: FileSystem):
        if not TKINTER_AVAILABLE:
            print("Error: tkinter is not available")
            return
        
        self.fs = fs
        self.root = tk.Tk()
        self.root.title("File System Block Allocation - Live View")
        self.root.geometry("1200x800")
        self.root.configure(bg='#2c3e50')
        
        # Color scheme
        self.colors = {
            'superblock': '#e74c3c',  # Red
            'inode': '#3498db',        # Blue
            'used': '#2ecc71',         # Green
            'free': '#ecf0f1',         # Light gray
            'bg': '#2c3e50',           # Dark blue-gray
            'card_bg': '#34495e',      # Lighter gray
            'text': '#ecf0f1'          # Light text
        }
        
        self.block_buttons = []
        self.last_data = None
        
        self.create_widgets()
        self.update_loop()
        
    def create_widgets(self):
        """Create all GUI widgets."""
        # Header
        header_frame = tk.Frame(self.root, bg='#34495e', pady=20)
        header_frame.pack(fill='x')
        
        title_label = tk.Label(
            header_frame,
            text="🗂️ File System Block Allocation Visualizer",
            font=('Helvetica', 24, 'bold'),
            bg='#34495e',
            fg='#ecf0f1'
        )
        title_label.pack()
        
        status_label = tk.Label(
            header_frame,
            text="● LIVE",
            font=('Helvetica', 12),
            bg='#2ecc71',
            fg='white',
            padx=15,
            pady=5,
            borderwidth=2,
            relief='raised'
        )
        status_label.pack(pady=10)
        
        # Main container with scrollbar
        main_container = tk.Frame(self.root, bg=self.colors['bg'])
        main_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Canvas with scrollbar for scrolling
        canvas = tk.Canvas(main_container, bg=self.colors['bg'], highlightthickness=0)
        scrollbar = tk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=self.colors['bg'])
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Statistics cards frame
        stats_frame = tk.Frame(self.scrollable_frame, bg=self.colors['bg'])
        stats_frame.pack(fill='x', padx=10, pady=10)
        
        # Create stat cards
        self.stat_cards = {}
        cards_data = [
            ('superblock', 'Superblock', self.colors['superblock']),
            ('inode', 'Inode Blocks', self.colors['inode']),
            ('used', 'Data Used', self.colors['used']),
            ('free', 'Free Blocks', self.colors['free']),
            ('io', 'Disk I/O', '#9b59b6')
        ]
        
        for i, (key, label, color) in enumerate(cards_data):
            card = self.create_stat_card(stats_frame, label, color)
            card.grid(row=0, column=i, padx=5, sticky='ew')
            stats_frame.columnconfigure(i, weight=1)
            self.stat_cards[key] = card
        
        # Legend
        legend_frame = tk.Frame(self.scrollable_frame, bg=self.colors['bg'], pady=15)
        legend_frame.pack(fill='x')
        
        legend_items = [
            ('S - Superblock', self.colors['superblock']),
            ('I - Inode Blocks', self.colors['inode']),
            ('D - Data (Used)', self.colors['used']),
            ('F - Free Blocks', self.colors['free'])
        ]
        
        for i, (text, color) in enumerate(legend_items):
            item_frame = tk.Frame(legend_frame, bg=self.colors['bg'])
            item_frame.pack(side='left', padx=20)
            
            color_box = tk.Label(
                item_frame,
                text='  ',
                bg=color,
                width=3,
                relief='solid',
                borderwidth=2
            )
            color_box.pack(side='left', padx=5)
            
            text_label = tk.Label(
                item_frame,
                text=text,
                font=('Helvetica', 11),
                bg=self.colors['bg'],
                fg=self.colors['text']
            )
            text_label.pack(side='left')
        
        # Blocks grid container
        blocks_container = tk.Frame(
            self.scrollable_frame,
            bg='#34495e',
            relief='groove',
            borderwidth=2
        )
        blocks_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        title = tk.Label(
            blocks_container,
            text="📦 Block Allocation Grid",
            font=('Helvetica', 14, 'bold'),
            bg='#34495e',
            fg=self.colors['text'],
            pady=10
        )
        title.pack()
        
        # Scrollable blocks grid
        self.blocks_grid_frame = tk.Frame(blocks_container, bg='#34495e')
        self.blocks_grid_frame.pack(padx=15, pady=15)
        
        # Info label
        info_label = tk.Label(
            self.scrollable_frame,
            text="Hover over blocks to see details • Updates automatically every second",
            font=('Helvetica', 10, 'italic'),
            bg=self.colors['bg'],
            fg='#95a5a6',
            pady=10
        )
        info_label.pack()
    
    def create_stat_card(self, parent, label_text, color):
        """Create a statistics card."""
        card_frame = tk.Frame(
            parent,
            bg=color,
            relief='raised',
            borderwidth=2
        )
        
        label = tk.Label(
            card_frame,
            text=label_text,
            font=('Helvetica', 10),
            bg=color,
            fg='white',
            pady=5
        )
        label.pack()
        
        value = tk.Label(
            card_frame,
            text="-",
            font=('Helvetica', 24, 'bold'),
            bg=color,
            fg='white',
            pady=10
        )
        value.pack()
        
        # Store value label for updates
        card_frame.value_label = value
        
        return card_frame
    
    def update_visualization(self):
        """Update the visualization with current data."""
        if not self.fs.mounted:
            return
        
        data = self.fs.get_visualization_data()
        if not data or data.get('total_blocks', 0) == 0:
            return
        
        # Check if data changed
        if data == self.last_data:
            return
        
        self.last_data = data.copy()
        
        # Update statistics
        self.stat_cards['superblock'].value_label.config(
            text=str(len(data.get('superblock_blocks', [])))
        )
        self.stat_cards['inode'].value_label.config(
            text=str(len(data.get('inode_blocks', [])))
        )
        self.stat_cards['used'].value_label.config(
            text=str(len(data.get('data_blocks_used', [])))
        )
        self.stat_cards['free'].value_label.config(
            text=str(len(data.get('data_blocks_free', [])))
        )
        self.stat_cards['io'].value_label.config(
            text=f"R:{data.get('disk_reads', 0)} W:{data.get('disk_writes', 0)}"
        )
        
        # Update blocks grid
        self.update_blocks_grid(data)
    
    def update_blocks_grid(self, data):
        """Update the blocks grid."""
        # Clear existing blocks
        for widget in self.blocks_grid_frame.winfo_children():
            widget.destroy()
        
        self.block_buttons = []
        total_blocks = data['total_blocks']
        
        # Calculate grid dimensions (try to make it roughly square)
        cols = min(40, total_blocks)  # Max 40 columns
        rows = (total_blocks + cols - 1) // cols
        
        superblock_set = set(data.get('superblock_blocks', []))
        inode_set = set(data.get('inode_blocks', []))
        used_set = set(data.get('data_blocks_used', []))
        
        for i in range(total_blocks):
            row = i // cols
            col = i % cols
            
            # Determine block type and color
            if i in superblock_set:
                bg_color = self.colors['superblock']
                block_type = 'Superblock'
                block_info = 'File system metadata'
                text = 'S'
            elif i in inode_set:
                bg_color = self.colors['inode']
                block_type = 'Inode Block'
                block_info = 'File/directory metadata'
                text = 'I'
            elif i in used_set:
                bg_color = self.colors['used']
                block_type = 'Data Block (Used)'
                block_info = 'Contains file data'
                text = 'D'
            else:
                bg_color = self.colors['free']
                block_type = 'Free Block'
                block_info = 'Available for allocation'
                text = ''
            
            # Create block button
            block_btn = tk.Label(
                self.blocks_grid_frame,
                text=text,
                width=2,
                height=1,
                bg=bg_color,
                fg='white' if bg_color != self.colors['free'] else '#7f8c8d',
                font=('Courier', 8, 'bold'),
                relief='raised',
                borderwidth=1,
                cursor='hand2'
            )
            block_btn.grid(row=row, column=col, padx=1, pady=1)
            
            # Bind hover events
            block_btn.bind('<Enter>', 
                          lambda e, num=i, typ=block_type, info=block_info: 
                          self.on_block_hover(e, num, typ, info))
            block_btn.bind('<Leave>', self.on_block_leave)
            
            self.block_buttons.append(block_btn)
    
    def on_block_hover(self, event, block_num, block_type, block_info):
        """Handle block hover event."""
        widget = event.widget
        
        # Highlight effect
        current_bg = widget.cget('bg')
        widget.original_bg = current_bg
        
        # Make it brighter
        widget.config(relief='solid', borderwidth=2)
        
        # Show tooltip
        tooltip_text = f"Block #{block_num}\nType: {block_type}\n{block_info}"
        widget.config(cursor='hand2')
        
        # Create tooltip window
        self.tooltip = tk.Toplevel(widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
        
        label = tk.Label(
            self.tooltip,
            text=tooltip_text,
            justify='left',
            background='#2c3e50',
            foreground='white',
            relief='solid',
            borderwidth=1,
            font=('Helvetica', 9),
            padx=10,
            pady=5
        )
        label.pack()
    
    def on_block_leave(self, event):
        """Handle block leave event."""
        widget = event.widget
        widget.config(relief='raised', borderwidth=1)
        
        # Destroy tooltip
        if hasattr(self, 'tooltip'):
            self.tooltip.destroy()
    
    def update_loop(self):
        """Continuous update loop."""
        self.update_visualization()
        self.root.after(1000, self.update_loop)  # Update every second
    
    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()


class GUIManager:
    """Manager for GUI in separate thread."""
    
    def __init__(self, fs: FileSystem):
        self.fs = fs
        self.gui = None
        self.thread = None
        self.is_running = False
        
        global global_fs
        global_fs = fs
    
    def start(self):
        """Start GUI in separate thread."""
        if not TKINTER_AVAILABLE:
            print("Error: tkinter is not available. Cannot start GUI.")
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._run_gui, daemon=False)
        self.thread.start()
        
        print("\n🖥️  GUI Visualization window opened!")
        print("   The visualization updates automatically every second.\n")
    
    def _run_gui(self):
        """Run GUI in thread."""
        try:
            self.gui = BlockVisualizationGUI(self.fs)
            self.gui.run()
        except Exception as e:
            print(f"GUI Error: {e}")
        finally:
            # Mark as not running when window closes
            self.is_running = False
            self.gui = None
    
    def is_alive(self):
        """Check if GUI is still running."""
        return self.is_running and self.thread and self.thread.is_alive()


class Shell:
    """Interactive shell for file system operations."""
    
    def __init__(self):
        self.fs = FileSystem()
        self.disk = None
        self.running = True
        self.gui_server = None
    
    def run(self, disk_path: str, blocks: int):
        """Run the shell."""
        print("=" * 60)
        print("File System Simulator - Interactive Shell with Live GUI")
        print("=" * 60)
        
        # Open disk
        self.disk = DiskEmulator(disk_path, blocks)
        if not self.disk.open():
            print("Failed to open disk")
            return
        
        print(f"Disk opened: {disk_path} ({blocks} blocks)")
        print("Type 'help' for available commands")
        print("Type 'gui' to open the live visualization\n")
        
        while self.running:
            try:
                # Get current directory
                if self.fs.mounted:
                    prompt = f"sfs:{self.fs.current_dir_inode}> "
                else:
                    prompt = "sfs> "
                
                command = input(prompt).strip()
                if not command:
                    continue
                
                self.execute_command(command)
                
            except KeyboardInterrupt:
                print("\nUse 'exit' or 'quit' to exit")
            except EOFError:
                break
            except Exception as e:
                print(f"Error: {e}")
        
        # Cleanup
        if self.gui_server:
            self.gui_server.stop()
        if self.fs.mounted:
            self.fs.unmount()
        self.disk.close()
        print("\nGoodbye!")
    
    def execute_command(self, command: str):
        """Execute a shell command."""
        parts = command.split()
        if not parts:
            return
        
        cmd = parts[0].lower()
        args = parts[1:]
        
        # Command routing
        commands = {
            'help': self.cmd_help,
            'gui': self.cmd_gui,
            'format': self.cmd_format,
            'mount': self.cmd_mount,
            'unmount': self.cmd_unmount,
            'debug': self.cmd_debug,
            'create': self.cmd_create,
            'mkdir': self.cmd_mkdir,
            'ls': self.cmd_ls,
            'cd': self.cmd_cd,
            'rm': self.cmd_rm,
            'stat': self.cmd_stat,
            'cat': self.cmd_cat,
            'write': self.cmd_write,
            'edit': self.cmd_edit,
            'cp': self.cmd_cp,
            'copyin': self.cmd_copyin,
            'copyout': self.cmd_copyout,
            'exit': self.cmd_exit,
            'quit': self.cmd_exit,
        }
        
        if cmd in commands:
            commands[cmd](args)
        else:
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")
    
    def cmd_help(self, args):
        """Display help information."""
        print("\nAvailable Commands:")
        print("  gui                 - Open live GUI visualization in browser")
        print("  format              - Format the disk with a new file system")
        print("  mount               - Mount the file system")
        print("  unmount             - Unmount the file system")
        print("  debug               - Display file system debug information")
        print("  create <file>       - Create a new file")
        print("  mkdir <dir>         - Create a new directory")
        print("  ls                  - List files in current directory")
        print("  cd <dir>            - Change directory")
        print("  rm <inode>          - Remove a file by inode number")
        print("  stat <inode>        - Display file statistics")
        print("  cat <inode>         - Display file contents")
        print("  write <inode> <txt> - Append text to end of file")
        print("  edit <inode>        - Interactive editor for file")
        print("  cp <src> <dst>      - Copy file (inode numbers)")
        print("  copyin <file> <ino> - Copy file from host to fs")
        print("  copyout <ino> <file>- Copy file from fs to host")
        print("  help                - Display this help message")
        print("  exit, quit          - Exit the shell\n")
    
    def cmd_gui(self, args):
        """Open GUI visualization."""
        if not TKINTER_AVAILABLE:
            print("Error: tkinter is not available on your system.")
            print("Please install tkinter: sudo apt-get install python3-tk (Linux)")
            return
        
        # Check if GUI is actually running
        if self.gui_server and self.gui_server.is_alive():
            print("GUI is already running!")
            return
        
        # Start new GUI instance
        self.gui_server = GUIManager(self.fs)
        self.gui_server.start()
    
    def cmd_format(self, args):
        """Format the file system."""
        if not self.disk:
            print("Error: No disk loaded")
            return
        
        if self.fs.format(self.disk):
            print("File system formatted successfully")
        else:
            print("Failed to format file system")
    
    def cmd_mount(self, args):
        """Mount the file system."""
        if not self.disk:
            print("Error: No disk loaded")
            return
        
        if self.fs.mount(self.disk):
            print("File system mounted successfully")
        else:
            print("Failed to mount file system")
    
    def cmd_unmount(self, args):
        """Unmount the file system."""
        self.fs.unmount()
    
    def cmd_debug(self, args):
        """Display debug information."""
        self.fs.debug()
    
    def cmd_create(self, args):
        """Create a new file."""
        if not args:
            print("Usage: create <filename>")
            return
        
        filename = args[0]
        inode_num = self.fs.create_file(filename)
        if inode_num >= 0:
            # Get inode to show creation time
            inode = self.fs._load_inode(self.fs.disk, inode_num)
            if inode:
                created_time = datetime.fromtimestamp(inode.created).strftime('%Y-%m-%d %H:%M:%S')
                print(f"Created file '{filename}' with inode {inode_num}")
                print(f"  Created at: {created_time}")
        else:
            print("Failed to create file")
    
    def cmd_mkdir(self, args):
        """Create a new directory."""
        if not args:
            print("Usage: mkdir <dirname>")
            return
        
        dirname = args[0]
        inode_num = self.fs.mkdir(dirname)
        if inode_num >= 0:
            # Get inode to show creation time
            inode = self.fs._load_inode(self.fs.disk, inode_num)
            if inode:
                created_time = datetime.fromtimestamp(inode.created).strftime('%Y-%m-%d %H:%M:%S')
                print(f"Created directory '{dirname}' with inode {inode_num}")
                print(f"  Created at: {created_time}")
        else:
            print("Failed to create directory")
    
    def cmd_ls(self, args):
        """List files in current directory."""
        entries = self.fs.ls()
        if not entries:
            print("(empty directory)")
            return
        
        print(f"\n{'Name':<20} {'Inode':<8} {'Type':<6} {'Size':<10} {'Created':<20} {'Modified':<20}")
        print("-" * 100)
        for name, inode_num, inode_type, size in entries:
            # Get inode to retrieve timestamps
            inode = self.fs._load_inode(self.fs.disk, inode_num)
            if inode:
                created = datetime.fromtimestamp(inode.created).strftime('%Y-%m-%d %H:%M:%S')
                modified = datetime.fromtimestamp(inode.modified).strftime('%Y-%m-%d %H:%M:%S')
                print(f"{name:<20} {inode_num:<8} {inode_type:<6} {size:<10} {created:<20} {modified:<20}")
        print()
    
    def cmd_cd(self, args):
        """Change directory."""
        if not args:
            print("Usage: cd <directory>")
            return
        
        if self.fs.cd(args[0]):
            print(f"Changed to directory '{args[0]}'")
    
    def cmd_rm(self, args):
        """Remove a file."""
        if not args:
            print("Usage: rm <inode_number>")
            return
        
        try:
            inode_num = int(args[0])
            if self.fs.remove_file(inode_num):
                print(f"Removed inode {inode_num}")
            else:
                print("Failed to remove file")
        except ValueError:
            print("Error: Invalid inode number")
    
    def cmd_stat(self, args):
        """Display file statistics."""
        if not args:
            print("Usage: stat <inode_number>")
            return
        
        try:
            inode_num = int(args[0])
            
            # Get inode details
            inode = self.fs._load_inode(self.fs.disk, inode_num)
            if not inode or not inode.valid:
                print("Error: Invalid inode")
                return
            
            # Display detailed information
            print(f"\n{'='*60}")
            print(f"File Statistics for Inode {inode_num}")
            print(f"{'='*60}")
            print(f"  Type:           {'Directory' if inode.inode_type == Inode.TYPE_DIR else 'File'}")
            print(f"  Size:           {inode.size} bytes")
            print(f"  Created:        {datetime.fromtimestamp(inode.created).strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Modified:       {datetime.fromtimestamp(inode.modified).strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Show allocated blocks
            direct_blocks = [b for b in inode.direct if b != 0]
            if direct_blocks:
                print(f"  Direct Blocks:  {direct_blocks}")
            else:
                print(f"  Direct Blocks:  None")
            
            if inode.indirect != 0:
                print(f"  Indirect Block: {inode.indirect}")
                
                # Count indirect pointers
                indirect_data = self.fs.disk.read(inode.indirect)
                if indirect_data:
                    pointers = struct.unpack('<' + 'I' * POINTERS_PER_BLOCK, indirect_data)
                    indirect_count = sum(1 for p in pointers if p != 0)
                    print(f"  Indirect Ptrs:  {indirect_count} data blocks")
            else:
                print(f"  Indirect Block: None")
            
            total_blocks = len(direct_blocks) + (1 if inode.indirect != 0 else 0)
            print(f"  Total Blocks:   {total_blocks}")
            print(f"{'='*60}\n")
            
        except ValueError:
            print("Error: Invalid inode number")
    
    def cmd_cat(self, args):
        """Display file contents."""
        if not args:
            print("Usage: cat <inode_number>")
            return
        
        try:
            inode_num = int(args[0])
            size = self.fs.stat(inode_num)
            if size < 0:
                print("Error: Invalid inode")
                return
            
            if size == 0:
                print("(empty file)")
                return
            
            data = self.fs.read(inode_num, size)
            if data:
                try:
                    print(data.decode('utf-8'))
                except UnicodeDecodeError:
                    print(f"(binary data, {len(data)} bytes)")
                    print("First 100 bytes (hex):", data[:100].hex())
            else:
                print("(empty file)")
        except ValueError:
            print("Error: Invalid inode number")
    
    def cmd_write(self, args):
        """Write text to a file (appends to end by default)."""
        if len(args) < 2:
            print("Usage: write <inode_number> <text>")
            return
        
        try:
            inode_num = int(args[0])
            
            # Get current file info
            inode_before = self.fs._load_inode(self.fs.disk, inode_num)
            if not inode_before or not inode_before.valid:
                print("Error: Invalid inode")
                return
            
            size_before = inode_before.size
            
            text = ' '.join(args[1:])
            data = text.encode('utf-8')
            
            # Append at the end
            bytes_written = self.fs.write(inode_num, data, offset=size_before)
            if bytes_written > 0:
                # Get updated inode to show modification time
                inode_after = self.fs._load_inode(self.fs.disk, inode_num)
                if inode_after:
                    modified_time = datetime.fromtimestamp(inode_after.modified).strftime('%Y-%m-%d %H:%M:%S')
                    print(f"Wrote {bytes_written} bytes to inode {inode_num}")
                    print(f"  Modified at: {modified_time}")
                    if size_before > 0:
                        print(f"  Size: {size_before} → {inode_after.size} bytes")
            else:
                print("Failed to write data")
        except ValueError:
            print("Error: Invalid inode number")
    
    def cmd_edit(self, args):
        """Interactive editor for file."""
        if not args:
            print("Usage: edit <inode_number>")
            return
        
        try:
            inode_num = int(args[0])
            
            # Read current content
            size = self.fs.stat(inode_num)
            if size < 0:
                print("Error: Invalid inode")
                return
            
            current_text = ""
            if size > 0:
                data = self.fs.read(inode_num, size)
                if data:
                    try:
                        current_text = data.decode('utf-8')
                    except UnicodeDecodeError:
                        print("Error: File contains binary data, cannot edit")
                        return
            
            # Show current content
            print("\n" + "="*60)
            print(f"Editing inode {inode_num} (current size: {size} bytes)")
            print("="*60)
            if current_text:
                print("Current content:")
                print(current_text)
                print("-"*60)
            else:
                print("(empty file)")
                print("-"*60)
            
            print("\nEnter new content (type 'END' on a new line to finish):")
            print("Or type 'CANCEL' to discard changes\n")
            
            # Read new content
            lines = []
            while True:
                try:
                    line = input()
                    if line == "END":
                        break
                    if line == "CANCEL":
                        print("Edit cancelled")
                        return
                    lines.append(line)
                except EOFError:
                    break
            
            # Write new content
            new_text = '\n'.join(lines)
            new_data = new_text.encode('utf-8')
            
            bytes_written = self.fs.write(inode_num, new_data, offset=0)
            if bytes_written > 0:
                print(f"\n✓ Saved {bytes_written} bytes to inode {inode_num}")
            else:
                print("\nFailed to save changes")
                
        except ValueError:
            print("Error: Invalid inode number")
        except KeyboardInterrupt:
            print("\nEdit cancelled")
    
    def cmd_cp(self, args):
        """Copy a file."""
        if len(args) < 2:
            print("Usage: cp <src_inode> <dst_inode>")
            return
        
        try:
            src_inode = int(args[0])
            dst_inode = int(args[1])
            
            # Read source
            size = self.fs.stat(src_inode)
            if size < 0:
                print("Error: Invalid source inode")
                return
            
            data = self.fs.read(src_inode, size)
            if data is None:
                print("Error: Failed to read source")
                return
            
            # Write to destination
            bytes_written = self.fs.write(dst_inode, data)
            if bytes_written > 0:
                print(f"Copied {bytes_written} bytes from inode {src_inode} to {dst_inode}")
            else:
                print("Failed to copy")
        except ValueError:
            print("Error: Invalid inode number")
    
    def cmd_copyin(self, args):
        """Copy a file from host to file system."""
        if len(args) < 2:
            print("Usage: copyin <host_file> <inode_number>")
            return
        
        host_file = args[0]
        try:
            inode_num = int(args[1])
            
            # Read host file
            if not os.path.exists(host_file):
                print(f"Error: File '{host_file}' not found")
                return
            
            with open(host_file, 'rb') as f:
                data = f.read()
            
            # Write to file system
            bytes_written = self.fs.write(inode_num, data)
            if bytes_written > 0:
                print(f"Copied {bytes_written} bytes from '{host_file}' to inode {inode_num}")
            else:
                print("Failed to copy file")
        except ValueError:
            print("Error: Invalid inode number")
        except Exception as e:
            print(f"Error: {e}")
    
    def cmd_copyout(self, args):
        """Copy a file from file system to host."""
        if len(args) < 2:
            print("Usage: copyout <inode_number> <host_file>")
            return
        
        try:
            inode_num = int(args[0])
            host_file = args[1]
            
            # Read from file system
            size = self.fs.stat(inode_num)
            if size < 0:
                print("Error: Invalid inode")
                return
            
            data = self.fs.read(inode_num, size)
            if data is None:
                print("Error: Failed to read file")
                return
            
            # Write to host
            with open(host_file, 'wb') as f:
                f.write(data)
            
            print(f"Copied {len(data)} bytes from inode {inode_num} to '{host_file}'")
        except ValueError:
            print("Error: Invalid inode number")
        except Exception as e:
            print(f"Error: {e}")
    
    def cmd_exit(self, args):
        """Exit the shell."""
        self.running = False


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("File System Simulator with Live GUI Visualization")
        print("=" * 60)
        print("\nUsage: python fs_simulator.py <disk_image> <num_blocks>")
        print("\nExample:")
        print("  python fs_simulator.py disk.img 100")
        print("\nThis will create a 100-block disk (400 KB total)")
        print("Minimum 10 blocks required.")
        print("\nAfter starting, type 'gui' to open the live visualization!")
        sys.exit(1)
    
    disk_path = sys.argv[1]
    try:
        blocks = int(sys.argv[2])
        if blocks < 10:
            print("Error: Number of blocks must be at least 10")
            sys.exit(1)
    except ValueError:
        print("Error: Invalid number of blocks")
        sys.exit(1)
    
    # Run shell
    shell = Shell()
    shell.run(disk_path, blocks)


if __name__ == "__main__":
    main()