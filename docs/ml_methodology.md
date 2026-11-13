# ClassPulse AI — Machine Learning Methodology & Governance

## 1. Predictive Philosophy: Academic vs. Financial Risk Separation

Per SRS requirements **ML-027, ML-028, and ML-029**, ClassPulse AI strictly decouples academic exam performance from student tuition and fee payment statuses. 

### Why Decoupling is Essential
In conventional administrative software, unpaid tuition fees are frequently treated as predictive risks. In ClassPulse AI:
- An academic prediction must estimate whether a student has mastered the syllabus and is statistically prepared to clear their competitive examination (JEE, NEET, Board exams).
- Conflating fee defaulter status into exam pass probability introduces harmful socioeconomic bias.
- **Academic Model:** Predicts pass probability using only academic and attendance variables.
- **Financial Assessment:** Operates as a completely independent ledger calculation (`Clear`, `Moderate Dues`, `Payment Overdue`).

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

## 3. Evaluation Metrics & Held-Out Validation (ML-007 to ML-014)

The model is trained on a synthetic benchmark dataset calibrated to Indian competitive exam profiles ($N = 1,200$) with a stratified 80/20 train/test split:

- **Held-Out Test Accuracy:** $74.2\%$
- **F1 Score:** $79.3\%$
- **ROC-AUC Score:** $82.8\%$
- **Brier Score Loss:** $0.174$ (Well-calibrated probabilities)
- **5-Fold Stratified Cross-Validation:** $80.7\% \pm 4.26\%$
- **Feature Importances:**
  - Mock Exam Score: $\approx 39.7\%$
  - Attendance Rate: $\approx 31.1\%$
  - Classes Attended: $\approx 19.2\%$
  - Attendance Trend: $\approx 6.9\%$
  - Course Rigor: $\approx 3.1\%$

---

## 4. Retraining Engine & Validation Gates (ML-015 to ML-020)

Centres can retrain the Random Forest model on their own historical cohorts. Before a newly retrained model replaces the active model, it must pass three mandatory validation gates:

1. **Sample Size Gate (ML-017):** Requires at least $30$ verified student records with logged mock scores and actual examination outcomes.
2. **Class Balance Gate (ML-017):** Must contain at least $5$ verified pass instances and $5$ verified fail instances.
3. **Performance Gate (ML-020):** Must achieve a held-out test accuracy of $\ge 60\%$. If the candidate model fails, the engine automatically rolls back to the previous benchmark model without service interruption.

---

## 5. Transparent Handling of Missing Data (DATA-018, ML-023)

In accordance with Section 3.1 of the SRS, ClassPulse AI **never** silently fabricates synthetic mock scores for students without test data. When mock scores are absent:
- The profile is explicitly tagged with `is_incomplete = True` and `data_status = "incomplete_missing_mock_scores"`.
- Missing fields are listed under `missing_inputs`.
- Transparent UI warnings inform faculty that the prediction is tentative pending diagnostic exam scheduling.
