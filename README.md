# ClassPulse AI - Student Analytics & ML Exam Pass Predictor

A local-first coaching-centre intelligence platform with an integrated **Machine Learning Predictive Model** to analyze and forecast which students are likely to pass or fail their upcoming examinations based on spreadsheet and database records.

---

## Key Features

1. **AI Exam Success Predictor (Machine Learning Engine)**
   - Utilizes a calibrated **Random Forest Classifier Ensemble** trained on coaching-centre performance benchmarks (e.g. JEE, NEET, Foundation, Boards).
   - Generates exact continuous **Pass Probabilities (0–100%)** for each enrolled student.
   - Categorizes student risk into actionable tiers:
     - **Safe / Likely to Pass** (&ge; 75% probability)
     - **Borderline / Moderate Risk** (50% – 74.9% probability)
     - **High Risk of Failing** (&lt; 50% probability)
   - Provides **Explainable AI feature drivers**:
     - Classroom Attendance Rate (%) and sessions attended
     - Mock test / unit exam performance averages
     - Fee clearance regularity (financial commitment / dropout risk)
     - Attendance trend (improving vs declining participation)
     - Course benchmark rigor index (JEE / NEET / Foundation)
   - Generates tailored, automated **AI Recommended Interventions** for each student (e.g. parent attendance alert, 1-on-1 subject remedial sessions, advanced problem-solving tracks).

2. **Interactive Student "What-If" Simulator**
   - Faculty and academic counselors can interactively adjust attendance rates, mock scores, fee clearance, and target courses to simulate instant real-time shifts in exam pass probabilities.

3. **Universal Spreadsheet Ingestion (.csv & .xlsx)**
   - Accepts **ANY** spreadsheet format:
     - **Arbitrary Flat Student Tables**: School marks cards, attendance registers, custom Excel spreadsheets with column names like `Roll No`, `Student Name`, `Attendance %`, `Term 1 Marks`, `Fee Status`, `Due Amount`.
     - **Multi-Subject Marksheets**: Automatically detects and averages marks across subject columns (Math, Physics, Chemistry, Biology, etc.).
     - **Standard ClassPulse Log Templates**: Multi-record-type event logs (`student`, `attendance`, `exam`, `obligation`, `payment`).
   - Built-in **Automatic Column Detection**: Fuzzy regex matcher maps disparate column aliases to academic features seamlessly.
   - Dual-Mode: Direct instant ML analysis via `/api/v1/ml/analyze-sheet` (no DB needed) or 2-phase database import via `/api/v1/imports/preview`.

4. **Coaching Centre Business KPIs**
   - Enquiries, Admissions, Conversion Rates, Fee Collections, Outstanding Balances, and Attendance tracking with date and cohort filters.

5. **Reports & Prediction Export**
   - Download CSV reports of student pass predictions with risk levels, influencing factors, and recommended interventions for faculty meetings and parent consultations.

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
