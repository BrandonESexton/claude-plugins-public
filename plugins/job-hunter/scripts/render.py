#!/usr/bin/env python3
"""Render a resume or cover letter from simple Markdown to a one-column .docx and a text-based PDF.
Stdlib only (no Word, LibreOffice, or Node needed), so it runs the same in Cowork and Claude Code.

  render.py resume.md --out DIR --name First_Last_Resume_Company

Markdown it understands (anything else is a plain paragraph):
  # Full Name                    name line (first line)
  City, ST | phone | email       contact lines: plain lines after the name, before the first ##
  ## Section                     section heading with a rule under it
  ### Title, Employer | Dates    role line: bold left, right-aligned text after the last " | "
  - bullet text                  bullet
  **bold** inside any line

Prints the output paths and "pages: N". Contact info stays in the page body, never a Word header,
because many applicant systems ignore headers and footers.
"""
import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

# Helvetica and Helvetica-Bold advance widths (1/1000 em) for ASCII 32..126.
W_REG = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 + [
    278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 222, 556, 556, 500, 556, 556,
    278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334,
    260, 334, 584]
W_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 + [
    333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 278, 556, 611, 556, 611, 556,
    333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389,
    280, 389, 584]

PAGE_W, PAGE_H, MARGIN = 612, 792, 54  # US Letter, 0.75 inch margins
TEXT_W = PAGE_W - 2 * MARGIN
SIZES = {"name": 18, "contact": 10, "h2": 11, "role": 10.5, "body": 10.5}


def runs(text):
    """'a **b** c' -> [('a ', False), ('b', True), (' c', False)]"""
    parts = re.split(r"\*\*(.+?)\*\*", text)
    return [(p, i % 2 == 1) for i, p in enumerate(parts) if p]


def parse(md):
    """Markdown subset -> list of (kind, payload)."""
    blocks, seen_section = [], False
    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# ") and not blocks:
            blocks.append(("name", line[2:].strip()))
        elif line.startswith("## "):
            seen_section = True
            blocks.append(("h2", line[3:].strip()))
        elif line.startswith("### "):
            left, _, right = line[4:].rpartition(" | ")
            blocks.append(("role", (left or right, right if left else "")))
        elif line[:2] in ("- ", "* ", "• "):
            blocks.append(("bullet", line[2:].strip()))
        elif blocks and blocks[0][0] == "name" and not seen_section and all(k in ("name", "contact") for k, _ in blocks):
            blocks.append(("contact", line))
        else:
            blocks.append(("para", line))
    return blocks


# --------------------------------------------------------------------------- PDF

def width(text, bold, size):
    table = W_BOLD if bold else W_REG
    return sum(table[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in text) * size / 1000


def wrap(rs, size, max_w):
    """Greedy word wrap over styled runs -> list of lines, each a list of (text, bold)."""
    words = []
    for text, bold in rs:
        for w in re.split(r"( )", text):
            if w:
                words.append((w, bold))
    lines, cur, cur_w = [], [], 0.0
    for w, bold in words:
        ww = width(w, bold, size)
        if w != " " and cur and cur_w + ww > max_w:
            while cur and cur[-1][0] == " ":
                cur_w -= width(" ", cur[-1][1], size)
                cur.pop()
            lines.append(cur)
            cur, cur_w = [], 0.0
        if w == " " and not cur:
            continue
        cur.append((w, bold))
        cur_w += ww
    if cur:
        lines.append(cur)
    return lines or [[("", False)]]


def pdf_str(text):
    b = text.encode("cp1252", errors="replace")
    return b"(" + b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


class Pdf:
    def __init__(self):
        self.pages, self.ops, self.y = [], [], PAGE_H - MARGIN

    def new_page(self):
        self.pages.append(b"\n".join(self.ops))
        self.ops, self.y = [], PAGE_H - MARGIN

    def need(self, h):
        if self.y - h < MARGIN and self.ops:
            self.new_page()

    def text(self, x, y, s, bold, size):
        if s:
            self.ops.append(b"BT /%s %.1f Tf %.2f %.2f Td %s Tj ET" % (b"F2" if bold else b"F1", size, x, y, pdf_str(s)))

    def line_of_runs(self, x, line, size):
        for s, bold in line:
            self.text(x, self.y, s, bold, size)
            x += width(s, bold, size)

    def paragraph(self, rs, size, indent=0, align="left", gap=3, keep=0, marker=None):
        lines = wrap(rs, size, TEXT_W - indent)
        lead = size * 1.25
        self.need(lead * (len(lines) + keep) if len(lines) <= 3 else lead * 2)  # no orphaned short paragraphs
        for i, ln in enumerate(lines):
            self.need(lead)
            self.y -= lead
            if marker and i == 0:
                self.text(MARGIN + 2, self.y, marker, False, size)
            x = MARGIN + indent
            if align == "center":
                x = (PAGE_W - sum(width(s, b, size) for s, b in ln)) / 2
            self.line_of_runs(x, ln, size)
        self.y -= gap

    def finish(self):
        if self.ops:
            self.new_page()
        objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
        kids = []
        for content in self.pages:
            objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
            objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
                        b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>" % (PAGE_W, PAGE_H, len(objs)))
            kids.append(b"%d 0 R" % len(objs))
        objs[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), len(kids))
        out, offsets = bytearray(b"%PDF-1.4\n"), []
        for i, o in enumerate(objs, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
        out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
        return bytes(out), len(self.pages)


def to_pdf(blocks):
    p = Pdf()
    for i, (kind, val) in enumerate(blocks):
        if kind == "name":
            p.paragraph([(val, True)], SIZES["name"], align="center", gap=2)
        elif kind == "contact":
            p.paragraph(runs(val), SIZES["contact"], align="center", gap=1)
        elif kind == "h2":
            p.y -= 6
            p.paragraph([(val.upper(), True)], SIZES["h2"], gap=0, keep=2)  # keep heading with what follows
            p.ops.append(b"0.5 w %.2f %.2f m %.2f %.2f l S" % (MARGIN, p.y - 2, PAGE_W - MARGIN, p.y - 2))
            p.y -= 6
        elif kind == "role":
            left, right = val
            size = SIZES["role"]
            rw = width(right, False, size) + 12 if right else 0
            lines = wrap([(left, True)], size, TEXT_W - rw)
            p.need(size * 1.25 * (len(lines) + 1))
            for j, ln in enumerate(lines):
                p.y -= size * 1.25
                p.line_of_runs(MARGIN, ln, size)
                if j == 0 and right:
                    p.text(PAGE_W - MARGIN - width(right, False, size), p.y, right, False, size)
            p.y -= 2
        elif kind == "bullet":
            p.paragraph(runs(val), SIZES["body"], indent=12, gap=1, marker="•")
        else:
            p.paragraph(runs(val), SIZES["body"], gap=6)
    return p.finish()


# --------------------------------------------------------------------------- DOCX

def w_runs(rs, size, bold_all=False):
    out = []
    for text, bold in rs:
        b = "<w:b/>" if bold or bold_all else ""
        out.append(f'<w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>{b}<w:sz w:val="{int(size * 2)}"/></w:rPr>'
                   f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>')
    return "".join(out)


def w_para(inner, ppr=""):
    return f"<w:p><w:pPr>{ppr}</w:pPr>{inner}</w:p>"


def to_docx(blocks, path):
    tw = int(TEXT_W * 20)
    body = []
    for kind, val in blocks:
        if kind == "name":
            body.append(w_para(w_runs([(val, True)], SIZES["name"]), '<w:jc w:val="center"/><w:spacing w:after="40"/>'))
        elif kind == "contact":
            body.append(w_para(w_runs(runs(val), SIZES["contact"]), '<w:jc w:val="center"/><w:spacing w:after="0"/>'))
        elif kind == "h2":
            body.append(w_para(w_runs([(val.upper(), True)], SIZES["h2"]),
                               '<w:keepNext/><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="000000"/></w:pBdr>'
                               '<w:spacing w:before="200" w:after="80"/>'))
        elif kind == "role":
            left, right = val
            tab = f'<w:r><w:tab/></w:r>{w_runs([(right, False)], SIZES["role"])}' if right else ""
            body.append(w_para(w_runs([(left, True)], SIZES["role"]) + tab,
                               f'<w:keepNext/><w:tabs><w:tab w:val="right" w:pos="{tw}"/></w:tabs><w:spacing w:before="80" w:after="20"/>'))
        elif kind == "bullet":
            body.append(w_para(w_runs([("•", False)], SIZES["body"]) + '<w:r><w:tab/></w:r>' + w_runs(runs(val), SIZES["body"]),
                               '<w:tabs><w:tab w:val="left" w:pos="240"/></w:tabs><w:ind w:left="240" w:hanging="240"/><w:spacing w:after="20"/>'))
        else:
            body.append(w_para(w_runs(runs(val), SIZES["body"]), '<w:spacing w:after="120"/>'))
    m = MARGIN * 20
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(body) +
           f'<w:sectPr><w:pgSz w:w="{PAGE_W * 20}" w:h="{PAGE_H * 20}"/>'
           f'<w:pgMar w:top="{m}" w:right="{m}" w:bottom="{m}" w:left="{m}" w:header="0" w:footer="0" w:gutter="0"/></w:sectPr>'
           '</w:body></w:document>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '</Relationships>')
        z.writestr("word/document.xml", doc)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--name", required=True, help="file name without extension, e.g. Jane_Doe_Resume_Acme")
    a = ap.parse_args(argv)
    blocks = parse(Path(a.source).read_text(encoding="utf-8"))
    if not blocks:
        sys.exit("render: source is empty")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    docx, pdf = out / f"{a.name}.docx", out / f"{a.name}.pdf"
    to_docx(blocks, docx)
    data, pages = to_pdf(blocks)
    pdf.write_bytes(data)
    print(f"{docx}\n{pdf}\npages: {pages}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a code page that cannot print every character
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
