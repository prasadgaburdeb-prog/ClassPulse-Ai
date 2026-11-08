const $ = s => document.querySelector(s), app = $('#app');
let user = null, preview = null, currentRiskFilter = 'all';

const money = n => n == null ? 'Unavailable' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n);

async function api(path, options = {}) {
  let r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  let d = r.headers.get('content-type')?.includes('json') ? await r.json() : await r.text();
  if (!r.ok) throw new Error(d.detail || 'Something went wrong.');
  return d;
}

function auth() {
  app.innerHTML = `
    <section class="panel auth">
      <div class="brand">Class<span>Pulse</span> <span class="ai-badge">AI Powered</span></div>
      <p class="sub">Coaching-centre intelligence & machine learning student pass predictions.</p>
      
      <div style="margin: 20px 0 14px;">
        <button id="instantDemoBtn" style="background: linear-gradient(135deg, #2563eb, #10b981); color: white; width: 100%; padding: 13px 18px; font-size: 14px; font-weight: 700; border-radius: 8px; box-shadow: 0 4px 14px rgba(37, 99, 235, 0.28); border: none; cursor: pointer;">
          ⚡ 1-Click Instant Demo (Explore Matplotlib Charts & Sample Data)
        </button>
        <p class="small" style="text-align: center; margin: 6px 0 0; color: var(--muted);">Loads full student cohort, mock tests, fee data & Matplotlib graphs immediately!</p>
      </div>

      <div style="display: flex; align-items: center; margin: 18px 0 14px;">
        <div style="flex: 1; height: 1px; background: var(--line);"></div>
        <span class="small" style="padding: 0 10px; color: var(--muted);">or sign in to your centre</span>
        <div style="flex: 1; height: 1px; background: var(--line);"></div>
      </div>

      <div id="message"></div>
      <div class="two">
        <button class="secondary" id="showLogin">Sign in</button>
        <button class="secondary" id="showRegister">Create centre</button>
      </div>
      <form id="form"></form>
    </section>
  `;
  $('#showLogin').onclick = () => form('login');
  $('#showRegister').onclick = () => form('register');
  $('#instantDemoBtn').onclick = async () => {
    try {
      $('#instantDemoBtn').textContent = 'Loading demo data & Matplotlib graphs...';
      let d = await api('/api/v1/auth/demo', { method: 'POST' });
      user = d.user;
      dashboard();
    } catch (e) {
      alert('Demo login failed: ' + e.message);
      $('#instantDemoBtn').textContent = '⚡ 1-Click Instant Demo (Explore Matplotlib Charts & Sample Data)';
    }
  };
  form('login');
}

function form(kind) {
  $('#message').innerHTML = '';
  $('#form').innerHTML = kind === 'login' ? `
    <p class="small">Sign in to your centre account.</p>
    <label>Email</label>
    <input name="email" type="email" autocomplete="email" required>
    <label>Password</label>
    <input name="password" type="password" autocomplete="current-password" required>
    <br><button>Sign in</button>
  ` : `
    <p class="small">Create your centre account to explore analytics and ML exam predictions.</p>
    <label>Centre name</label>
    <input name="centre_name" autocomplete="organization" required>
    <label>Email</label>
    <input name="email" type="email" autocomplete="email" required>
    <label>Password</label>
    <input name="password" type="password" autocomplete="new-password" minlength="8" required>
    <p class="small">Use at least 8 characters.</p>
    <button>Create centre account</button>
  `;

  $('#form').onsubmit = async e => {
    e.preventDefault();
    try {
      let d = await api('/api/v1/auth/' + kind, {
        method: 'POST',
        body: JSON.stringify(Object.fromEntries(new FormData(e.target)))
      });
      user = d.user;
      dashboard();
    } catch (x) {
      $('#message').innerHTML = '<p class="notice error">' + x.message + '</p>';
    }
  };
}

function dashboard() {
  app.innerHTML = `
    <header>
      <div>
        <div class="brand">Class<span>Pulse</span> <span class="ai-badge">AI Predictor</span></div>
        <div class="sub">${user.centre_name} · Real-Time Student Analytics & ML Pass Probability</div>
      </div>
      <button class="secondary" id="logout">Sign out</button>
    </header>

    <!-- Top Sticky Navigation Bar -->
    <nav class="dashboard-nav">
      <button class="nav-tab charts-tab" id="navCharts">📈 Matplotlib Charts (Master + 7 Small Graphs)</button>
      <button class="nav-tab" id="navKPIs">📊 Overview KPIs</button>
      <button class="nav-tab" id="navAI">🤖 AI Pass Predictor</button>
      <button class="nav-tab" id="navRecords">📋 Data Records</button>
      <button class="nav-tab" id="navImport">📁 Import Sheets</button>
    </nav>

    <!-- Global Filters -->
    <section class="panel" id="filtersSection">
      <div class="filters">
        <div><label>Start date</label><input id="start" type="date"></div>
        <div><label>End date</label><input id="end" type="date"></div>
        <div><label>Course ID</label><input id="course" placeholder="e.g. JEE, NEET"></div>
        <div><label>Batch ID</label><input id="batch" placeholder="e.g. JEE-A"></div>
        <button id="apply">Apply filters</button>
        <button id="resetFilters" class="secondary">Reset</button>
        <button id="jumpChartsBtn" style="background: #2563eb; color: white;">📈 Jump to Charts</button>
        <button id="export" class="secondary">Download KPI Report</button>
      </div>
      <p id="filterStatus" class="small"></p>
    </section>

    <!-- Core KPI Cards -->
    <section class="grid" id="cards"></section>

    <!-- MATPLOTLIB VISUAL ANALYTICS & MASTER INTELLIGENCE GRAPH -->
    <section class="panel" id="matplotlibSection" style="border-top: 3px solid #2563eb; scroll-margin-top: 70px;">
      <div class="panel-header">
        <div>
          <h2>📈 Matplotlib Visual Analytics & Master Intelligence Graph</h2>
          <p class="small">High-resolution scientific visualizations generated via Python Matplotlib: individual focused graphs for every metric dimension, plus a unified Master Graph for executive reporting.</p>
        </div>
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
          <a id="downloadMasterLink" class="button" style="text-decoration: none; display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 8px 14px; background: #1e293b; color: white; border-radius: 6px; font-weight: 600;" href="/api/v1/charts/master" target="_blank" download="classpulse-master-chart.png">&#8595; Download Master Graph (PNG)</a>
          <button id="refreshChartsBtn" class="secondary" style="font-size: 12px; padding: 8px 14px;">&#8635; Refresh Graphs</button>
        </div>
      </div>

      <!-- Master Graph Section -->
      <div style="margin-bottom: 24px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <div>
            <h3 style="margin: 0; font-size: 15px; color: var(--ink);">Unified Master Graph (All Academic & Financial Details)</h3>
            <p class="small" style="margin: 2px 0 0;">Multi-panel executive dashboard combining attendance regularity, mock exam performance, fee obligations & collections, admissions funnel, and AI risk distribution into a single figure.</p>
          </div>
          <span class="badge badge-success" style="font-size: 11px;">150 DPI High-Res</span>
        </div>
        <div id="masterGraphBox" class="graph-master-box">
          <div style="text-align: center; padding: 30px; color: var(--muted);">&#9680; Generating Master Graph with Matplotlib...</div>
        </div>
      </div>

      <!-- Individual Small Graphs for Every Data Dimension -->
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <div>
            <h3 style="margin: 0; font-size: 15px; color: var(--ink);">Individual Data Graphs (One Graph per Data Dimension)</h3>
            <p class="small" style="margin: 2px 0 0;">Dedicated Matplotlib visualizations for granular analysis of each individual KPI.</p>
          </div>
        </div>
        <div class="small-graphs-grid" id="smallGraphsGrid">
          <div style="text-align: center; padding: 30px; color: var(--muted); grid-column: 1 / -1;">Rendering individual data graphs...</div>
        </div>
      </div>
    </section>

    <!-- MACHINE LEARNING PREDICTION SUITE -->
    <section class="panel" id="mlSection" style="border-top: 3px solid var(--accent); scroll-margin-top: 70px;">
      <div class="panel-header">
        <div>
          <h2>AI Student Exam Pass Predictor</h2>
          <p class="small">Machine Learning model (Random Forest Classifier) analyzing attendance regularity, mock exam scores, fee adherence, and course benchmark rigor to predict student pass probabilities.</p>
        </div>
        <button id="exportPredictions" class="secondary">Export Predictions (CSV)</button>
      </div>

      <!-- Cohort Summary Metrics -->
      <div class="grid" id="mlSummaryCards"></div>

      <!-- Universal Spreadsheet Analyzer Box -->
      <div style="background: var(--info-light); border: 1px solid #b3e5fc; border-radius: 10px; padding: 14px 18px; margin: 16px 0;">
        <div style="font-weight: 700; color: #0277bd; font-size: 13px;">Universal Spreadsheet Ingestion & Automatic Schema Detection</div>
        <p class="small" style="margin: 4px 0 10px; color: #01579b;">
          Works with <strong>ANY</strong> custom spreadsheet (CSV or Excel .xlsx). Upload school marks cards, attendance registers, or tuition rosters with custom column names (e.g. <em>Roll No, Student Name, Attendance %, Term Marks, Fees</em>). The AI auto-detects your columns and generates instant predictions!
        </p>
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
          <input id="directSheetFile" type="file" accept=".csv, .xlsx" style="max-width: 320px; font-size: 12px; padding: 6px 10px; background: white;">
          <button id="directSheetBtn" style="padding: 7px 14px; font-size: 12px;">Analyze Custom Spreadsheet</button>
        </div>
        <div id="directSheetStatus" style="margin-top: 10px;"></div>
      </div>

      <!-- Risk Filter Tabs -->
      <div style="display: flex; gap: 8px; margin: 16px 0; align-items: center; flex-wrap: wrap;">
        <span class="small" style="font-weight: 600;">Filter by Risk:</span>
        <button class="risk-filter-btn" id="filterRiskAll" onclick="setRiskFilter('all')">All Students</button>
        <button class="risk-filter-btn secondary" id="filterRiskHigh" onclick="setRiskFilter('high')">High Risk (&lt; 50%)</button>
        <button class="risk-filter-btn secondary" id="filterRiskBorderline" onclick="setRiskFilter('borderline')">Borderline (50 - 75%)</button>
        <button class="risk-filter-btn secondary" id="filterRiskSafe" onclick="setRiskFilter('safe')">Safe (&gt; 75%)</button>
      </div>

      <!-- Student Prediction Table -->
      <div id="mlPredictionsResult" class="table-wrap"></div>

      <!-- Interactive What-If Simulator & Model Explainability -->
      <div class="two" style="margin-top: 24px;">
        <!-- Simulator -->
        <div class="sim-box">
          <h3 style="margin-top: 0; font-size: 15px;">Student What-If Risk Simulator</h3>
          <p class="small">Simulate how improving attendance or test scores affects a student's predicted exam pass probability.</p>

          <div class="sim-slider-row">
            <div class="sim-slider-label">
              <span>Attendance Rate</span>
              <span id="simAttVal" class="sim-slider-val">75%</span>
            </div>
            <input id="simAtt" type="range" min="10" max="100" value="75" step="1">
          </div>

          <div class="sim-slider-row">
            <div class="sim-slider-label">
              <span>Mock / Unit Exam Average</span>
              <span id="simMockVal" class="sim-slider-val">65 / 100</span>
            </div>
            <input id="simMock" type="range" min="10" max="100" value="65" step="1">
          </div>

          <div class="sim-slider-row">
            <div class="sim-slider-label">
              <span>Fee Clearance</span>
              <span id="simFeeVal" class="sim-slider-val">100%</span>
            </div>
            <input id="simFee" type="range" min="0" max="100" value="100" step="5">
          </div>

          <div class="sim-slider-row">
            <label>Course Rigor Target</label>
            <select id="simCourse">
              <option value="JEE">JEE (Advanced & Mains - Rigor 1.25x)</option>
              <option value="NEET">NEET (Medical Entrance - Rigor 1.20x)</option>
              <option value="Foundation">Foundation (Class 9-10 - Rigor 0.90x)</option>
              <option value="General">General / Other (Rigor 1.00x)</option>
            </select>
          </div>

          <!-- Live Prediction Display -->
          <div class="sim-result-card" id="simResultCard">
            <div class="label">Simulated Pass Probability</div>
            <div class="sim-result-prob" id="simProbText">--</div>
            <div id="simRiskBadge" style="margin: 8px 0;"></div>
            <div id="simAdvice" class="small" style="margin-top: 4px;"></div>
          </div>
        </div>

        <!-- Explainable AI / Feature Importance -->
        <div class="sim-box">
          <h3 style="margin-top: 0; font-size: 15px;">Model Explainability & Feature Drivers</h3>
          <p class="small">How the Machine Learning model weights academic & behavioral signals when computing pass predictions:</p>
          <div id="featImportanceBox" style="margin-top: 16px;"></div>

          <div style="background: white; border: 1px solid var(--line); border-radius: 8px; padding: 12px; margin-top: 16px;">
            <div style="font-size: 12px; font-weight: 700; color: var(--ink);">Model Verification Details</div>
            <div class="small" id="modelDetailsText" style="margin-top: 4px; line-height: 1.6;"></div>
          </div>
        </div>
      </div>
    </section>

    <!-- Detailed Raw Data Records -->
    <section class="panel" id="recordsSection" style="scroll-margin-top: 70px;">
      <div class="details-head">
        <div>
          <h2>Data Records Browser</h2>
          <p class="small">Every imported record from your spreadsheets. Dashboard filters apply here too.</p>
        </div>
        <div>
          <label>Show Record Type</label>
          <select id="detailsType">
            <option value="">All records</option>
            <option value="exam">Exams & Mock Tests</option>
            <option value="student">Admissions</option>
            <option value="attendance">Attendance</option>
            <option value="obligation">Fee obligations</option>
            <option value="payment">Payments</option>
            <option value="enquiry">Enquiries</option>
          </select>
        </div>
      </div>
      <div id="detailsResult" class="table-wrap"></div>
    </section>

    <!-- Upload Sheets / CSV / XLSX -->
    <section class="panel" id="importSection" style="scroll-margin-top: 70px;">
      <h2>Import Spreadsheet</h2>
      <p class="small">Upload <strong>.csv</strong> or <strong>.xlsx (Excel)</strong> files up to 15 MB. Validates all rows before import. Supports enquiry, student, obligation, payment, attendance, and exam records.</p>
      <input id="file" type="file" accept=".csv, .xlsx">
      <p><button id="preview">Validate and preview</button></p>
      <div id="importResult"></div>
    </section>

    <!-- Import History -->
    <section class="panel">
      <h2>Import history</h2>
      <div id="history"></div>
    </section>

    <!-- Account Actions -->
    <section class="panel">
      <h2>Metric definitions & Data Management</h2>
      <p id="definition" class="small"></p>
      <div style="display: flex; gap: 10px; margin-top: 14px;">
        <button id="delete" class="danger">Delete imported data</button>
        <button id="deleteAccount" class="danger">Delete centre account</button>
      </div>
    </section>
  `;

  $('#logout').onclick = async () => {
    await api('/api/v1/auth/logout', { method: 'POST' });
    auth();
  };

  function highlightSection(el) {
    if (!el) return;
    el.classList.remove('section-highlight');
    void el.offsetWidth;
    el.classList.add('section-highlight');
  }

  $('#navCharts').onclick = () => {
    $('#matplotlibSection')?.scrollIntoView({ behavior: 'smooth' });
    highlightSection($('#matplotlibSection'));
  };
  $('#navKPIs').onclick = () => {
    $('#filtersSection')?.scrollIntoView({ behavior: 'smooth' });
  };
  $('#navAI').onclick = () => {
    $('#mlSection')?.scrollIntoView({ behavior: 'smooth' });
    highlightSection($('#mlSection'));
  };
  $('#navRecords').onclick = () => {
    $('#recordsSection')?.scrollIntoView({ behavior: 'smooth' });
  };
  $('#navImport').onclick = () => {
    $('#importSection')?.scrollIntoView({ behavior: 'smooth' });
  };
  $('#jumpChartsBtn').onclick = () => {
    $('#matplotlibSection')?.scrollIntoView({ behavior: 'smooth' });
    highlightSection($('#matplotlibSection'));
  };

  $('#apply').onclick = () => { load(); loadPredictions(); loadCharts(); loadDetails(); };
  $('#resetFilters').onclick = () => {
    ['start', 'end', 'course', 'batch'].forEach(id => $('#' + id).value = '');
    load(); loadPredictions(); loadCharts(); loadDetails();
  };
  $('#export').onclick = () => window.location = '/api/v1/reports/export?' + params();
  $('#exportPredictions').onclick = () => window.location = '/api/v1/ml/export-predictions?' + params() + (currentRiskFilter !== 'all' ? '&risk_level=' + currentRiskFilter : '');
  $('#directSheetBtn').onclick = analyzeDirectSheet;
  $('#refreshChartsBtn').onclick = () => loadCharts();
  $('#preview').onclick = upload;
  $('#detailsType').onchange = loadDetails;
  $('#delete').onclick = async () => {
    if (confirm('Delete all imported records for this centre?')) {
      await api('/api/v1/account/data', { method: 'DELETE' });
      load(); loadPredictions(); loadCharts(); loadDetails();
    }
  };
  $('#deleteAccount').onclick = deleteAccount;

  // Simulator event listeners
  ['simAtt', 'simMock', 'simFee', 'simCourse'].forEach(id => {
    $('#' + id).addEventListener('input', runSimulation);
  });

  load();
  loadPredictions();
  loadCharts();
  loadDetails();
  runSimulation();
}

function params() {
  return new URLSearchParams(Object.fromEntries(['start', 'end', 'course', 'batch'].map(k => [k, $('#' + k).value]).filter(x => x[1])));
}

function setRiskFilter(level) {
  currentRiskFilter = level;
  ['all', 'high', 'borderline', 'safe'].forEach(k => {
    let btn = $('#filterRisk' + k.charAt(0).toUpperCase() + k.slice(1));
    if (btn) {
      if (k === level) {
        btn.className = 'risk-filter-btn';
      } else {
        btn.className = 'risk-filter-btn secondary';
      }
    }
  });
  loadPredictions();
}

async function load() {
  try {
    let d = await api('/api/v1/analytics/overview?' + params()), m = d.metrics;
    $('#definition').textContent = d.definition;
    let f = d.filters;
    let active = [f.start && 'from ' + f.start, f.end && 'to ' + f.end, f.course && 'course ' + f.course, f.batch && 'batch ' + f.batch].filter(Boolean);
    $('#filterStatus').textContent = active.length ? `Applied: ${active.join(', ')} · ${f.matched_records} matching records.` : `Showing all data · ${f.matched_records} records.`;
    
    let prior = d.comparison;
    let cards = [
      ['Enquiries', m.enquiries],
      ['Admissions', m.admissions],
      ['Conversion rate', m.conversion_rate == null ? 'Unavailable' : m.conversion_rate + '%'],
      ['Fee collection', money(m.fee_collection)],
      ['Outstanding fees', money(m.outstanding_fees)],
      ['Attendance rate', m.attendance_rate == null ? 'Unavailable' : m.attendance_rate + '%'],
      ['Mock Tests Logged', m.mock_exams_count || 0],
      ['Mock Exam Avg', m.avg_mock_score == null ? 'Unavailable' : m.avg_mock_score + ' / 100']
    ];

    $('#cards').innerHTML = cards.map(([a, b]) => `
      <article class="card">
        <div class="label">${a}</div>
        <div class="value">${b}</div>
        ${prior ? `<div class="small">Previous period: ${a === 'Fee collection' ? money(prior.fee_collection) : a === 'Attendance rate' ? (prior.attendance_rate ?? 'Unavailable') + '%' : 'Available when filtered'}</div>` : ''}
      </article>
    `).join('');

    let h = await api('/api/v1/imports');
    $('#history').innerHTML = h.length ? `
      <table>
        <tr><th>File</th><th>Status</th><th>Accepted</th><th>Rejected</th><th>Imported</th></tr>
        ${h.map(x => `<tr><td>${x.filename}</td><td>${x.status}</td><td>${x.accepted_rows}</td><td>${x.rejected_rows}</td><td>${new Date(x.created_at).toLocaleString()}</td></tr>`).join('')}
      </table>
    ` : '<p class="small">No imports yet. Upload a CSV or Excel sheet above to get started.</p>';
  } catch (x) {
    console.error(x);
  }
}

async function loadPredictions() {
  try {
    let q = params();
    if (currentRiskFilter !== 'all') {
      q.set('risk_level', currentRiskFilter);
    }
    let data = await api('/api/v1/ml/predictions?' + q);
    let s = data.summary;

    // Render ML Summary Cards
    $('#mlSummaryCards').innerHTML = `
      <article class="card">
        <div class="label">Total Students</div>
        <div class="value">${s.total_students}</div>
        <div class="small">Across active courses</div>
      </article>
      <article class="card">
        <div class="label">Cohort Pass Probability</div>
        <div class="value" style="color: ${s.avg_pass_probability >= 70 ? 'var(--safe)' : s.avg_pass_probability >= 50 ? 'var(--warning)' : 'var(--danger)'};">
          ${s.avg_pass_probability}%
        </div>
        <div class="small">Cohort average expectation</div>
      </article>
      <article class="card">
        <div class="label">High Risk (&lt; 50%)</div>
        <div class="value" style="color: var(--danger);">${s.high_risk}</div>
        <div class="small">Require urgent intervention</div>
      </article>
      <article class="card">
        <div class="label">Likely to Pass (&ge; 75%)</div>
        <div class="value" style="color: var(--safe);">${s.likely_to_pass}</div>
        <div class="small">${s.borderline} borderline students</div>
      </article>
    `;

    // Render Feature Importance
    if (s.feature_importances) {
      $('#featImportanceBox').innerHTML = s.feature_importances.map(f => `
        <div class="feat-item">
          <div class="feat-name">${f.feature}</div>
          <div class="feat-bar-bg"><div class="feat-bar-fill" style="width: ${f.importance_pct}%;"></div></div>
          <div class="feat-pct">${f.importance_pct}%</div>
        </div>
      `).join('');
    }

    $('#modelDetailsText').innerHTML = `
      Algorithm: <strong>${s.model_name}</strong><br>
      Validation Accuracy: <strong>${s.model_accuracy}%</strong> &nbsp;|&nbsp; ROC-AUC: <strong>${s.model_roc_auc}%</strong><br>
      Calibrated on real-world Indian coaching entrance examination benchmarks (JEE/NEET/Boards).
    `;

    // Render Student Predictions Table
    renderPredictionsList(data.predictions, s);
  } catch (e) {
    console.error(e);
    $('#mlPredictionsResult').innerHTML = '<p class="notice error">Failed to load ML predictions: ' + e.message + '</p>';
  }
}

function renderPredictionsList(preds, s) {
  if (!preds || !preds.length) {
    $('#mlPredictionsResult').innerHTML = '<p class="small" style="padding: 12px 0;">No student records match the selected risk filter.</p>';
    return;
  }

  let rowsHtml = preds.map(p => {
    let color = p.pass_probability >= 75 ? 'var(--safe)' : p.pass_probability >= 50 ? 'var(--warning)' : 'var(--danger)';
    let badgeClass = p.pass_probability >= 75 ? 'badge-success' : p.pass_probability >= 50 ? 'badge-warning' : 'badge-danger';
    return `
      <tr>
        <td><strong>${p.student_id}</strong></td>
        <td>${p.course_id} <span class="small">(${p.batch_id})</span></td>
        <td>
          <strong>${p.attendance_rate}%</strong>
          <div class="small">${p.classes_attended} / ${p.total_classes} sessions</div>
        </td>
        <td>
          ${p.has_mock_records ? `<strong>${p.avg_mock_score}</strong>/100` : `<span class="small" title="Estimated from attendance & course rigor">${p.avg_mock_score}/100 (est.)</span>`}
        </td>
        <td>
          ${p.fee_clearance_pct}%
          ${p.outstanding_fees > 0 ? `<div class="small" style="color:var(--danger)">Due: ${money(p.outstanding_fees)}</div>` : ''}
        </td>
        <td style="min-width: 140px;">
          <div class="prob-meter">
            <div class="prob-bar">
              <div class="prob-fill" style="width: ${p.pass_probability}%; background: ${color};"></div>
            </div>
            <div class="prob-val" style="color: ${color};">${p.pass_probability}%</div>
          </div>
        </td>
        <td><span class="badge ${badgeClass}">${p.risk_level}</span></td>
        <td>
          <ul style="margin: 0; padding-left: 16px; font-size: 12px;">
            ${p.recommendations.map(r => `<li>${r}</li>`).join('')}
          </ul>
        </td>
      </tr>
    `;
  }).join('');

  $('#mlPredictionsResult').innerHTML = `
    <p class="small" style="margin-bottom: 8px;">Showing ${preds.length} predicted students (sorted by risk level):</p>
    <table>
      <thead>
        <tr>
          <th>Student ID</th>
          <th>Course / Batch</th>
          <th>Attendance</th>
          <th>Mock Score</th>
          <th>Fee Status</th>
          <th>Pass Probability</th>
          <th>Risk Level</th>
          <th>AI Guidance & Recommended Action</th>
        </tr>
      </thead>
      <tbody>
        ${rowsHtml}
      </tbody>
    </table>
  `;
}

async function loadCharts() {
  let masterBox = $('#masterGraphBox');
  let smallGrid = $('#smallGraphsGrid');
  if (masterBox) {
    masterBox.innerHTML = '<div style="text-align: center; padding: 30px; color: var(--muted);">&#9680; Rendering Master Graph via Matplotlib...</div>';
  }
  if (smallGrid) {
    smallGrid.innerHTML = '<div style="text-align: center; padding: 30px; color: var(--muted); grid-column: 1 / -1;">Generating individual Matplotlib charts...</div>';
  }

  try {
    let q = params();
    let d = await api('/api/v1/charts/all?' + q);
    renderChartsBundle(d, q.toString());
  } catch (err) {
    console.error('Failed to load Matplotlib charts:', err);
    if (masterBox) masterBox.innerHTML = `<p class="notice error">Failed to load graphs: ${err.message}</p>`;
    if (smallGrid) smallGrid.innerHTML = `<p class="notice error" style="grid-column: 1 / -1;">Failed to load small graphs: ${err.message}</p>`;
  }
}

function renderChartsBundle(d, queryStr) {
  let q = queryStr || '';
  let masterDownload = $('#downloadMasterLink');
  if (masterDownload) {
    if (q && q !== 'custom-sheet') {
      masterDownload.href = '/api/v1/charts/master?' + q;
    } else if (d.master_graph) {
      masterDownload.href = d.master_graph;
    }
  }

  let masterBox = $('#masterGraphBox');
  if (masterBox) {
    if (d.master_graph) {
      masterBox.innerHTML = `
        <div style="position: relative;">
          <img src="${d.master_graph}" alt="ClassPulse Master Graph" style="width: 100%; height: auto; display: block; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
          <div style="position: absolute; top: 12px; right: 12px; display: flex; gap: 8px;">
            <a href="${d.master_graph}" download="classpulse-master-graph.png" class="badge" style="background: rgba(15, 23, 42, 0.85); color: white; text-decoration: none; padding: 6px 12px; cursor: pointer; font-size: 11px; font-weight: 600; box-shadow: 0 2px 6px rgba(0,0,0,0.2);">
              &#8595; Save Master PNG
            </a>
          </div>
        </div>
      `;
    } else {
      masterBox.innerHTML = '<p class="small" style="padding: 24px; text-align: center;">No data available to plot master graph.</p>';
    }
  }

  let smallGrid = $('#smallGraphsGrid');
  if (smallGrid && d.small_graphs) {
    const titles = {
      attendance: { title: "1. Attendance Breakdown & Rate", desc: "Present, Absent & Excused distribution", badge: "Attendance" },
      exams: { title: "2. Exam & Mock Score Distribution", desc: "Score spread against 50% pass mark", badge: "Exams" },
      financials: { title: "3. Fee Obligations & Collections", desc: "Collected fees vs. outstanding balance", badge: "Financials" },
      conversion: { title: "4. Admissions Conversion Funnel", desc: "Inquiries converted into enrolled students", badge: "Admissions" },
      risk: { title: "5. AI Student Risk Segmentation", desc: "Safe, Borderline & High Risk student count", badge: "AI Risk" },
      probability: { title: "6. Pass Probability Spread", desc: "Distribution curve of predicted pass chances", badge: "Predictions" },
      scatter: { title: "7. Attendance vs. Score Correlation", desc: "Scatter matrix color-coded by AI risk tier", badge: "Correlation" }
    };

    smallGrid.innerHTML = Object.entries(d.small_graphs).map(([key, dataUri]) => {
      let meta = titles[key] || { title: key.toUpperCase(), desc: "Matplotlib Data Chart", badge: "Data" };
      if (!dataUri) {
        return `
          <div class="small-graph-card">
            <div class="small-graph-head">
              <div>
                <div class="small-graph-title">${meta.title}</div>
                <div class="small-graph-desc">${meta.desc}</div>
              </div>
              <span class="badge" style="background:#f1f5f9; color:#475569;">${meta.badge}</span>
            </div>
            <p class="small" style="padding: 40px 10px; text-align: center; color: var(--muted);">No data available</p>
          </div>
        `;
      }
      let directUrl = (q && q !== 'custom-sheet') ? `/api/v1/charts/small/${key}?${q}` : dataUri;
      return `
        <div class="small-graph-card">
          <div class="small-graph-head">
            <div>
              <div class="small-graph-title">${meta.title}</div>
              <div class="small-graph-desc">${meta.desc}</div>
            </div>
            <span class="badge" style="background:#e0f2fe; color:#0369a1; font-size:10px;">${meta.badge}</span>
          </div>
          <div class="small-graph-img-wrap" onclick="window.open('${dataUri}', '_blank')">
            <img src="${dataUri}" alt="${meta.title}" class="small-graph-img">
          </div>
          <div class="small-graph-foot">
            <a href="${directUrl}" download="classpulse-${key}-chart.png" class="small-graph-btn" style="text-decoration:none;">
              &#8595; Download PNG
            </a>
            <button class="small-graph-btn secondary" onclick="window.open('${dataUri}', '_blank')">
              Full View
            </button>
          </div>
        </div>
      `;
    }).join('');
  }
}

async function analyzeDirectSheet() {
  let fileInput = $('#directSheetFile');
  let f = fileInput.files[0];
  if (!f) return alert('Select any CSV or XLSX spreadsheet first.');
  let fd = new FormData();
  fd.append('file', f);
  $('#directSheetStatus').innerHTML = '<p class="small" style="color:#0277bd;">Analyzing columns and computing ML predictions...</p>';

  try {
    let r = await fetch('/api/v1/ml/analyze-sheet', { method: 'POST', body: fd });
    let d = await r.json();
    if (!r.ok) throw new Error(d.detail);

    let mapText = Object.entries(d.detected_columns).map(([k, v]) => `<strong>${k}</strong> &rarr; <em>"${v}"</em>`).join(', ');
    $('#directSheetStatus').innerHTML = `
      <div class="notice" style="background:#e8f5e9; color:#1b5e20; margin: 8px 0; font-size:12px;">
        <strong>Auto-Detected Schema:</strong> ${d.sheet_type}<br>
        <strong>Mapped Fields:</strong> ${mapText || 'Standard attributes'}<br>
        <strong>Analyzed:</strong> ${d.summary.total_students} students | Avg Pass Probability: <strong>${d.summary.avg_pass_probability}%</strong>
      </div>
    `;

    renderPredictionsList(d.predictions, d.summary);

    // Also generate and render Matplotlib graphs for this custom uploaded spreadsheet!
    try {
      let fdCharts = new FormData();
      fdCharts.append('file', f);
      let cr = await fetch('/api/v1/charts/generate-from-sheet', { method: 'POST', body: fdCharts });
      if (cr.ok) {
        let cd = await cr.json();
        renderChartsBundle(cd, 'custom-sheet');
      }
    } catch (chartErr) {
      console.warn('Could not render sheet charts:', chartErr);
    }
  } catch (err) {
    $('#directSheetStatus').innerHTML = `<p class="notice error">${err.message}</p>`;
  }
}


async function runSimulation() {
  let att = parseFloat($('#simAtt').value);
  let mock = parseFloat($('#simMock').value);
  let fee = parseFloat($('#simFee').value) / 100.0;
  let course = $('#simCourse').value;

  $('#simAttVal').textContent = att + '%';
  $('#simMockVal').textContent = mock + ' / 100';
  $('#simFeeVal').textContent = (fee * 100) + '%';

  try {
    let r = await api('/api/v1/ml/simulate', {
      method: 'POST',
      body: JSON.stringify({
        attendance_rate: att,
        avg_mock_score: mock,
        fee_clearance_ratio: fee,
        course_id: course
      })
    });
    let p = r.prediction;
    let color = p.pass_probability >= 75 ? 'var(--safe)' : p.pass_probability >= 50 ? 'var(--warning)' : 'var(--danger)';
    let badgeClass = p.pass_probability >= 75 ? 'badge-success' : p.pass_probability >= 50 ? 'badge-warning' : 'badge-danger';

    $('#simProbText').textContent = p.pass_probability + '%';
    $('#simProbText').style.color = color;
    $('#simRiskBadge').innerHTML = `<span class="badge ${badgeClass}">${p.risk_level}</span>`;
    $('#simAdvice').textContent = p.recommendations[0] || 'On track with current learning pace.';
  } catch (err) {
    console.error('Simulation error:', err);
  }
}

async function loadDetails() {
  let type = $('#detailsType').value;
  let q = params();
  if (type) q.set('record_type', type);
  try {
    let d = await api('/api/v1/records?' + q);
    let cols = ['record_type', 'id', 'date', 'course_id', 'batch_id', 'student_id', 'amount', 'status', 'refund_amount'];
    let label = d.result_count === d.records.length ? `${d.result_count} records` : `Showing ${d.records.length} of ${d.result_count} records`;
    
    $('#detailsResult').innerHTML = d.records.length ? `
      <p class="small">${label}</p>
      <table>
        <tr>${cols.map(c => `<th>${c.replace('_', ' ')}</th>`).join('')}</tr>
        ${d.records.map(r => `
          <tr>${cols.map(c => `<td>${(c === 'amount' && r.record_type !== 'exam') || c === 'refund_amount' ? money(Number(r[c] || 0)) : (c === 'amount' && r.record_type === 'exam' ? r[c] + ' / 100' : r[c] || '—')}</td>`).join('')}</tr>
        `).join('')}
      </table>
    ` : '<p class="small">No records match the selected filters.</p>';
  } catch (x) {
    $('#detailsResult').innerHTML = '<p class="notice error">' + x.message + '</p>';
  }
}

async function upload() {
  let f = $('#file').files[0];
  if (!f) return alert('Choose a CSV or XLSX file first.');
  let fd = new FormData();
  fd.append('file', f);
  try {
    let r = await fetch('/api/v1/imports/preview', { method: 'POST', body: fd });
    let d = await r.json();
    if (!r.ok) throw new Error(d.detail);
    preview = d.preview_id;
    $('#importResult').innerHTML = `
      <p class="notice">${d.summary.accepted_rows} valid rows, ${d.summary.rejected_rows} rejected rows, ${d.summary.duplicates} duplicate IDs detected.</p>
      ${d.errors.length ? '<p class="notice error">' + d.errors.map(e => 'Line ' + e.line + ': ' + e.issues.join('; ')).join('<br>') + '</p>' : ''}
      <button id="confirm">Confirm import of valid rows</button>
    `;
    $('#confirm').onclick = confirmImport;
  } catch (x) {
    $('#importResult').innerHTML = '<p class="notice error">' + x.message + '</p>';
  }
}

async function confirmImport() {
  try {
    let r = await api('/api/v1/imports/' + preview + '/confirm', { method: 'POST' });
    $('#importResult').innerHTML = '<p class="notice">' + r.message + ' ' + r.accepted_rows + ' rows imported.</p>';
    load();
    loadPredictions();
    loadCharts();
    loadDetails();
  } catch (x) {
    $('#importResult').innerHTML = '<p class="notice error">' + x.message + '</p>';
  }
}

async function deleteAccount() {
  let confirmation = prompt('This permanently deletes your account and every stored record. Type DELETE to continue.');
  if (confirmation !== null) {
    try {
      await api('/api/v1/account', { method: 'DELETE', body: JSON.stringify({ confirmation }) });
      user = null;
      auth();
    } catch (x) {
      alert(x.message);
    }
  }
}

(async () => {
  try {
    user = await api('/api/v1/me');
    dashboard();
  } catch {
    auth();
  }
})();
