#!/usr/bin/env python3
"""One-time script: imports network_questions.csv into the questions table.
Run from the project root: python3 scripts/import-questions.py
"""
import csv
import os
import sys

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("psycopg2 not found. Installing...")
    os.system("pip3 install -q psycopg2-binary")
    import psycopg2
    from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://sikdorak_app:sikdorak_password@127.0.0.1:5432/sikdorak"
)
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "csv", "network_questions.csv")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Create table if not exists (matches db.js schema)
cur.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id BIGSERIAL PRIMARY KEY,
        subject TEXT NOT NULL,
        question TEXT NOT NULL,
        option1 TEXT NOT NULL,
        option2 TEXT NOT NULL,
        option3 TEXT NOT NULL,
        option4 TEXT NOT NULL,
        answer SMALLINT NOT NULL CHECK (answer BETWEEN 1 AND 4)
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS questions_subject_idx ON questions (subject)")
conn.commit()

cur.execute("SELECT COUNT(*) FROM questions")
existing = cur.fetchone()[0]
if existing > 0:
    print(f"questions table already has {existing} rows — skipping import.")
    cur.close()
    conn.close()
    sys.exit(0)

rows = []
with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        subject = row["과목"].strip()
        question = row["문제"].strip()
        opt1 = row["보기1"].strip()
        opt2 = row["보기2"].strip()
        opt3 = row["보기3"].strip()
        opt4 = row["보기4"].strip()
        try:
            answer = int(row["답"].strip())
        except ValueError:
            continue
        if answer not in (1, 2, 3, 4):
            continue
        if not subject or not question:
            continue
        rows.append((subject, question, opt1, opt2, opt3, opt4, answer))

execute_values(
    cur,
    "INSERT INTO questions (subject, question, option1, option2, option3, option4, answer) VALUES %s",
    rows
)
conn.commit()
print(f"Imported {len(rows)} questions successfully.")

# Print per-subject counts
cur.execute("SELECT subject, COUNT(*) FROM questions GROUP BY subject ORDER BY subject")
for subj, cnt in cur.fetchall():
    print(f"  {subj}: {cnt}문제")

cur.close()
conn.close()
