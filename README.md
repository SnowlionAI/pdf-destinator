# PDF Destinator

An interactive GUI tool to add **named destinations** and **clickable link regions** to PDF files - without expensive software like Adobe Acrobat.

## Features

- **Visual PDF navigation** with zoom and page controls
- **Click to set destination positions** for internal navigation
- **Drag to create link regions** pointing to destinations or external URLs
- **Load/save destinations** - preserves existing destinations in PDF
- **Hover-to-delete** link regions with visual feedback
- **Mouse wheel scrolling** with automatic page changes at boundaries
- **Keyboard shortcuts** for efficient workflow
- **JSON configuration support** for batch workflows
- **Diagnose mode** to inspect existing PDF structure
- **PDF outline/TOC generation** for reader sidebar navigation

## Installation

```bash
pip install pdf-destinator
```

### System Requirements

- Python 3.8+
- tkinter (GUI toolkit)

**Windows:** tkinter is included with the standard Python installer - no extra steps needed.

**Linux:** Install tkinter separately:
```bash
sudo apt-get install python3-tk  # Debian/Ubuntu
sudo dnf install python3-tkinter  # Fedora
```

**macOS:** Included with python.org installer. If using Homebrew Python:
```bash
brew install python-tk
```

## Usage

### Basic Usage

Open a PDF and add destinations interactively:

```bash
pdf-destinator document.pdf
```

### With Pre-defined Titles

Pre-populate the destination list with titles:

```bash
pdf-destinator document.pdf --titles "Introduction" "Chapter 1" "Chapter 2" "Conclusion"
```

### With JSON Configuration

Load destinations from a JSON file:

```bash
pdf-destinator document.pdf --json destinations.json
```

JSON format:
```json
[
  {
    "pdfFile": "document.pdf",
    "destinations": [
      { "id": "intro", "title": "Introduction" },
      { "id": "chapter-1", "title": "Chapter 1" },
      { "id": "https://example.com", "title": "External Link", "type": "url" }
    ]
  }
]
```

### Diagnose Mode

Inspect existing destinations and links in a PDF:

```bash
pdf-destinator document.pdf --diagnose
```

### Generate PDF Outline/TOC

Generate a PDF outline (table of contents) that appears in PDF reader sidebars (like Evince, Adobe Reader, ReadEra, etc.).

> **Note:** Link annotations (clickable regions on pages) are different from the PDF outline. The outline is what PDF readers display in their navigation sidebar. This feature creates that outline structure.

**Command-line options:**

```bash
# From named destinations in the PDF
pdf-destinator document.pdf --toc

# From links on specific TOC pages (extracts link text as titles)
pdf-destinator document.pdf --toc-from-links 3 5

# Both methods combined
pdf-destinator document.pdf --toc --toc-from-links 3 5
```

**GUI options:**

Use the "TOC" dropdown in the action bar before saving:

| Option | Description |
|--------|-------------|
| None | No TOC generation (default) |
| From destinations | Create TOC from all positioned destinations |
| From page links | Extract TOC from links on specified pages |
| Both | Combine both methods |

When "From page links" or "Both" is selected, enter the page range in the "Pages" field:
- `3-5` - pages 3 to 5
- `1,3,5` - specific pages
- `2-4,7` - combination

## Workflow

1. **Open PDF** - Run pdf-destinator with your PDF file
2. **Navigate** - Use arrow keys or buttons to browse pages, or click the page indicator to jump to a specific page
3. **Click** - Click on the page to set a destination position
4. **Drag** - Drag a rectangle to create a clickable link region
5. **Delete** - Hover over a link region (cursor changes to X) and click to delete
6. **TOC** - Optionally select TOC generation mode before saving
7. **Save** - Click "Save and quit" when done

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Left/Right | Navigate pages |
| Up/Down | Navigate destinations |
| Mouse wheel | Scroll page (changes pages at boundaries) |

## Page Navigation

Click the page indicator button (e.g., "Page 1 / 10") to open a dialog where you can jump directly to any page number.

## Mouse Actions

| Action | Result |
|--------|--------|
| Click | Set destination position at click location |
| Drag | Create link region pointing to current destination |
| Hover + Click on link | Delete the link region |

## Status Indicators

In the destination list:
- `[x]` - Destination has a position set
- `[o]` - Destination exists in PDF (loaded)
- `[ ]` - Destination needs a position
- `[URL]` - External URL (no position needed)

## Use Cases

- **Create table of contents links** in newsletters or reports
- **Add navigation** to long PDF documents
- **Link external resources** from PDF pages
- **Fix or update** existing PDF destinations
- **Batch processing** with JSON configuration
- **Generate PDF outline/TOC** so destinations appear in reader sidebars

## Python API

You can also use pdf-destinator programmatically:

```python
from pdf_destinator import PDFDestinationPicker

destinations = [
    {"id": "intro", "title": "Introduction"},
    {"id": "chapter-1", "title": "Chapter 1"},
]

app = PDFDestinationPicker("document.pdf", destinations)
app.run()
```

## Dependencies

- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF rendering and link annotations
- [pypdf](https://pypdf.readthedocs.io/) - Named destinations
- [Pillow](https://pillow.readthedocs.io/) - Image processing for display

## License

MIT License - see [LICENSE](LICENSE) file.

## Contributing

Contributions welcome! Please open an issue or pull request on GitHub.

## Acknowledgments

Created with the help of Claude (Anthropic) as a free alternative to expensive PDF editing tools.
