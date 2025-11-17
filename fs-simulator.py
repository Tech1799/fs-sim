#!/usr/bin/env python3
"""
File System Simulator with Interactive Shell and Custom Allocation Visualization
A comprehensive educational tool for understanding file system internals.

Authors: Based on requirements by Bhupinder Bhattarai, Vidyabharathi Ramachandran, Yathish Karkera
"""

import os
import sys
import json
import time
import struct
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# Constants
BLOCK_SIZE = 4096  # 4KB blocks
MAGIC_NUMBER = 0xF0F03410
POINTERS_PER_INODE = 5  # Direct pointers
INODES_PER_BLOCK = 128
MAX_FILENAME = 255


class DiskEmulator:
    """Emulates a disk by dividing a file into fixed-size blocks."""
    
    def __init__(self, path: str, blocks: int):
        """Initialize disk emulator.
        
        Args:
            path: Path to disk image file
            blocks: Number of blocks in disk
        """
        self.path = path
        self.blocks = blocks
        self.reads = 0
        self.writes = 0
        self.fd = None
        
    def open(self) -> bool:
        """Open or create the disk image."""
        try:
            # Create new disk if doesn't exist
            if not os.path.exists(self.path):
                with open(self.path, 'wb') as f:
                    # Initialize with zeros
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
        """Read a block from disk.
        
        Args:
            block_num: Block number to read
            
        Returns:
            Block data or None on error
        """
        if block_num < 0 or block_num >= self.blocks:
            print(f"Error: Invalid block number {block_num}")
            return None
        
        try:
            self.fd.seek(block_num * BLOCK_SIZE)
            data = self.fd.read(BLOCK_SIZE)
            self.reads += 1
            return data
        except Exception as e:
            print(f"Error reading block {block_num}: {e}")
            return None
    
    def write(self, block_num: int, data: bytes) -> bool:
        """Write a block to disk.
        
        Args:
            block_num: Block number to write
            data: Data to write (must be BLOCK_SIZE bytes)
            
        Returns:
            True on success, False on error
        """
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
        data = struct.pack('<IIIII', 
                          self.magic_number,
                          self.blocks,
                          self.inode_blocks,
                          self.inodes,
                          self.root_inode)
        return data + b'\x00' * (BLOCK_SIZE - len(data))
    
    @staticmethod
    def unpack(data: bytes) -> 'SuperBlock':
        """Unpack superblock from bytes."""
        sb = SuperBlock()
        values = struct.unpack('<IIIII', data[:20])
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
        """Pack inode into bytes (32 bytes)."""
        return struct.pack('<IIIIII' + 'I' * POINTERS_PER_INODE + 'I',
                          self.valid,
                          self.inode_type,
                          self.size,
                          self.created,
                          self.modified,
                          0,  # padding
                          *self.direct,
                          self.indirect)
    
    @staticmethod
    def unpack(data: bytes) -> 'Inode':
        """Unpack inode from bytes."""
        inode = Inode()
        values = struct.unpack('<IIIIII' + 'I' * POINTERS_PER_INODE + 'I', data[:32])
        inode.valid = values[0]
        inode.inode_type = values[1]
        inode.size = values[2]
        inode.created = values[3]
        inode.modified = values[4]
        inode.direct = list(values[6:6+POINTERS_PER_INODE])
        inode.indirect = values[6+POINTERS_PER_INODE]
        return inode


class DirEntry:
    """Represents a directory entry."""
    
    def __init__(self, name: str = "", inode_num: int = 0):
        self.name = name[:MAX_FILENAME]
        self.inode_num = inode_num
    
    def pack(self) -> bytes:
        """Pack directory entry (260 bytes)."""
        name_bytes = self.name.encode('utf-8')[:MAX_FILENAME]
        name_bytes = name_bytes + b'\x00' * (MAX_FILENAME - len(name_bytes))
        return name_bytes + struct.pack('<I', self.inode_num) + b'\x00'
    
    @staticmethod
    def unpack(data: bytes) -> 'DirEntry':
        """Unpack directory entry."""
        name = data[:MAX_FILENAME].rstrip(b'\x00').decode('utf-8', errors='ignore')
        inode_num = struct.unpack('<I', data[MAX_FILENAME:MAX_FILENAME+4])[0]
        return DirEntry(name, inode_num)


class FileSystem:
    """Main file system implementation."""
    
    def __init__(self):
        self.disk = None
        self.mounted = False
        self.free_blocks = []
        self.superblock = SuperBlock()
        self.current_dir_inode = 0
    
    def format(self, disk: DiskEmulator) -> bool:
        """Format the disk with a new file system."""
        if self.mounted:
            print("Error: Cannot format mounted file system")
            return False
        
        print("Formatting file system...")
        
        # Calculate inode blocks (10% of total)
        inode_blocks = max(1, disk.blocks // 10)
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
        
        # Create root directory
        root = Inode()
        root.valid = 1
        root.inode_type = Inode.TYPE_DIR
        root.size = 0
        root.created = int(time.time())
        root.modified = root.created
        
        if not self._save_inode(disk, 0, root):
            return False
        
        print(f"Format complete: {disk.blocks} blocks, {inodes} inodes")
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
            print("Error: Invalid file system (bad magic number)")
            return False
        
        self.disk = disk
        self.mounted = True
        self.current_dir_inode = self.superblock.root_inode
        
        # Build free block bitmap
        self._build_free_block_map()
        
        print(f"Mounted file system: {self.superblock.blocks} blocks, "
              f"{self.superblock.inodes} inodes")
        return True
    
    def unmount(self):
        """Unmount the file system."""
        if self.mounted:
            self.disk = None
            self.mounted = False
            self.free_blocks = []
            print("File system unmounted")
    
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
        for i in range(sb.inodes):
            inode = self._load_inode(self.disk, i)
            if inode and inode.valid:
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
        
        # Show free block statistics
        if self.mounted:
            free_count = sum(1 for b in self.free_blocks if b)
            used_count = len(self.free_blocks) - free_count
            print(f"\nBlock Usage:")
            print(f"  Free blocks: {free_count}")
            print(f"  Used blocks: {used_count}")
        
        return True
    
    def create_file(self, name: str) -> int:
        """Create a new file in current directory."""
        if not self.mounted:
            print("Error: File system not mounted")
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
            self.remove_file(inode_num)
            return -1
        
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
                pointers = struct.unpack('<' + 'I' * 1024, indirect_data)
                for ptr in pointers:
                    if ptr != 0:
                        self._free_block(ptr)
            self._free_block(inode.indirect)
        
        # Mark inode as invalid
        inode.valid = 0
        return self._save_inode(self.disk, inode_num, inode)
    
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
                    break
                
                if not self._set_block_pointer(inode, block_index, block_num):
                    self._free_block(block_num)
                    break
            
            # Read existing block data
            block_data = bytearray(self.disk.read(block_num) or b'\x00' * BLOCK_SIZE)
            
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
        
        return bytes_written
    
    def mkdir(self, name: str) -> int:
        """Create a new directory."""
        if not self.mounted:
            print("Error: File system not mounted")
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
        
        return inode_num
    
    def ls(self) -> List[Tuple[str, int, str, int]]:
        """List files in current directory.
        
        Returns:
            List of (name, inode_num, type, size) tuples
        """
        if not self.mounted:
            return []
        
        entries = []
        dir_inode = self._load_inode(self.disk, self.current_dir_inode)
        if not dir_inode or not dir_inode.valid:
            return []
        
        # Read directory data
        data = self.read(self.current_dir_inode, dir_inode.size)
        if not data:
            return []
        
        # Parse directory entries
        entry_size = 260  # Size of packed DirEntry
        for i in range(0, len(data), entry_size):
            if i + entry_size > len(data):
                break
            
            entry = DirEntry.unpack(data[i:i+entry_size])
            if entry.name and entry.inode_num > 0:
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
        entries = self.ls()
        for name, inode_num, inode_type, _ in entries:
            if name == path and inode_type == "DIR":
                self.current_dir_inode = inode_num
                return True
        
        print(f"Error: Directory '{path}' not found")
        return False
    
    def get_visualization_data(self) -> Dict[str, Any]:
        """Get data for visualization."""
        if not self.mounted:
            return {}
        
        total_blocks = self.superblock.blocks
        used_blocks = len([b for b in self.free_blocks if not b])
        free_blocks_count = len([b for b in self.free_blocks if b])
        
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
            'used_blocks': used_blocks,
            'free_blocks': free_blocks_count,
            'superblock_blocks': superblock_blocks,
            'inode_blocks': inode_blocks,
            'data_blocks_used': data_blocks_used,
            'data_blocks_free': data_blocks_free,
        }
    
    def _build_free_block_map(self):
        """Build free block bitmap by scanning inodes."""
        self.free_blocks = [True] * self.superblock.blocks
        
        # Mark superblock and inode blocks as used
        for i in range(self.superblock.inode_blocks + 1):
            self.free_blocks[i] = False
        
        # Scan all inodes and mark used blocks
        for i in range(self.superblock.inodes):
            inode = self._load_inode(self.disk, i)
            if inode and inode.valid:
                # Mark direct blocks
                for block in inode.direct:
                    if block > 0 and block < self.superblock.blocks:
                        self.free_blocks[block] = False
                
                # Mark indirect blocks
                if inode.indirect > 0 and inode.indirect < self.superblock.blocks:
                    self.free_blocks[inode.indirect] = False
                    
                    # Mark blocks pointed to by indirect block
                    indirect_data = self.disk.read(inode.indirect)
                    if indirect_data:
                        pointers = struct.unpack('<' + 'I' * 1024, indirect_data)
                        for ptr in pointers:
                            if ptr > 0 and ptr < self.superblock.blocks:
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
            if self.free_blocks[i]:
                self.free_blocks[i] = False
                return i
        return -1
    
    def _free_block(self, block_num: int):
        """Free a block."""
        if 0 <= block_num < self.superblock.blocks:
            self.free_blocks[block_num] = True
    
    def _load_inode(self, disk: DiskEmulator, inode_num: int) -> Optional[Inode]:
        """Load an inode from disk."""
        if inode_num < 0 or inode_num >= self.superblock.inodes:
            return None
        
        # Calculate block and offset
        block_num = 1 + (inode_num // INODES_PER_BLOCK)
        block_offset = (inode_num % INODES_PER_BLOCK) * 32
        
        # Read block
        data = disk.read(block_num)
        if not data:
            return None
        
        return Inode.unpack(data[block_offset:block_offset + 32])
    
    def _save_inode(self, disk: DiskEmulator, inode_num: int, inode: Inode) -> bool:
        """Save an inode to disk."""
        if inode_num < 0 or inode_num >= self.superblock.inodes:
            return False
        
        # Calculate block and offset
        block_num = 1 + (inode_num // INODES_PER_BLOCK)
        block_offset = (inode_num % INODES_PER_BLOCK) * 32
        
        # Read block
        block_data = bytearray(disk.read(block_num) or b'\x00' * BLOCK_SIZE)
        
        # Update inode data
        inode_data = inode.pack()
        block_data[block_offset:block_offset + 32] = inode_data
        
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
        if indirect_index >= 1024:
            return 0
        
        pointers = struct.unpack('<' + 'I' * 1024, indirect_data)
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
            empty_pointers = struct.pack('<' + 'I' * 1024, *([0] * 1024))
            self.disk.write(inode.indirect, empty_pointers)
        
        # Update indirect block
        indirect_data = bytearray(self.disk.read(inode.indirect))
        indirect_index = block_index - POINTERS_PER_INODE
        
        if indirect_index >= 1024:
            return False
        
        # Update pointer
        struct.pack_into('<I', indirect_data, indirect_index * 4, block_num)
        return self.disk.write(inode.indirect, bytes(indirect_data))
    
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


class Shell:
    """Interactive shell for file system operations."""
    
    def __init__(self):
        self.fs = FileSystem()
        self.disk = None
        self.running = True
    
    def run(self, disk_path: str, blocks: int):
        """Run the shell."""
        print("=" * 60)
        print("File System Simulator - Interactive Shell")
        print("=" * 60)
        
        # Open disk
        self.disk = DiskEmulator(disk_path, blocks)
        if not self.disk.open():
            print("Failed to open disk")
            return
        
        print(f"Disk opened: {disk_path} ({blocks} blocks)")
        print("Type 'help' for available commands\n")
        
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
            'cp': self.cmd_cp,
            'mv': self.cmd_mv,
            'copyin': self.cmd_copyin,
            'copyout': self.cmd_copyout,
            'visualize': self.cmd_visualize,
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
        print("  write <inode> <txt> - Write text to a file")
        print("  cp <src> <dst>      - Copy file (inode numbers)")
        print("  mv <src> <dst>      - Move/rename file (inode numbers)")
        print("  copyin <file> <ino> - Copy file from host to fs")
        print("  copyout <ino> <file>- Copy file from fs to host")
        print("  visualize           - Display block allocation visualization")
        print("  help                - Display this help message")
        print("  exit, quit          - Exit the shell")
        print()
    
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
            print(f"Created file '{filename}' with inode {inode_num}")
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
            print(f"Created directory '{dirname}' with inode {inode_num}")
        else:
            print("Failed to create directory")
    
    def cmd_ls(self, args):
        """List files in current directory."""
        entries = self.fs.ls()
        if not entries:
            print("(empty directory)")
            return
        
        print(f"\n{'Name':<20} {'Inode':<8} {'Type':<6} {'Size':<10}")
        print("-" * 50)
        for name, inode_num, inode_type, size in entries:
            print(f"{name:<20} {inode_num:<8} {inode_type:<6} {size:<10}")
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
            size = self.fs.stat(inode_num)
            if size >= 0:
                print(f"Inode {inode_num}: {size} bytes")
            else:
                print("Error: Invalid inode")
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
            
            data = self.fs.read(inode_num, size)
            if data:
                try:
                    print(data.decode('utf-8'))
                except UnicodeDecodeError:
                    print(f"(binary data, {len(data)} bytes)")
            else:
                print("(empty file)")
        except ValueError:
            print("Error: Invalid inode number")
    
    def cmd_write(self, args):
        """Write text to a file."""
        if len(args) < 2:
            print("Usage: write <inode_number> <text>")
            return
        
        try:
            inode_num = int(args[0])
            text = ' '.join(args[1:])
            data = text.encode('utf-8')
            
            bytes_written = self.fs.write(inode_num, data)
            if bytes_written > 0:
                print(f"Wrote {bytes_written} bytes to inode {inode_num}")
            else:
                print("Failed to write data")
        except ValueError:
            print("Error: Invalid inode number")
    
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
            if not data:
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
    
    def cmd_mv(self, args):
        """Move/rename a file."""
        if len(args) < 2:
            print("Usage: mv <src_inode> <dst_inode>")
            return
        
        # Copy then remove
        self.cmd_cp(args)
        try:
            src_inode = int(args[0])
            self.fs.remove_file(src_inode)
        except ValueError:
            pass
    
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
    
    def cmd_visualize(self, args):
        """Display block allocation visualization."""
        if not self.fs.mounted:
            print("Error: File system not mounted")
            return
        
        data = self.fs.get_visualization_data()
        if not data:
            return
        
        print("\n" + "=" * 60)
        print("Block Allocation Visualization")
        print("=" * 60)
        
        print(f"\nTotal Blocks: {data['total_blocks']}")
        print(f"Used Blocks:  {data['used_blocks']}")
        print(f"Free Blocks:  {data['free_blocks']}")
        
        # Calculate percentages
        used_pct = (data['used_blocks'] / data['total_blocks'] * 100) if data['total_blocks'] > 0 else 0
        free_pct = (data['free_blocks'] / data['total_blocks'] * 100) if data['total_blocks'] > 0 else 0
        
        print(f"\nUsage: {used_pct:.1f}% used, {free_pct:.1f}% free")
        
        # Visual representation
        print("\nBlock Map Legend:")
        print("  [S] = Superblock")
        print("  [I] = Inode block")
        print("  [D] = Data block (used)")
        print("  [.] = Free block")
        
        print("\nBlock Allocation Map:")
        blocks_per_line = 40
        
        for i in range(0, data['total_blocks'], blocks_per_line):
            line = f"{i:4d}: "
            for j in range(i, min(i + blocks_per_line, data['total_blocks'])):
                if j in data['superblock_blocks']:
                    line += "S"
                elif j in data['inode_blocks']:
                    line += "I"
                elif j in data['data_blocks_used']:
                    line += "D"
                else:
                    line += "."
            print(line)
        
        print("\n" + "=" * 60 + "\n")
    
    def cmd_exit(self, args):
        """Exit the shell."""
        self.running = False


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python fs_simulator.py <disk_image> <num_blocks>")
        print("\nExample:")
        print("  python fs_simulator.py disk.img 100")
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