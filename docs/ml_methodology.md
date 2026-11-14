# ClassPulse AI — Machine Learning Methodology & Governance (v2.0)

## 1. Predictive Philosophy: Academic vs. Financial Risk Separation

Per SRS requirements **ML-027, ML-028, and ML-029**, ClassPulse AI strictly decouples academic exam performance from student tuition and fee payment statuses.

### Ethical Decoupling
Treating unpaid tuition fees as a direct penalty in academic success forecasts introduces severe socioeconomic bias. In ClassPulse AI:
- **Academic Model:** Predicts pass probability using only academic and attendance variables.
- **Financial Assessment:** Operates as an independent administrative ledger assessment (`Clear`, `Moderate Dues`, `High Financial Due`).

---

## 2. Feature Vector Definition

The Random Forest model consumes an input feature vector $X \in \mathbb{R}^5$ containing:

1. **Mock Exam Score ($x_1$):** Average score scaled to a normalized $[0, 100]$ basis.
2. **Attendance Rate ($x_2$):** Classroom attendance percentage $[0, 100]$.
3. **Classes Attended ($x_3$):** Absolute count of physical/virtual sessions attended.
4. **Attendance Trend ($x_4$):** Velocity of attendance $(\Delta \text{Rate} = \text{Rate}_{\text{recent}} - \text{Rate}_{\text{prior}})$.
5. **Course Rigor Index ($x_5$):** Multiplier reflecting examination difficulty:
   - JEE Advanced: $1.25$
   - NEET: $1.20$
   - General / Other: $1.00$
   - Foundation (Class 9-10): $0.90$

---

## 3. Benchmark Model Provenance & Transparency (ML-005, ML-008, ML-011)

The base model version is **`v2.1.0-benchmark`**, trained on a synthetic benchmark dataset calibrated to Indian competitive exam profiles ($N = 1,200$) with a stratified 80/20 train/test split.

> [!IMPORTANT]
> The system explicitly labels this model as `synthetic_benchmark` in the user interface, API responses (`provenance`), and exported PDF reports. Benchmark metrics are explicitly documented as synthetic benchmark evaluations and are never falsely claimed to represent real-world institution outcomes.

### Held-Out Evaluation Metrics:
- **Held-Out Test Accuracy:** $74.2\%$
- **F1 Score:** $79.3\%$
- **ROC-AUC Score:** $82.8\%$
- **Brier Score Loss:** $0.174$ (Well-calibrated probabilities)
- **5-Fold Stratified Cross-Validation:** $80.7\% \pm 4.26\%$

---

## 4. Retraining Engine & Validation Gates (ML-015 to ML-020)

Centres can retrain the Random Forest model on their own historical cohorts. Before a newly retrained candidate model replaces the active model, it must pass three mandatory validation gates:

1. **Sample Size Gate (ML-017):** Requires at least $30$ verified student records with logged mock scores and actual examination outcomes.
2. **Class Balance Gate (ML-017):** Must contain at least $5$ verified pass instances and $5$ verified fail instances.
3. **Performance Gate (ML-020):** Must achieve a held-out test accuracy of $\ge 60\%$. If the candidate model fails, the engine automatically rolls back to the previous benchmark model without service interruption.

---

## 5. Strict Data Integrity: No Data Fabrication (DATA-018, ML-023)

In accordance with the SRS, ClassPulse AI **never** fabricates missing student information:
- If a spreadsheet lacks fee information, no default fee obligations (e.g. ₹20,000) are created.
- If a spreadsheet lacks attendance logs, no fake daily attendance records are synthesized.
- If mock scores are missing, the prediction is transparently flagged with `is_tentative = True`, `is_incomplete = True`, and `data_status = "incomplete_missing_mock_scores"`.
