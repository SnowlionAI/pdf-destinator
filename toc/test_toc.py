import fitz

doc = fitz.open("output_with_toc.pdf")
toc = doc.get_toc()

print("TOC length:", len(toc))
for entry in toc[:10]:
    print(entry)
