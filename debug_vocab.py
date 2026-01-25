import sqlite3
from database import DatabaseManager

def check_db():
    print("Checking Database Vocabulary...")
    db_path = "market_app.db"
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    try:
        c.execute("SELECT * FROM user_vocabulary")
        rows = c.fetchall()
        print(f"Total Rules: {len(rows)}")
        print(f"{'Original (Input)':<20} | {'Corrected (Search Target)':<30}")
        print("-" * 55)
        for r in rows:
            print(f"{r[0]:<20} | {r[1]:<30}")
            
    except Exception as e:
        print(f"Error reading DB: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    import os
    check_db()
