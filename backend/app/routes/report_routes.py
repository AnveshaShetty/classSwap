from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Optional

from backend.app.database import get_db
from backend.app.core.dependencies import require_admin
from backend.app.schemas.reports import MonthlyReportResponse
from backend.app.services.report_service import (
    calculate_monthly_analytics,
    generate_pdf_report,
    generate_csv_report
)

router = APIRouter(prefix="/api/reports", tags=["Reports & Analytics"])

@router.get("/monthly", response_model=MonthlyReportResponse)
def get_monthly_report(
    year: Optional[int] = Query(None, description="Report Year"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Report Month (1-12)"),
    current_user = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Calculate and return monthly substitution analytics."""
    target_year = year or datetime.now().year
    target_month = month or datetime.now().month
    report_data = calculate_monthly_analytics(db, target_year, target_month)
    return report_data

@router.get("/download/pdf")
def download_pdf_report(
    year: Optional[int] = Query(None, description="Report Year"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Report Month (1-12)"),
    current_user = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Download verified monthly report in PDF format."""
    target_year = year or datetime.now().year
    target_month = month or datetime.now().month
    report_data = calculate_monthly_analytics(db, target_year, target_month)
    pdf_bytes = generate_pdf_report(report_data)
    
    filename = f"ClassSwap_Report_{report_data.month_name}_{target_year}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/download/csv")
def download_csv_report(
    year: Optional[int] = Query(None, description="Report Year"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Report Month (1-12)"),
    current_user = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Download verified monthly report in CSV format."""
    target_year = year or datetime.now().year
    target_month = month or datetime.now().month
    report_data = calculate_monthly_analytics(db, target_year, target_month)
    csv_string = generate_csv_report(report_data)

    filename = f"ClassSwap_Report_{report_data.month_name}_{target_year}.csv"
    return Response(
        content=csv_string,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
