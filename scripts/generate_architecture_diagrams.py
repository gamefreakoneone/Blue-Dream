"""Generate the Project Memoria architecture diagrams (Qwen profile).

Produces two PNGs into ``Demo/``:

* ``memoria-architecture-qwen.png``          -- simple 5-part headline diagram
* ``memoria-architecture-qwen-detailed.png`` -- all-layers appendix diagram

The diagrams are code-grounded: every model label matches
``Blue_dream_agents/llm/model_registry.py`` ``_PRESETS["qwen"]`` and the layers
match ``TECHNICAL_DESIGN.md``. Regenerate with:

    conda run -n Project-Memoria python scripts/generate_architecture_diagrams.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

DEMO_DIR = Path(__file__).resolve().parent.parent / "Demo"

# ---------------------------------------------------------------------------
# Palette (accessible, print-friendly). Band tints are light; box borders are
# the matching accent. Gemini fallback edges are drawn dashed grey.
# ---------------------------------------------------------------------------
INK = "#1E2329"
MUTED = "#5F6672"
FALLBACK = "#8A9099"
WHITE = "#FFFFFF"

LAYERS = {
    "capture":     {"band": "#E7F1EA", "accent": "#2E7D5B"},
    "ingestion":   {"band": "#FBEEE1", "accent": "#C4772E"},
    "stores":      {"band": "#E6EEF8", "accent": "#3A6EA5"},
    "provider":    {"band": "#EFE8F5", "accent": "#6B4FA0"},
    "interaction": {"band": "#E2F1F0", "accent": "#2C8A82"},
}


def box(ax, x, y, w, h, text, *, accent, fc=WHITE, fs=11, bold=False,
        dashed=False, tc=INK, ha="center"):
    style = "round,pad=0.015,rounding_size=0.12"
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=style, linewidth=1.7,
        edgecolor=accent, facecolor=fc,
        linestyle=(0, (5, 3)) if dashed else "-", zorder=3))
    tx = x + w / 2 if ha == "center" else x + 0.35
    ax.text(tx, y + h / 2, text, ha=ha, va="center", fontsize=fs,
            color=tc, zorder=4, weight="bold" if bold else "normal",
            linespacing=1.35)


def band(ax, x, y, w, h, title, key):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.25",
        linewidth=0, facecolor=LAYERS[key]["band"], zorder=1))
    ax.text(x + 0.4, y + h - 0.35, title, ha="left", va="top", fontsize=12.5,
            weight="bold", color=LAYERS[key]["accent"], zorder=2)


def arrow(ax, p1, p2, *, color=MUTED, dashed=False, rad=0.0, lw=1.7, label=None,
          label_dxy=(0, 0.5), label_color=None):
    ax.add_patch(FancyArrowPatch(
        p1, p2, arrowstyle="-|>", mutation_scale=15, color=color, lw=lw,
        linestyle=(0, (5, 3)) if dashed else "-",
        connectionstyle=f"arc3,rad={rad}", zorder=2))
    if label:
        mx, my = (p1[0] + p2[0]) / 2 + label_dxy[0], (p1[1] + p2[1]) / 2 + label_dxy[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=8.5,
                color=label_color or MUTED, style="italic", zorder=5)


def new_ax(w_in, h_in, xlim, ylim):
    fig, ax = plt.subplots(figsize=(w_in, h_in))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    return fig, ax


# ===========================================================================
# 1. Headline diagram
# ===========================================================================
def headline():
    fig, ax = new_ax(16, 7.2, (0, 100), (0, 45))

    ax.text(50, 43, "Project Memoria — Architecture (Qwen profile)",
            ha="center", va="top", fontsize=19, weight="bold", color=INK)
    ax.text(50, 38.6,
            "Home cameras  →  durable memory  →  grounded recall, safety, and proactive guidance",
            ha="center", va="top", fontsize=11.5, color=MUTED)

    stages = [
        ("capture", "CAPTURE",
         "Cameras + Mic\nYOLO fall / person\nrecord clip + audio"),
        ("ingestion", "INGESTION",
         "Consolidator\nQwen video + ASR\n→ MemoryEvent"),
        ("stores", "MEMORY STORES",
         "MongoDB — truth\nChromaDB — index\nlifecycle + recall"),
        ("interaction", "INTERACTION",
         "Jeeves router\nReact PWA\nproactive + push"),
    ]
    w, h, y = 19.5, 13.5, 19
    xs = [2, 26.5, 51, 75.5]
    centers = []
    for (key, title, body), x in zip(stages, xs):
        band(ax, x, y, w, h, title, key)
        ax.text(x + w / 2, y + h - 2.7, body, ha="center", va="top",
                fontsize=11, color=INK, linespacing=1.5, weight="normal")
        centers.append((x, x + w, y + h / 2))

    for i in range(3):
        arrow(ax, (centers[i][1], centers[i][2]), (centers[i + 1][0], centers[i + 1][2]),
              color="#44515E", lw=2.2)

    # Provider layer as a foundation bar serving ingestion + interaction.
    px, pw, py, ph = 2, 93, 3, 10
    ax.add_patch(FancyBboxPatch(
        (px, py), pw, ph, boxstyle="round,pad=0.02,rounding_size=0.25",
        linewidth=1.8, edgecolor=LAYERS["provider"]["accent"],
        facecolor=LAYERS["provider"]["band"], zorder=3))
    ax.text(px + pw / 2, py + ph - 2.4, "PROVIDER LAYER", ha="center", va="top",
            fontsize=12.5, weight="bold", color=LAYERS["provider"]["accent"])
    ax.text(px + pw / 2, py + 3.1,
            "one async OpenAI-protocol client   ·   LLM_PROVIDER=qwen  "
            "(text · vision · video · embeddings · ASR)   ·   Gemini fallback for video + spatial",
            ha="center", va="center", fontsize=10.5, color=INK)

    # dashed connectors from provider up into ingestion + interaction
    arrow(ax, (36, py + ph), (36, 19), color=LAYERS["provider"]["accent"],
          dashed=True, lw=1.5)
    arrow(ax, (85, py + ph), (85, 19), color=LAYERS["provider"]["accent"],
          dashed=True, lw=1.5)

    out = DEMO_DIR / "memoria-architecture-qwen.png"
    fig.savefig(out, dpi=150, facecolor=WHITE)
    plt.close(fig)
    print("wrote", out)


# ===========================================================================
# 2. Detailed diagram
# ===========================================================================
def detailed():
    fig, ax = new_ax(16, 20, (0, 100), (0, 128))

    ax.text(50, 126, "Project Memoria — Detailed Architecture (Qwen profile)",
            ha="center", va="top", fontsize=18, weight="bold", color=INK)
    ax.text(50, 122.5,
            "MongoDB is the source of truth · ChromaDB is a rebuildable index · "
            "one provider client serves every model capability",
            ha="center", va="top", fontsize=10.5, color=MUTED)

    A = {k: LAYERS[k]["accent"] for k in LAYERS}

    # ---- CAPTURE -------------------------------------------------------
    band(ax, 2, 100, 96, 18, "①  CAPTURE   ·   Capture/  (local machine)", "capture")
    yc = 103.5
    box(ax, 4,   yc, 15, 7, "Cameras + Mic", accent=A["capture"], bold=True)
    box(ax, 21,  yc, 17, 7, "YOLO\ncustom FALLEN /\nNOT-FALLEN model", accent=A["capture"], fs=9.5)
    box(ax, 40,  yc, 18, 7, "Record\nsilent mp4  ‖  mic mp3\n(parallel)", accent=A["capture"], fs=9.5)
    box(ax, 60,  yc, 16, 7, "End-of-event\nscreenshot\n(last frame)", accent=A["capture"], fs=9.5)
    box(ax, 78,  yc, 16, 7, "VideoProcessing\nQueue", accent=A["capture"], fs=9.5, bold=True)
    box(ax, 60,  113.4, 34, 4, "fall ≥ 3.5 s  →  Caretaker Gmail alert  (email only)",
        accent=FALLBACK, fs=9.5, dashed=True, tc=MUTED)
    arrow(ax, (19, yc + 3.5), (21, yc + 3.5), color=A["capture"])
    arrow(ax, (38, yc + 3.5), (40, yc + 3.5), color=A["capture"])
    arrow(ax, (58, yc + 3.5), (60, yc + 3.5), color=A["capture"])
    arrow(ax, (76, yc + 3.5), (78, yc + 3.5), color=A["capture"])
    arrow(ax, (29.5, yc + 7), (60, 113.4), color=FALLBACK, dashed=True, rad=-0.2)

    # ---- INGESTION -----------------------------------------------------
    band(ax, 2, 78, 96, 19, "②  INGESTION   ·   consolidator.py  (the orchestrator)", "ingestion")
    yi = 86
    box(ax, 4,  yi, 19, 8, "[ Qwen video via OSS URL\n‖  Qwen ASR ]\nparallel", accent=A["ingestion"], fs=9.5, bold=True)
    box(ax, 25, yi, 14, 8, "Build\nMemoryEvent", accent=A["ingestion"], fs=10)
    box(ax, 41, yi, 15, 8, "Safety agent\n(vision judge)", accent=A["ingestion"], fs=10)
    box(ax, 58, yi, 13, 8, "Importance\nscore", accent=A["ingestion"], fs=10)
    box(ax, 73, yi, 15, 8, "MongoDB\ninsert", accent=A["ingestion"], fs=10, bold=True)
    box(ax, 30, 79.4, 34, 4.6,
        "side-effects:  patient alert  ·  morning report  ·  event-reminder match",
        accent=A["ingestion"], fs=9, tc=MUTED)
    box(ax, 4, 79.4, 24, 4.6,
        "OSS bridge (oss_media.py)\nladder: Qwen → Gemini → partial",
        accent=FALLBACK, fs=8.5, dashed=True, tc=MUTED)
    for x0, x1 in [(23, 25), (39, 41), (56, 58), (71, 73)]:
        arrow(ax, (x0, yi + 4), (x1, yi + 4), color=A["ingestion"])
    arrow(ax, (86, 103.5), (13.5, yi + 8), color="#44515E", rad=0.12,
          label="queued recording", label_dxy=(0, 1.2))

    # ---- MEMORY STORES -------------------------------------------------
    band(ax, 2, 52, 96, 24, "③  MEMORY STORES", "stores")
    box(ax, 4, 54.5, 45, 18.5,
        "MongoDB  —  source of truth   (dementia_assistance)\n\n"
        "events · memory_summaries · memory_digests\n"
        "conversation_sessions · profile_facts · reminders\n"
        "proactive_messages · push_subscriptions\n"
        "safety_alerts · devices · geofence_settings",
        accent=A["stores"], fs=10, ha="left")
    box(ax, 51, 66, 45, 7,
        "ChromaDB  —  rebuildable semantic index\nmemory_events__qwen__text-embedding-v4__1024",
        accent=A["stores"], fs=9.5)
    box(ax, 51, 54.5, 45, 8.5,
        "Memory lifecycle\nimportance @ ingest → daily consolidation →\n"
        "pin / unpin → budgeted recall\n(similarity × recency-decay × (1 + importance))",
        accent=A["stores"], fs=9.5)
    # insert → MongoDB source of truth (left box); embed → Chroma index (right box)
    arrow(ax, (76, yi), (45, 73.2), color="#44515E", rad=-0.12)
    arrow(ax, (84, yi), (84, 73.2), color="#44515E", dashed=True)

    # ---- INTERACTION ---------------------------------------------------
    band(ax, 2, 26, 96, 24, "④  INTERACTION   ·   api.py  +  UI/  (React PWA)", "interaction")
    box(ax, 4,  40, 14, 7, "User\n(PWA)", accent=A["interaction"], bold=True, fs=10)
    box(ax, 20, 40, 18, 7, "Jeeves router\n(qwen3.7-plus)", accent=A["interaction"], bold=True, fs=10)
    box(ax, 40, 39, 56, 9,
        "intents:   object   ·   time   ·   semantic   ·   general   ·   reminder",
        accent=A["interaction"], fs=10.5, ha="center")
    box(ax, 4, 28.5, 44, 9,
        "object → vision presence check → Qwen spatial\nbox (qwen3-vl-plus) → highlighted PNG\n"
        "semantic → Chroma recall → judge → budgeted\nsynthesis  (exposes recall_debug)",
        accent=A["interaction"], fs=9, ha="left")
    box(ax, 51, 28.5, 45, 9,
        "Proactive channel\nsafety · morning report · reminders\n"
        "→ /proactive/pending poll (5 s)  +  Web Push wake-up",
        accent=A["interaction"], fs=9.5)
    arrow(ax, (18, 43.5), (20, 43.5), color=A["interaction"])
    arrow(ax, (38, 43.5), (40, 43.5), color=A["interaction"])
    arrow(ax, (26, 54.5), (26, 47), color="#44515E", dashed=True,
          label="recall", label_dxy=(3, 0))
    arrow(ax, (73, 54.5), (73, 37.5), color="#44515E", dashed=True,
          label="proactive triggers", label_dxy=(9, 0))

    # ---- PROVIDER LAYER (foundation) -----------------------------------
    band(ax, 2, 2, 96, 22, "⑤  PROVIDER LAYER   ·   llm/client.py", "provider")
    box(ax, 4, 12.5, 92, 8.5,
        "one async OpenAI-protocol client   ·   LLM_PROVIDER = qwen   "
        "(DashScope compatible-mode)   ·   provider is hot-swappable (openai / ollama)",
        accent=A["provider"], fs=11, bold=True)
    box(ax, 4, 3.5, 92, 7.2,
        "text  qwen3.7-plus     ·     vision  qwen3-vl-flash     ·     spatial  qwen3-vl-plus     ·     "
        "video  qwen3-vl-flash\nembeddings  text-embedding-v4 (1024d)     ·     ASR  qwen3-asr-flash"
        "     ·     Gemini fallback:  video + spatial",
        accent=A["provider"], fs=10, tc=INK)
    arrow(ax, (30, 24), (30, 28.5), color=A["provider"], dashed=True, lw=1.5,
          label="serves", label_dxy=(-4, 0))
    ax.text(78, 22.4, "↑  provider client serves ingestion ②  and interaction ④",
            ha="center", va="center", fontsize=9.5, style="italic",
            color=A["provider"], zorder=5)

    out = DEMO_DIR / "memoria-architecture-qwen-detailed.png"
    fig.savefig(out, dpi=150, facecolor=WHITE)
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    headline()
    detailed()
