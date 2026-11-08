"""
ClassPulse AI - Matplotlib Visualization Engine
Generates individual small graphs for every data facet:
- Attendance breakdown & rate
- Exam / mock test scores distribution
- Financial collections vs outstanding fees
- Enquiries vs Admissions conversion funnel
- AI Student Risk tier segmentation
- Pass probability distribution
- Correlation scatter: Attendance vs Exam Scores

And one comprehensive Master Graph combining all details into a unified executive dashboard.
Refined with uncluttered typography, spacious padding, and clean modern aesthetic.
"""

import base64
import io
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend safe for web servers
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.ticker as ticker
import numpy as np

# Apply clean global font and rendering defaults
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Segoe UI", "DejaVu Sans", "Arial", "Helvetica", "sans-serif"]
plt.rcParams["figure.autolayout"] = False

# Modern scientific palette definition
COLOR_PRIMARY = "#2563eb"     # Royal Blue
COLOR_SUCCESS = "#10b981"     # Emerald Green
COLOR_WARNING = "#f59e0b"     # Amber
COLOR_DANGER = "#ef4444"      # Crimson Red
COLOR_PURPLE = "#8b5cf6"      # Indigo / Purple
COLOR_TEAL = "#06b6d4"        # Cyan / Teal
COLOR_BG = "#ffffff"
COLOR_CARD_BG = "#f8fafc"
COLOR_GRID = "#e2e8f0"
COLOR_TEXT_MAIN = "#0f172a"
COLOR_TEXT_MUTED = "#64748b"


def _fig_to_bytes(fig: plt.Figure, dpi: int = 140, format: str = "png") -> bytes:
    """Helper to convert a Matplotlib figure into raw bytes and close the figure."""
    buf = io.BytesIO()
    fig.savefig(buf, format=format, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _fig_to_base64(fig: plt.Figure, dpi: int = 140, format: str = "png") -> str:
    """Helper to convert a Matplotlib figure into a base64 encoded data URI."""
    raw = _fig_to_bytes(fig, dpi=dpi, format=format)
    encoded = base64.b64encode(raw).decode("utf-8")
    return f"data:image/{format};base64,{encoded}"


def _extract_dataset_metrics(records: List[Dict[str, Any]], ml_predictions: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Synthesizes numerical aggregations from records and ML predictions
    to power both small individual graphs and the master graph.
    Supports both standard ClassPulse records and arbitrary flat spreadsheet rows.
    """
    from decimal import Decimal

    # Auto-convert arbitrary flat spreadsheet rows if needed
    if records and not any("record_type" in r for r in records[:5]):
        from app.ml_model import UniversalSheetAdapter
        if not UniversalSheetAdapter.is_standard_classpulse(list(records[0].keys())):
            records = UniversalSheetAdapter.convert_flat_to_classpulse_records(records)

    # Base record collections
    enquiries = [r for r in records if (r.get("record_type") or "").strip().lower() == "enquiry"]
    admissions = [r for r in records if (r.get("record_type") or "").strip().lower() == "student"]
    obligations_raw = [r for r in records if (r.get("record_type") or "").strip().lower() == "obligation"]
    payments_raw = [r for r in records if (r.get("record_type") or "").strip().lower() == "payment" and (r.get("status") or "").strip().lower() == "successful"]
    attendance_raw = [r for r in records if (r.get("record_type") or "").strip().lower() == "attendance"]
    exams_raw = [r for r in records if (r.get("record_type") or "").strip().lower() in ("exam", "test", "score")]

    # Financial sums
    total_obligations = float(sum((Decimal(str(r.get("amount") or 0)) for r in obligations_raw), Decimal()))
    total_payments = float(sum((Decimal(str(r.get("amount") or 0)) - Decimal(str(r.get("refund_amount") or 0)) for r in payments_raw), Decimal()))
    outstanding_fees = max(0.0, total_obligations - total_payments)

    # Attendance counts
    present_count = sum(1 for r in attendance_raw if (r.get("status") or "").strip().lower() == "present")
    absent_count = sum(1 for r in attendance_raw if (r.get("status") or "").strip().lower() == "absent")
    excused_count = sum(1 for r in attendance_raw if (r.get("status") or "").strip().lower() == "excused")
    valid_att_count = present_count + absent_count
    attendance_rate = round((present_count / valid_att_count * 100.0), 1) if valid_att_count > 0 else 0.0

    # Exam scores
    exam_scores = []
    for r in exams_raw:
        try:
            score = float(r.get("amount") or 0)
            exam_scores.append(score)
        except (ValueError, TypeError):
            pass
    avg_mock_score = round(float(np.mean(exam_scores)), 1) if exam_scores else None

    # Conversion
    enq_count = len(enquiries)
    adm_count = len(admissions)
    conversion_rate = round(100.0 * adm_count / enq_count, 1) if enq_count > 0 else 0.0

    # ML predictions synthesis if not provided
    if ml_predictions is None:
        try:
            from app.ml_model import predictor
            ml_predictions = predictor.predict_cohort(records)
        except Exception:
            ml_predictions = {"summary": {}, "predictions": []}

    preds = ml_predictions.get("predictions", [])
    safe_count = sum(1 for p in preds if p.get("risk_level", "").startswith("Safe"))
    borderline_count = sum(1 for p in preds if p.get("risk_level", "").startswith("Borderline"))
    high_risk_count = sum(1 for p in preds if p.get("risk_level", "").startswith("High Risk"))
    probabilities = [float(p.get("pass_probability", 0)) for p in preds if "pass_probability" in p]
    avg_pass_prob = round(float(np.mean(probabilities)), 1) if probabilities else 0.0

    # Student-level scatter data
    scatter_students = []
    for p in preds:
        att = p.get("attendance_rate")
        score = p.get("avg_mock_score")
        prob = p.get("pass_probability", 50.0)
        risk = p.get("risk_level", "Borderline")
        sid = p.get("student_id", "")
        if att is not None and score is not None:
            scatter_students.append({
                "student_id": sid,
                "attendance": float(att),
                "score": float(score),
                "pass_probability": float(prob),
                "risk_level": risk
            })

    return {
        "enquiries_count": enq_count,
        "admissions_count": adm_count,
        "conversion_rate": conversion_rate,
        "total_obligations": total_obligations,
        "total_payments": total_payments,
        "outstanding_fees": outstanding_fees,
        "present_count": present_count,
        "absent_count": absent_count,
        "excused_count": excused_count,
        "attendance_rate": attendance_rate,
        "exam_scores": exam_scores,
        "avg_mock_score": avg_mock_score,
        "safe_count": safe_count,
        "borderline_count": borderline_count,
        "high_risk_count": high_risk_count,
        "probabilities": probabilities,
        "avg_pass_prob": avg_pass_prob,
        "scatter_students": scatter_students,
        "total_students": len(preds)
    }


def _setup_plot_style(ax: plt.Axes, title: str, xlabel: str = "", ylabel: str = "", title_pad: int = 12) -> None:
    """Applies a spacious, uncluttered aesthetic with generous padding."""
    ax.set_facecolor(COLOR_BG)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_GRID)
    ax.spines["bottom"].set_color(COLOR_GRID)
    ax.spines["left"].set_linewidth(0.8)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(colors=COLOR_TEXT_MUTED, labelsize=8.5, length=3, width=0.8)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9, fontweight="600", color=COLOR_TEXT_MAIN, labelpad=7)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, fontweight="600", color=COLOR_TEXT_MAIN, labelpad=7)
    if title:
        ax.set_title(title, fontsize=10.5, fontweight="700", color=COLOR_TEXT_MAIN, pad=title_pad, loc="left")
    ax.grid(axis="y", linestyle="--", alpha=0.35, color=COLOR_GRID, linewidth=0.7)


# ============================================================================
# INDIVIDUAL SMALL GRAPHS (One small graph for every data facet)
# Spacious 5.6 x 4.0 in layout with clean padding and no text collisions.
# ============================================================================

def generate_attendance_chart(records: List[Dict[str, Any]], ml_predictions: Optional[Dict[str, Any]] = None, as_base64: bool = False) -> Any:
    """Small graph 1: Attendance breakdown (Present, Absent, Excused) & Rate."""
    metrics = _extract_dataset_metrics(records, ml_predictions)
    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=140)
    fig.patch.set_facecolor(COLOR_BG)

    p, a, e = metrics["present_count"], metrics["absent_count"], metrics["excused_count"]
    total = p + a + e

    if total == 0:
        ax.text(0.5, 0.5, "No Attendance Records\nAvailable", ha="center", va="center", color=COLOR_TEXT_MUTED, fontsize=11)
        ax.axis("off")
    else:
        labels = ["Present", "Absent", "Excused"]
        counts = [p, a, e]
        colors = [COLOR_SUCCESS, COLOR_DANGER, COLOR_WARNING]
        
        filtered = [(l, c, col) for l, c, col in zip(labels, counts, colors) if c > 0]
        f_labels = [f"{x[0]} ({x[1]})" for x in filtered]
        f_counts = [x[1] for x in filtered]
        f_colors = [x[2] for x in filtered]

        wedges, texts, autotexts = ax.pie(
            f_counts,
            autopct=lambda pct: f"{pct:.0f}%" if pct >= 8 else "",
            pctdistance=0.72,
            startangle=140,
            colors=f_colors,
            wedgeprops=dict(width=0.40, edgecolor="white", linewidth=2.5)
        )
        for at in autotexts:
            at.set_color("white")
            at.set_fontsize(8.5)
            at.set_fontweight("bold")

        # Center KPI ring with clear vertical separation
        ax.text(0, 0.08, f"{metrics['attendance_rate']:.1f}%", ha="center", va="center", fontsize=15, fontweight="700", color=COLOR_SUCCESS)
        ax.text(0, -0.12, "Attendance Rate", ha="center", va="center", fontsize=8, fontweight="normal", color=COLOR_TEXT_MUTED)

        # Uncluttered legend below the donut
        ax.legend(wedges, f_labels, loc="lower center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False, fontsize=8)

    ax.set_title("Attendance Breakdown & Rate", fontsize=10.5, fontweight="700", color=COLOR_TEXT_MAIN, pad=12, loc="left")
    return _fig_to_base64(fig) if as_base64 else _fig_to_bytes(fig)


def generate_exam_chart(records: List[Dict[str, Any]], ml_predictions: Optional[Dict[str, Any]] = None, as_base64: bool = False) -> Any:
    """Small graph 2: Exam & Mock Test Score Distribution."""
    metrics = _extract_dataset_metrics(records, ml_predictions)
    scores = metrics["exam_scores"]

    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=140)
    fig.patch.set_facecolor(COLOR_BG)

    if not scores:
        preds = (ml_predictions or {}).get("predictions", [])
        scores = [p["avg_mock_score"] for p in preds if p.get("avg_mock_score") is not None]

    if not scores:
        ax.text(0.5, 0.5, "No Exam / Mock Score\nRecords Available", ha="center", va="center", color=COLOR_TEXT_MUTED, fontsize=11)
        ax.axis("off")
    else:
        _setup_plot_style(ax, "Mock & Exam Score Distribution", xlabel="Score (0 to 100)", ylabel="Test Submissions")
        
        bins = np.arange(0, 105, 10)
        n, b, patches_list = ax.hist(scores, bins=bins, color=COLOR_PRIMARY, edgecolor="white", linewidth=1.2, rwidth=0.82)
        
        for patch, left_edge in zip(patches_list, bins[:-1]):
            if left_edge >= 60:
                patch.set_facecolor(COLOR_SUCCESS)
            elif left_edge >= 40:
                patch.set_facecolor(COLOR_WARNING)
            else:
                patch.set_facecolor(COLOR_DANGER)

        # Headroom so labels never touch top
        max_n = max(n) if len(n) > 0 and max(n) > 0 else 5
        ax.set_ylim(0, max_n * 1.35)

        # Clean count on top of bars
        for count, rect in zip(n, patches_list):
            if count > 0:
                ax.annotate(f"{int(count)}", xy=(rect.get_x() + rect.get_width()/2, count),
                            xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                            fontsize=8, fontweight="600", color=COLOR_TEXT_MUTED)

        mean_score = float(np.mean(scores))
        ax.axvline(mean_score, color=COLOR_TEXT_MAIN, linestyle="--", linewidth=1.6, label=f"Mean: {mean_score:.1f}")
        ax.axvline(50, color=COLOR_DANGER, linestyle=":", linewidth=1.4, label="Pass Cutoff: 50")
        ax.legend(loc="upper right", frameon=True, facecolor=COLOR_CARD_BG, edgecolor=COLOR_GRID, framealpha=0.9, fontsize=8)
        ax.set_xlim(0, 100)

    return _fig_to_base64(fig) if as_base64 else _fig_to_bytes(fig)


def generate_financials_chart(records: List[Dict[str, Any]], ml_predictions: Optional[Dict[str, Any]] = None, as_base64: bool = False) -> Any:
    """Small graph 3: Financials (Obligations, Collected, Outstanding)."""
    metrics = _extract_dataset_metrics(records, ml_predictions)
    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=140)
    fig.patch.set_facecolor(COLOR_BG)

    ob, paid, due = metrics["total_obligations"], metrics["total_payments"], metrics["outstanding_fees"]
    
    if ob == 0 and paid == 0 and due == 0:
        ax.text(0.5, 0.5, "No Fee / Payment\nRecords Available", ha="center", va="center", color=COLOR_TEXT_MUTED, fontsize=11)
        ax.axis("off")
    else:
        _setup_plot_style(ax, "Fee Obligations & Collections", ylabel="Amount (INR)")
        categories = ["Obligations", "Collected", "Outstanding"]
        values = [ob, paid, due]
        colors = [COLOR_PRIMARY, COLOR_SUCCESS, COLOR_DANGER]

        bars = ax.bar(categories, values, color=colors, width=0.48, edgecolor="white", linewidth=1.5)
        
        max_val = max(values) if values and max(values) > 0 else 1000
        ax.set_ylim(0, max_val * 1.35)

        for bar in bars:
            height = bar.get_height()
            label = f"₹{height:,.0f}" if height < 50000 else f"₹{height/1000:,.1f}k"
            ax.annotate(
                label,
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center", va="bottom",
                fontsize=8.5, fontweight="600",
                color=COLOR_TEXT_MAIN
            )

        # Recovery rate badge positioned with comfortable padding
        recovery_pct = round(100.0 * paid / ob, 1) if ob > 0 else 100.0
        ax.text(0.96, 0.92, f"Recovery: {recovery_pct}%", transform=ax.transAxes, ha="right", va="top",
                fontsize=8.5, fontweight="600", color=COLOR_SUCCESS if recovery_pct >= 75 else COLOR_WARNING,
                bbox=dict(boxstyle="round,pad=0.35", fc=COLOR_CARD_BG, ec=COLOR_GRID, lw=0.8))

    return _fig_to_base64(fig) if as_base64 else _fig_to_bytes(fig)


def generate_conversion_chart(records: List[Dict[str, Any]], ml_predictions: Optional[Dict[str, Any]] = None, as_base64: bool = False) -> Any:
    """Small graph 4: Admissions Funnel (Enquiries vs Admissions)."""
    metrics = _extract_dataset_metrics(records, ml_predictions)
    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=140)
    fig.patch.set_facecolor(COLOR_BG)

    enq, adm = metrics["enquiries_count"], metrics["admissions_count"]

    if enq == 0 and adm == 0:
        ax.text(0.5, 0.5, "No Admissions or Enquiry\nRecords Available", ha="center", va="center", color=COLOR_TEXT_MUTED, fontsize=11)
        ax.axis("off")
    else:
        _setup_plot_style(ax, "Admissions Conversion Funnel", xlabel="Student Count")
        stages = ["Enrolled", "Inquiries"]
        counts = [adm, enq]
        colors = [COLOR_PURPLE, COLOR_TEAL]

        bars = ax.barh(stages, counts, color=colors, height=0.42, edgecolor="white", linewidth=1.5)
        
        max_c = max(counts) if counts and max(counts) > 0 else 10
        ax.set_xlim(0, max_c * 1.40)

        for idx, bar in enumerate(bars):
            width = bar.get_width()
            label = f"{int(width)} Students" if idx == 0 else f"{int(width)} Leads"
            ax.annotate(
                label,
                xy=(width, bar.get_y() + bar.get_height() / 2),
                xytext=(8, 0),
                textcoords="offset points",
                ha="left", va="center",
                fontsize=8.5, fontweight="600",
                color=COLOR_TEXT_MAIN
            )

        conv_pct = metrics["conversion_rate"]
        ax.text(0.96, 0.90, f"Conversion: {conv_pct}%", transform=ax.transAxes, ha="right", va="top",
                fontsize=8.5, fontweight="600", color=COLOR_PURPLE,
                bbox=dict(boxstyle="round,pad=0.35", fc=COLOR_CARD_BG, ec=COLOR_GRID, lw=0.8))

        ax.grid(axis="x", linestyle="--", alpha=0.35, color=COLOR_GRID)
        ax.yaxis.grid(False)

    return _fig_to_base64(fig) if as_base64 else _fig_to_bytes(fig)


def generate_risk_chart(records: List[Dict[str, Any]], ml_predictions: Optional[Dict[str, Any]] = None, as_base64: bool = False) -> Any:
    """Small graph 5: AI Student Risk Segmentation (Safe, Borderline, High Risk)."""
    metrics = _extract_dataset_metrics(records, ml_predictions)
    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=140)
    fig.patch.set_facecolor(COLOR_BG)

    safe, b_line, high = metrics["safe_count"], metrics["borderline_count"], metrics["high_risk_count"]
    total = safe + b_line + high

    if total == 0:
        ax.text(0.5, 0.5, "No Student Risk\nPredictions Available", ha="center", va="center", color=COLOR_TEXT_MUTED, fontsize=11)
        ax.axis("off")
    else:
        _setup_plot_style(ax, "AI Student Risk Tiers", ylabel="Student Count")
        tiers = ["High Risk\n(<50%)", "Borderline\n(50–75%)", "Safe\n(>75%)"]
        counts = [high, b_line, safe]
        colors = [COLOR_DANGER, COLOR_WARNING, COLOR_SUCCESS]

        bars = ax.bar(tiers, counts, color=colors, width=0.48, edgecolor="white", linewidth=1.5)
        
        max_h = max(counts) if counts and max(counts) > 0 else 10
        ax.set_ylim(0, max_h * 1.32)

        for bar in bars:
            height = bar.get_height()
            pct = (height / total * 100.0) if total > 0 else 0
            ax.annotate(
                f"{int(height)} ({pct:.0f}%)",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center", va="bottom",
                fontsize=8.5, fontweight="600",
                color=COLOR_TEXT_MAIN
            )

    return _fig_to_base64(fig) if as_base64 else _fig_to_bytes(fig)


def generate_probability_chart(records: List[Dict[str, Any]], ml_predictions: Optional[Dict[str, Any]] = None, as_base64: bool = False) -> Any:
    """Small graph 6: Exam Pass Probability Spread."""
    metrics = _extract_dataset_metrics(records, ml_predictions)
    probs = metrics["probabilities"]

    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=140)
    fig.patch.set_facecolor(COLOR_BG)

    if not probs:
        ax.text(0.5, 0.5, "No Pass Probability\nData Available", ha="center", va="center", color=COLOR_TEXT_MUTED, fontsize=11)
        ax.axis("off")
    else:
        _setup_plot_style(ax, "Pass Probability Spread", xlabel="Predicted Pass Probability (%)", ylabel="Student Count")
        
        bins = np.linspace(0, 100, 11)
        n, b, patches_list = ax.hist(probs, bins=bins, color=COLOR_PURPLE, edgecolor="white", linewidth=1.2, rwidth=0.82)

        for patch, left_edge in zip(patches_list, bins[:-1]):
            if left_edge >= 70:
                patch.set_facecolor(COLOR_SUCCESS)
            elif left_edge >= 50:
                patch.set_facecolor(COLOR_WARNING)
            else:
                patch.set_facecolor(COLOR_DANGER)

        max_n = max(n) if len(n) > 0 and max(n) > 0 else 5
        ax.set_ylim(0, max_n * 1.35)

        avg_p = metrics["avg_pass_prob"]
        ax.axvline(avg_p, color=COLOR_TEXT_MAIN, linestyle="--", linewidth=1.6, label=f"Cohort Mean: {avg_p:.1f}%")
        ax.legend(loc="upper left", frameon=True, facecolor=COLOR_CARD_BG, edgecolor=COLOR_GRID, framealpha=0.9, fontsize=8)
        ax.set_xlim(0, 100)

    return _fig_to_base64(fig) if as_base64 else _fig_to_bytes(fig)


def generate_scatter_chart(records: List[Dict[str, Any]], ml_predictions: Optional[Dict[str, Any]] = None, as_base64: bool = False) -> Any:
    """Small graph 7: Correlation Scatter (Attendance Rate vs Exam Score)."""
    metrics = _extract_dataset_metrics(records, ml_predictions)
    scatter_data = metrics["scatter_students"]

    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=140)
    fig.patch.set_facecolor(COLOR_BG)

    if not scatter_data:
        ax.text(0.5, 0.5, "Insufficient Pairwise Data\nfor Scatter Plot", ha="center", va="center", color=COLOR_TEXT_MUTED, fontsize=11)
        ax.axis("off")
    else:
        _setup_plot_style(ax, "Attendance vs. Mock Exam Score", xlabel="Attendance Rate (%)", ylabel="Mock Score (%)")
        
        att_vals = [s["attendance"] for s in scatter_data]
        score_vals = [s["score"] for s in scatter_data]
        colors = []
        for s in scatter_data:
            risk = s["risk_level"]
            if risk.startswith("Safe"):
                colors.append(COLOR_SUCCESS)
            elif risk.startswith("Borderline"):
                colors.append(COLOR_WARNING)
            else:
                colors.append(COLOR_DANGER)

        ax.scatter(att_vals, score_vals, c=colors, s=55, alpha=0.85, edgecolors="white", linewidth=0.8)
        
        ax.axvline(75, color=COLOR_PRIMARY, linestyle=":", linewidth=1.2, alpha=0.7, label="75% Attendance Min")
        ax.axhline(50, color=COLOR_DANGER, linestyle=":", linewidth=1.2, alpha=0.7, label="50% Score Cutoff")
        ax.set_xlim(0, 105)
        ax.set_ylim(0, 105)
        ax.legend(loc="lower right", frameon=True, facecolor="white", edgecolor=COLOR_GRID, framealpha=0.92, fontsize=7.5)

    return _fig_to_base64(fig) if as_base64 else _fig_to_bytes(fig)


# ============================================================================
# MASTER GRAPH (One Master Graph for Every Detail)
# Spacious 18 x 12 in layout with distinct KPI chips, ample margins, and no overlap.
# ============================================================================

def generate_master_graph(
    records: List[Dict[str, Any]],
    ml_predictions: Optional[Dict[str, Any]] = None,
    centre_name: str = "ClassPulse Analytics",
    as_base64: bool = False
) -> Any:
    """
    Generates one master graph for every detail.
    Combines:
    1. Header summary banner (Centre name, total students, pass rate, attendance, fee collection)
    2. Panel 1: Attendance Distribution & Status
    3. Panel 2: Exam & Mock Performance Histogram
    4. Panel 3: Financial Obligations vs Collections
    5. Panel 4: Admissions Conversion Funnel
    6. Panel 5: AI Student Risk Tiers (Safe / Borderline / High Risk)
    7. Panel 6: Correlation Scatter (Attendance vs Mock Score with Risk Coloring)
    """
    metrics = _extract_dataset_metrics(records, ml_predictions)

    # Master Figure dimensions: 18 x 12 inches for maximum legibility and zero clutter
    fig = plt.figure(figsize=(18, 12), dpi=150)
    fig.patch.set_facecolor(COLOR_BG)

    # Grid layout: generous horizontal and vertical spacing to prevent any text overlapping
    gs = fig.add_gridspec(2, 3, top=0.86, bottom=0.07, left=0.06, right=0.95, hspace=0.48, wspace=0.32)

    # ------------------------------------------------------------------------
    # TOP EXECUTIVE HEADER BANNER (Clean left title + distinct right KPI chips)
    # ------------------------------------------------------------------------
    banner_ax = fig.add_axes([0.06, 0.89, 0.89, 0.08])
    banner_ax.set_facecolor(COLOR_CARD_BG)
    banner_ax.spines["top"].set_color(COLOR_GRID)
    banner_ax.spines["bottom"].set_color(COLOR_GRID)
    banner_ax.spines["left"].set_color(COLOR_PRIMARY)
    banner_ax.spines["left"].set_linewidth(4)
    banner_ax.spines["right"].set_color(COLOR_GRID)
    banner_ax.set_xticks([])
    banner_ax.set_yticks([])

    # Banner title and clean subtitle on left
    banner_ax.text(0.015, 0.65, f"{centre_name.upper()} · EXECUTIVE INTELLIGENCE DASHBOARD",
                   fontsize=13, fontweight="700", color=COLOR_TEXT_MAIN, va="center")
    banner_ax.text(0.015, 0.28, "Unified Academic Performance, Financial Health & AI Exam Pass Predictor Overview",
                   fontsize=8.5, color=COLOR_TEXT_MUTED, va="center")

    # Distinct, well-spaced summary KPI chips on the right
    chip_items = [
        ("Students", str(metrics["total_students"])),
        ("Pass Rate", f"{metrics['avg_pass_prob']:.1f}%"),
        ("Attendance", f"{metrics['attendance_rate']:.1f}%"),
        ("Collected", f"₹{metrics['total_payments']/1000:,.1f}k" if metrics['total_payments'] >= 10000 else f"₹{metrics['total_payments']:,.0f}")
    ]
    
    chip_x = 0.985
    for label, val in reversed(chip_items):
        txt = f"{label}: {val}"
        t_obj = banner_ax.text(chip_x, 0.50, txt, fontsize=9, fontweight="700",
                               color=COLOR_PRIMARY, ha="right", va="center",
                               bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=COLOR_GRID, lw=1.0))
        chip_x -= 0.125

    # ------------------------------------------------------------------------
    # SUBPLOT 1: ATTENDANCE REGULARITY (TOP-LEFT)
    # ------------------------------------------------------------------------
    ax1 = fig.add_subplot(gs[0, 0])
    p, a, e = metrics["present_count"], metrics["absent_count"], metrics["excused_count"]
    tot_att = p + a + e
    if tot_att == 0:
        ax1.text(0.5, 0.5, "No Attendance Records", ha="center", va="center", color=COLOR_TEXT_MUTED)
        ax1.axis("off")
    else:
        labels = ["Present", "Absent", "Excused"]
        counts = [p, a, e]
        colors = [COLOR_SUCCESS, COLOR_DANGER, COLOR_WARNING]
        f_filtered = [(l, c, col) for l, c, col in zip(labels, counts, colors) if c > 0]
        
        wedges, texts, autotexts = ax1.pie(
            [x[1] for x in f_filtered],
            autopct=lambda pct: f"{pct:.0f}%" if pct >= 8 else "",
            pctdistance=0.72,
            startangle=140,
            colors=[x[2] for x in f_filtered],
            wedgeprops=dict(width=0.40, edgecolor="white", linewidth=2.5)
        )
        for at in autotexts:
            at.set_color("white")
            at.set_fontsize(8.5)
            at.set_fontweight("bold")

        ax1.text(0, 0.08, f"{metrics['attendance_rate']:.1f}%", ha="center", va="center", fontsize=15, fontweight="700", color=COLOR_SUCCESS)
        ax1.text(0, -0.12, "Attendance Rate", ha="center", va="center", fontsize=8, color=COLOR_TEXT_MUTED)
        
        leg_labels = [f"{x[0]} ({x[1]})" for x in f_filtered]
        ax1.legend(wedges, leg_labels, loc="lower center", bbox_to_anchor=(0.5, -0.15), ncol=3, frameon=False, fontsize=8)
    
    ax1.set_title("1. Attendance Distribution & Regularity", fontsize=10.5, fontweight="700", color=COLOR_TEXT_MAIN, pad=12, loc="left")

    # ------------------------------------------------------------------------
    # SUBPLOT 2: EXAM & MOCK PERFORMANCE (TOP-MIDDLE)
    # ------------------------------------------------------------------------
    ax2 = fig.add_subplot(gs[0, 1])
    scores = metrics["exam_scores"]
    if not scores:
        preds = (ml_predictions or {}).get("predictions", [])
        scores = [p["avg_mock_score"] for p in preds if p.get("avg_mock_score") is not None]
    
    if not scores:
        ax2.text(0.5, 0.5, "No Exam Scores Recorded", ha="center", va="center", color=COLOR_TEXT_MUTED)
        ax2.axis("off")
    else:
        _setup_plot_style(ax2, "2. Exam & Mock Test Score Spread", xlabel="Score (0 to 100)", ylabel="Test Submissions")
        bins = np.arange(0, 105, 10)
        n, b, patches_list = ax2.hist(scores, bins=bins, color=COLOR_PRIMARY, edgecolor="white", linewidth=1.2, rwidth=0.82)
        for patch, left_edge in zip(patches_list, bins[:-1]):
            if left_edge >= 60:
                patch.set_facecolor(COLOR_SUCCESS)
            elif left_edge >= 40:
                patch.set_facecolor(COLOR_WARNING)
            else:
                patch.set_facecolor(COLOR_DANGER)
        
        max_n = max(n) if len(n) > 0 and max(n) > 0 else 5
        ax2.set_ylim(0, max_n * 1.35)

        for count, rect in zip(n, patches_list):
            if count > 0:
                ax2.annotate(f"{int(count)}", xy=(rect.get_x() + rect.get_width()/2, count),
                             xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                             fontsize=8, fontweight="600", color=COLOR_TEXT_MUTED)

        mean_score = float(np.mean(scores))
        ax2.axvline(mean_score, color=COLOR_TEXT_MAIN, linestyle="--", linewidth=1.6, label=f"Mean: {mean_score:.1f}")
        ax2.axvline(50, color=COLOR_DANGER, linestyle=":", linewidth=1.4, label="Pass Mark: 50")
        ax2.legend(loc="upper right", frameon=True, facecolor=COLOR_CARD_BG, edgecolor=COLOR_GRID, framealpha=0.9, fontsize=8)
        ax2.set_xlim(0, 100)

    # ------------------------------------------------------------------------
    # SUBPLOT 3: FINANCIAL HEALTH (TOP-RIGHT)
    # ------------------------------------------------------------------------
    ax3 = fig.add_subplot(gs[0, 2])
    ob, paid, due = metrics["total_obligations"], metrics["total_payments"], metrics["outstanding_fees"]
    if ob == 0 and paid == 0:
        ax3.text(0.5, 0.5, "No Fee Data Logged", ha="center", va="center", color=COLOR_TEXT_MUTED)
        ax3.axis("off")
    else:
        _setup_plot_style(ax3, "3. Fee Obligations vs Collections", ylabel="Amount (INR)")
        cats = ["Obligations", "Collected", "Outstanding"]
        vals = [ob, paid, due]
        cols = [COLOR_PRIMARY, COLOR_SUCCESS, COLOR_DANGER]
        bars3 = ax3.bar(cats, vals, color=cols, width=0.48, edgecolor="white", linewidth=1.5)
        
        max_val3 = max(vals) if vals and max(vals) > 0 else 1000
        ax3.set_ylim(0, max_val3 * 1.35)

        for b in bars3:
            h = b.get_height()
            label = f"₹{h:,.0f}" if h < 50000 else f"₹{h/1000:,.1f}k"
            ax3.annotate(label,
                         xy=(b.get_x() + b.get_width() / 2, h), xytext=(0, 5),
                         textcoords="offset points", ha="center", va="bottom",
                         fontsize=8.5, fontweight="600", color=COLOR_TEXT_MAIN)
        
        recovery_pct = round(100.0 * paid / ob, 1) if ob > 0 else 100.0
        ax3.text(0.96, 0.92, f"Recovery: {recovery_pct}%", transform=ax3.transAxes, ha="right", va="top",
                 fontsize=8.5, fontweight="600", color=COLOR_SUCCESS if recovery_pct >= 75 else COLOR_WARNING,
                 bbox=dict(boxstyle="round,pad=0.35", fc=COLOR_CARD_BG, ec=COLOR_GRID, lw=0.8))

    # ------------------------------------------------------------------------
    # SUBPLOT 4: ADMISSIONS CONVERSION FUNNEL (BOTTOM-LEFT)
    # ------------------------------------------------------------------------
    ax4 = fig.add_subplot(gs[1, 0])
    enq, adm = metrics["enquiries_count"], metrics["admissions_count"]
    if enq == 0 and adm == 0:
        ax4.text(0.5, 0.5, "No Admissions Data", ha="center", va="center", color=COLOR_TEXT_MUTED)
        ax4.axis("off")
    else:
        _setup_plot_style(ax4, "4. Inquiries & Admissions Conversion", xlabel="Student Count")
        bars4 = ax4.barh(["Enrolled", "Inquiries"], [adm, enq], color=[COLOR_PURPLE, COLOR_TEAL], height=0.42, edgecolor="white", linewidth=1.5)
        
        max_c4 = max(enq, adm, 1)
        ax4.set_xlim(0, max_c4 * 1.40)

        for idx, b in enumerate(bars4):
            w = b.get_width()
            lbl = f"{int(w)} Enrolled" if idx == 0 else f"{int(w)} Leads"
            ax4.annotate(lbl,
                         xy=(w, b.get_y() + b.get_height() / 2), xytext=(8, 0),
                         textcoords="offset points", ha="left", va="center",
                         fontsize=8.5, fontweight="600", color=COLOR_TEXT_MAIN)
        
        ax4.text(0.96, 0.90, f"Conversion: {metrics['conversion_rate']}%", transform=ax4.transAxes,
                 ha="right", va="top", fontsize=8.5, fontweight="600", color=COLOR_PURPLE,
                 bbox=dict(boxstyle="round,pad=0.35", fc=COLOR_CARD_BG, ec=COLOR_GRID, lw=0.8))
        ax4.grid(axis="x", linestyle="--", alpha=0.35, color=COLOR_GRID)
        ax4.yaxis.grid(False)

    # ------------------------------------------------------------------------
    # SUBPLOT 5: AI STUDENT RISK TIERS (BOTTOM-MIDDLE)
    # ------------------------------------------------------------------------
    ax5 = fig.add_subplot(gs[1, 1])
    safe, b_line, high = metrics["safe_count"], metrics["borderline_count"], metrics["high_risk_count"]
    tot_risk = safe + b_line + high
    if tot_risk == 0:
        ax5.text(0.5, 0.5, "No AI Prediction Data", ha="center", va="center", color=COLOR_TEXT_MUTED)
        ax5.axis("off")
    else:
        _setup_plot_style(ax5, "5. AI Exam Pass Risk Segmentation", ylabel="Student Count")
        tiers = ["High Risk\n(<50%)", "Borderline\n(50–75%)", "Safe\n(>75%)"]
        risk_vals = [high, b_line, safe]
        r_cols = [COLOR_DANGER, COLOR_WARNING, COLOR_SUCCESS]
        bars5 = ax5.bar(tiers, risk_vals, color=r_cols, width=0.48, edgecolor="white", linewidth=1.5)
        
        max_h5 = max(risk_vals) if risk_vals and max(risk_vals) > 0 else 10
        ax5.set_ylim(0, max_h5 * 1.32)

        for b in bars5:
            h = b.get_height()
            pct = (h / tot_risk * 100.0) if tot_risk > 0 else 0
            ax5.annotate(f"{int(h)} ({pct:.0f}%)",
                         xy=(b.get_x() + b.get_width() / 2, h), xytext=(0, 5),
                         textcoords="offset points", ha="center", va="bottom",
                         fontsize=8.5, fontweight="600", color=COLOR_TEXT_MAIN)

    # ------------------------------------------------------------------------
    # SUBPLOT 6: CORRELATION MATRIX (BOTTOM-RIGHT)
    # ------------------------------------------------------------------------
    ax6 = fig.add_subplot(gs[1, 2])
    scatter_data = metrics["scatter_students"]
    if not scatter_data:
        ax6.text(0.5, 0.5, "No Paired Student Data", ha="center", va="center", color=COLOR_TEXT_MUTED)
        ax6.axis("off")
    else:
        _setup_plot_style(ax6, "6. Attendance vs. Score Correlation", xlabel="Attendance Rate (%)", ylabel="Mock Score (%)")
        att_vals = [s["attendance"] for s in scatter_data]
        score_vals = [s["score"] for s in scatter_data]
        colors = []
        for s in scatter_data:
            risk = s["risk_level"]
            if risk.startswith("Safe"):
                colors.append(COLOR_SUCCESS)
            elif risk.startswith("Borderline"):
                colors.append(COLOR_WARNING)
            else:
                colors.append(COLOR_DANGER)

        ax6.scatter(att_vals, score_vals, c=colors, s=55, alpha=0.85, edgecolors="white", linewidth=0.8)
        ax6.axvline(75, color=COLOR_PRIMARY, linestyle=":", linewidth=1.2, alpha=0.7, label="75% Attendance Min")
        ax6.axhline(50, color=COLOR_DANGER, linestyle=":", linewidth=1.2, alpha=0.7, label="50% Score Cutoff")
        ax6.set_xlim(0, 105)
        ax6.set_ylim(0, 105)
        ax6.legend(loc="lower right", frameon=True, facecolor="white", edgecolor=COLOR_GRID, framealpha=0.92, fontsize=7.5)

    return _fig_to_base64(fig, dpi=150) if as_base64 else _fig_to_bytes(fig, dpi=150)


# ============================================================================
# BUNDLE / DISPATCHER FUNCTIONS
# ============================================================================

SMALL_GRAPH_DISPATCHER = {
    "attendance": generate_attendance_chart,
    "exams": generate_exam_chart,
    "financials": generate_financials_chart,
    "conversion": generate_conversion_chart,
    "risk": generate_risk_chart,
    "probability": generate_probability_chart,
    "scatter": generate_scatter_chart
}


def generate_small_graph(
    graph_type: str,
    records: List[Dict[str, Any]],
    ml_predictions: Optional[Dict[str, Any]] = None,
    as_base64: bool = False
) -> Any:
    """Generates an individual small graph by graph_type key."""
    fn = SMALL_GRAPH_DISPATCHER.get(graph_type.lower())
    if not fn:
        raise ValueError(f"Unknown graph type '{graph_type}'. Available: {list(SMALL_GRAPH_DISPATCHER.keys())}")
    return fn(records, ml_predictions=ml_predictions, as_base64=as_base64)


def generate_all_charts(
    records: List[Dict[str, Any]],
    ml_predictions: Optional[Dict[str, Any]] = None,
    centre_name: str = "ClassPulse Analytics"
) -> Dict[str, Any]:
    """
    Generates all small graphs and the master graph, returning them as
    base64 data URIs ready for instant HTML injection and downloading.
    """
    small_charts = {}
    for key, fn in SMALL_GRAPH_DISPATCHER.items():
        try:
            small_charts[key] = fn(records, ml_predictions=ml_predictions, as_base64=True)
        except Exception as e:
            small_charts[key] = None

    master_chart = generate_master_graph(
        records,
        ml_predictions=ml_predictions,
        centre_name=centre_name,
        as_base64=True
    )

    return {
        "master_graph": master_chart,
        "small_graphs": small_charts,
        "metrics_summary": _extract_dataset_metrics(records, ml_predictions)
    }


def save_all_charts(
    records: List[Dict[str, Any]],
    output_dir: str = "outputs/charts",
    ml_predictions: Optional[Dict[str, Any]] = None,
    centre_name: str = "ClassPulse Analytics"
) -> Dict[str, str]:
    """
    Saves the master graph and all individual small graphs directly to disk as PNG files.
    """
    from pathlib import Path

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    saved_files = {}

    # 1. Master Graph
    master_bytes = generate_master_graph(records, ml_predictions=ml_predictions, centre_name=centre_name, as_base64=False)
    master_file = out_path / "master_graph.png"
    master_file.write_bytes(master_bytes)
    saved_files["master_graph"] = str(master_file.resolve())

    # 2. Individual Small Graphs
    for key, fn in SMALL_GRAPH_DISPATCHER.items():
        chart_bytes = fn(records, ml_predictions=ml_predictions, as_base64=False)
        chart_file = out_path / f"small_graph_{key}.png"
        chart_file.write_bytes(chart_bytes)
        saved_files[f"small_graph_{key}"] = str(chart_file.resolve())

    return saved_files


if __name__ == "__main__":
    import csv
    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent
    sample_csv = base_dir / "data" / "synthetic" / "ClassPulse_Full_Demo.csv"

    if sample_csv.exists():
        print(f"Reading sample data from {sample_csv}...")
        with open(sample_csv, "r", encoding="utf-8") as f:
            demo_rows = list(csv.DictReader(f))
        
        target_dir = base_dir / "outputs" / "charts"
        results = save_all_charts(demo_rows, output_dir=str(target_dir), centre_name="ClassPulse Demo Academy")
        print("\nSuccessfully generated uncluttered Matplotlib graphs:")
        for name, path in results.items():
            print(f"  - {name}: {path}")
    else:
        print(f"Sample data file {sample_csv} not found.")
