"""Global constants for the file system."""

# Block and size constants
BLOCK_SIZE = 4096  # 4KB blocks
MAGIC_NUMBER = 0xF0F03410
POINTERS_PER_INODE = 5  # Direct pointers
POINTERS_PER_BLOCK = 1024  # Pointers in indirect block
INODE_SIZE = 44  # Size of each inode in bytes
INODES_PER_BLOCK = BLOCK_SIZE // INODE_SIZE  # 93 inodes per block
MAX_FILENAME = 255