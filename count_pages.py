import sys
import json

# ---- Settings -------------------------------------------------------------
DPI = 75                # render quality used only for colour detection
TOLERANCE = 15          # R/G/B difference that still counts as grey (same as before)
MIN_COLOR_PIXELS = 1    # 1 = a single coloured pixel makes the page "colour" (same as before)
MAX_PAGES = 500         # refuse huge PDFs so the server cannot be overloaded

try:
    import numpy as np  # optional: makes the colour scan several times faster
except ImportError:
    np = None


def page_is_color(samples, n, tol=TOLERANCE, min_pixels=MIN_COLOR_PIXELS):
    """samples = raw RGB bytes of one page, n = bytes per pixel."""
    if n < 3:
        return False

    if np is not None:
        px = np.frombuffer(samples, dtype=np.uint8).reshape(-1, n)[:, :3]
        spread = px.max(axis=1).astype(np.int16) - px.min(axis=1)   # biggest R/G/B difference per pixel
        return int((spread > tol).sum()) >= min_pixels

    # slow fallback when numpy is not installed
    found = 0
    for i in range(0, len(samples) - n + 1, n):
        r, g, b = samples[i], samples[i + 1], samples[i + 2]
        if abs(r - g) > tol or abs(g - b) > tol or abs(r - b) > tol:
            found += 1
            if found >= min_pixels:
                return True
    return False


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No file path provided"}))
        return 1

    try:
        import fitz  # PyMuPDF
    except ImportError:
        print(json.dumps({"error": "PyMuPDF is not installed on the server (pip install pymupdf)"}))
        return 1

    try:
        doc = fitz.open(sys.argv[1])
        if doc.needs_pass:
            print(json.dumps({"error": "This PDF is password protected"}))
            return 1

        total = len(doc)
        if total < 1:
            print(json.dumps({"error": "This PDF has no pages"}))
            return 1
        if total > MAX_PAGES:
            print(json.dumps({"error": "PDF is too large (maximum %d pages)" % MAX_PAGES}))
            return 1

        color = 0
        for page in doc:
            pix = page.get_pixmap(dpi=DPI, colorspace=fitz.csRGB, alpha=False)
            if page_is_color(pix.samples, pix.n):
                color += 1

        print(json.dumps({"total": total, "color": color, "bw": total - color}))
        return 0

    except Exception as e:
        # No "total" key on purpose: the website then shows an error
        # instead of silently charging a broken file as 1 page.
        print(json.dumps({"error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())