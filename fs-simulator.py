#!/usr/bin/env python3
"""
File System Simulator with Interactive Shell and Tkinter Visualization
Authors: Bhupinder Bhattarai, Vidyabharathi Ramachandran, Yathish Karkera
"""

import os
import sys
import struct
import time
import queue
import types
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from visualizer import BlockVisualizer

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
        self.visualizer = None  # safe default

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
        data = struct.pack('<5I',
                           self.magic_number,
                           self.blocks,
                           self.inode_blocks,
                           self.inodes,
                           self.root_inode)
        return data + (b'\x00' * (BLOCK_SIZE - len(data)))

    @staticmethod
    def unpack(data: bytes) -> 'SuperBlock':
        sb = SuperBlock()
        values = struct.unpack('<5I', data[:20])
        sb.magic_number, sb.blocks, sb.inode_blocks, sb.inodes, sb.root_inode = values
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
        return struct.pack('<11I',
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

    @staticmethod
    def unpack(data: bytes) -> 'Inode':
        if len(data) < INODE_SIZE:
            data = data + b'\x00' * (INODE_SIZE - len(data))
        values = struct.unpack('<11I', data[:INODE_SIZE])
        inode = Inode()
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
    ENTRY_SIZE = 264  # 256 bytes name + 4 inode + 4 padding

    def __init__(self, name: str = "", inode_num: int = 0):
        self.name = name[:MAX_FILENAME]
        self.inode_num = inode_num

    def pack(self) -> bytes:
        name_bytes = self.name.encode('utf-8')[:MAX_FILENAME]
        name_bytes = name_bytes.ljust(256, b'\x00')
        return name_bytes + struct.pack('<I', self.inode_num) + b'\x00' * 4

    @staticmethod
    def unpack(data: bytes) -> 'DirEntry':
        if len(data) < DirEntry.ENTRY_SIZE:
            return DirEntry("", 0)
        name = data[:256].rstrip(b'\x00').decode('utf-8', errors='ignore')
        inode_num = struct.unpack('<I', data[256:260])[0]
        return DirEntry(name, inode_num)


class FileSystem:
    """Main file system implementation."""
    def __init__(self, disk_path: str, blocks: int, visualizer=None):
        self.disk = None
        self.mounted = False
        self.free_blocks = []
        self.superblock = SuperBlock()
        self.current_dir_inode = 0
        self.disk_path = disk_path
        self.blocks = blocks
        self.visualizer = visualizer  # expected to be an object with .queue

    def format(self, disk: DiskEmulator) -> bool:
        if self.mounted:
            print("Error: Cannot format mounted file system")
            return False
        print("Formatting file system...")
        inode_blocks = max(1, (disk.blocks + 9) // 10)
        inodes = inode_blocks * INODES_PER_BLOCK
        self.superblock.magic_number = MAGIC_NUMBER
        self.superblock.blocks = disk.blocks
        self.superblock.inode_blocks = inode_blocks
        self.superblock.inodes = inodes
        self.superblock.root_inode = 0

        if not disk.write(0, self.superblock.pack()):
            return False

        empty_block = b'\x00' * BLOCK_SIZE
        for i in range(1, inode_blocks + 1):
            if not disk.write(i, empty_block):
                return False

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
        if self.mounted:
            print("Error: File system already mounted")
            return False
        data = disk.read(0)
        if not data:
            return False
        self.superblock = SuperBlock.unpack(data)
        if self.superblock.magic_number != MAGIC_NUMBER:
            print(f"Error: Invalid file system (bad magic number: 0x{self.superblock.magic_number:08x})")
            return False
        self.disk = disk
        self.mounted = True
        self.current_dir_inode = self.superblock.root_inode
        self._build_free_block_map()
        print(f"Mounted file system: {self.superblock.blocks} blocks, {self.superblock.inodes} inodes")
        return True

    def unmount(self):
        if self.mounted:
            self.disk = None
            self.mounted = False
            self.free_blocks = []
            print("File system unmounted")

    def debug(self) -> bool:
        if not self.disk:
            print("Error: No disk loaded")
            return False
        data = self.disk.read(0)
        if not data:
            return False
        sb = SuperBlock.unpack(data)
        print("\n=== File System Debug ===")
        print(f"SuperBlock:")
        print(f"  Magic Number: 0x{sb.magic_number:08x} ({'valid' if sb.magic_number == MAGIC_NUMBER else 'INVALID'})")
        print(f"  Total Blocks: {sb.blocks}")
        print(f"  Inode Blocks: {sb.inode_blocks}")
        print(f"  Total Inodes: {sb.inodes}")
        print(f"  Root Inode: {sb.root_inode}")

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
                direct_blocks = [b for b in inode.direct if b != 0]
                if direct_blocks:
                    print(f"    Direct blocks: {direct_blocks}")
                if inode.indirect != 0:
                    print(f"    Indirect block: {inode.indirect}")

        if valid_count == 0:
            print("  (no valid inodes)")

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
        if not self.mounted:
            print("Error: File system not mounted")
            return -1
        if self._find_dir_entry(self.current_dir_inode, name) >= 0:
            print(f"Error: File '{name}' already exists")
            return -1
        inode_num = self._allocate_inode()
        if inode_num < 0:
            print("Error: No free inodes")
            return -1
        inode = Inode()
        inode.valid = 1
        inode.inode_type = Inode.TYPE_FILE
        inode.size = 0
        inode.created = int(time.time())
        inode.modified = inode.created
        if not self._save_inode(self.disk, inode_num, inode):
            return -1
        if not self._add_dir_entry(self.current_dir_inode, name, inode_num):
            inode.valid = 0
            self._save_inode(self.disk, inode_num, inode)
            return -1
        self._notify_visualizer()
        return inode_num

    def remove_file(self, inode_num: int) -> bool:
        if not self.mounted:
            print("Error: File system not mounted")
            return False
        inode = self._load_inode(self.disk, inode_num)
        if not inode or not inode.valid:
            print(f"Error: Invalid inode {inode_num}")
            return False
        for block in inode.direct:
            if block != 0:
                self._free_block(block)
        if inode.indirect != 0:
            indirect_data = self.disk.read(inode.indirect)
            if indirect_data:
                pointers = struct.unpack('<' + 'I' * POINTERS_PER_BLOCK, indirect_data)
                for ptr in pointers:
                    if ptr != 0:
                        self._free_block(ptr)
            self._free_block(inode.indirect)
        inode.valid = 0
        ok = self._save_inode(self.disk, inode_num, inode)
        self._notify_visualizer()
        return ok

    def stat(self, inode_num: int) -> int:
        if not self.mounted:
            print("Error: File system not mounted")
            return -1
        inode = self._load_inode(self.disk, inode_num)
        if not inode or not inode.valid:
            return -1
        return inode.size

    def read(self, inode_num: int, length: int, offset: int = 0) -> Optional[bytes]:
        if not self.mounted:
            print("Error: File system not mounted")
            return None
        inode = self._load_inode(self.disk, inode_num)
        if not inode or not inode.valid:
            print(f"Error: Invalid inode {inode_num}")
            return None
        if offset >= inode.size:
            return b''
        length = min(length, inode.size - offset)
        result = bytearray()
        bytes_read = 0
        while bytes_read < length:
            file_offset = offset + bytes_read
            block_index = file_offset // BLOCK_SIZE
            block_offset = file_offset % BLOCK_SIZE
            block_num = self._get_block_pointer(inode, block_index)
            if block_num == 0:
                break
            block_data = self.disk.read(block_num)
            if not block_data:
                break
            bytes_to_copy = min(BLOCK_SIZE - block_offset, length - bytes_read)
            result.extend(block_data[block_offset:block_offset + bytes_to_copy])
            bytes_read += bytes_to_copy
        return bytes(result)

    def write(self, inode_num: int, data: bytes, offset: int = 0) -> int:
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
            file_offset = offset + bytes_written
            block_index = file_offset // BLOCK_SIZE
            block_offset = file_offset % BLOCK_SIZE
            block_num = self._get_block_pointer(inode, block_index)
            if block_num == 0:
                block_num = self._allocate_block()
                if block_num < 0:
                    print("Error: Disk full")
                    break
                if not self._set_block_pointer(inode, block_index, block_num):
                    self._free_block(block_num)
                    break
            if block_offset != 0 or (data_len - bytes_written) < BLOCK_SIZE:
                block_data = bytearray(self.disk.read(block_num) or b'\x00' * BLOCK_SIZE)
            else:
                block_data = bytearray(BLOCK_SIZE)
            bytes_to_write = min(BLOCK_SIZE - block_offset, data_len - bytes_written)
            block_data[block_offset:block_offset + bytes_to_write] = data[bytes_written:bytes_written + bytes_to_write]
            if not self.disk.write(block_num, bytes(block_data)):
                break
            bytes_written += bytes_to_write
        inode.size = max(inode.size, offset + bytes_written)
        inode.modified = int(time.time())
        self._save_inode(self.disk, inode_num, inode)
        self._notify_visualizer()
        return bytes_written

    def append(self, inode_num: int, data: bytes) -> int:
        if not self.mounted:
            print("Error: File system not mounted")
            return -1
        inode = self._load_inode(self.disk, inode_num)
        if not inode or not inode.valid:
            print("Invalid inode")
            return -1
        data_bytes = data if isinstance(data, (bytes, bytearray)) else str(data).encode('utf-8')
        bytes_written = 0
        total_size = inode.size + len(data_bytes)
        while bytes_written < len(data_bytes):
            file_offset = inode.size + bytes_written
            block_index = file_offset // BLOCK_SIZE
            block_offset = file_offset % BLOCK_SIZE
            block_num = self._get_block_pointer(inode, block_index)
            if block_num == 0:
                block_num = self._allocate_block()
                if block_num < 0:
                    print("Error: Disk full")
                    break
                if not self._set_block_pointer(inode, block_index, block_num):
                    self._free_block(block_num)
                    break
            block_data = bytearray(self.disk.read(block_num) or b'\x00' * BLOCK_SIZE)
            writable = min(BLOCK_SIZE - block_offset, len(data_bytes) - bytes_written)
            block_data[block_offset:block_offset + writable] = data_bytes[bytes_written:bytes_written + writable]
            if not self.disk.write(block_num, bytes(block_data)):
                break
            bytes_written += writable
        inode.size = total_size
        inode.modified = int(time.time())
        self._save_inode(self.disk, inode_num, inode)
        self._notify_visualizer()
        return bytes_written

    def mkdir(self, name: str) -> int:
        if not self.mounted:
            print("Error: File system not mounted")
            return -1
        if self._find_dir_entry(self.current_dir_inode, name) >= 0:
            print(f"Error: Directory '{name}' already exists")
            return -1
        inode_num = self._allocate_inode()
        if inode_num < 0:
            print("Error: No free inodes")
            return -1
        inode = Inode()
        inode.valid = 1
        inode.inode_type = Inode.TYPE_DIR
        inode.size = 0
        inode.created = int(time.time())
        inode.modified = inode.created
        if not self._save_inode(self.disk, inode_num, inode):
            return -1
        self._add_dir_entry(inode_num, ".", inode_num)
        self._add_dir_entry(inode_num, "..", self.current_dir_inode)
        if not self._add_dir_entry(self.current_dir_inode, name, inode_num):
            self.remove_file(inode_num)
            return -1
        self._notify_visualizer()
        return inode_num

    def ls(self) -> List[Tuple[str, int, str, int]]:
        if not self.mounted:
            return []
        entries = []
        dir_inode = self._load_inode(self.disk, self.current_dir_inode)
        if not dir_inode or not dir_inode.valid or dir_inode.size == 0:
            return []
        data = self.read(self.current_dir_inode, dir_inode.size)
        if not data:
            return []
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
        if not self.mounted:
            print("Error: File system not mounted")
            return False
        if path == "/":
            self.current_dir_inode = self.superblock.root_inode
            return True
        target_inode = self._find_dir_entry(self.current_dir_inode, path)
        if target_inode < 0:
            print(f"Error: Directory '{path}' not found")
            return False
        inode = self._load_inode(self.disk, target_inode)
        if not inode or not inode.valid or inode.inode_type != Inode.TYPE_DIR:
            print(f"Error: '{path}' is not a directory")
            return False
        self.current_dir_inode = target_inode
        return True

    def get_visualization_data(self) -> Dict[str, Any]:
     if not self.mounted:
        return {}

     total_blocks = self.superblock.blocks
     used_blocks = len([b for b in self.free_blocks if not b])
     free_blocks_count = len([b for b in self.free_blocks if b])

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

    # ✅ NEW: build block → inode mapping
     block_to_inode = {}
     for i in range(self.superblock.inodes):
        inode = self._load_inode(self.disk, i)
        if inode and inode.valid:
            # direct blocks
            for block in inode.direct:
                if 0 < block < self.superblock.blocks:
                    block_to_inode[block] = i
            # indirect block + its pointers
            if 0 < inode.indirect < self.superblock.blocks:
                block_to_inode[inode.indirect] = i
                indirect_data = self.disk.read(inode.indirect)
                if indirect_data:
                    pointers = struct.unpack('<' + 'I' * POINTERS_PER_BLOCK, indirect_data)
                    for ptr in pointers:
                        if 0 < ptr < self.superblock.blocks:
                            block_to_inode[ptr] = i

     return {
        'total_blocks': total_blocks,
        'used_blocks': used_blocks,
        'free_blocks': free_blocks_count,
        'superblock_blocks': superblock_blocks,
        'inode_blocks': inode_blocks,
        'data_blocks_used': data_blocks_used,
        'data_blocks_free': data_blocks_free,
        'block_to_inode': block_to_inode,   # ✅ include mapping
    }

    def _notify_visualizer(self):
        if self.visualizer and hasattr(self.visualizer, "queue"):
            self._build_free_block_map()
            vis_data = self.get_visualization_data()
            self.visualizer.queue.put(vis_data)

    def _build_free_block_map(self):
        self.free_blocks = [True] * self.superblock.blocks
        for i in range(self.superblock.inode_blocks + 1):
            if i < len(self.free_blocks):
                self.free_blocks[i] = False
        for i in range(self.superblock.inodes):
            inode = self._load_inode(self.disk, i)
            if inode and inode.valid:
                for block in inode.direct:
                    if 0 < block < self.superblock.blocks:
                        self.free_blocks[block] = False
                if 0 < inode.indirect < self.superblock.blocks:
                    self.free_blocks[inode.indirect] = False
                    indirect_data = self.disk.read(inode.indirect)
                    if indirect_data:
                        pointers = struct.unpack('<' + 'I' * POINTERS_PER_BLOCK, indirect_data)
                        for ptr in pointers:
                            if 0 < ptr < self.superblock.blocks:
                                self.free_blocks[ptr] = False

    def _allocate_inode(self) -> int:
        for i in range(self.superblock.inodes):
            inode = self._load_inode(self.disk, i)
            if inode and not inode.valid:
                return i
        return -1

    def _allocate_block(self) -> int:
        for i in range(self.superblock.inode_blocks + 1, self.superblock.blocks):
            if i < len(self.free_blocks) and self.free_blocks[i]:
                self.free_blocks[i] = False
                return i
        return -1

    def _free_block(self, block_num: int):
        if 0 <= block_num < len(self.free_blocks):
            self.free_blocks[block_num] = True

    def _load_inode(self, disk: DiskEmulator, inode_num: int) -> Optional[Inode]:
        if inode_num < 0 or inode_num >= self.superblock.inodes:
            return None
        block_num = 1 + (inode_num // INODES_PER_BLOCK)
        block_offset = (inode_num % INODES_PER_BLOCK) * INODE_SIZE
        data = disk.read(block_num)
        if not data:
            return None
        return Inode.unpack(data[block_offset:block_offset + INODE_SIZE])

    def _save_inode(self, disk: DiskEmulator, inode_num: int, inode: Inode) -> bool:
        if inode_num < 0 or inode_num >= self.superblock.inodes:
            return False
        block_num = 1 + (inode_num // INODES_PER_BLOCK)
        block_offset = (inode_num % INODES_PER_BLOCK) * INODE_SIZE
        block_data = bytearray(disk.read(block_num) or b'\x00' * BLOCK_SIZE)
        inode_data = inode.pack()
        block_data[block_offset:block_offset + INODE_SIZE] = inode_data
        return disk.write(block_num, bytes(block_data))

    def _get_block_pointer(self, inode: Inode, block_index: int) -> int:
        if block_index < POINTERS_PER_INODE:
            return inode.direct[block_index]
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
        if block_index < POINTERS_PER_INODE:
            inode.direct[block_index] = block_num
            return True
        if inode.indirect == 0:
            inode.indirect = self._allocate_block()
            if inode.indirect < 0:
                return False
            empty_pointers = struct.pack('<' + 'I' * POINTERS_PER_BLOCK, *([0] * POINTERS_PER_BLOCK))
            self.disk.write(inode.indirect, empty_pointers)
        indirect_data = bytearray(self.disk.read(inode.indirect))
        indirect_index = block_index - POINTERS_PER_INODE
        if indirect_index >= POINTERS_PER_BLOCK:
            return False
        struct.pack_into('<I', indirect_data, indirect_index * 4, block_num)
        return self.disk.write(inode.indirect, bytes(indirect_data))

    def _find_dir_entry(self, dir_inode_num: int, name: str) -> int:
        dir_inode = self._load_inode(self.disk, dir_inode_num)
        if not dir_inode or not dir_inode.valid or dir_inode.size == 0:
            return -1
        data = self.read(dir_inode_num, dir_inode.size)
        if not data:
            return -1
        entry_size = DirEntry.ENTRY_SIZE
        for i in range(0, len(data), entry_size):
            if i + entry_size > len(data):
                break
            entry = DirEntry.unpack(data[i:i+entry_size])
            if entry.name == name:
                return entry.inode_num
        return -1

    def _add_dir_entry(self, dir_inode_num: int, name: str, inode_num: int) -> bool:
        entry = DirEntry(name, inode_num)
        entry_data = entry.pack()
        dir_inode = self._load_inode(self.disk, dir_inode_num)
        if not dir_inode or not dir_inode.valid:
            return False
        bytes_written = self.write(dir_inode_num, entry_data, dir_inode.size)
        return bytes_written == len(entry_data)


class Shell:
    """Interactive shell for file system operations."""
    def __init__(self, fs: FileSystem):
        self.fs = fs
        self.running = True
        self.vis_queue = queue.Queue()
        self.disk: Optional[DiskEmulator] = None

    def run(self, disk_path: str, blocks: int):
        print("=" * 60)
        print("File System Simulator - Interactive Shell")
        print("=" * 60)

        self.disk = DiskEmulator(disk_path, blocks)
        if not self.disk.open():
            print("Failed to open disk")
            return

        # Attach one visualizer queue to both disk and fs (before any operations)
        vis_obj = types.SimpleNamespace(queue=self.vis_queue)
        self.disk.visualizer = vis_obj
        self.fs.visualizer = vis_obj

        print(f"Disk opened: {disk_path} ({blocks} blocks)")
        print("Type 'help' for available commands\n")

        while self.running:
            try:
                prompt = f"sfs:{self.fs.current_dir_inode}> " if self.fs.mounted else "sfs> "
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

        if self.fs.mounted:
            self.fs.unmount()
        self.disk.close()
        print("\nGoodbye!")

    def execute_command(self, command: str):
        parts = command.split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]
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
            'append': self.cmd_append,
            'cp': self.cmd_cp,
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
        print("  append <inode> <txt>- Append text to a file")
        print("  cp <src> <dst>      - Copy file (inode numbers)")
        print("  copyin <file> <ino> - Copy file from host to fs")
        print("  copyout <ino> <file>- Copy file from fs to host")
        print("  visualize           - Open Tkinter block allocation visualization")
        print("  exit, quit          - Exit the shell\n")

    def cmd_format(self, args):
        if not self.disk:
            print("Error: No disk loaded")
            return
        if self.fs.format(self.disk):
            print("File system formatted successfully")
        else:
            print("Failed to format file system")

    def cmd_mount(self, args):
        if not self.disk:
            print("Error: No disk loaded")
            return
        if self.fs.mount(self.disk):
            print("File system mounted successfully")
        else:
            print("Failed to mount file system")

    def cmd_unmount(self, args):
        self.fs.unmount()

    def cmd_debug(self, args):
        self.fs.debug()

    def cmd_create(self, args):
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
        if not args:
            print("Usage: cd <directory>")
            return
        if self.fs.cd(args[0]):
            print(f"Changed to directory '{args[0]}'")

    def cmd_rm(self, args):
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

    def cmd_append(self, args):
        if len(args) < 2:
            print("Usage: append <inode_number> <text>")
            return
        try:
            inode_num = int(args[0])
            text = ' '.join(args[1:])
            bytes_written = self.fs.append(inode_num, text.encode('utf-8'))
            if bytes_written >= 0:
                print(f"Appended {bytes_written} bytes to inode {inode_num}")
            else:
                print("Failed to append data")
        except ValueError:
            print("Error: Invalid inode number")

    def cmd_cp(self, args):
        if len(args) < 2:
            print("Usage: cp <src_inode> <dst_inode>")
            return
        try:
            src_inode = int(args[0])
            dst_inode = int(args[1])
            size = self.fs.stat(src_inode)
            if size < 0:
                print("Error: Invalid source inode")
                return
            data = self.fs.read(src_inode, size)
            if data is None:
                print("Error: Failed to read source")
                return
            bytes_written = self.fs.write(dst_inode, data)
            if bytes_written > 0:
                print(f"Copied {bytes_written} bytes from inode {src_inode} to {dst_inode}")
            else:
                print("Failed to copy")
        except ValueError:
            print("Error: Invalid inode number")

    def cmd_copyin(self, args):
        if len(args) < 2:
            print("Usage: copyin <host_file> <inode_number>")
            return
        host_file = args[0]
        try:
            inode_num = int(args[1])
            if not os.path.exists(host_file):
                print(f"Error: File '{host_file}' not found")
                return
            with open(host_file, 'rb') as f:
                data = f.read()
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
        if len(args) < 2:
            print("Usage: copyout <inode_number> <host_file>")
            return
        try:
            inode_num = int(args[0])
            host_file = args[1]
            size = self.fs.stat(inode_num)
            if size < 0:
                print("Error: Invalid inode")
                return
            data = self.fs.read(inode_num, size)
            if data is None:
                print("Error: Failed to read file")
                return
            with open(host_file, 'wb') as f:
                f.write(data)
            print(f"Copied {len(data)} bytes from inode {inode_num} to '{host_file}'")
        except ValueError:
            print("Error: Invalid inode number")
        except Exception as e:
            print(f"Error: {e}")

    def cmd_visualize(self, args):
        if not self.fs.mounted:
            print("Error: File system not mounted")
            return
        # Push current snapshot to queue so GUI starts populated
        self.fs._notify_visualizer()
        total_blocks = self.fs.superblock.blocks or (self.disk.blocks if self.disk else 0)
        visualizer = BlockVisualizer(total_blocks, self.vis_queue)
        visualizer.run()  # Tkinter mainloop (blocks until window closed)

    def cmd_exit(self, args):
        self.running = False


def main():
    if len(sys.argv) < 3:
        print("File System Simulator - Educational Tool")
        print("=" * 60)
        print("\nUsage: python fs-simulator.py <disk_image> <num_blocks>")
        print("\nExample:")
        print("  python fs-simulator.py disk.img 100")
        print("\nMinimum 10 blocks required.")
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
    fs = FileSystem(disk_path, blocks)
    shell = Shell(fs)
    shell.run(disk_path, blocks)


if __name__ == "__main__":
    main()