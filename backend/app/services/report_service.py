import io
import csv
from datetime import date, datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from backend.app.config import settings
from backend.app.models.user import User, UserRole
from backend.app.models.academic import Subject, Section
from backend.app.models.timetable import PeriodConfig
from backend.app.models.substitution import Absence, Substitution, SubstitutionStatus, DateOverride
from backend.app.schemas.reports import (
    MonthlyReportResponse,
    FacultyWorkloadItem,
    DepartmentStatItem,
    SubjectSubstitutedItem
)

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

def calculate_monthly_analytics(db: Session, year: int, month: int) -> MonthlyReportResponse:
    """Calculate verified analytics from database records for the specified month/year."""
    # 1. Total absences in month
    absences_query = db.query(Absence).filter(
        extract("year", Absence.date) == year,
        extract("month", Absence.date) == month
    )
    total_absences = absences_query.count()

    # 2. Total substitutions requested in month
    subs_query = db.query(Substitution).join(Absence).filter(
        extract("year", Absence.date) == year,
        extract("month", Absence.date) == month
    )
    total_requested = subs_query.count()

    # 3. Accepted & Declined
    total_accepted = subs_query.filter(
        Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
    ).count()

    total_declined = subs_query.filter(
        Substitution.status == SubstitutionStatus.DECLINED.value
    ).count()

    classes_recovered = total_accepted
    period_hours = settings.PERIOD_DURATION_MINUTES / 60.0
    idle_hours_saved = round(classes_recovered * period_hours, 2)
    recovery_rate = round((classes_recovered / total_absences * 100.0), 1) if total_absences > 0 else 0.0

    # 4. Faculty-wise Workload
    all_faculty = db.query(User).filter(User.role == UserRole.FACULTY.value).order_by(User.name).all()
    faculty_workload: List[FacultyWorkloadItem] = []

    for f in all_faculty:
        comp_count = db.query(Substitution).join(Absence).filter(
            Substitution.substitute_id == f.id,
            extract("year", Absence.date) == year,
            extract("month", Absence.date) == month,
            Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
        ).count()

        last_sub = db.query(Absence.date).join(Substitution).filter(
            Substitution.substitute_id == f.id,
            Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
        ).order_by(Absence.date.desc()).first()

        faculty_workload.append(
            FacultyWorkloadItem(
                faculty_id=f.id,
                faculty_name=f.name,
                department=f.department,
                substitutions_completed=comp_count,
                hours_covered=round(comp_count * period_hours, 2),
                last_substitution_date=last_sub[0].strftime("%Y-%m-%d") if last_sub else None
            )
        )

    faculty_workload.sort(key=lambda x: x.substitutions_completed, reverse=True)

    # 5. Department-wise Statistics
    departments = [row[0] for row in db.query(User.department).distinct().all() if row[0]]
    department_stats: List[DepartmentStatItem] = []

    for dept in departments:
        dept_absences = db.query(Absence).join(User).filter(
            User.department == dept,
            extract("year", Absence.date) == year,
            extract("month", Absence.date) == month
        ).count()

        dept_recovered = db.query(Substitution).join(User, Substitution.substitute_id == User.id).join(Absence).filter(
            User.department == dept,
            extract("year", Absence.date) == year,
            extract("month", Absence.date) == month,
            Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
        ).count()

        dept_hours = round(dept_recovered * period_hours, 2)
        dept_rate = round((dept_recovered / dept_absences * 100.0), 1) if dept_absences > 0 else 0.0

        department_stats.append(
            DepartmentStatItem(
                department=dept,
                total_absences=dept_absences,
                substitutions_completed=dept_recovered,
                hours_recovered=dept_hours,
                recovery_rate_pct=dept_rate
            )
        )

    # 6. Most frequently substituted subjects
    sub_subject_counts = db.query(
        Subject.code,
        Subject.name,
        Subject.department,
        func.count(Substitution.id).label("cnt")
    ).join(DateOverride, DateOverride.subject_id == Subject.id)\
     .join(Substitution, DateOverride.substitution_id == Substitution.id)\
     .filter(
         extract("year", DateOverride.date) == year,
         extract("month", DateOverride.date) == month,
         Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
     ).group_by(Subject.id).order_by(func.count(Substitution.id).desc()).limit(5).all()

    top_subjects: List[SubjectSubstitutedItem] = []
    for code, name, dept, cnt in sub_subject_counts:
        top_subjects.append(
            SubjectSubstitutedItem(
                subject_code=code,
                subject_name=name,
                department=dept,
                substitutions_count=cnt
            )
        )

    return MonthlyReportResponse(
        month=month,
        year=year,
        month_name=MONTH_NAMES[month] if 1 <= month <= 12 else "Unknown",
        total_absences=total_absences,
        substitutions_requested=total_requested,
        substitutions_accepted=total_accepted,
        substitutions_declined=total_declined,
        classes_recovered=classes_recovered,
        idle_hours_saved=idle_hours_saved,
        recovery_rate_pct=recovery_rate,
        faculty_workload=faculty_workload,
        department_stats=department_stats,
        top_substituted_subjects=top_subjects
    )

def generate_pdf_report(report_data: MonthlyReportResponse) -> bytes:
    """Generate high-quality PDF report using ReportLab with corporate academic styling."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#0f172a")  # Deep Navy
    accent_color = colors.HexColor("#2563eb")   # Royal Blue
    light_bg = colors.HexColor("#f8fafc")
    border_color = colors.HexColor("#cbd5e1")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
        alignment=TA_LEFT
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#64748b"),
        leading=14,
        alignment=TA_LEFT
    )

    heading2_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=primary_color,
        spaceBefore=12,
        spaceAfter=6
    )

    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1e293b")
    )

    cell_bold_style = ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=primary_color
    )

    elements = []

    # Title & Header
    elements.append(Paragraph(f"{settings.COLLEGE_NAME}", title_style))
    elements.append(Paragraph(f"ClassSwap Monthly Faculty Substitution & Timetable Recovery Report — {report_data.month_name} {report_data.year}", subtitle_style))
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')} | Smart Substitutions. Zero Idle Hours.", subtitle_style))
    elements.append(Spacer(1, 14))

    # Executive Summary Cards (as a 2x3 or 2x4 table)
    kpi_data = [
        [
            Paragraph("<b>Total Faculty Absences</b>", cell_bold_style),
            Paragraph(str(report_data.total_absences), cell_style),
            Paragraph("<b>Substitutions Accepted</b>", cell_bold_style),
            Paragraph(f"{report_data.substitutions_accepted} / {report_data.substitutions_requested}", cell_style)
        ],
        [
            Paragraph("<b>Classes Recovered</b>", cell_bold_style),
            Paragraph(str(report_data.classes_recovered), cell_style),
            Paragraph("<b>Idle Class Hours Saved</b>", cell_bold_style),
            Paragraph(f"<b>{report_data.idle_hours_saved} hrs</b>", cell_bold_style)
        ],
        [
            Paragraph("<b>Recovery Rate</b>", cell_bold_style),
            Paragraph(f"{report_data.recovery_rate_pct}%", cell_style),
            Paragraph("<b>Declined Swaps</b>", cell_bold_style),
            Paragraph(str(report_data.substitutions_declined), cell_style)
        ]
    ]

    kpi_table = Table(kpi_data, colWidths=[150, 110, 150, 130])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), light_bg),
        ('BOX', (0, 0), (-1, -1), 1, accent_color),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 14))

    # Departmental Statistics Table
    elements.append(Paragraph("Departmental Substitution & Recovery Breakdown", heading2_style))
    dept_table_data = [
        [
            Paragraph("<b>Department</b>", cell_bold_style),
            Paragraph("<b>Faculty Absences</b>", cell_bold_style),
            Paragraph("<b>Substitutions Covered</b>", cell_bold_style),
            Paragraph("<b>Hours Recovered</b>", cell_bold_style),
            Paragraph("<b>Recovery %</b>", cell_bold_style),
        ]
    ]

    for d in report_data.department_stats:
        dept_table_data.append([
            Paragraph(d.department, cell_style),
            Paragraph(str(d.total_absences), cell_style),
            Paragraph(str(d.substitutions_completed), cell_style),
            Paragraph(f"{d.hours_recovered} hrs", cell_style),
            Paragraph(f"{d.recovery_rate_pct}%", cell_style),
        ])

    dept_table = Table(dept_table_data, colWidths=[200, 85, 95, 85, 75])
    dept_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
        ('BOX', (0, 0), (-1, -1), 0.5, border_color),
    ]))
    elements.append(dept_table)
    elements.append(Spacer(1, 14))

    # Faculty Workload Distribution Table
    elements.append(Paragraph("Faculty Substitution Workload (Fairness Audit)", heading2_style))
    fac_table_data = [
        [
            Paragraph("<b>Faculty Member</b>", cell_bold_style),
            Paragraph("<b>Department</b>", cell_bold_style),
            Paragraph("<b>Substitutions Completed</b>", cell_bold_style),
            Paragraph("<b>Hours Taught</b>", cell_bold_style),
            Paragraph("<b>Last Sub Date</b>", cell_bold_style),
        ]
    ]

    for f in report_data.faculty_workload[:15]:  # Top 15 faculty
        fac_table_data.append([
            Paragraph(f.faculty_name, cell_style),
            Paragraph(f.department, cell_style),
            Paragraph(str(f.substitutions_completed), cell_style),
            Paragraph(f"{f.hours_covered} hrs", cell_style),
            Paragraph(f.last_substitution_date or "—", cell_style),
        ])

    fac_table = Table(fac_table_data, colWidths=[150, 160, 95, 75, 60])
    fac_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
        ('BOX', (0, 0), (-1, -1), 0.5, border_color),
    ]))
    elements.append(fac_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def generate_csv_report(report_data: MonthlyReportResponse) -> str:
    """Generate comprehensive CSV report string for spreadsheet analysis."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header section
    writer.writerow(["ClassSwap Monthly Substitution & Analytics Report"])
    writer.writerow(["College", settings.COLLEGE_NAME])
    writer.writerow(["Month", f"{report_data.month_name} {report_data.year}"])
    writer.writerow(["Generated At", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])

    # Summary Metrics
    writer.writerow(["EXECUTIVE SUMMARY"])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Total Faculty Absences", report_data.total_absences])
    writer.writerow(["Substitutions Requested", report_data.substitutions_requested])
    writer.writerow(["Substitutions Accepted", report_data.substitutions_accepted])
    writer.writerow(["Substitutions Declined", report_data.substitutions_declined])
    writer.writerow(["Classes Recovered", report_data.classes_recovered])
    writer.writerow(["Total Idle Hours Saved", f"{report_data.idle_hours_saved} hours"])
    writer.writerow(["Recovery Rate", f"{report_data.recovery_rate_pct}%"])
    writer.writerow([])

    # Departmental Statistics
    writer.writerow(["DEPARTMENTAL BREAKDOWN"])
    writer.writerow(["Department", "Absences", "Substitutions Completed", "Hours Recovered", "Recovery Rate %"])
    for d in report_data.department_stats:
        writer.writerow([d.department, d.total_absences, d.substitutions_completed, d.hours_recovered, d.recovery_rate_pct])
    writer.writerow([])

    # Faculty Workload
    writer.writerow(["FACULTY WORKLOAD DISTRIBUTION"])
    writer.writerow(["Faculty ID", "Faculty Name", "Department", "Substitutions Completed", "Hours Covered", "Last Substitution Date"])
    for f in report_data.faculty_workload:
        writer.writerow([f.faculty_id, f.faculty_name, f.department, f.substitutions_completed, f.hours_covered, f.last_substitution_date or ""])
    writer.writerow([])

    # Top Substituted Subjects
    writer.writerow(["TOP SUBSTITUTED SUBJECTS"])
    writer.writerow(["Subject Code", "Subject Name", "Department", "Substitutions Count"])
    for s in report_data.top_substituted_subjects:
        writer.writerow([s.subject_code, s.subject_name, s.department, s.substitutions_count])

    return output.getvalue()
