"""Interactive shell for file system operations."""

import os
import sys
import struct
from datetime import datetime

from file_system import FileSystem
from disk_emulator import DiskEmulator
from structures import Inode
from constants import BLOCK_SIZE, POINTERS_PER_BLOCK

try:
    from gui import GUIManager, TKINTER_AVAILABLE
except ImportError:
    TKINTER_AVAILABLE = False
    print("Warning: GUI module not available")


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
            # GUI cleanup handled by window close
            pass
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
        print("  gui                 - Open live GUI visualization in window")
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