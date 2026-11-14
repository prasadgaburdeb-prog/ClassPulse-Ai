"""
ClassPulse AI - PDF Analytical Reporting Engine
Generates official Student Performance Report Cards and Executive Cohort Summary Reports
per SRS requirements FEAT-013, FEAT-014, FEAT-015, FEAT-016.
"""

from datetime import datetime, timezone
import io
from typing import Any, Dict, List, Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Brand color palette
COLOR_PRIMARY = HexColor("#2563eb")     # Brand Blue
COLOR_DARK = HexColor("#0f172a")        # Text Dark
COLOR_MUTED = HexColor("#64748b")       # Text Slate
COLOR_LIGHT_BG = HexColor("#f8fafc")    # Card / Row BG
COLOR_BORDER = HexColor("#e2e8f0")      # Table Lines
COLOR_SUCCESS = HexColor("#10b981")     # Green
COLOR_WARNING = HexColor("#f59e0b")     # Amber
COLOR_DANGER = HexColor("#ef4444")       # Red

def get_report_stylesheet():
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name="ReportTitle",
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=COLOR_PRIMARY,
        spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=COLOR_MUTED,
        spaceAfter=12
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=COLOR_DARK,
        spaceBefore=10,
        spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        name="TableHeader",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=COLOR_DARK
    ))
    styles.add(ParagraphStyle(
        name="TableCell",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=COLOR_DARK
    ))
    styles.add(ParagraphStyle(
        name="TableCellBold",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=COLOR_DARK
    ))
    styles.add(ParagraphStyle(
        name="DisclaimerText",
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        leading=10,
        textColor=COLOR_MUTED
    ))
    styles.add(ParagraphStyle(
        name="CalloutText",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=COLOR_DARK
    ))
    return styles


def generate_student_report_card(
    student_profile: Dict[str, Any],
    centre_name: str = "ClassPulse Coaching Centre",
    author: str = "Faculty Administrator"
) -> bytes:
    """
    Generates a comprehensive Student Progress & AI Predictive Report Card (PDF).
    Complies with FEAT-013, FEAT-014, FEAT-015, FEAT-016.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    styles = get_report_stylesheet()
    story = []

    # 1. Header & Centre Identity
    gen_time = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    header_data = [
        [
            Paragraph(f"<b>{centre_name}</b>", styles["ReportTitle"]),
            Paragraph(f"<b>CONFIDENTIAL</b><br/>Generated: {gen_time}", ParagraphStyle("RightMeta", fontName="Helvetica", fontSize=8, leading=11, alignment=2, textColor=COLOR_MUTED))
        ]
    ]
    header_table = Table(header_data, colWidths=[4.0 * inch, 3.2 * inch])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Paragraph("Student Academic Evaluation & AI Pass Probability Report Card", styles["ReportSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARY, spaceBefore=0, spaceAfter=12))

    # 2. Student Information Table
    stu_obj = student_profile.get("student", {})
    sid = student_profile.get("student_id") or stu_obj.get("student_id", "N/A")
    cid = student_profile.get("course_id") or stu_obj.get("course_id", "General")
    bid = student_profile.get("batch_id") or stu_obj.get("batch_id", "Standard")
    att_summary = student_profile.get("attendance_summary", {})
    att_rate = student_profile.get("attendance_rate", att_summary.get("attendance_rate", 0.0))
    att_present = student_profile.get("classes_attended", student_profile.get("present_count", att_summary.get("present_count", 0)))
    att_total = student_profile.get("total_classes", student_profile.get("total_sessions", att_summary.get("total_sessions", 40)))

    info_data = [
        [
            Paragraph("<b>Student Identifier:</b>", styles["TableCellBold"]),
            Paragraph(str(sid), styles["TableCell"]),
            Paragraph("<b>Course Enrollment:</b>", styles["TableCellBold"]),
            Paragraph(str(cid), styles["TableCell"])
        ],
        [
            Paragraph("<b>Assigned Batch:</b>", styles["TableCellBold"]),
            Paragraph(str(bid), styles["TableCell"]),
            Paragraph("<b>Attendance Record:</b>", styles["TableCellBold"]),
            Paragraph(f"{att_present} / {att_total} sessions ({att_rate}%)", styles["TableCell"])
        ]
    ]
    info_table = Table(info_data, colWidths=[1.8 * inch, 1.8 * inch, 1.8 * inch, 1.8 * inch])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8))

    # Model metadata provenance table (REP-01)
    m_ver = student_profile.get("model_version", "v2.1.0-benchmark")
    m_prov = student_profile.get("dataset_provenance") or student_profile.get("provenance", "synthetic_benchmark")
    prov_label = "Synthetic Academic Benchmark" if "synthetic" in str(m_prov).lower() else "Verified Historical Outcomes"
    model_meta = [
        [
            Paragraph("<b>Model Version:</b>", styles["TableCellBold"]),
            Paragraph(str(m_ver), styles["TableCell"]),
            Paragraph("<b>Model Provenance:</b>", styles["TableCellBold"]),
            Paragraph(prov_label, styles["TableCell"])
        ]
    ]
    meta_table = Table(model_meta, colWidths=[1.8 * inch, 1.8 * inch, 1.8 * inch, 1.8 * inch])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # 3. AI Predictive Pass Assessment
    story.append(Paragraph("1. Machine Learning Academic Pass Prediction", styles["SectionHeading"]))
    latest_pred = student_profile.get("latest_prediction", {})
    pass_prob = student_profile.get("pass_probability", latest_pred.get("pass_probability", 0.0))
    risk_level = student_profile.get("risk_level", latest_pred.get("risk_level", "Unknown"))
    predicted_outcome = student_profile.get("predicted_outcome", latest_pred.get("predicted_outcome", "Pending"))
    is_incomplete = student_profile.get("is_incomplete", student_profile.get("is_tentative", False))

    risk_color = COLOR_SUCCESS if pass_prob >= 75.0 else (COLOR_WARNING if pass_prob >= 50.0 else COLOR_DANGER)

    ai_summary_data = [
        [
            Paragraph("<b>Predicted Pass Probability</b>", styles["TableHeader"]),
            Paragraph("<b>Academic Risk Tier</b>", styles["TableHeader"]),
            Paragraph("<b>Forecasted Outcome</b>", styles["TableHeader"]),
            Paragraph("<b>Input Data Quality</b>", styles["TableHeader"])
        ],
        [
            Paragraph(f"<font size=14 color='{risk_color.hexval()}'><b>{pass_prob}%</b></font>", styles["TableCell"]),
            Paragraph(f"<b>{risk_level}</b>", styles["TableCell"]),
            Paragraph(str(predicted_outcome), styles["TableCell"]),
            Paragraph("⚠️ Missing Mock Tests" if is_incomplete else "✅ Complete Profile", styles["TableCell"])
        ]
    ]
    ai_table = Table(ai_summary_data, colWidths=[1.8 * inch, 2.0 * inch, 1.6 * inch, 1.8 * inch])
    ai_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 1), (0, 1), "CENTER"),
    ]))
    story.append(ai_table)
    story.append(Spacer(1, 10))

    # 4. Contributing Factors & Recommended Faculty Interventions
    latest_pred = student_profile.get("latest_prediction", {})
    factors = student_profile.get("key_factors") or latest_pred.get("factors", [])
    recs = student_profile.get("recommendations", [])

    callout_data = []
    if factors:
        factor_items = "<br/>• ".join(factors)
        callout_data.append([
            Paragraph("<b>Key Contributing Factors:</b>", styles["TableCellBold"]),
            Paragraph(f"• {factor_items}", styles["CalloutText"])
        ])
    if recs:
        rec_items = "<br/>• ".join(recs)
        callout_data.append([
            Paragraph("<b>Recommended Interventions:</b>", styles["TableCellBold"]),
            Paragraph(f"• {rec_items}", styles["CalloutText"])
        ])

    if callout_data:
        callout_table = Table(callout_data, colWidths=[2.2 * inch, 5.0 * inch])
        callout_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#eff6ff")),
            ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#bfdbfe")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, HexColor("#bfdbfe")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(callout_table)
        story.append(Spacer(1, 12))

    # 5. Examination History Table
    story.append(Paragraph("2. Academic Examination & Mock Test Records", styles["SectionHeading"]))
    exam_history = student_profile.get("exam_scores_detail", [])
    if exam_history:
        exam_rows = [
            [
                Paragraph("<b>Date</b>", styles["TableHeader"]),
                Paragraph("<b>Subject / Assessment ID</b>", styles["TableHeader"]),
                Paragraph("<b>Score Obtained</b>", styles["TableHeader"]),
                Paragraph("<b>Benchmark / Status</b>", styles["TableHeader"])
            ]
        ]
        for exam in exam_history[:8]:
            exam_rows.append([
                Paragraph(str(exam.get("date", "N/A")), styles["TableCell"]),
                Paragraph(str(exam.get("subject", exam.get("id", "Mock Test"))), styles["TableCell"]),
                Paragraph(f"{exam.get('score', exam.get('amount', 'N/A'))} / 100", styles["TableCellBold"]),
                Paragraph(str(exam.get("status", "Passed" if float(exam.get("amount", 50)) >= 50 else "Failed")), styles["TableCell"])
            ])
        exam_table = Table(exam_rows, colWidths=[1.5 * inch, 2.5 * inch, 1.6 * inch, 1.6 * inch])
        exam_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_LIGHT_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(exam_table)
    else:
        avg_score = student_profile.get("avg_mock_score")
        if avg_score is not None:
            story.append(Paragraph(f"Historical mock examinations logged: Average Mock Score is <b>{avg_score} / 100</b>.", styles["TableCell"]))
        else:
            story.append(Paragraph("<i>No individual mock examination scores have been recorded for this student cohort yet.</i>", styles["TableCell"]))
    story.append(Spacer(1, 12))

    # 6. Financial Clearance Standing (Tracked Independently per ML-027, ML-030)
    story.append(Paragraph("3. Financial Standing (Administered Separately)", styles["SectionHeading"]))
    fin = student_profile.get("financial_standing") or student_profile.get("financial_risk", {})
    fee_pct = fin.get("fee_clearance_pct", fin.get("clearance_pct", student_profile.get("fee_clearance_pct", 100.0)))
    fee_due = fin.get("outstanding_fees", student_profile.get("outstanding_fees", 0.0))
    fin_status = fin.get("financial_status", fin.get("fee_status", "Paid in Full" if fee_due <= 0 else "Pending Dues"))

    fin_data = [
        [
            Paragraph("<b>Clearance Ratio:</b>", styles["TableCellBold"]),
            Paragraph(f"{fee_pct}%", styles["TableCell"]),
            Paragraph("<b>Outstanding Balance:</b>", styles["TableCellBold"]),
            Paragraph(f"INR {fee_due:,.2f}", styles["TableCellBold"]),
            Paragraph("<b>Status:</b>", styles["TableCellBold"]),
            Paragraph(str(fin_status), styles["TableCell"])
        ]
    ]
    fin_table = Table(fin_data, colWidths=[1.3 * inch, 1.0 * inch, 1.5 * inch, 1.3 * inch, 0.8 * inch, 1.3 * inch])
    fin_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(fin_table)
    story.append(Spacer(1, 14))

    # 7. Statutory Prediction Disclaimers & Limitations (ML-024, ML-025, FEAT-016)
    disclaimer_block = [
        Paragraph(
            "<b>Important Legal & Academic Notice (ML-025, FEAT-016):</b> This report is generated by ClassPulse AI using "
            "supervised machine learning models (Random Forest classifier). Predictions are statistical estimates for educational "
            "counseling and early diagnostic intervention only. They do NOT constitute guaranteed academic results or definitive "
            "examination outcomes. Financial records are presented for administrative reconciliation and do not affect academic pass scoring.",
            styles["DisclaimerText"]
        )
    ]
    story.append(KeepTogether(disclaimer_block))

    doc.build(story)
    return buf.getvalue()


def generate_cohort_summary_report(
    summary_data: Dict[str, Any],
    centre_name: str = "ClassPulse Coaching Centre",
    filters_applied: Optional[Dict[str, Any]] = None
) -> bytes:
    """
    Generates an Executive Cohort Analytics & Predictive Intelligence Report (PDF).
    Complies with FEAT-013, FEAT-014, FEAT-016.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    styles = get_report_stylesheet()
    story = []

    gen_time = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    
    # 1. Header
    story.append(Paragraph(f"<b>{centre_name}</b>", styles["ReportTitle"]))
    story.append(Paragraph("Executive Cohort Performance, Financial Health & AI Pass Risk Dashboard", styles["ReportSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARY, spaceBefore=0, spaceAfter=10))

    # 2. Scope & Filter metadata (FEAT-014, FEAT-016)
    f_course = (filters_applied or {}).get("course") or "All Courses"
    f_batch = (filters_applied or {}).get("batch") or "All Batches"
    f_start = (filters_applied or {}).get("start") or "Beginning"
    f_end = (filters_applied or {}).get("end") or "Present"

    filter_data = [
        [
            Paragraph("<b>Course Scope:</b>", styles["TableCellBold"]),
            Paragraph(str(f_course), styles["TableCell"]),
            Paragraph("<b>Batch Scope:</b>", styles["TableCellBold"]),
            Paragraph(str(f_batch), styles["TableCell"])
        ],
        [
            Paragraph("<b>Date Window:</b>", styles["TableCellBold"]),
            Paragraph(f"{f_start} to {f_end}", styles["TableCell"]),
            Paragraph("<b>Report Generated:</b>", styles["TableCellBold"]),
            Paragraph(gen_time, styles["TableCell"])
        ]
    ]
    filter_table = Table(filter_data, colWidths=[1.8 * inch, 1.8 * inch, 1.8 * inch, 1.8 * inch])
    filter_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(filter_table)
    story.append(Spacer(1, 12))

    # 3. Core Cohort KPIs
    story.append(Paragraph("1. Executive Summary & AI Forecast", styles["SectionHeading"]))
    tot_students = summary_data.get("total_students", 0)
    avg_pass = summary_data.get("avg_pass_probability", 0.0)
    likely_pass = summary_data.get("likely_to_pass", 0)
    borderline = summary_data.get("borderline", 0)
    high_risk = summary_data.get("high_risk", 0)

    kpi_data = [
        [
            Paragraph("<b>Total Active Cohort</b>", styles["TableHeader"]),
            Paragraph("<b>Avg Pass Likelihood</b>", styles["TableHeader"]),
            Paragraph("<b>Safe / Likely Pass</b>", styles["TableHeader"]),
            Paragraph("<b>Borderline Risk</b>", styles["TableHeader"]),
            Paragraph("<b>High Risk (Action Needed)</b>", styles["TableHeader"])
        ],
        [
            Paragraph(f"<b>{tot_students}</b>", styles["TableCellBold"]),
            Paragraph(f"<font color='{COLOR_PRIMARY.hexval()}'><b>{avg_pass}%</b></font>", styles["TableCellBold"]),
            Paragraph(f"<font color='{COLOR_SUCCESS.hexval()}'><b>{likely_pass}</b></font>", styles["TableCellBold"]),
            Paragraph(f"<font color='{COLOR_WARNING.hexval()}'><b>{borderline}</b></font>", styles["TableCellBold"]),
            Paragraph(f"<font color='{COLOR_DANGER.hexval()}'><b>{high_risk}</b></font>", styles["TableCellBold"])
        ]
    ]
    kpi_table = Table(kpi_data, colWidths=[1.4 * inch, 1.4 * inch, 1.4 * inch, 1.4 * inch, 1.6 * inch])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 12))

    # 4. Model Evaluation & Methodology Metadata (ML-007, ML-008, ML-010)
    story.append(Paragraph("2. Machine Learning Pipeline Provenance & Model Audit", styles["SectionHeading"]))
    m_name = summary_data.get("model_name", "Random Forest Classifier")
    m_ver = summary_data.get("model_version", "v2.1.0-benchmark")
    m_prov = summary_data.get("dataset_provenance", "synthetic_benchmark")
    m_acc = summary_data.get("model_accuracy", 0.0)
    m_auc = summary_data.get("model_roc_auc", 0.0)

    prov_display = "Synthetic Academic Benchmark" if "synthetic" in str(m_prov).lower() else "Retrained on Verified Historical Outcomes"

    ml_meta_data = [
        [
            Paragraph("<b>Active ML Architecture:</b>", styles["TableCellBold"]),
            Paragraph(str(m_name), styles["TableCell"]),
            Paragraph("<b>Model Version:</b>", styles["TableCellBold"]),
            Paragraph(str(m_ver), styles["TableCell"])
        ],
        [
            Paragraph("<b>Dataset Provenance:</b>", styles["TableCellBold"]),
            Paragraph(prov_display, styles["TableCell"]),
            Paragraph("<b>Held-out Validation:</b>", styles["TableCellBold"]),
            Paragraph(f"Accuracy: {m_acc}% | ROC-AUC: {m_auc}%", styles["TableCell"])
        ]
    ]
    ml_meta_table = Table(ml_meta_data, colWidths=[1.8 * inch, 2.0 * inch, 1.6 * inch, 1.8 * inch])
    ml_meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(ml_meta_table)
    story.append(Spacer(1, 14))

    # 5. Statutory Disclaimers
    story.append(Paragraph(
        "<b>Governance Notice:</b> Predictions are generated through algorithmic estimation of academic attendance and assessment history. "
        "ClassPulse AI does not guarantee academic outcomes. Reports should be used to support pedagogical interventions and student mentoring.",
        styles["DisclaimerText"]
    ))

    doc.build(story)
    return buf.getvalue()
