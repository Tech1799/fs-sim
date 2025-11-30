"""Core file system implementation."""

import time
import struct
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

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