import time
import json
import logging
import psycopg2
import paho.mqtt.client as mqtt
import os
from datetime import datetime, timezone, timedelta

# ==========================================
# 1. KONFIGURASI
# ==========================================
POSTGRES_HOST = os.environ.get("DB_HOST", "postgres")
POSTGRES_PORT = int(os.environ.get("DB_PORT", 5432))
POSTGRES_DB   = os.environ.get("DB_NAME", "microgrid_db")
POSTGRES_USER = os.environ.get("DB_USER", "microgrid_user")
POSTGRES_PASS = os.environ.get("DB_PASS", "change-me")

MQTT_BROKER   = os.environ.get("MQTT_BROKER", "mqtt_broker")
MQTT_PORT     = int(os.environ.get("MQTT_PORT", 1883))
MQTT_TOPIC    = "microgrid/monitoring"

INTERVAL_DETIK   = 60
FROZEN_THRESHOLD = 20    # jumlah baris identik berturut-turut = frozen
STALE_THRESHOLD  = 120   # detik maksimum sejak data terakhir

WIB = timezone(timedelta(hours=7))

# ==========================================
# 2. PARAMETER RANGE VALIDASI (C1)
# ==========================================
RANGE = {
    "pac_inverter":   {"min": 0,      "max": 5000},
    "grid_voltage":   {"min": 180,    "max": 280},
    "grid_current":   {"min": 0,      "max": 25},
    "grid_apparent_power_va": {"min": 0, "max": 5500},
    "dc_voltage":     {"min": 44,     "max": 58},
    "dc_current":     {"min": -120,   "max": 120},
    "dc_meassoc":     {"min": 0,      "max": 100},
    "dc_temperature": {"min": 0,      "max": 45},
    "load_watt":      {"min": 0,      "max": 2700},
    "p_inverter":     {"min": -5000,  "max": 5000},
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ==========================================
# 3. KONEKSI POSTGRESQL
# ==========================================
def get_db():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASS,
        connect_timeout=5,
    )

# ==========================================
# 4. AMBIL DATA TERBARU
# ==========================================
def load_latest_data(n=25):
    """Ambil n baris terakhir dari sensor_data."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(f"""
            SELECT timestamp, pac_inverter, grid_voltage, grid_current,
                   COALESCE(grid_apparent_power_va, grid_pactive) AS grid_apparent_power_va,
                   dc_voltage, dc_current, dc_meassoc,
                   dc_temperature, load_watt, p_inverter
            FROM sensor_data
            ORDER BY timestamp DESC
            LIMIT {n}
        """)
        cols = [desc[0] for desc in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        # rows[0] = terbaru, rows[-1] = terlama
        return rows
    except Exception as e:
        logging.error(f"DB error: {e}")
        return []

# ==========================================
# 5. VALIDASI C1 — RANGE
# ==========================================
def validate_range(row):
    alerts = []
    for param, batas in RANGE.items():
        nilai = row.get(param)
        if nilai is None:
            continue
        if not (batas["min"] <= nilai <= batas["max"]):
            alerts.append({
                "parameter":    param,
                "nilai_aktual": nilai,
                "jenis_alert":  "OUT_OF_RANGE",
                "severity":     "ERROR",
                "pesan": (
                    f"{param} = {nilai} di luar range "
                    f"[{batas['min']}, {batas['max']}]"
                )
            })
    return alerts

# ==========================================
# 6. VALIDASI C2 — STALENESS
# ==========================================
def validate_staleness(rows):
    if not rows:
        return [{
            "parameter":    "sensor_data",
            "nilai_aktual": None,
            "jenis_alert":  "DATA_STALE",
            "severity":     "ERROR",
            "pesan":        "Tidak ada data di sensor_data"
        }]
    ts_terbaru = rows[0]["timestamp"]
    if ts_terbaru.tzinfo is None:
        ts_terbaru = ts_terbaru.replace(tzinfo=WIB)
    sekarang   = datetime.now(WIB)
    delta_detik = (sekarang - ts_terbaru).total_seconds()
    if delta_detik < -60:
        return [{
            "parameter": "timestamp",
            "nilai_aktual": delta_detik,
            "jenis_alert": "TIMESTAMP_FUTURE",
            "severity": "ERROR",
            "pesan": f"Timestamp data {abs(int(delta_detik))} detik di masa depan",
        }]
    if delta_detik > STALE_THRESHOLD:
        return [{
            "parameter":    "timestamp",
            "nilai_aktual": delta_detik,
            "jenis_alert":  "DATA_STALE",
            "severity":     "ERROR",
            "pesan": (
                f"Data terakhir {int(delta_detik)} detik yang lalu "
                f"(threshold: {STALE_THRESHOLD} detik)"
            )
        }]
    return []

# ==========================================
# 7. VALIDASI C3 — FROZEN DATA
# ==========================================
def is_daytime():
    jam = datetime.now(WIB).hour
    return 6 <= jam < 18

def validate_frozen(rows, param):
    if len(rows) < FROZEN_THRESHOLD:
        return []
    nilai_terbaru = rows[0].get(param)
    # Konteks malam: pac_inverter dan p_inverter = 0 adalah normal
    if param in {"pac_inverter", "p_inverter"} and not is_daytime():
        return []
    # Cek apakah N baris terakhir semua identik
    semua_sama = all(r.get(param) == nilai_terbaru for r in rows[:FROZEN_THRESHOLD])
    if semua_sama:
        return [{
            "parameter":    param,
            "nilai_aktual": nilai_terbaru,
            "jenis_alert":  "FROZEN",
            "severity":     "WARNING",
            "pesan": (
                f"{param} tidak berubah selama "
                f"{FROZEN_THRESHOLD} pembacaan terakhir "
                f"(nilai: {nilai_terbaru})"
            )
        }]
    return []

# ==========================================
# 8. VALIDASI C5 — URUTAN TIMESTAMP
# ==========================================
def validate_timestamp_order(rows):
    alerts = []
    for i in range(len(rows) - 1):
        ts_baru = rows[i]["timestamp"]
        ts_lama = rows[i+1]["timestamp"]
        if ts_baru < ts_lama:
            alerts.append({
                "parameter":    "timestamp",
                "nilai_aktual": None,
                "jenis_alert":  "TIMESTAMP_ANOMALY",
                "severity":     "WARNING",
                "pesan": (
                    f"Urutan timestamp tidak monoton: "
                    f"{ts_baru} < {ts_lama}"
                )
            })
            break  # cukup laporkan satu kejadian
    return alerts

# ==========================================
# 9. JALANKAN SEMUA VALIDASI
# ==========================================
def run_validasi():
    rows = load_latest_data(n=25)
    semua_alerts = []

    # C2 — staleness
    semua_alerts += validate_staleness(rows)

    # C5 — urutan timestamp
    if rows:
        semua_alerts += validate_timestamp_order(rows)

    # C1 — range (gunakan baris terbaru)
    if rows:
        semua_alerts += validate_range(rows[0])

    # C3 — frozen (cek semua parameter yang ada di RANGE)
    # dc_meassoc dikecualikan karena SoC konstan adalah karakteristik sistem
    FROZEN_SKIP = {"dc_meassoc", "dc_voltage", "dc_temperature"}
    for param in RANGE.keys():
        if rows and param not in FROZEN_SKIP:
            semua_alerts += validate_frozen(rows, param)

    # Tentukan status global
    severities   = [a["severity"] for a in semua_alerts]
    if "ERROR" in severities:
        status_global = "ERROR"
    elif "WARNING" in severities:
        status_global = "WARNING"
    else:
        status_global = "OK"

    payload = {
        "timestamp":     datetime.now(WIB).isoformat(),
        "status_global": status_global,
        "jumlah_alert":  len(semua_alerts),
        "alerts":        semua_alerts
    }

    return payload

# ==========================================
# 10. MQTT
# ==========================================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Terhubung ke MQTT Broker.")
    else:
        logging.error(f"Gagal terhubung ke MQTT, kode: {rc}")

def main():
    client = mqtt.Client(client_id="service_pemantauan")
    client.on_connect = on_connect
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
    except Exception as e:
        logging.error(f"Koneksi MQTT gagal: {e}")
        return

    logging.info("Service Pemantauan mulai berjalan...")
    logging.info(f"Interval: {INTERVAL_DETIK}s | Frozen threshold: {FROZEN_THRESHOLD} baris | Stale threshold: {STALE_THRESHOLD}s")

    while True:
        try:
            hasil = run_validasi()
            if hasil:
                payload_str = json.dumps(hasil, default=str)
                client.publish(MQTT_TOPIC, payload_str)
                logging.info(
                    f"Status: {hasil['status_global']} | "
                    f"Alert: {hasil['jumlah_alert']} | "
                    f"Dipublish ke {MQTT_TOPIC}"
                )
        except Exception as e:
            logging.error(f"Error saat validasi: {e}")

        time.sleep(INTERVAL_DETIK)

if __name__ == "__main__":
    main()
