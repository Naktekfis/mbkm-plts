import docker
import psycopg2
import requests
import time
import logging
import os
from datetime import datetime, timedelta

# ==========================================
# KONFIGURASI
# ==========================================
CHECK_INTERVAL  = 120   # cek setiap 2 menit
MAX_DATA_AGE    = 180   # data dianggap stale jika > 3 menit
STARTUP_GRACE   = int(os.environ.get("STARTUP_GRACE_SECONDS", 180))
RESTART_COOLDOWN = int(os.environ.get("RESTART_COOLDOWN_SECONDS", 600))
MAX_RESTARTS = int(os.environ.get("MAX_RESTARTS", 3))
HMI_URL         = os.environ.get("HMI_URL", "http://service_hmi:5000/health/ready")
HMI_TIMEOUT     = 5     # detik

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "postgres"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "microgrid_db"),
    "user":     os.environ.get("DB_USER", "microgrid_user"),
    "password": os.environ.get("DB_PASS", "change-me"),
    "connect_timeout": 5,
}

# Mapping: nama container → tabel yang dicek
SERVICE_TABLE_MAP = {
    "service_sensor":  "sensor_data",
    "service_billing": "billing_data",
    "service_control": "control_data",
}

# ==========================================
# LOGGING
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WATCHDOG] %(levelname)s - %(message)s'
)
log = logging.getLogger("watchdog")


# ==========================================
# CEK FRESHNESS DATA DI POSTGRESQL
# ==========================================
def cek_data_freshness(table_name):
    """
    Cek apakah tabel memiliki data terbaru dalam MAX_DATA_AGE detik.
    Return True jika data masih fresh, False jika stale.
    """
    try:
        conn   = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(f"SELECT MAX(timestamp) FROM {table_name}")
        result = cursor.fetchone()
        conn.close()

        if not result or not result[0]:
            log.warning(f"Tabel {table_name} kosong atau tidak ada data.")
            return False

        last_ts  = result[0]
        now      = datetime.now()
        selisih  = (now - last_ts).total_seconds()

        if selisih < -60:
            log.warning(f"{table_name}: timestamp {abs(selisih):.0f}s di masa depan")
            return False

        if selisih > MAX_DATA_AGE:
            log.warning(f"{table_name}: data terakhir {selisih:.0f}s lalu (batas {MAX_DATA_AGE}s)")
            return False

        return True

    except Exception as e:
        log.error(f"Error cek {table_name}: {e}")
        return False


# ==========================================
# CEK HMI HTTP
# ==========================================
def cek_hmi():
    """
    Cek apakah HMI merespons HTTP 200.
    Return True jika OK, False jika bermasalah.
    """
    try:
        resp = requests.get(HMI_URL, timeout=HMI_TIMEOUT)
        return resp.status_code == 200
    except Exception as e:
        log.warning(f"HMI tidak merespons: {e}")
        return False


# ==========================================
# RESTART CONTAINER
# ==========================================
def restart_container(client, container_name):
    """
    Restart container menggunakan Docker SDK.
    """
    try:
        container = client.containers.get(container_name)
        log.warning(f"Merestart container: {container_name}")
        container.restart(timeout=30)
        log.info(f"Container {container_name} berhasil direstart.")
        return True
    except docker.errors.NotFound:
        log.error(f"Container {container_name} tidak ditemukan.")
        return False
    except Exception as e:
        log.error(f"Gagal restart {container_name}: {e}")
        return False


# ==========================================
# MAIN LOOP
# ==========================================
def main():
    log.info("=" * 50)
    log.info("Service Watchdog dimulai.")
    log.info(f"Interval cek : {CHECK_INTERVAL} detik")
    log.info(f"Max data age : {MAX_DATA_AGE} detik")
    log.info("=" * 50)

    # Inisialisasi Docker client via socket
    try:
        docker_client = docker.from_env()
        log.info("Docker client terhubung.")
    except Exception as e:
        log.error(f"Gagal terhubung ke Docker socket: {e}")
        return

    restart_count = {}
    last_restart = {}
    log.info(f"Menunggu startup grace {STARTUP_GRACE}s sebelum pengecekan pertama.")
    time.sleep(STARTUP_GRACE)

    while True:
        log.info("--- Mulai pengecekan ---")

        # 1. Freshness adalah sinyal kualitas data, bukan bukti proses gagal.
        for container_name, table_name in SERVICE_TABLE_MAP.items():
            is_fresh = cek_data_freshness(table_name)
            if not is_fresh:
                log.warning(f"[{container_name}] Data stale di {table_name}; periksa sumber, broker, dan logger.")
            else:
                log.info(f"[{container_name}] OK — data {table_name} fresh.")

        # 2. Cek HMI
        hmi_ok = cek_hmi()
        if not hmi_ok:
            name = "service_hmi_flask"
            elapsed = time.time() - last_restart.get(name, 0)
            count = restart_count.get(name, 0)
            if count < MAX_RESTARTS and elapsed >= RESTART_COOLDOWN:
                log.warning(f"[{name}] Readiness gagal; restart {count + 1}/{MAX_RESTARTS}.")
                if restart_container(docker_client, name):
                    restart_count[name] = count + 1
                    last_restart[name] = time.time()
            else:
                log.error(f"[{name}] Readiness gagal; restart ditahan oleh cooldown/budget.")
        else:
            log.info("[service_hmi_flask] OK — HMI merespons.")
            restart_count["service_hmi_flask"] = 0

        log.info(f"--- Selesai. Tidur {CHECK_INTERVAL}s ---")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
