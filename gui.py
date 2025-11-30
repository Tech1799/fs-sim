"""Tkinter GUI for block allocation visualization."""

import threading
import time
from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import ttk
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    print("Warning: tkinter not available. GUI visualization will be disabled.")

if TYPE_CHECKING:
    from file_system import FileSystem


class BlockVisualizationGUI:
    """Tkinter GUI for real-time block allocation visualization."""
    
    def __init__(self, fs: 'FileSystem'):
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
    
    def __init__(self, fs: 'FileSystem'):
        self.fs = fs
        self.gui = None
        self.thread = None
        self.is_running = False
    
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