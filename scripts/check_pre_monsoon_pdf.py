
import pdfplumber

pdf_path = "data/raw/pre-monsoon_2014-2024.pdf"

rajasthan_rows = 0
pages_with_rajasthan = 0

with pdfplumber.open(pdf_path) as pdf:
    print("Total pages:", len(pdf.pages))

    for page_number, page in enumerate(pdf.pages, start=1):
        text = page.extract_text()

        if not text:
            continue

        page_rows = 0

        for line in text.split("\n"):
            if line.strip().lower().startswith("rajasthan "):
                page_rows += 1

        if page_rows > 0:
            rajasthan_rows += page_rows
            pages_with_rajasthan += 1

        if page_number % 500 == 0:
            print("Pages checked:", page_number)

print("\nPages containing Rajasthan:", pages_with_rajasthan)
print("Rajasthan rows found:", rajasthan_rows)
