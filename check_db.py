import sqlite3

conn = sqlite3.connect("brain/data/memory/memory.db")
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", cur.fetchall())

for table in ["semantic_nodes", "episodes", "sources", "procedures"]:
    print(f"\n--- {table} schema ---")
    cur.execute(f"PRAGMA table_info({table})")
    cols = cur.fetchall()
    print("  Columns:", [c[1] for c in cols])
    cur.execute(f"SELECT * FROM {table} LIMIT 3")
    rows = cur.fetchall()
    print(f"  Rows ({len(rows)}):")
    for r in rows:
        print(f"    {str(r)[:160]}")

conn.close()
