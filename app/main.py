import base64
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import openpyxl
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from app.ml_model import predictor, UniversalSheetAdapter

BASE_DIR = Path(__file__).resolve().parent.parent

def load_local_env() -> None:
    """Load simple KEY=value pairs from the project .env without adding a runtime dependency."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists(): return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_local_env()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./classpulse.db")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024
SECRET = os.getenv("SECRET_KEY", "local-development-secret-change-me").encode()
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()]

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase): pass
class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="owner")
class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30))
    accepted_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class Record(Base):
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id"), index=True)
    record_type: Mapped[str] = mapped_column(String(30), index=True)
    data_json: Mapped[str] = mapped_column(Text)
class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    event: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)
app = FastAPI(title="ClassPulse Analytics & Universal AI Exam Predictor", version="1.2.0")
if ALLOWED_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
previews: dict[str, dict[str, Any]] = {}

def db_session():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def password_hash(value: str) -> str:
    salt = secrets.token_bytes(16); digest = hashlib.pbkdf2_hmac("sha256", value.encode(), salt, 300_000)
    return base64.b64encode(salt + digest).decode()

def verify_password(value: str, stored: str) -> bool:
    raw = base64.b64decode(stored); return hmac.compare_digest(raw[16:], hashlib.pbkdf2_hmac("sha256", value.encode(), raw[:16], 300_000))

def token_for(user: User) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"uid": user.id, "tid": user.tenant_id, "exp": (datetime.now(timezone.utc)+timedelta(hours=12)).timestamp()}).encode()).decode()
    return body + "." + hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()

def current_user(request: Request, db: Session = Depends(db_session)) -> User:
    token = request.cookies.get("classpulse_session")
    if not token or "." not in token: raise HTTPException(401, "Please sign in to continue.")
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()): raise HTTPException(401, "Invalid session.")
    try: payload = json.loads(base64.urlsafe_b64decode(body)); assert payload["exp"] > datetime.now(timezone.utc).timestamp()
    except Exception: raise HTTPException(401, "Session expired. Please sign in again.")
    user = db.get(User, payload["uid"])
    if not user or user.tenant_id != payload["tid"]: raise HTTPException(401, "Session unavailable.")
    return user

def audit(db: Session, tenant_id: int, event: str): db.add(AuditEvent(tenant_id=tenant_id, event=event))

def set_session_cookie(response: JSONResponse, user: User) -> JSONResponse:
    response.set_cookie("classpulse_session", token_for(user), httponly=True, samesite="lax", secure=COOKIE_SECURE, max_age=12 * 60 * 60)
    return response

REQUIRED_COLUMNS = {"record_type", "id", "date", "course_id", "batch_id", "student_id", "amount", "status"}
VALID_TYPES = {"enquiry", "student", "obligation", "payment", "attendance", "exam", "test"}

def extract_rows_from_bytes(data: bytes, filename: str) -> tuple[list[dict], list[str]]:
    """
    Extracts structured dictionary rows from either CSV or Excel (.xlsx) file bytes.
    Accepts ANY spreadsheet format without schema constraints.
    """
    fname = filename.lower()
    if fname.endswith(".xlsx"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        except Exception as e:
            raise HTTPException(400, f"Failed to read Excel file: {str(e)}")
        
        ws = None
        for candidate in ["Import CSV", "import_csv", "Students", "Data", "Sheet1"]:
            if candidate in wb.sheetnames:
                ws = wb[candidate]
                break
        if ws is None:
            ws = wb.active

        all_rows = list(ws.iter_rows(values_only=True))
        header_idx = -1
        headers: list[str] = []
        
        # Scan for header row (first non-empty row with at least 2 named cells)
        for idx, row in enumerate(all_rows):
            named_cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if len(named_cells) >= 2:
                header_idx = idx
                headers = [str(cell).strip() if cell is not None else f"col_{c_i}" for c_i, cell in enumerate(row)]
                break
        
        if header_idx == -1:
            raise HTTPException(400, "Could not find a valid table with headers in this Excel spreadsheet.")
        
        dict_rows = []
        for r in all_rows[header_idx + 1:]:
            if not any(r): continue
            row_dict = {}
            for col_name, val in zip(headers, r):
                if not col_name: continue
                if isinstance(val, (datetime, date)):
                    row_dict[col_name] = val.strftime("%Y-%m-%d")
                elif val is not None:
                    row_dict[col_name] = str(val).strip()
                else:
                    row_dict[col_name] = ""
            dict_rows.append(row_dict)
        return dict_rows, headers
    else:
        try:
            text = data.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            fieldnames = [f.strip() for f in (reader.fieldnames or [])]
            return list(reader), fieldnames
        except UnicodeDecodeError:
            raise HTTPException(400, "Use a UTF-8 encoded CSV file or an .xlsx spreadsheet.")

def parse_sheet_data(data: bytes, filename: str) -> tuple[list[dict], list[dict], dict]:
    """
    Intelligently parses sheet data. If sheet matches ClassPulse event log template, validates normally.
    If sheet is an arbitrary flat student table (any school/coaching format), it automatically
    converts it to normalized ClassPulse records so it works with ANY spreadsheet!
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds the {MAX_UPLOAD_BYTES // 1024 // 1024} MB limit.")
    
    rows, fieldnames = extract_rows_from_bytes(data, filename)
    clean_fieldnames = {k.strip().lower() for k in fieldnames}

    # Case 1: Standard ClassPulse log schema
    if UniversalSheetAdapter.is_standard_classpulse(fieldnames):
        valid, errors, seen = [], [], set()
        for line, raw_row in enumerate(rows, start=2):
            row = {k.strip().lower(): (str(v or "").strip()) for k, v in raw_row.items()}
            problems = []
            kind = row.get("record_type", "").lower()
            row["record_type"] = kind
            row["status"] = row.get("status", "").lower()

            if kind not in VALID_TYPES:
                problems.append("record_type must be enquiry, student, obligation, payment, attendance, or exam")
            if not row.get("id"):
                problems.append("id is required")
            if (kind, row.get("id")) in seen:
                problems.append("duplicate ID in this file")
            seen.add((kind, row.get("id")))

            try:
                date.fromisoformat(row.get("date", ""))
            except ValueError:
                problems.append("date must use YYYY-MM-DD")

            if kind in {"student", "obligation", "payment", "attendance", "exam", "test"} and not row.get("student_id"):
                problems.append("student_id is required")

            if kind in {"obligation", "payment", "exam", "test"}:
                try:
                    amt = Decimal(row.get("amount") or "0")
                    if amt < 0: problems.append("amount must not be negative")
                except (InvalidOperation, ValueError):
                    problems.append("amount must be a valid number")

            if kind == "attendance" and row.get("status") not in {"present", "absent", "excused"}:
                problems.append("attendance status must be present, absent, or excused")

            if kind == "payment" and row.get("status") not in {"successful", "refunded"}:
                problems.append("payment status must be successful or refunded")

            if problems:
                errors.append({"line": line, "issues": problems})
            else:
                valid.append(row)

        summary = {
            "total_rows": len(valid) + len(errors),
            "accepted_rows": len(valid),
            "rejected_rows": len(errors),
            "duplicates": sum(1 for e in errors if any('duplicate' in x for x in e['issues'])),
            "format_detected": "ClassPulse Standard Template"
        }
        return valid, errors, summary

    # Case 2: ANY Arbitrary Spreadsheet (Flat student marksheet, attendance register, etc.)
    # Automatically convert flat rows to normalized records!
    normalized_records = UniversalSheetAdapter.convert_flat_to_classpulse_records(rows)
    summary = {
        "total_rows": len(rows),
        "accepted_rows": len(normalized_records),
        "rejected_rows": 0,
        "duplicates": 0,
        "format_detected": f"Universal Sheet Ingestion (Auto-converted {len(rows)} student rows into {len(normalized_records)} normalized analytics records)"
    }
    return normalized_records, [], summary

def filtered(records: list[Record], start: str|None, end: str|None, course: str|None, batch: str|None):
    selected_course = course.strip().casefold() if course else None
    selected_batch = batch.strip().casefold() if batch else None
    out=[]
    for record in records:
        row=json.loads(record.data_json); d=row["date"]
        if ((start and d < start) or (end and d > end) or
            (selected_course and row.get("course_id", "").strip().casefold() != selected_course) or
            (selected_batch and row.get("batch_id", "").strip().casefold() != selected_batch)):
            continue
        out.append(row)
    return out

def validate_filters(start: str|None, end: str|None) -> None:
    try:
        if start: date.fromisoformat(start)
        if end: date.fromisoformat(end)
    except ValueError: raise HTTPException(400, "Dates must use YYYY-MM-DD.")
    if start and end and start > end: raise HTTPException(400, "End date must be on or after the start date.")

def metrics(rows: list[dict]):
    enquiries=[r for r in rows if r["record_type"]=="enquiry"]
    admissions=[r for r in rows if r["record_type"]=="student"]
    obligations=sum((Decimal(r["amount"]) for r in rows if r["record_type"]=="obligation"), Decimal())
    payments=sum((Decimal(r["amount"])-Decimal(r.get("refund_amount") or 0) for r in rows if r["record_type"]=="payment" and r["status"].lower()=="successful"), Decimal())
    attendance=[r for r in rows if r["record_type"]=="attendance" and r["status"].lower() != "excused"]
    present=sum(r["status"].lower()=="present" for r in attendance)
    exams=[r for r in rows if r["record_type"] in ("exam", "test")]
    avg_mock_score = round(float(sum(Decimal(r["amount"]) for r in exams) / len(exams)), 1) if exams else None

    return {
        "enquiries": len(enquiries),
        "admissions": len(admissions),
        "conversion_rate": round(100*len(admissions)/len(enquiries),1) if enquiries else None,
        "fee_collection": float(payments),
        "outstanding_fees": float(max(Decimal(), obligations-payments)),
        "attendance_rate": round(100*present/len(attendance),1) if attendance else None,
        "attendance_denominator": len(attendance),
        "mock_exams_count": len(exams),
        "avg_mock_score": avg_mock_score
    }

@app.get("/")
def home(): return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/health")
def health(): return {"status":"ok", "ml_model_loaded": predictor.is_trained, "universal_sheet_support": True}

@app.post("/api/v1/auth/register")
async def register(request: Request, db: Session = Depends(db_session)):
    body=await request.json(); name=body.get("centre_name", "").strip(); email=body.get("email", "").strip().lower(); password=body.get("password", "")
    if len(name)<2 or "@" not in email or len(password)<8: raise HTTPException(400, "Centre name, a valid email, and a password of at least 8 characters are required.")
    if db.scalar(select(User).where(User.email==email)): raise HTTPException(409,"An account with that email already exists.")
    tenant=Tenant(name=name); db.add(tenant); db.flush(); user=User(tenant_id=tenant.id,email=email,password_hash=password_hash(password)); db.add(user); audit(db,tenant.id,"account_created"); db.commit()
    return set_session_cookie(JSONResponse({"user":{"email":email,"centre_name":name,"role":"owner"}}), user)

@app.post("/api/v1/auth/login")
async def login(request: Request, db: Session = Depends(db_session)):
    body=await request.json(); user=db.scalar(select(User).where(User.email==body.get("email","").lower()))
    if not user or not verify_password(body.get("password",""),user.password_hash): raise HTTPException(401,"Incorrect email or password.")
    tenant=db.get(Tenant,user.tenant_id); audit(db,user.tenant_id,"signed_in"); db.commit(); return set_session_cookie(JSONResponse({"user":{"email":user.email,"centre_name":tenant.name,"role":user.role}}), user)

@app.post("/api/v1/auth/logout")
def logout(): res=JSONResponse({"ok":True}); res.delete_cookie("classpulse_session"); return res

@app.get("/api/v1/me")
def me(user: User=Depends(current_user), db: Session=Depends(db_session)): return {"email":user.email,"centre_name":db.get(Tenant,user.tenant_id).name,"role":user.role}

@app.post("/api/v1/imports/preview")
async def preview(file: UploadFile=File(...), user: User=Depends(current_user)):
    ext = file.filename.lower().split(".")[-1]
    if ext not in ("csv", "xlsx"):
        raise HTTPException(400, "Only .csv and .xlsx spreadsheet files are accepted.")
    
    valid, errors, summary = parse_sheet_data(await file.read(), file.filename)
    key = secrets.token_urlsafe(18)
    previews[key] = {
        "tenant_id": user.tenant_id,
        "filename": file.filename,
        "valid": valid,
        "errors": errors,
        "summary": summary
    }
    return {
        "preview_id": key,
        "filename": file.filename,
        "summary": summary,
        "errors": errors[:15],
        "sample": valid[:5]
    }

@app.post("/api/v1/imports/{preview_id}/confirm")
def confirm_import(preview_id: str, user: User=Depends(current_user), db: Session=Depends(db_session)):
    preview=previews.pop(preview_id,None)
    if not preview or preview["tenant_id"]!=user.tenant_id: raise HTTPException(404,"Import preview expired. Upload the file again.")
    job=ImportJob(tenant_id=user.tenant_id,filename=preview["filename"],status="completed",accepted_rows=len(preview["valid"]),rejected_rows=len(preview["errors"]),summary_json=json.dumps(preview["summary"])); db.add(job); db.flush()
    for row in preview["valid"]: db.add(Record(tenant_id=user.tenant_id,import_id=job.id,record_type=row["record_type"],data_json=json.dumps(row)))
    audit(db,user.tenant_id,"import_confirmed"); db.commit(); return {"id":job.id,"message":"Import completed.",**preview["summary"]}

@app.get("/api/v1/imports")
def imports(user: User=Depends(current_user),db: Session=Depends(db_session)):
    jobs=db.scalars(select(ImportJob).where(ImportJob.tenant_id==user.tenant_id).order_by(ImportJob.created_at.desc())).all(); return [{"id":j.id,"filename":j.filename,"status":j.status,"accepted_rows":j.accepted_rows,"rejected_rows":j.rejected_rows,"created_at":j.created_at.isoformat()} for j in jobs]

@app.get("/api/v1/records")
def records(record_type: str|None=None, start: str|None=None, end: str|None=None, course: str|None=None, batch: str|None=None, user: User=Depends(current_user), db: Session=Depends(db_session)):
    validate_filters(start, end)
    if record_type and record_type not in VALID_TYPES: raise HTTPException(400, "Unsupported record type.")
    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    result = filtered(tenant_records, start, end, course, batch)
    if record_type: result = [row for row in result if row["record_type"] == record_type]
    result.sort(key=lambda row: (row["date"], row["id"]), reverse=True)
    return {"records": result[:500], "result_count": len(result), "limit": 500}

@app.get("/api/v1/analytics/overview")
def overview(start: str|None=None,end: str|None=None,course: str|None=None,batch: str|None=None,user: User=Depends(current_user),db: Session=Depends(db_session)):
    validate_filters(start, end)
    recs=db.scalars(select(Record).where(Record.tenant_id==user.tenant_id)).all(); current=filtered(recs,start,end,course,batch)
    prior=None
    if start and end:
        days=(date.fromisoformat(end)-date.fromisoformat(start)).days+1; prior_end=(date.fromisoformat(start)-timedelta(days=1)); prior_start=prior_end-timedelta(days=days-1); prior=metrics(filtered(recs,prior_start.isoformat(),prior_end.isoformat(),course,batch))
    
    ml_analysis = predictor.predict_cohort(current, course_filter=course, batch_filter=batch)

    return {
        "metrics": metrics(current),
        "comparison": prior,
        "filters": {"start":start,"end":end,"course":course,"batch":batch,"matched_records":len(current)},
        "ml_summary": ml_analysis["summary"],
        "definition": "Universal sheet ingestion enabled. Predictions adapt automatically to any spreadsheet format (attendance, fees, mock marks)."
    }

@app.get("/api/v1/ml/predictions")
def get_predictions(course: str|None=None, batch: str|None=None, risk_level: str|None=None, user: User=Depends(current_user), db: Session=Depends(db_session)):
    """
    Returns AI / Machine Learning predictions for all students in the tenant's sheets.
    """
    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    rows = [json.loads(r.data_json) for r in tenant_records]
    return predictor.predict_cohort(rows, course_filter=course, batch_filter=batch, risk_filter=risk_level)

@app.post("/api/v1/ml/analyze-sheet")
async def analyze_arbitrary_sheet(file: UploadFile=File(...), user: User=Depends(current_user)):
    """
    UNIVERSAL ANALYZER: Upload ANY spreadsheet (.csv or .xlsx) with ANY column headers.
    Auto-detects columns and delivers instant exam pass predictions without DB write requirement!
    """
    ext = file.filename.lower().split(".")[-1]
    if ext not in ("csv", "xlsx"):
        raise HTTPException(400, "Only .csv and .xlsx spreadsheet files are accepted.")
    
    data = await file.read()
    rows, fieldnames = extract_rows_from_bytes(data, file.filename)
    if not rows:
        raise HTTPException(400, "Uploaded spreadsheet contains no data rows.")
    
    result = predictor.predict_from_generic_sheet(rows, filename=file.filename)
    return {
        "filename": file.filename,
        **result
    }

@app.post("/api/v1/ml/simulate")
async def simulate_student(request: Request, user: User=Depends(current_user)):
    """
    What-If Simulator: allows faculty/admins to simulate student scenarios.
    """
    body = await request.json()
    att_rate = float(body.get("attendance_rate", 75.0))
    mock_score = float(body.get("avg_mock_score", 65.0))
    fee_ratio = float(body.get("fee_clearance_ratio", 1.0))
    course_id = body.get("course_id", "General")
    classes_attended = body.get("classes_attended")
    if classes_attended is not None:
        classes_attended = int(classes_attended)
    
    pred = predictor.simulate(att_rate, mock_score, fee_ratio, course_id, classes_attended)
    return {"prediction": pred}

@app.get("/api/v1/ml/export-predictions")
def export_predictions(course: str|None=None, batch: str|None=None, risk_level: str|None=None, user: User=Depends(current_user), db: Session=Depends(db_session)):
    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    rows = [json.loads(r.data_json) for r in tenant_records]
    results = predictor.predict_cohort(rows, course_filter=course, batch_filter=batch, risk_filter=risk_level)
    
    audit(db, user.tenant_id, "ml_predictions_exported")
    db.commit()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ClassPulse AI - Student Exam Pass Predictions Report"])
    writer.writerow(["Model Name", results["summary"].get("model_name", "Random Forest Classifier")])
    writer.writerow(["Model Validation Accuracy", f"{results['summary'].get('model_accuracy', 0)}%"])
    writer.writerow(["Model ROC-AUC", f"{results['summary'].get('model_roc_auc', 0)}%"])
    writer.writerow(["Cohort Pass Probability Average", f"{results['summary'].get('avg_pass_probability', 0)}%"])
    writer.writerow([])
    writer.writerow([
        "Student ID", "Course", "Batch", "Attendance Rate (%)",
        "Classes Attended", "Fee Clearance (%)", "Outstanding Fees (INR)",
        "Mock Score Avg", "Pass Probability (%)", "Predicted Outcome",
        "Risk Level", "Key Influencing Factors", "AI Recommended Interventions"
    ])
    for p in results["predictions"]:
        writer.writerow([
            p["student_id"],
            p["course_id"],
            p["batch_id"],
            p["attendance_rate"],
            p["classes_attended"],
            p["fee_clearance_pct"],
            p["outstanding_fees"],
            p["avg_mock_score"],
            p["pass_probability"],
            p["predicted_outcome"],
            p["risk_level"],
            " | ".join(p["key_factors"]),
            " | ".join(p["recommendations"])
        ])
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=classpulse-exam-pass-predictions.csv"}
    )

@app.get("/api/v1/reports/export")
def export(start: str|None=None,end: str|None=None,course: str|None=None,batch: str|None=None,user: User=Depends(current_user),db: Session=Depends(db_session)):
    validate_filters(start, end)
    recs=db.scalars(select(Record).where(Record.tenant_id==user.tenant_id)).all(); data=metrics(filtered(recs,start,end,course,batch)); audit(db,user.tenant_id,"report_exported"); db.commit()
    output=io.StringIO(); writer=csv.writer(output); writer.writerow(["ClassPulse Analytics report"]); writer.writerow(["Period",f"{start or 'All time'} to {end or 'Today'}"]); writer.writerow([]); writer.writerow(["Metric","Value"]); [writer.writerow([key.replace('_',' ').title(),value if value is not None else 'Unavailable']) for key,value in data.items()]
    return Response(output.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=classpulse-report.csv"})

@app.delete("/api/v1/account/data")
def delete_data(user: User=Depends(current_user),db: Session=Depends(db_session)):
    db.query(Record).filter_by(tenant_id=user.tenant_id).delete(); db.query(ImportJob).filter_by(tenant_id=user.tenant_id).delete(); audit(db,user.tenant_id,"tenant_data_deleted"); db.commit(); return {"message":"All imported analytics records were deleted. Your account remains active."}

@app.delete("/api/v1/account")
async def delete_account(request: Request, user: User=Depends(current_user), db: Session=Depends(db_session)):
    body = await request.json()
    if body.get("confirmation") != "DELETE": raise HTTPException(400, "Type DELETE to permanently remove this account and all of its data.")
    tenant_id = user.tenant_id
    db.query(Record).filter_by(tenant_id=tenant_id).delete()
    db.query(ImportJob).filter_by(tenant_id=tenant_id).delete()
    db.query(AuditEvent).filter_by(tenant_id=tenant_id).delete()
    db.query(User).filter_by(tenant_id=tenant_id).delete()
    db.query(Tenant).filter_by(id=tenant_id).delete()
    db.commit()
    response = JSONResponse({"message":"Your account and stored records were permanently deleted."})
    response.delete_cookie("classpulse_session")
    return response
