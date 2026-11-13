import sqlite3

con = sqlite3.connect('classpulse.db')
cur = con.cursor()

cur.execute("PRAGMA table_info(users)")
existing = [row[1] for row in cur.fetchall()]

new_cols = [
    ("full_name", "VARCHAR(255) DEFAULT ''"),
    ("is_active", "BOOLEAN DEFAULT 1"),
    ("created_at", "DATETIME DEFAULT '2026-01-01 00:00:00'"),
    ("last_login_at", "DATETIME DEFAULT NULL")
]

for col_name, col_def in new_cols:
    if col_name not in existing:
        print(f"Adding column {col_name} to users table...")
        cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")

con.commit()
print("Migration completed.")
cur.execute("PRAGMA table_info(users)")
print("Updated columns:", [row[1] for row in cur.fetchall()])
con.close()
