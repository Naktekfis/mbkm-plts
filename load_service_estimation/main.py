from model_beban import get_data
import psycopg2
import os
from datetime import datetime
from psycopg2.extras import execute_values

# ── Konfigurasi ──
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "postgres"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "microgrid_db"),
    "user":     os.environ.get("DB_USER", "microgrid_user"),
    "password": os.environ.get("DB_PASS", "change-me"),
    "connect_timeout": 5,
}
def run():
    print(f"[{datetime.now()}] Memulai estimasi Load...")

    load_output = get_data()
    print(f"Total baris estimasi: {len(load_output)}")
    if len(load_output) != 1440:
        raise ValueError(f"Output load harus 1440 baris, diterima {len(load_output)}")

    # Koneksi PostgreSQL
    conn   = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS load_estimasi (
            timestamp TIMESTAMP PRIMARY KEY,
            daya_estimasi FLOAT
        )
    """)

    rows = []
    for k in range(len(load_output)):
        timestamp = load_output["timestamp"][k]
        daya      = float(load_output["daya"][k])

        if daya < 0:
            daya = 0.0

        time_str = str(timestamp.to_pydatetime())[:-6]

        rows.append((time_str, daya))

    execute_values(cursor, """
        INSERT INTO load_estimasi (timestamp, daya_estimasi) VALUES %s
        ON CONFLICT (timestamp) DO UPDATE
        SET daya_estimasi = EXCLUDED.daya_estimasi
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[{datetime.now()}] Selesai. {len(rows)} baris tersimpan.")
    return len(rows), load_output["timestamp"].iloc[0].date()

if __name__ == "__main__":
    run()
