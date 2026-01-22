import fitz

doc = fitz.open("input.pdf")
outline = []

for pno in range(6, 9):
    page = doc[pno]
    words = page.get_text("words")

    for link in page.get_links():
        rect = fitz.Rect(link["from"])
        text = " ".join(
            w[4] for w in words
            if fitz.Rect(w[:4]).intersects(rect)
        ).strip()

        target_page = link.get("page")

        if text and target_page is not None:
            outline.append([1, text, target_page + 1])

print("Collected outline entries:", len(outline))

doc.set_toc(outline)
doc.save("output_with_toc.pdf", incremental=False, deflate=True)
