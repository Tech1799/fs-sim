import tkinter as tk
import queue

class BlockVisualizer:
    def __init__(self, total_blocks, vis_queue):
        self.total_blocks = total_blocks
        self.vis_queue = vis_queue
        self.block_info = {}  
        self.root = tk.Tk()
        self.root.title("Disk Block Allocation Visualizer")

        # Top stats
        top = tk.Frame(self.root)
        top.pack(fill=tk.X, padx=8, pady=6)
        self.stats_label = tk.Label(top, text="Blocks: 0 | Used: 0 | Free: 0 | Used %: 0.0%")
        self.stats_label.pack(anchor="w")

        # Legend
        legend = tk.Frame(self.root)
        legend.pack(fill=tk.X, padx=8)
        tk.Label(legend, text="Legend:").pack(side=tk.LEFT)
        for color, text in [("yellow", "Superblock"), ("green", "Inode"), ("red", "Data used"), ("white", "Free")]:
            box = tk.Canvas(legend, width=16, height=16)
            box.pack(side=tk.LEFT, padx=4)
            box.create_rectangle(0, 0, 16, 16, fill=color, outline="gray")
            tk.Label(legend, text=text).pack(side=tk.LEFT, padx=8)

        # Grid canvas
        self.side = int(self.total_blocks ** 0.5) + 1
        self.cell = 16
        self.canvas = tk.Canvas(self.root, width=self.side * self.cell, height=self.side * self.cell, bg="white")
        self.canvas.pack(padx=8, pady=8)

        # Pre-create rectangles
        self.rects = []
        for i in range(self.total_blocks):
            x = (i % self.side) * self.cell
            y = (i // self.side) * self.cell
            rect = self.canvas.create_rectangle(x, y, x + self.cell, y + self.cell, fill="white", outline="#ddd")
            self.rects.append(rect)

    def _apply_vis_data(self, vis_data):
     total = vis_data.get('total_blocks', self.total_blocks)
     used = vis_data.get('used_blocks', 0)
     free = vis_data.get('free_blocks', 0)
     used_pct = (used / total * 100) if total else 0.0
     self.stats_label.config(
        text=f"Blocks: {total} | Used: {used} | Free: {free} | Used %: {used_pct:.1f}%"
    )

    # Reset all to free
     for rect in self.rects:
        self.canvas.itemconfig(rect, fill="white")

    # ✅ Clear block info
     self.block_info.clear()

    # Color categories + tooltip info
     for b in vis_data.get('superblock_blocks', []):
        if 0 <= b < len(self.rects):
            self.canvas.itemconfig(self.rects[b], fill="yellow")
            self.block_info[b] = "Superblock"

     for b in vis_data.get('inode_blocks', []):
        if 0 <= b < len(self.rects):
            self.canvas.itemconfig(self.rects[b], fill="green")
            self.block_info[b] = "Inode"

     for b in vis_data.get('data_blocks_used', []):
        if 0 <= b < len(self.rects):
            self.canvas.itemconfig(self.rects[b], fill="red")
            # ✅ Enrich with inode ownership if available
            inode_owner = vis_data.get('block_to_inode', {}).get(b)
            if inode_owner is not None:
                self.block_info[b] = f"Used by inode {inode_owner}"
            else:
                self.block_info[b] = "Used Data"

     for b in vis_data.get('data_blocks_free', []):
        if 0 <= b < len(self.rects):
            self.canvas.itemconfig(self.rects[b], fill="white")
            self.block_info[b] = "Free"

    def _poll_queue(self):
        try:
            while True:
                vis_data = self.vis_queue.get_nowait()
                self._apply_vis_data(vis_data)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)

    def run(self):
        self._poll_queue()
        self.root.mainloop()