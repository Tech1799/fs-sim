"""Data structures for the file system."""

import struct
from constants import (
    BLOCK_SIZE, MAGIC_NUMBER, POINTERS_PER_INODE,
    INODE_SIZE, MAX_FILENAME
)


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