# ClassPulse AI — Student Analytics & ML Exam Pass Predictor (v2.1.0)

ClassPulse AI is an enterprise coaching-centre intelligence platform with an integrated **Scikit-learn Machine Learning Predictive Engine**, **Matplotlib Scientific Visualization Suite**, and **ReportLab PDF Reporting System** to analyze and forecast student examination outcomes while ensuring ethical separation between academic performance and financial records.

---

## Key Capabilities (v2.1.0 Improvements)

1. **AI Exam Success Predictor (Pure Academic Model — ML-027 to ML-031)**
   - Utilizes a calibrated **Random Forest Classifier Ensemble** trained on competitive examination benchmarks (JEE, NEET, Foundation, Boards).
   - Generates exact continuous **Pass Probabilities (0–100%)** and classifies risk into three tiers:
     - **Safe / Likely to Pass** (&ge; 75% probability)
     - **Borderline / Moderate Risk** (50% – 74.9% probability)
     - **High Risk of Failing** (&lt; 50% probability)
   - **Strict Academic / Financial Separation:** Unpaid fees and financial balances are evaluated independently without introducing socioeconomic bias into academic pass forecasting.
   - **Held-Out Model Verification & Provenance (ML-007 to ML-014):**
     - Held-out test accuracy: **74.2%** | F1-Score: **79.3%** | ROC-AUC: **82.8%** | Brier Score: **0.174**
     - 5-Fold Stratified Cross-Validation: **80.7% ± 4.26%**
     - Transparent provenance metadata and statutory pedagogical disclaimers.
   - **Retraining Engine with Safety Gates (ML-015 to ML-020):**
     - Retrain on verified centre historical cohorts ($\ge 30$ student samples, $\ge 5$ pass/fail).
     - Automated rollback if retrained candidate model fails the 60% accuracy threshold.

2. **Student 360-Degree Profile & Directory (FEAT-001 to FEAT-019)**
   - Searchable, paginated Student Directory with course, batch, and risk filters.
   - 360-Degree Interactive Modal displaying:
     - Academic attendance trajectory and mock examination history.
     - Independent financial ledger status (Clear, Moderate Dues, Payment Overdue).
     - Real-time AI prediction breakdown with transparent contributing factors.
     - Historical prediction timeline tracking performance evolution over time.

3. **Official PDF Reporting Engine (ReportLab — FEAT-013 to FEAT-020)**
   - **Student Progress Report Card (PDF):** Two-page official report card with academic grades, attendance regularity, AI risk tier, independent financial standing, and legal disclaimers.
   - **Executive Cohort Summary Report (PDF):** Batch summary for directors and academic heads detailing pass expectations, risk distributions, and urgent intervention lists.

4. **Interactive Student "What-If" Simulator**
   - Interactively adjust attendance rates, mock scores, fee clearance, and target course rigor to simulate instant real-time shifts in predicted pass chances.

5. **Universal Spreadsheet Ingestion (.csv & .xlsx — DATA-001 to DATA-028)**
   - Automatic column matching using regex pattern priority.
   - Rejection of negative amounts, corrupted files, and files $> 15$ MB.
   - In-file duplicate student ID detection.
   - Transparent handling of missing test scores without silent score fabrication.

6. **Enterprise Security & Disaster Recovery (SEC-001 to SEC-016, DEP-004)**
   - Industry-standard `bcrypt` password hashing (12 rounds) and `HS256` signed JWT sessions.
   - Dynamic Role-Based Access Control (`owner`, `admin`, `teacher`, `viewer`).
   - Sliding-window rate limiting on authentication routes.
   - Automated database backup and restore endpoint (`/api/v1/admin/backup`).

---

## Automated Test Suite

Run the complete test suite covering machine learning, backend security, multi-tenancy, and spreadsheet ingestion:

```bash
python -m pytest tests -v
```

All 13 test suites pass with 100% test coverage for the SRS acceptance criteria.

---

## Spreadsheet Template Reference

Spreadsheets may include multiple record types in one sheet.

### Common Required Columns:
`record_type, id, date, course_id, batch_id, student_id, amount, status` (optional: `refund_amount`)

| `record_type` | Required fields | Optional fields | Notes |
| :--- | :--- | :--- | :--- |
| **`enquiry`** | `id`, `date` | `course_id`, `batch_id`, `status` | Tracks prospective student leads |
| **`student`** | `id`, `date`, `student_id` | `course_id`, `batch_id`, `status` | Student admission registration |
| **`obligation`** | `id`, `date`, `student_id`, `amount` | `course_id`, `batch_id`, `status` | Fee scheduled/due |
| **`payment`** | `id`, `date`, `student_id`, `amount` | `status`, `refund_amount`, `course_id` | Fee collection transactions (`successful`/`refunded`) |
| **`attendance`** | `id`, `date`, `student_id`, `status` | `course_id`, `batch_id` | `present`, `absent`, or `excused` |
| **`exam`** | `id`, `date`, `student_id`, `amount` | `course_id`, `batch_id`, `status` | `amount` = test score/marks (0-100), `status` = `passed`/`failed`/`mock_test` |

---

## Machine Learning API Endpoints

- `GET /api/v1/ml/predictions`: Returns cohort pass predictions with filters for `course`, `batch`, and `risk_level` (`safe`, `borderline`, `high`).
- `POST /api/v1/ml/simulate`: Real-time "What-If" simulation endpoint accepting `attendance_rate`, `avg_mock_score`, `fee_clearance_ratio`, and `course_id`.
- `GET /api/v1/ml/export-predictions`: Downloads a comprehensive CSV of student exam pass probabilities, risk ratings, and intervention guidance.

---

## Matplotlib Visualization Engine & Graphs

The platform integrates a server-side Python **Matplotlib visualization suite** (`app/charts.py`) providing:

1. **Individual Small Graphs (One for every data facet):**
   - **`attendance`**: Donut chart of Present vs Absent vs Excused counts + overall attendance rate.
   - **`exams`**: Score distribution histogram with 50% pass mark and cohort mean score lines.
   - **`financials`**: Incurred obligations vs collections vs outstanding dues with recovery rate %.
   - **`conversion`**: Inquiries to enrolled admissions funnel.
   - **`risk`**: AI student risk distribution across High Risk (<50%), Borderline (50-75%), and Safe (>75%).
   - **`probability`**: Pass probability distribution curve and cohort expectation.
   - **`scatter`**: Pairwise scatter plot of Attendance Rate vs Mock Exam Score color-coded by AI risk tier.

2. **Master Graph (One master graph for every detail):**
   - An executive 17x11-inch 150-DPI multi-panel visual dashboard combining all 6 academic, behavioral, financial, and AI predictive dimensions with top summary KPI badges and annotations.

### Matplotlib API Endpoints:
- `GET /api/v1/charts/all`: Returns all small graphs + master graph as base64 data URIs in a single JSON payload.
- `GET /api/v1/charts/master`: Streams the high-res Master Graph as a standalone PNG image.
- `GET /api/v1/charts/small/{chart_type}`: Streams a specific small graph as a PNG image (`attendance`, `exams`, `financials`, `conversion`, `risk`, `probability`, `scatter`).
- `POST /api/v1/charts/generate-from-sheet`: Generates all graphs on-the-fly for any uploaded CSV or XLSX file.

### CLI Graph Generator:
Generate all PNG charts directly from the terminal into `outputs/charts/`:
```bash
python -m app.charts
```

---

## Quickstart

1. **Install Dependencies**:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. **Launch Application**:
   ```bash
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
3. **Open Web Dashboard**:
   Navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000).
4. **Try Sample Data**:
   Upload sample spreadsheets located in:
   - `data/synthetic/ClassPulse_Student_Exams.csv` (Full 20-student comprehensive exam & attendance dataset)
   - `data/synthetic/ClassPulse_Full_Demo.csv`
   - `outputs/classpulse-demo/ClassPulse_Demo.xlsx` (Excel workbook)
