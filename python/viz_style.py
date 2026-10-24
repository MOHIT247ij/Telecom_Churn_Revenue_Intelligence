"""Shared chart style - validated categorical palette, recessive grid, thin marks."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE, ORANGE, AQUA, YELLOW = PALETTE[:4]
RETAINED, CHURNED = BLUE, ORANGE
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
SEQ_CMAP = "Blues"


def apply():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titlecolor": INK,
        "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.labelsize": 10, "xtick.color": INK2, "ytick.color": INK2,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.prop_cycle": plt.cycler(color=PALETTE), "lines.linewidth": 2,
        "font.family": "DejaVu Sans", "font.size": 10, "legend.frameon": False,
        "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
    })


def inr(x, _=None):
    """Indian currency formatter: ₹ lakh / crore."""
    if abs(x) >= 1e7:
        return f"₹{x/1e7:.1f} Cr"
    if abs(x) >= 1e5:
        return f"₹{x/1e5:.1f} L"
    if abs(x) >= 1e3:
        return f"₹{x/1e3:.0f}K"
    return f"₹{x:.0f}"
