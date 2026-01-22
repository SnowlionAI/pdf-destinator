import fitz  # PyMuPDF

INPUT = "input.pdf"
OUTPUT = "output_with_toc.pdf"

TOC_START = 6   # page index for page 7
TOC_END   = 8   # page index for page 9 (inclusive)

print("Opening PDF:", INPUT)
doc = fitz.open(INPUT)
print("Total pages:", doc.page_count)

outline = []

for pno in range(TOC_START, TOC_END + 1):
    print(f"\n--- Scanning TOC page index {pno} ---")

    if pno < 0 or pno >= doc.page_count:
        print("  !! Page index out of range, skipping")
        continue

    page = doc[pno]

    links = page.get_links()
    print(f"  Found {len(links)} links on this page")

    words = page.get_text("words")
    print(f"  Found {len(words)} words on this page")

    for i, link in enumerate(links):
        print(f"\n  Link {i+1}/{len(links)}")
        print("    Raw link dict:", link)

        if link["kind"] != fitz.LINK_GOTO:
            print("    -> Not an internal GOTO link, skipping")
            continue

        rect = fitz.Rect(link["from"])
        print("    Link rectangle:", rect)

        overlapping = [
            w[4] for w in words
            if fitz.Rect(w[:4]).intersects(rect)
        ]

        text = " ".join(overlapping).strip()
        print("    Extracted text:", repr(text))

        target_page = link.get("page")
        print("    Target page (0-based):", target_page)

        if not text:
            print("    -> Empty text, skipping")
            continue

        if target_page is None:
            print("    -> No target page, skipping")
            continue

        outline.append([1, text, target_page + 1])
        print("    -> Added TOC entry")

print("\n=== Summary ===")
print("Total outline entries collected:", len(outline))

if outline:
    print("First few entries:")
    for entry in outline[:5]:
        print(" ", entry)
else:
    print("!! Outline is empty")

print("\nWriting TOC to PDF...")
doc.set_toc(outline)
doc.save(OUTPUT)

print("Saved output PDF as:", OUTPUT)
