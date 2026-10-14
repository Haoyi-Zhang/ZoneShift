# Copyright (c) 2026 ZoneShift contributors
# SPDX-License-Identifier: MIT
"""Optional retained-data vector route; no experiments or summary recomputation.

Drawing code reused from paper/figures/draw_signature_budget.py. See the artifact LICENSE.
Pass --source (retained input file), --output-dir and --font-root explicitly.
"""
import argparse
import math
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor


def require_fonts(root):
    """Use installed metrics/outlines; never search, install, or copy fonts."""
    for relative in ("afm/urw/times/utmr8a.afm", "type1/urw/times/utmr8a.pfb"):
        if not (root / relative).is_file():
            raise FileNotFoundError(f"Required installed font: {root / relative}")


def load_data(source):
    lines = source.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].split() != ["budget", "boundary", "uniform"]:
        raise ValueError("Expected budget boundary uniform header")
    data = [tuple(map(float, line.split())) for line in lines[1:] if line.strip()]
    if any(len(row) != 3 for row in data) or [row[0] for row in data] != [16, 32, 64, 128, 256, 512, 1120]:
        raise ValueError("Expected seven retained budgets and two mean series")
    if any(not math.isfinite(v) or not 0 <= v <= 12 for row in data for v in row[1:]):
        raise ValueError("Signature means must be finite and within the retained 0..12 axis")
    return data



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    data = load_data(args.source)
    require_fonts(args.font_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    face = pdfmetrics.EmbeddedType1Face(
        str(args.font_root / "afm/urw/times/utmr8a.afm"),
        str(args.font_root / "type1/urw/times/utmr8a.pfb"))
    pdfmetrics.registerTypeFace(face)
    pdfmetrics.registerFont(pdfmetrics.Font("ManuscriptRoman", face.name, "WinAnsiEncoding"))
    width, height = 252, 4.7 * 72 / 2.54
    c = canvas.Canvas(str(args.output_dir / "signature-budget.pdf"), pagesize=(width, height), invariant=1, initialFontName="ManuscriptRoman")
    c.setTitle("")
    left, right, bottom, top = 37, width - 10, 32, height - 26
    x = lambda v: left + (math.log2(v) - math.log2(14)) / (math.log2(1250) - math.log2(14)) * (right - left)
    y = lambda v: bottom + v / 12 * (top - bottom)
    c.setFont("ManuscriptRoman", 7)
    c.setStrokeColor(HexColor("#d6d6d6"))
    c.setLineWidth(.35)
    for tick in range(0, 13, 3):
        c.line(left, y(tick), right, y(tick))
        c.setFillColor(HexColor("#222222"))
        c.drawRightString(left - 5, y(tick) - 2.2, str(tick))
    for budget, _, _ in data:
        c.setStrokeColor(HexColor("#d6d6d6"))
        c.line(x(budget), bottom, x(budget), top)
        c.drawCentredString(x(budget), bottom - 12, str(int(budget)))
    c.setStrokeColor(HexColor("#444444"))
    c.setLineWidth(.5)
    c.line(left, bottom, left, top)
    c.line(left, bottom, right, bottom)
    c.setFont("ManuscriptRoman", 8)
    c.drawCentredString((left + right) / 2, 8, "Windows sampled per module")
    c.saveState()
    c.translate(10, (bottom + top) / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, "Mean unique signatures")
    c.restoreState()
    for index, color, dashed, label, legend_x in [
        (1, "#24629b", False, "Transition-focused", 48),
        (2, "#a23e36", True, "Uniform", 177),
    ]:
        c.setStrokeColor(HexColor(color))
        c.setFillColor(HexColor(color))
        c.setLineWidth(1.1)
        c.setDash([3, 2] if dashed else [])
        path = c.beginPath()
        path.moveTo(x(data[0][0]), y(data[0][index]))
        for row in data[1:]:
            path.lineTo(x(row[0]), y(row[index]))
        c.drawPath(path)
        c.setDash([])
        for row in data:
            xp, yp = x(row[0]), y(row[index])
            if dashed:
                c.rect(xp - 1.8, yp - 1.8, 3.6, 3.6, stroke=0, fill=1)
            else:
                c.circle(xp, yp, 1.8, stroke=0, fill=1)
        legend_y = height - 10
        c.setDash([3, 2] if dashed else [])
        c.line(legend_x, legend_y, legend_x + 14, legend_y)
        c.setDash([])
        c.setFont("ManuscriptRoman", 8)
        c.setFillColor(HexColor("#222222"))
        c.drawString(legend_x + 18, legend_y - 2.5, label)
    c.showPage()
    c.save()


if __name__ == "__main__":
    main()
