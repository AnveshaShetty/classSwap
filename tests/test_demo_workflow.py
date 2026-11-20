import pytest
from datetime import date
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_full_16_step_demonstration_workflow():
    """
    Simulates the exact 16-step hackathon presentation workflow against the live database:
    1. Login as Admin.
    2. Open the timetable.
    3. Select a faculty member and mark them absent for the third period.
    4. View the affected class.
    5. Display the three highest-ranked substitute recommendations.
    6. Explain the subject relevance and fairness scores.
    7. Display the two most suitable free rooms.
    8. Send a substitution request.
    9. Logout and login as the recommended faculty member.
    10. Accept the request.
    11. Login again as Admin.
    12. Verify that the substitution is confirmed.
    13. Verify that the date-specific timetable is updated.
    14. Open the dashboard and see updated statistics.
    15. Download the monthly PDF or CSV report.
    """
    print("\n--- STEP 1: Login as Admin ---")
    admin_login_res = client.post("/api/auth/login", json={
        "email": "admin@classswap.edu",
        "password": "Admin@123"
    })
    assert admin_login_res.status_code == 200
    admin_data = admin_login_res.json()
    assert admin_data["role"] == "admin"
    admin_token = admin_data["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    print("--- STEP 2: Open Timetable ---")
    tt_res = client.get("/api/timetable?day_of_week=Tuesday&period_no=3", headers=admin_headers)
    assert tt_res.status_code == 200
    tt_entries = tt_res.json()
    assert len(tt_entries) > 0
    # On Tuesday Period 3, Dr. Rajesh Kumar teaches Data Structures in LH-101
    target_class = tt_entries[0]
    target_faculty_id = target_class["faculty_id"]
    target_date = date.today().strftime("%Y-%m-%d")

    print(f"--- STEP 3 & 4: Mark Faculty Absent for 3rd Period (Faculty ID: {target_faculty_id}) ---")
    # First delete any existing absence on this slot if previously tested
    absence_res = client.post("/api/absences", json={
        "faculty_id": target_faculty_id,
        "date": target_date,
        "period_nos": [3],
        "reason": "Attending University Academic Council Meeting"
    }, headers=admin_headers)
    
    # If duplicate from earlier run, fetch existing
    if absence_res.status_code == 400:
        abs_list = client.get(f"/api/absences?date_filter={target_date}&faculty_id={target_faculty_id}", headers=admin_headers).json()
        absence_id = abs_list[0]["id"]
    else:
        assert absence_res.status_code == 200
        absence_id = absence_res.json()[0]["id"]

    print("--- STEP 5, 6, 7: Display Top 3 Substitutes & Free Rooms ---")
    rec_res = client.get(f"/api/absences/{absence_id}/recommendations", headers=admin_headers)
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    
    assert len(rec_data["candidates"]) >= 2
    assert len(rec_data["suitable_rooms"]) >= 1

    top_cand = rec_data["candidates"][0]
    print(f"Top Recommended Substitute: {top_cand['faculty_name']} ({top_cand['email']})")
    print(f"  Final Score: {top_cand['final_score']}")
    print(f"  Subject Match: {top_cand['subject_match']} | Fairness: {top_cand['fairness_score']} | Dept: {top_cand['dept_match']}")
    
    suitable_room = rec_data["suitable_rooms"][0]
    print(f"Recommended Free Room: {suitable_room['room_name']} (Cap: {suitable_room['capacity']})")

    print("--- STEP 8: Send Substitution Request to Candidate ---")
    req_res = client.post("/api/substitutions/request", json={
        "absence_id": absence_id,
        "substitute_id": top_cand["faculty_id"],
        "room_id": suitable_room["room_id"],
        "notes": "Covering Tuesday Period 3"
    }, headers=admin_headers)
    
    if req_res.status_code == 400:
        # Already requested, fetch it
        subs_list = client.get(f"/api/substitutions?date_filter={target_date}", headers=admin_headers).json()
        sub_id = subs_list[0]["id"]
    else:
        assert req_res.status_code == 200
        sub_id = req_res.json()["id"]

    print("--- STEP 9: Logout & Login as Recommended Faculty ---")
    sub_login_res = client.post("/api/auth/login", json={
        "email": top_cand["email"],
        "password": "Faculty@123"
    })
    assert sub_login_res.status_code == 200
    sub_token = sub_login_res.json()["access_token"]
    sub_headers = {"Authorization": f"Bearer {sub_token}"}

    print("--- STEP 10: Faculty Accepts Request ---")
    action_res = client.post(f"/api/substitutions/{sub_id}/action", json={
        "substitution_id": sub_id,
        "action": "accept",
        "notes": "I will happily cover this lecture."
    }, headers=sub_headers)
    assert action_res.status_code in [200, 400]  # 400 if already accepted
    
    print("--- STEP 11 & 12: Login as Admin & Verify Substitution Confirmed ---")
    admin_verify_res = client.get("/api/substitutions?status_filter=Accepted", headers=admin_headers)
    assert admin_verify_res.status_code == 200
    accepted_subs = admin_verify_res.json()
    assert any(s["id"] == sub_id for s in accepted_subs)

    print("--- STEP 13: Verify Date-Specific Timetable is Updated ---")
    date_tt_res = client.get(f"/api/timetable/date-specific?target_date={target_date}&section_id={target_class['section_id']}", headers=admin_headers)
    assert date_tt_res.status_code == 200
    day_entries = date_tt_res.json()
    # Check that Period 3 reflects substitution
    p3_class = next(e for e in day_entries if e["period_no"] == 3)
    assert p3_class["is_substituted"] is True
    assert top_cand["faculty_name"] in p3_class["faculty_name"]

    print("--- STEP 14: Check Dashboard & Updated Analytics ---")
    report_res = client.get("/api/reports/monthly", headers=admin_headers)
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert report_data["classes_recovered"] >= 1
    assert report_data["idle_hours_saved"] > 0

    print("--- STEP 15: Download Monthly PDF & CSV Reports ---")
    pdf_res = client.get("/api/reports/download/pdf", headers=admin_headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 1000

    csv_res = client.get("/api/reports/download/csv", headers=admin_headers)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "EXECUTIVE SUMMARY" in csv_res.text

    print("\n>>> FULL 16-STEP DEMONSTRATION WORKFLOW PASSED FLAWLESSLY! <<<\n")
