#!/usr/bin/env python3
"""
PDF Destinator - Interactive tool to add named destinations and links to PDFs.

This tool displays each page and lets you click on the location for each destination.
After completion, the PDF is saved with all named destinations and link annotations.

Destinations can be:
- Local: A position within the PDF (for internal navigation)
- External URL: A web link (for link annotations)

Usage:
  pdf-destinator document.pdf
  pdf-destinator document.pdf --titles "Chapter 1" "Chapter 2" "Chapter 3"
  pdf-destinator document.pdf --json destinations.json

Requirements:
  pip install pymupdf pillow pypdf

  On Linux also:
  sudo apt-get install python3-tk

Keyboard shortcuts:
  Left/Right  Navigate pages
  Up/Down     Navigate destinations
  Mouse wheel Scroll (changes pages at boundaries)

Mouse actions:
  Click       Set destination position
  Drag        Create link region
  Hover+Click Delete link region (cursor shows X)
"""

import sys
import json
import argparse
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Error: PyMuPDF not installed. Run: pip install pymupdf")
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog
except ImportError:
    print("Error: tkinter not available.")
    print("  Linux: sudo apt-get install python3-tk")
    print("  macOS: brew install python-tk")
    sys.exit(1)

try:
    from PIL import Image, ImageTk
except ImportError:
    print("Error: Pillow not installed. Run: pip install pillow")
    sys.exit(1)


def title_to_id(title):
    """Convert title to URL-friendly ID (lowercase, hyphens)."""
    import re
    # Normalize special characters
    id_str = title.lower()
    id_str = id_str.replace('–', '-').replace('—', '-').replace('…', '').replace('...', '')
    id_str = re.sub(r'[^a-z0-9\s-]', '', id_str)
    id_str = re.sub(r'\s+', '-', id_str)
    id_str = re.sub(r'-+', '-', id_str)
    return id_str.strip('-')


def load_destinations_from_json(json_path, pdf_name):
    """Load destinations from a JSON file for the given PDF."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Support both array format and object format
    if isinstance(data, list):
        # Array of PDF configs
        for entry in data:
            if entry.get('pdfFile') == pdf_name:
                # Support both 'destinations' and 'sections' keys
                return entry.get('destinations', entry.get('sections', []))
    elif isinstance(data, dict):
        # Single PDF config or keyed by filename
        if 'destinations' in data or 'sections' in data:
            return data.get('destinations', data.get('sections', []))
        elif pdf_name in data:
            entry = data[pdf_name]
            return entry.get('destinations', entry.get('sections', []))

    return None


class PDFDestinationPicker:
    def __init__(self, pdf_path, destinations=None):
        self.pdf_path = Path(pdf_path)
        self.sections = list(destinations) if destinations else []
        self.current_section_idx = 0
        self.destinations = {}  # Dict of section_id -> (page_num, x, y)
        self.existing_destinations = {}  # Destinations already in the PDF
        self.custom_sections = []  # List of custom sections added by user

        self.doc = fitz.open(str(self.pdf_path))
        self.current_page = 0
        self.zoom = 1.0

        # For link annotation drawing
        self.link_annotations = []  # List of {page, rect, dest_id, type}
        self.original_link_count = 0  # Track how many links were loaded initially
        self.drag_start = None
        self.drag_rect = None

        # Load existing named destinations from PDF
        self.load_existing_destinations()
        self.load_existing_links()

        self.setup_ui()

    def load_existing_destinations(self):
        """Load named destinations already present in the PDF."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(self.pdf_path))

            # Build a map of page indirect references to page indices
            page_ref_to_idx = {}
            for i, page in enumerate(reader.pages):
                if page.indirect_reference:
                    page_ref_to_idx[page.indirect_reference.idnum] = i

            # Method 1: Try pypdf's named_destinations (reads from /Names tree)
            named_dests = reader.named_destinations

            if named_dests:
                print(f"Existing destinations found in PDF (Names tree):")
                for name, dest in named_dests.items():
                    self._process_destination(name, dest, reader, page_ref_to_idx)

            # Method 2: Also check /Dests in catalog (our custom format)
            if hasattr(reader, '_root_object') and '/Dests' in reader._root_object:
                dests_obj = reader._root_object['/Dests']
                if hasattr(dests_obj, 'get_object'):
                    dests_obj = dests_obj.get_object()
                print(f"Existing destinations found in PDF (Dests catalog):")
                for name, dest_array in dests_obj.items():
                    clean_name = str(name).lstrip('/')
                    if clean_name in self.existing_destinations:
                        continue  # Already loaded from Names tree

                    if hasattr(dest_array, 'get_object'):
                        dest_array = dest_array.get_object()

                    # Parse the destination array [page_ref, /XYZ, left, top, zoom]
                    if isinstance(dest_array, list) and len(dest_array) >= 2:
                        page_ref = dest_array[0]

                        # Find page index using idnum
                        page_idx = None
                        if hasattr(page_ref, 'idnum'):
                            page_idx = page_ref_to_idx.get(page_ref.idnum)
                        elif hasattr(page_ref, 'get_object'):
                            resolved = page_ref.get_object()
                            for i, page in enumerate(reader.pages):
                                if page.get_object() == resolved:
                                    page_idx = i
                                    break

                        if page_idx is not None:
                            x, y = 0, 0
                            page_height = self.doc[page_idx].rect.height

                            if len(dest_array) >= 4 and str(dest_array[1]) == '/XYZ':
                                try:
                                    x = float(dest_array[2]) if dest_array[2] else 0
                                    pdf_y = float(dest_array[3]) if dest_array[3] else 0
                                    y = page_height - pdf_y
                                except (ValueError, TypeError):
                                    pass

                            self.existing_destinations[clean_name] = (page_idx, x, y)
                            print(f"  * {clean_name} -> page {page_idx + 1}, position ({x:.0f}, {y:.0f})")
                        else:
                            print(f"  ! {clean_name} -> could not determine page")

            # Pre-populate destinations dict with existing ones that match our sections
            matched_count = 0
            section_ids = {s.get('id', title_to_id(s.get('title', ''))) for s in self.sections}

            for section in self.sections:
                section_id = section.get('id', title_to_id(section.get('title', '')))
                if section_id in self.existing_destinations:
                    self.destinations[section_id] = self.existing_destinations[section_id]
                    matched_count += 1

            # Add unmatched destinations from PDF as custom sections
            custom_count = 0
            for dest_id, dest_data in self.existing_destinations.items():
                if dest_id not in section_ids:
                    # Skip common bookmark patterns from publishing software
                    if ':' in dest_id and any(x in dest_id.lower() for x in ['bladwijzer', 'bookmark', 'toc']):
                        continue
                    # Add as custom section
                    custom_section = {
                        "id": dest_id,
                        "title": dest_id.replace('-', ' ').title(),
                        "custom": True,
                        "type": "local"
                    }
                    self.sections.append(custom_section)
                    self.destinations[dest_id] = dest_data
                    custom_count += 1

            if self.existing_destinations:
                print(f"\n{len(self.existing_destinations)} existing destinations loaded.")
                print(f"{matched_count} matched to config, {custom_count} loaded as custom.")
            else:
                print("No existing destinations found.\n")

        except Exception as e:
            import traceback
            print(f"Could not load existing destinations: {e}")
            traceback.print_exc()

    def _process_destination(self, name, dest, reader, page_ref_to_idx):
        """Process a single destination from pypdf."""
        clean_name = str(name).lstrip('/')

        page_idx = None

        if hasattr(dest, 'page') and dest.page is not None:
            if hasattr(dest.page, 'idnum'):
                page_idx = page_ref_to_idx.get(dest.page.idnum)
            if page_idx is None:
                for i, page in enumerate(reader.pages):
                    if page.indirect_reference == dest.page:
                        page_idx = i
                        break

        if page_idx is None and '/Page' in dest:
            page_ref = dest['/Page']
            if hasattr(page_ref, 'idnum'):
                page_idx = page_ref_to_idx.get(page_ref.idnum)
            if page_idx is None:
                for i, page in enumerate(reader.pages):
                    if page.indirect_reference == page_ref:
                        page_idx = i
                        break

        if page_idx is None:
            print(f"  ! {clean_name} -> could not determine page")
            return

        page_height = self.doc[page_idx].rect.height

        x, y = 0, 0
        if hasattr(dest, 'left') and dest.left is not None:
            x = float(dest.left)
        if hasattr(dest, 'top') and dest.top is not None:
            pdf_y = float(dest.top)
            y = page_height - pdf_y

        self.existing_destinations[clean_name] = (page_idx, x, y)
        print(f"  * {clean_name} -> page {page_idx + 1}, position ({x:.0f}, {y:.0f})")

    def load_existing_links(self):
        """Load existing link annotations from the PDF."""
        try:
            for page_num in range(len(self.doc)):
                page = self.doc[page_num]
                links = page.get_links()

                for link in links:
                    link_type = link.get("kind")
                    rect = link.get("from")

                    if rect is None:
                        continue

                    if link_type == fitz.LINK_NAMED:
                        dest_name = link.get("nameddest", link.get("name", "")).lstrip("/")
                        if dest_name:
                            self.link_annotations.append({
                                "page": page_num,
                                "rect": (rect.x0, rect.y0, rect.x1, rect.y1),
                                "dest_id": dest_name,
                                "type": "local",
                                "existing": True
                            })
                    elif link_type == fitz.LINK_URI:
                        uri = link.get("uri", "")
                        if uri:
                            self.link_annotations.append({
                                "page": page_num,
                                "rect": (rect.x0, rect.y0, rect.x1, rect.y1),
                                "dest_id": uri,
                                "type": "url",
                                "existing": True
                            })
                            # Add as custom URL section if not already present
                            if not any(s.get('id') == uri for s in self.sections):
                                self.sections.append({
                                    "id": uri,
                                    "title": uri,
                                    "custom": True,
                                    "type": "url"
                                })
                    elif link_type == fitz.LINK_GOTO:
                        dest_page = link.get("page", 0)
                        dest_name = link.get("nameddest", link.get("name", ""))
                        dest_name = dest_name.lstrip("/") if dest_name else None
                        dest_to = link.get("to")

                        if dest_name:
                            self.link_annotations.append({
                                "page": page_num,
                                "rect": (rect.x0, rect.y0, rect.x1, rect.y1),
                                "dest_id": dest_name,
                                "type": "local",
                                "existing": True
                            })
                        elif dest_to:
                            matched_dest = self._find_destination_by_position(dest_page, dest_to.x, dest_to.y)
                            if matched_dest:
                                self.link_annotations.append({
                                    "page": page_num,
                                    "rect": (rect.x0, rect.y0, rect.x1, rect.y1),
                                    "dest_id": matched_dest,
                                    "type": "local",
                                    "existing": True
                                })
                            else:
                                self.link_annotations.append({
                                    "page": page_num,
                                    "rect": (rect.x0, rect.y0, rect.x1, rect.y1),
                                    "dest_id": f"page-{dest_page + 1}",
                                    "type": "page",
                                    "existing": True
                                })
                        else:
                            self.link_annotations.append({
                                "page": page_num,
                                "rect": (rect.x0, rect.y0, rect.x1, rect.y1),
                                "dest_id": f"page-{dest_page + 1}",
                                "type": "page",
                                "existing": True
                            })

            if self.link_annotations:
                self.original_link_count = len(self.link_annotations)
                print(f"{len(self.link_annotations)} existing link annotations loaded.\n")
        except Exception as e:
            import traceback
            print(f"Could not load existing links: {e}")
            traceback.print_exc()

    def _find_destination_by_position(self, page_num, x, y, tolerance=5):
        """Find a destination that matches the given page and position."""
        for dest_id, (dest_page, dest_x, dest_y) in self.existing_destinations.items():
            if dest_page == page_num:
                if abs(dest_x - x) < tolerance and abs(dest_y - y) < tolerance:
                    return dest_id
        return None

    def setup_ui(self):
        self.root = tk.Tk()
        self.root.title(f"PDF Destinator - {self.pdf_path.name}")

        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        # Top frame with section info and list
        top_frame = ttk.Frame(main_frame)
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        top_frame.columnconfigure(0, weight=2)
        top_frame.columnconfigure(1, weight=3)
        top_frame.rowconfigure(0, weight=1)

        # Info frame (left side)
        info_frame = ttk.LabelFrame(top_frame, text="Current destination", padding="10")
        info_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self.section_var = tk.StringVar()
        self.section_label = ttk.Label(info_frame, textvariable=self.section_var, font=("Arial", 12, "bold"), wraplength=320)
        self.section_label.pack(anchor="w")

        self.section_id_label = ttk.Label(info_frame, text="", foreground="gray")
        self.section_id_label.pack(anchor="w")

        self.progress_label = ttk.Label(info_frame, text="")
        self.progress_label.pack()

        self.instruction_label = ttk.Label(info_frame, text="Click on the position for this destination", foreground="blue")
        self.instruction_label.pack()

        # Destination list (right side)
        list_frame = ttk.LabelFrame(top_frame, text="Destinations", padding="5")
        list_frame.grid(row=0, column=1, sticky="nsew")

        list_scroll = ttk.Scrollbar(list_frame, orient="vertical")
        self.section_listbox = tk.Listbox(list_frame, width=50, height=8, yscrollcommand=list_scroll.set, font=("Arial", 10))
        list_scroll.config(command=self.section_listbox.yview)

        self.section_listbox.pack(side="left", fill="both")
        list_scroll.pack(side="right", fill="y")

        self.section_listbox.bind("<<ListboxSelect>>", self.on_section_select)

        # Add/remove destination buttons
        button_frame = ttk.Frame(list_frame)
        button_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(button_frame, text="+ New destination", command=self.add_custom_destination).pack(fill="x")
        ttk.Button(button_frame, text="- Remove destination", command=self.remove_destination).pack(fill="x", pady=(2, 0))

        # Canvas frame with scrollbars
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")

        self.v_scroll = ttk.Scrollbar(canvas_frame, orient="vertical")
        self.h_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal")

        self.canvas = tk.Canvas(
            canvas_frame,
            width=800,
            height=600,
            yscrollcommand=self.v_scroll.set,
            xscrollcommand=self.h_scroll.set
        )

        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)

        self.v_scroll.pack(side="right", fill="y")
        self.h_scroll.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        # Mouse bindings
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        # Mouse motion for hover effects (link deletion)
        self.canvas.bind("<Motion>", self.on_mouse_motion)
        self.hovered_link_index = None

        # Mouse wheel scrolling
        self.canvas.bind("<Button-4>", self.on_scroll_up)
        self.canvas.bind("<Button-5>", self.on_scroll_down)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)

        # Keyboard bindings
        self.root.bind("<Left>", self.on_key_left)
        self.root.bind("<Right>", self.on_key_right)
        self.root.bind("<Up>", self.on_key_up)
        self.root.bind("<Down>", self.on_key_down)

        self.canvas.focus_set()

        # Navigation frame
        nav_frame = ttk.Frame(main_frame)
        nav_frame.grid(row=2, column=0, columnspan=2, pady=10)

        ttk.Button(nav_frame, text="< Page", command=self.prev_page).pack(side="left", padx=5)
        self.page_label = ttk.Label(nav_frame, text="Page 1 / 1")
        self.page_label.pack(side="left", padx=20)
        ttk.Button(nav_frame, text="Page >", command=self.next_page).pack(side="left", padx=5)

        ttk.Separator(nav_frame, orient="vertical").pack(side="left", padx=20, fill="y")

        ttk.Button(nav_frame, text="Zoom -", command=self.zoom_out).pack(side="left", padx=5)
        self.zoom_label = ttk.Label(nav_frame, text="100%")
        self.zoom_label.pack(side="left", padx=5)
        ttk.Button(nav_frame, text="Zoom +", command=self.zoom_in).pack(side="left", padx=5)

        # Action frame
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=3, column=0, columnspan=2, pady=10)

        ttk.Button(action_frame, text="< Previous", command=self.prev_section).pack(side="left", padx=5)
        ttk.Button(action_frame, text="Next >", command=self.next_section).pack(side="left", padx=5)

        ttk.Separator(action_frame, orient="vertical").pack(side="left", padx=10, fill="y")

        ttk.Button(action_frame, text="X Remove position", command=self.remove_current_destination).pack(side="left", padx=5)

        ttk.Separator(action_frame, orient="vertical").pack(side="left", padx=10, fill="y")

        ttk.Button(action_frame, text="Save and quit", command=self.save_and_quit).pack(side="left", padx=10)
        ttk.Button(action_frame, text="Cancel", command=self.cancel).pack(side="left", padx=5)

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        self.update_section_list()
        self.update_display()

    def on_section_select(self, event):
        """Handle selection in section listbox."""
        selection = self.section_listbox.curselection()
        if selection:
            new_idx = selection[0]
            if new_idx != self.current_section_idx:
                self.current_section_idx = new_idx
                self._navigate_to_current_destination()
                self.update_display()
            self.canvas.focus_set()

    def add_custom_destination(self):
        """Add a custom destination - either local (text) or external (URL)."""
        import re

        text = simpledialog.askstring(
            "New destination",
            "Enter title (for local destination) or URL (for external link):",
            parent=self.root
        )
        if text:
            text = text.strip()
            url_pattern = re.compile(r'^https?://', re.IGNORECASE)
            if url_pattern.match(text):
                dest_id = text
                new_dest = {"id": dest_id, "title": text, "custom": True, "type": "url"}
                self.sections.append(new_dest)
                self.custom_sections.append(new_dest)
                self.update_section_list()
                self.current_section_idx = len(self.sections) - 1
                self.update_display()
                print(f"+ External URL added: {text}")
            else:
                dest_id = title_to_id(text)
                new_dest = {"id": dest_id, "title": text, "custom": True, "type": "local"}
                self.sections.append(new_dest)
                self.custom_sections.append(new_dest)
                self.update_section_list()
                self.current_section_idx = len(self.sections) - 1
                self.update_display()
                print(f"+ Local destination added: {text} (id: {dest_id})")

    def remove_destination(self):
        """Remove the current destination from the list."""
        if self.current_section_idx >= len(self.sections):
            return

        section = self.sections[self.current_section_idx]
        section_id = section.get('id', title_to_id(section.get('title', '')))
        title = section.get('title', section_id)

        link_count = sum(1 for l in self.link_annotations if l['dest_id'] == section_id)

        msg = f"Are you sure you want to remove this destination?\n\n{title}"
        if link_count > 0:
            msg += f"\n\nThis will also remove {link_count} link region(s) pointing to it."
        if not messagebox.askyesno("Remove destination", msg):
            return

        self.sections.pop(self.current_section_idx)

        if section in self.custom_sections:
            self.custom_sections.remove(section)

        if section_id in self.destinations:
            del self.destinations[section_id]
        if section_id in self.existing_destinations:
            del self.existing_destinations[section_id]

        self.link_annotations = [l for l in self.link_annotations if l['dest_id'] != section_id]

        if self.current_section_idx >= len(self.sections) and len(self.sections) > 0:
            self.current_section_idx = len(self.sections) - 1

        print(f"- Destination removed: {title}" + (f" (and {link_count} link regions)" if link_count > 0 else ""))
        self.update_section_list()
        self.update_display()

    def update_section_list(self):
        """Update the destination listbox with status markers."""
        self.section_listbox.delete(0, tk.END)
        for i, section in enumerate(self.sections):
            section_id = section.get('id', title_to_id(section.get('title', '')))
            title = section.get('title', section_id)
            is_url = section.get('type') == 'url'

            if is_url:
                prefix = "[URL] "
            elif section_id in self.destinations:
                prefix = "[x] "
            elif section_id in self.existing_destinations:
                prefix = "[o] "
            else:
                prefix = "[ ] "

            # Only show (custom) for interactively added destinations, not PDF-loaded ones
            if section in self.custom_sections and not is_url:
                suffix = " (custom)"
            else:
                suffix = ""

            display_title = title[:40] + "..." if len(title) > 40 else title
            self.section_listbox.insert(tk.END, f"{prefix}{display_title}{suffix}")

        if self.current_section_idx < len(self.sections):
            self.section_listbox.selection_clear(0, tk.END)
            self.section_listbox.selection_set(self.current_section_idx)
            self.section_listbox.see(self.current_section_idx)

    def render_page(self):
        """Render the current page to an image."""
        page = self.doc[self.current_page]
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img, pix.width, pix.height

    def update_display(self):
        """Update the UI with current status."""
        if self.current_section_idx < len(self.sections):
            section = self.sections[self.current_section_idx]
            title = section.get('title', section.get('id', '?'))
            section_id = section.get('id', title_to_id(title))

            self.section_var.set(title)
            self.section_id_label.config(text=f"ID: {section_id}")

            local_dests = [s for s in self.sections if s.get('type') != 'url']
            completed = sum(1 for s in local_dests if s.get('id', title_to_id(s.get('title', ''))) in self.destinations)
            self.progress_label.config(text=f"Destination {self.current_section_idx + 1} of {len(self.sections)} ({completed} positioned)")

            is_url = section.get('type') == 'url'

            if is_url:
                self.instruction_label.config(
                    text="[URL] External URL - drag a rectangle to create a clickable link region",
                    foreground="purple"
                )
            elif section_id in self.destinations:
                page_num, x, y = self.destinations[section_id]
                if section_id in self.existing_destinations and self.destinations[section_id] == self.existing_destinations[section_id]:
                    self.instruction_label.config(
                        text=f"[o] Existing on page {page_num + 1} - click to change, drag to add link",
                        foreground="orange"
                    )
                else:
                    self.instruction_label.config(
                        text=f"[x] Position on page {page_num + 1} - drag to add a link region",
                        foreground="green"
                    )
            elif section_id in self.existing_destinations:
                page_num, x, y = self.existing_destinations[section_id]
                self.instruction_label.config(
                    text=f"[o] Existing on page {page_num + 1} - click to change, drag to add link",
                    foreground="orange"
                )
            else:
                self.instruction_label.config(
                    text="Click to set position, or drag to create a link region",
                    foreground="blue"
                )
        else:
            self.section_var.set("No destinations")
            self.section_id_label.config(text="")
            self.progress_label.config(text="")
            self.instruction_label.config(text="Add destinations or click 'Save'", foreground="gray")

        self.update_section_list()

        self.page_label.config(text=f"Page {self.current_page + 1} / {len(self.doc)}")
        self.zoom_label.config(text=f"{int(self.zoom * 100)}%")

        img, width, height = self.render_page()
        self.tk_img = ImageTk.PhotoImage(img)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)
        self.canvas.config(scrollregion=(0, 0, width, height))

        current_section = self.sections[self.current_section_idx] if self.current_section_idx < len(self.sections) else None
        current_id = current_section.get('id', title_to_id(current_section.get('title', ''))) if current_section else None

        # Draw markers for destinations on this page
        for section_id, (page_num, x, y) in self.destinations.items():
            if page_num == self.current_page:
                canvas_x = x * self.zoom
                canvas_y = y * self.zoom

                if section_id == current_id:
                    color = "blue"
                    width_val = 4
                else:
                    color = "green"
                    width_val = 2

                self.canvas.create_oval(
                    canvas_x - 10, canvas_y - 10,
                    canvas_x + 10, canvas_y + 10,
                    outline=color, width=width_val
                )

                display_id = section_id[:25] + "..." if len(section_id) > 25 else section_id
                self.canvas.create_text(
                    canvas_x + 15, canvas_y,
                    text=display_id,
                    anchor="w",
                    fill=color,
                    font=("Arial", 9)
                )

        # Draw link annotation rectangles on this page
        for link in self.link_annotations:
            if link["page"] == self.current_page:
                x0, y0, x1, y1 = link["rect"]
                cx0, cy0 = x0 * self.zoom, y0 * self.zoom
                cx1, cy1 = x1 * self.zoom, y1 * self.zoom

                is_current = link["dest_id"] == current_id
                if link["type"] == "url":
                    color = "purple" if is_current else "violet"
                else:
                    color = "blue" if is_current else "cyan"

                width_val = 3 if is_current else 2
                dash = () if link.get("existing") else (4, 2)

                self.canvas.create_rectangle(
                    cx0, cy0, cx1, cy1,
                    outline=color, width=width_val, dash=dash
                )

                label = "[URL]" if link["type"] == "url" else "->"
                self.canvas.create_text(
                    cx0 + 5, cy0 + 5,
                    text=label,
                    anchor="nw",
                    fill=color,
                    font=("Arial", 10)
                )

    def on_mouse_down(self, event):
        """Handle mouse button down - start of click or drag."""
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

        # Check if clicking on a link region to delete it
        if self.hovered_link_index is not None:
            if self.delete_link_at_position(canvas_x, canvas_y):
                self.update_display()
                return

        self.drag_start = (canvas_x, canvas_y)
        self.drag_rect = None

    def on_mouse_drag(self, event):
        """Handle mouse drag - drawing link region."""
        if self.drag_start is None:
            return

        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

        if self.drag_rect:
            self.canvas.delete(self.drag_rect)

        x0, y0 = self.drag_start
        self.drag_rect = self.canvas.create_rectangle(
            x0, y0, canvas_x, canvas_y,
            outline="red", width=2, dash=(4, 4)
        )

    def on_mouse_up(self, event):
        """Handle mouse button up - end of click or drag."""
        if self.drag_start is None:
            return

        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        x0, y0 = self.drag_start

        drag_distance = ((canvas_x - x0) ** 2 + (canvas_y - y0) ** 2) ** 0.5

        if self.drag_rect:
            self.canvas.delete(self.drag_rect)
            self.drag_rect = None

        if self.current_section_idx >= len(self.sections):
            self.drag_start = None
            return

        section = self.sections[self.current_section_idx]
        section_id = section.get('id', title_to_id(section.get('title', '')))
        is_url = section.get('type') == 'url'

        if drag_distance < 10:
            if is_url:
                self.drag_start = None
                return

            pdf_x = x0 / self.zoom
            pdf_y = y0 / self.zoom

            was_new = section_id not in self.destinations
            self.destinations[section_id] = (self.current_page, pdf_x, pdf_y)

            action = "[+]" if was_new else "[~]"
            print(f"{action} {section_id}: page {self.current_page + 1}, position ({pdf_x:.0f}, {pdf_y:.0f})")
        else:
            pdf_x0 = min(x0, canvas_x) / self.zoom
            pdf_y0 = min(y0, canvas_y) / self.zoom
            pdf_x1 = max(x0, canvas_x) / self.zoom
            pdf_y1 = max(y0, canvas_y) / self.zoom

            link_type = "url" if is_url else "local"
            self.link_annotations.append({
                "page": self.current_page,
                "rect": (pdf_x0, pdf_y0, pdf_x1, pdf_y1),
                "dest_id": section_id,
                "type": link_type,
                "existing": False
            })

            print(f"[LINK] Link region created: {section_id} on page {self.current_page + 1}")

        self.drag_start = None
        self.update_display()

    def on_mouse_motion(self, event):
        """Handle mouse motion for hover effects on link regions."""
        if self.drag_start is not None:
            return

        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

        hovered_idx = None
        for i, link in enumerate(self.link_annotations):
            if link["page"] != self.current_page:
                continue

            x0, y0, x1, y1 = link["rect"]
            cx0, cy0 = x0 * self.zoom, y0 * self.zoom
            cx1, cy1 = x1 * self.zoom, y1 * self.zoom

            if cx0 <= canvas_x <= cx1 and cy0 <= canvas_y <= cy1:
                hovered_idx = i
                break

        if hovered_idx != self.hovered_link_index:
            self.hovered_link_index = hovered_idx
            if hovered_idx is not None:
                self.canvas.config(cursor="X_cursor")
            else:
                self.canvas.config(cursor="")

    def delete_link_at_position(self, canvas_x, canvas_y):
        """Delete link region at the given canvas position."""
        for i, link in enumerate(self.link_annotations):
            if link["page"] != self.current_page:
                continue

            x0, y0, x1, y1 = link["rect"]
            cx0, cy0 = x0 * self.zoom, y0 * self.zoom
            cx1, cy1 = x1 * self.zoom, y1 * self.zoom

            if cx0 <= canvas_x <= cx1 and cy0 <= canvas_y <= cy1:
                del self.link_annotations[i]
                print(f"[-] Link region deleted: {link['dest_id'][:40]}...")
                self.hovered_link_index = None
                self.canvas.config(cursor="")
                return True
        return False

    def on_key_left(self, event):
        self.prev_page()
        return "break"

    def on_key_right(self, event):
        self.next_page()
        return "break"

    def on_key_up(self, event):
        self.prev_section()
        return "break"

    def on_key_down(self, event):
        self.next_section()
        return "break"

    def on_scroll_up(self, event):
        self._do_scroll(-3)
        return "break"

    def on_scroll_down(self, event):
        self._do_scroll(3)
        return "break"

    def on_mouse_wheel(self, event):
        if event.delta > 0:
            self._do_scroll(-3)
        else:
            self._do_scroll(3)
        return "break"

    def _do_scroll(self, units):
        """Scroll the canvas, changing pages at boundaries."""
        top, bottom = self.canvas.yview()

        if units < 0:
            if top <= 0.0 and self.current_page > 0:
                self.current_page -= 1
                self.update_display()
                self.canvas.yview_moveto(1.0)
            else:
                self.canvas.yview_scroll(units, "units")
        else:
            if bottom >= 1.0 and self.current_page < len(self.doc) - 1:
                self.current_page += 1
                self.update_display()
                self.canvas.yview_moveto(0.0)
            else:
                self.canvas.yview_scroll(units, "units")

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_display()

    def next_page(self):
        if self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self.update_display()

    def zoom_in(self):
        self.zoom = min(3.0, self.zoom + 0.25)
        self.update_display()

    def zoom_out(self):
        self.zoom = max(0.5, self.zoom - 0.25)
        self.update_display()

    def prev_section(self):
        if self.current_section_idx > 0:
            self.current_section_idx -= 1
            self._navigate_to_current_destination()
            self.update_display()

    def next_section(self):
        if self.current_section_idx < len(self.sections) - 1:
            self.current_section_idx += 1
            self._navigate_to_current_destination()
            self.update_display()

    def _navigate_to_current_destination(self):
        """Navigate to the page of the current section's destination (if any)."""
        if self.current_section_idx < len(self.sections):
            section = self.sections[self.current_section_idx]
            section_id = section.get('id', title_to_id(section.get('title', '')))
            if section_id in self.destinations:
                page_num, x, y = self.destinations[section_id]
                self.current_page = page_num
            elif section_id in self.existing_destinations:
                page_num, x, y = self.existing_destinations[section_id]
                self.current_page = page_num

    def remove_current_destination(self):
        """Remove the position for the current destination."""
        if self.current_section_idx < len(self.sections):
            section = self.sections[self.current_section_idx]
            section_id = section.get('id', title_to_id(section.get('title', '')))
            removed = False
            if section_id in self.destinations:
                del self.destinations[section_id]
                removed = True
            if section_id in self.existing_destinations:
                del self.existing_destinations[section_id]
                removed = True
            if removed:
                print(f"[-] Position removed: {section_id}")
                self.update_section_list()
                self.update_display()
            else:
                messagebox.showinfo("No position", "This destination has no position set yet.")

    def save_and_quit(self):
        """Save the PDF with named destinations and link annotations."""
        # Merge existing destinations with new ones
        all_destinations = dict(self.existing_destinations)
        all_destinations.update(self.destinations)

        # Filter out URL destinations
        url_ids = {s.get('id') for s in self.sections if s.get('type') == 'url'}
        all_destinations = {k: v for k, v in all_destinations.items() if k not in url_ids}

        # Count link changes
        new_links = [l for l in self.link_annotations if not l.get("existing")]
        kept_existing_links = [l for l in self.link_annotations if l.get("existing")]
        removed_existing_links = self.original_link_count - len(kept_existing_links)
        has_link_changes = new_links or removed_existing_links > 0

        if not all_destinations and not has_link_changes:
            if messagebox.askyesno("No changes", "No destinations or links have been added. Exit anyway?"):
                self.doc.close()
                self.root.quit()
            return

        page_heights = [self.doc[i].rect.height for i in range(len(self.doc))]

        self.doc.close()

        try:
            from pypdf import PdfReader, PdfWriter
            from pypdf.generic import (
                ArrayObject, NameObject, NullObject, FloatObject,
                DictionaryObject
            )
        except ImportError:
            messagebox.showerror("Error", "pypdf not installed. Run: pip install pypdf")
            return

        new_dest_count = len([d for d in self.destinations if d not in url_ids])
        preserved_count = len(all_destinations) - new_dest_count
        print(f"\nStep 1: Adding {len(all_destinations)} destinations ({new_dest_count} new/modified, {preserved_count} preserved)...")

        reader = PdfReader(str(self.pdf_path))
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        if reader.metadata:
            writer.add_metadata(reader.metadata)

        dests_dict = DictionaryObject()

        for section_id, (page_num, x, y) in all_destinations.items():
            page_height = page_heights[page_num] if page_num < len(page_heights) else 800
            pdf_y = page_height - y

            page_ref = writer.pages[page_num].indirect_reference
            dest_array = ArrayObject([
                page_ref,
                NameObject("/XYZ"),
                FloatObject(float(x)),
                FloatObject(float(pdf_y)),
                NullObject()
            ])

            dests_dict[NameObject("/" + section_id)] = dest_array

            marker = "[+]" if section_id in self.destinations else "[o]"
            print(f"  {marker} {section_id} -> page {page_num + 1}, position ({x:.0f}, {y:.0f})")

        if dests_dict:
            writer._root_object[NameObject("/Dests")] = writer._add_object(dests_dict)

        temp_path = self.pdf_path.with_suffix('.tmp.pdf')
        with open(temp_path, 'wb') as f:
            writer.write(f)
        print(f"  Destinations saved to temp file")

        # Step 2: Handle link annotations
        if has_link_changes:
            print(f"\nStep 2: Updating link annotations...")
            if removed_existing_links > 0:
                print(f"  Removing {removed_existing_links} deleted link(s)")
            if new_links:
                print(f"  Adding {len(new_links)} new link(s)")
            if kept_existing_links:
                print(f"  Preserving {len(kept_existing_links)} existing link(s)")

            doc = fitz.open(str(temp_path))

            # Delete ALL existing links first
            for page_num in range(len(doc)):
                page = doc[page_num]
                links = page.get_links()
                for link in links:
                    page.delete_link(link)

            # Re-add all links we want to keep
            for link in self.link_annotations:
                page = doc[link["page"]]
                x0, y0, x1, y1 = link["rect"]
                rect = fitz.Rect(x0, y0, x1, y1)

                if link["type"] == "url":
                    page.insert_link({
                        "kind": fitz.LINK_URI,
                        "from": rect,
                        "uri": link["dest_id"]
                    })
                    marker = "[o]" if link.get("existing") else "[+]"
                    print(f"  {marker} [URL]: {link['dest_id'][:50]}...")
                else:
                    page.insert_link({
                        "kind": fitz.LINK_NAMED,
                        "from": rect,
                        "name": link["dest_id"]
                    })
                    marker = "[o]" if link.get("existing") else "[+]"
                    print(f"  {marker} -> {link['dest_id']}")

            final_path = self.pdf_path.with_suffix('.final.pdf')
            doc.save(str(final_path), garbage=4, deflate=True)
            doc.close()

            temp_path.unlink()
            final_path.replace(self.pdf_path)
        else:
            temp_path.replace(self.pdf_path)

        print(f"\n[OK] PDF saved: {self.pdf_path.name}")
        msg = f"Saved to {self.pdf_path.name}:\n"
        msg += f"- {len(all_destinations)} destinations ({new_dest_count} new, {preserved_count} preserved)\n"
        msg += f"- {len(self.link_annotations)} link annotations"
        if new_links or removed_existing_links > 0:
            msg += f" ({len(new_links)} added"
            if removed_existing_links > 0:
                msg += f", {removed_existing_links} removed"
            msg += ")"
        messagebox.showinfo("Saved", msg)

        self.root.quit()

    def cancel(self):
        """Cancel without saving."""
        if messagebox.askyesno("Cancel", "Are you sure you want to cancel? Changes will not be saved."):
            self.doc.close()
            self.root.quit()

    def run(self):
        self.root.mainloop()


def diagnose_pdf(pdf_path):
    """Diagnose what's in a PDF - show all destinations and links."""
    print(f"\n{'='*60}")
    print(f"DIAGNOSING: {pdf_path.name}")
    print('='*60)

    print("\n--- PyMuPDF Analysis ---")
    doc = fitz.open(str(pdf_path))
    print(f"Pages: {len(doc)}")

    total_links = 0
    for page_num in range(len(doc)):
        page = doc[page_num]
        links = page.get_links()
        if links:
            print(f"\nPage {page_num + 1}: {len(links)} links")
            for i, link in enumerate(links):
                total_links += 1
                kind = link.get("kind")
                rect = link.get("from")
                kind_names = {
                    0: "LINK_NONE",
                    1: "LINK_GOTO",
                    2: "LINK_URI",
                    3: "LINK_LAUNCH",
                    4: "LINK_NAMED",
                    5: "LINK_GOTOR"
                }
                kind_name = kind_names.get(kind, f"UNKNOWN({kind})")
                print(f"  [{i+1}] {kind_name}")
                print(f"      rect: ({rect.x0:.1f}, {rect.y0:.1f}) - ({rect.x1:.1f}, {rect.y1:.1f})")
                for key, value in link.items():
                    if key not in ['kind', 'from', 'xref']:
                        print(f"      {key}: {value}")

    print(f"\nTotal links (PyMuPDF): {total_links}")
    doc.close()

    print("\n--- pypdf Analysis ---")
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))

    named_dests = reader.named_destinations
    if named_dests:
        print(f"\nNamed destinations (/Names tree): {len(named_dests)}")
        for name, dest in named_dests.items():
            print(f"  * {name}")
    else:
        print("\nNo named destinations in /Names tree")

    if hasattr(reader, '_root_object') and '/Dests' in reader._root_object:
        dests_obj = reader._root_object['/Dests']
        if hasattr(dests_obj, 'get_object'):
            dests_obj = dests_obj.get_object()
        print(f"\nDestinations in /Dests catalog: {len(dests_obj)}")
        for name, dest_array in dests_obj.items():
            print(f"  * {name}")
    else:
        print("\nNo /Dests catalog in PDF")

    print("\n" + "="*60)
    print("END DIAGNOSIS")
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='PDF Destinator - Add named destinations and links to PDFs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s document.pdf
      Open interactively, add destinations manually

  %(prog)s document.pdf --titles "Chapter 1" "Chapter 2"
      Pre-populate with these destination titles

  %(prog)s document.pdf --json destinations.json
      Load destinations from JSON file

  %(prog)s document.pdf --diagnose
      Show existing destinations and links in PDF
        """
    )

    parser.add_argument('pdf', help='PDF file to edit')
    parser.add_argument('--titles', nargs='+', help='Destination titles to add')
    parser.add_argument('--json', dest='json_file', help='JSON file with destinations')
    parser.add_argument('--diagnose', action='store_true', help='Diagnose PDF structure')

    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.is_absolute():
        pdf_path = Path.cwd() / pdf_path

    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    if args.diagnose:
        diagnose_pdf(pdf_path)
        sys.exit(0)

    # Get destinations
    destinations = []

    if args.titles:
        destinations = [{"id": title_to_id(t), "title": t} for t in args.titles]
    elif args.json_file:
        json_path = Path(args.json_file)
        if not json_path.exists():
            print(f"Error: JSON file not found: {json_path}")
            sys.exit(1)
        destinations = load_destinations_from_json(json_path, pdf_path.name)
        if not destinations:
            print(f"No destinations found in {json_path} for {pdf_path.name}")
            print("Starting with empty destination list.")
            destinations = []

    print(f"PDF: {pdf_path.name}")
    print(f"Destinations: {len(destinations)}")
    print()
    print("Instructions:")
    print("  - Navigate pages: Left/Right arrows or buttons")
    print("  - Navigate destinations: Up/Down arrows")
    print("  - Click on page to set destination position")
    print("  - Drag on page to create link region")
    print("  - Hover over link + click to delete it")
    print("  - Click 'Save and quit' when done")
    print()

    app = PDFDestinationPicker(pdf_path, destinations)
    app.run()


if __name__ == "__main__":
    main()
