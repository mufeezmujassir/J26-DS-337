import psycopg2
import sys

def find_target_db():
    conn = psycopg2.connect("dbname=postgres user=postgres password=root host=localhost port=5432")
    cur = conn.cursor()
    cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
    dbs = [r[0] for r in cur.fetchall()]
    conn.close()
    
    for db in dbs:
        try:
            conn = psycopg2.connect(f"dbname={db} user=postgres password=root host=localhost port=5432")
            cur = conn.cursor()
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
            tables = [r[0] for r in cur.fetchall()]
            
            # Simple heuristic
            keywords = ['road', 'bus', 'train', 'scenic', 'rail']
            matches = [t for t in tables if any(k in t.lower() for k in keywords)]
            
            if matches:
                print(f"Database: {db}")
                print(f"Relevant tables found: {matches}")
                print("-" * 40)
            conn.close()
        except Exception as e:
            pass

if __name__ == '__main__':
    find_target_db()
