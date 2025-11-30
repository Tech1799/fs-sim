"""Main entry point for the file system simulator."""

import sys
from shell import Shell
from disk_emulator import DiskEmulator


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("File System Simulator with Live GUI Visualization")
        print("=" * 60)
        print("\nUsage: python main.py <disk_image> <num_blocks>")
        print("\nExample:")
        print("  python main.py disk.img 100")
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