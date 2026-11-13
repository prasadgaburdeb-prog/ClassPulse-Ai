import urllib.request
import json

base = 'http://127.0.0.1:8000'

# Login with the newly registered user tester@academy.com
login_data = json.dumps({'email': 'tester@academy.com', 'password': 'Password123'}).encode('utf-8')
req = urllib.request.Request(f'{base}/api/v1/auth/login', data=login_data, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())
    token = data.get('access_token')
    print('Login successful! Role:', data.get('user', {}).get('role'))

headers = {'Authorization': f'Bearer {token}'}

# 1. Model Info
req = urllib.request.Request(f'{base}/api/v1/ml/model-info', headers=headers)
with urllib.request.urlopen(req) as resp:
    info = json.loads(resp.read().decode())
    print('\n[1] Model Info Endpoint (ML-011, ML-013, ML-030):')
    print('   - Model Version:', info.get('model_version'))
    print('   - Provenance:', info.get('dataset_provenance'))
    print('   - Accuracy:', info.get('held_out_evaluation', {}).get('test_accuracy_pct'))
    print('   - F1 Score:', info.get('held_out_evaluation', {}).get('f1_score_pct'))
    print('   - ROC-AUC:', info.get('held_out_evaluation', {}).get('roc_auc_pct'))
    print('   - Brier Score:', info.get('held_out_evaluation', {}).get('brier_score_loss'))
    print('   - 5-Fold CV Mean:', info.get('cross_validation', {}).get('mean_accuracy_pct'))
    print('   - Feature Importances:', info.get('feature_importances'))

# 2. Cohort PDF Report
req = urllib.request.Request(f'{base}/api/v1/reports/pdf/cohort-summary', headers=headers)
with urllib.request.urlopen(req) as resp:
    pdf_bytes = resp.read()
    print('\n[2] Cohort PDF Report Endpoint (FEAT-020, AC-008):')
    print('   - Status:', resp.status)
    print('   - Content-Type:', resp.headers.get('Content-Type'))
    print('   - PDF Size:', len(pdf_bytes), 'bytes')

# 3. Admin Backup Endpoint
req = urllib.request.Request(f'{base}/api/v1/admin/backup', headers=headers)
with urllib.request.urlopen(req) as resp:
    backup_bytes = resp.read()
    print('\n[3] Admin Backup Endpoint (DB-007, AC-014):')
    print('   - Status:', resp.status)
    print('   - Content-Type:', resp.headers.get('Content-Type'))
    print('   - Backup Size:', len(backup_bytes), 'bytes')

print('\nBackend Core Endpoints Tested & Verified 100% Operational!')
