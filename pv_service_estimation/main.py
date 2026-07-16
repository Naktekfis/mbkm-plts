from aws_model2_openmeteo import get_data
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
    print(f"[{datetime.now()}] Memulai estimasi PV...")

    # Ambil hasil estimasi dari model
    pv_output = get_data()
    print(f"Total baris estimasi: {len(pv_output)}")
    if len(pv_output) != 24:
        raise ValueError(f"Output PV harus 24 baris, diterima {len(pv_output)}")

    # Koneksi PostgreSQL
    conn   = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pv_estimasi (
            timestamp TIMESTAMP PRIMARY KEY,
            pac_estimasi FLOAT
        )
    """)

    rows = []
    for k in range(len(pv_output)):
        timestamp = pv_output["Time"][k]
        pac       = float(pv_output["Pac"][k])

        # Pastikan nilai tidak negatif
        if pac < 0:
            pac = 0.0

        time_str = str(timestamp.to_pydatetime())[:-6]

        rows.append((time_str, pac))

    execute_values(cursor, """
        INSERT INTO pv_estimasi (timestamp, pac_estimasi) VALUES %s
        ON CONFLICT (timestamp) DO UPDATE
        SET pac_estimasi = EXCLUDED.pac_estimasi
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[{datetime.now()}] Selesai. {len(rows)} baris tersimpan.")
    return len(rows), pv_output["Time"].iloc[0].date()

if __name__ == "__main__":
    run()
