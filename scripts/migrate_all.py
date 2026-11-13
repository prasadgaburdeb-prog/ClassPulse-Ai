import sqlite3

con = sqlite3.connect('classpulse.db')
cur = con.cursor()

# Check tenants
cur.execute("PRAGMA table_info(tenants)")
tenant_cols = [c[1] for c in cur.fetchall()]
if "created_at" not in tenant_cols:
    print("Adding created_at to tenants...")
    cur.execute("ALTER TABLE tenants ADD COLUMN created_at DATETIME DEFAULT '2026-01-01 00:00:00'")

# Check audit_events
cur.execute("PRAGMA table_info(audit_events)")
ae_cols = [c[1] for c in cur.fetchall()]
print("audit_events cols:", ae_cols)

# Check import_jobs
cur.execute("PRAGMA table_info(import_jobs)")
ij_cols = [c[1] for c in cur.fetchall()]
print("import_jobs cols:", ij_cols)

# Check records
cur.execute("PRAGMA table_info(records)")
rec_cols = [c[1] for c in cur.fetchall()]
print("records cols:", rec_cols)

con.commit()
con.close()
print("All tables checked and migrated.")
