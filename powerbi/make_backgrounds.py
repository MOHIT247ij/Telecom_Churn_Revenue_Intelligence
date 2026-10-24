"""
make_backgrounds.py - generates Power BI canvas backgrounds (1920x1080, 16:9)
for the 6 report pages. Layout slots match Dashboard_Build_Guide.md.

Power BI: Format page -> Canvas background -> Image -> select PNG,
          Image fit = Fit, Transparency = 0%.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent / "backgrounds"
OUT.mkdir(exist_ok=True)
W, H, S = 1920, 1080, 2                     # draw at 2x then downscale for smooth edges
PAGE_BG, CARD, BORDER = "#F4F5F7", "#FFFFFF", "#E3E6EB"
HEADER, HEADER2, ACCENT = "#0F2D52", "#163E6E", "#2A78D6"
M, G = 24, 16                               # outer margin, gap
TOP = 186                                   # content starts below header (90) + slicer row


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for p in [f"/usr/share/fonts/truetype/dejavu/{name}", name]:
        try:
            return ImageFont.truetype(p, size * S)
        except OSError:
            continue
    return ImageFont.load_default()


LAYOUT, CUR = {}, [None]


def panel(img, x, y, w, h, r=14, accent=False, log=True):
    if log and CUR[0]:
        LAYOUT.setdefault(CUR[0], []).append((x, y, w, h))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([(x) * S, (y + 3) * S, (x + w) * S, (y + h + 3) * S], r * S,
                                         fill=(15, 45, 82, 28))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6 * S)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], r * S, fill=CARD, outline=BORDER, width=S)
    if accent:                                  # KPI card accent bar on the left
        d.rounded_rectangle([x * S, y * S, (x + 6) * S, (y + h) * S], 3 * S, fill=ACCENT)


def row(img, y, h, weights, accent=False):
    """Split the content width into panels by weight."""
    total_w = W - 2 * M - G * (len(weights) - 1)
    x = M
    for wt in weights:
        w = round(total_w * wt / sum(weights))
        panel(img, x, y, w, h, accent=accent)
        x += w + G


def base(page_no, title, subtitle):
    CUR[0] = f"{page_no:02d} {title}"
    img = Image.new("RGBA", (W * S, H * S), PAGE_BG)
    d = ImageDraw.Draw(img)
    # header gradient band
    for i in range(90 * S):
        t = i / (90 * S)
        c = tuple(int(int(HEADER[k:k + 2], 16) * (1 - t) + int(HEADER2[k:k + 2], 16) * t) for k in (1, 3, 5))
        d.line([(0, i), (W * S, i)], fill=c)
    # logo mark: signal bars
    for k, hgt in enumerate([14, 22, 30, 38]):
        x0 = (M + 6 + k * 10) * S
        d.rounded_rectangle([x0, (64 - hgt) * S, x0 + 6 * S, 64 * S], 2 * S, fill="#7FB3F0" if k < 3 else "#FFFFFF")
    d.text(((M + 58) * S, 20 * S), "Telecom Churn & Revenue Intelligence", font=font(24, True), fill="white")
    d.text(((M + 58) * S, 54 * S), f"{page_no:02d} · {title}  —  {subtitle}", font=font(14), fill="#BFD6F2")
    # page-navigator placeholder (6 pills, right side of header)
    px = W - M - 6 * 118
    for k in range(6):
        fill = ACCENT if k == page_no - 1 else "#24507F"
        d.rounded_rectangle([(px + k * 118) * S, 28 * S, (px + k * 118 + 108) * S, 62 * S], 17 * S, fill=fill)
    # slicer strip
    panel(img, M, 102, W - 2 * M, 70, r=12)          # slots logged: [0] = slicer strip
    return img


def save(img, name):
    img = img.resize((W, H), Image.LANCZOS).convert("RGB")
    img.save(OUT / name, optimize=True)
    print("saved", name)


KPI_H, R2_Y = 112, TOP + 112 + G
# ---------------------------------------------------------------- page 1
img = base(1, "Executive Overview", "KPIs, revenue & subscriber trend")
row(img, TOP, KPI_H, [1] * 6, accent=True)
row(img, R2_Y, 372, [1, 1])
row(img, R2_Y + 372 + G, H - (R2_Y + 372 + G) - M, [1.1, 1, 0.9])
save(img, "01_executive_overview.png")

# ---------------------------------------------------------------- page 2
img = base(2, "Churn Analysis", "who churns, when and why")
row(img, TOP, KPI_H, [1] * 4, accent=True)
row(img, R2_Y, 360, [2, 1])
row(img, R2_Y + 360 + G, H - (R2_Y + 360 + G) - M, [1, 1, 1.2])
save(img, "02_churn_analysis.png")

# ---------------------------------------------------------------- page 3
img = base(3, "Revenue Intelligence", "MRR, ARPU, leakage & CLV")
row(img, TOP, KPI_H, [1] * 5, accent=True)
row(img, R2_Y, 360, [1, 1, 1])
row(img, R2_Y + 360 + G, H - (R2_Y + 360 + G) - M, [1, 1, 1.3])
save(img, "03_revenue_intelligence.png")

# ---------------------------------------------------------------- page 4
img = base(4, "Churn Risk & Retention", "ML scores, revenue at risk & campaign ROI")
row(img, TOP, KPI_H, [1] * 5, accent=True)
row(img, R2_Y, 380, [1.2, 1.2, 0.9])
row(img, R2_Y + 380 + G, H - (R2_Y + 380 + G) - M, [1])
save(img, "04_risk_retention.png")

# ---------------------------------------------------------------- page 5
img = base(5, "Customer Experience & Network", "tickets, CSAT & network quality")
row(img, TOP, KPI_H, [1] * 5, accent=True)
row(img, R2_Y, 372, [1.3, 1])
row(img, R2_Y + 372 + G, H - (R2_Y + 372 + G) - M, [1, 1])
save(img, "05_customer_experience.png")

# ---------------------------------------------------------------- page 6 (drill-through)
img = base(6, "Customer 360", "drill-through profile")
left_w = 420
panel(img, M, TOP, left_w, H - TOP - M)                         # profile column
for k in range(6):                                              # profile cards inside
    panel(img, M + 16, TOP + 70 + k * 128, left_w - 32, 112, accent=True)
x2 = M + left_w + G
w2 = W - x2 - M
half = (H - TOP - M - 2 * G) // 3
for k in range(3):
    panel(img, x2, TOP + k * (half + G), w2, half)
save(img, "06_customer_360.png")

# ---------------------------------------------------------------- layout guide (Power BI units 1280x720)
k = 1280 / W
lines = ["# Visual positions (Power BI canvas 1280 x 720)",
         "",
         "Select a visual → **Format → General → Properties → Size & Position** and type these values.",
         "Slot numbers go left→right, top→bottom. Slot 0 = slicer strip.",
         ""]
for page, slots in LAYOUT.items():
    lines += [f"## {page}", "", "| Slot | X | Y | Width | Height |", "|---|---|---|---|---|"]
    for i, (x, y, w, h) in enumerate(slots):
        lines.append(f"| {i} | {round(x * k)} | {round(y * k)} | {round(w * k)} | {round(h * k)} |")
    lines.append("")
(OUT / "LAYOUT.md").write_text("\n".join(lines), encoding="utf-8")
import json
(OUT / "LAYOUT.json").write_text(json.dumps({pg: [[round(v * k, 1) for v in sl] for sl in slots] for pg, slots in LAYOUT.items()}, indent=1))
print("saved LAYOUT.md")
CUR[0] = None

# ---------------------------------------------------------------- tooltip page (small)
tip = Image.new("RGBA", (640 * S, 480 * S), PAGE_BG)
W0, H0 = W, H
W, H = 640, 480
panel(tip, 12, 12, 616, 456)
W, H = W0, H0
tip.resize((640, 480), Image.LANCZOS).convert("RGB").save(OUT / "07_tooltip.png", optimize=True)
print("saved 07_tooltip.png")
