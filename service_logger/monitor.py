import os
import json
import psycopg2
import paho.mqtt.client as mqtt
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# KONFIGURASI
# ==========================================
MQTT_BROKER = os.environ.get("MQTT_BROKER", "mqtt_broker")
MQTT_PORT   = int(os.environ.get("MQTT_PORT", 1883))

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "postgres"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "microgrid_db"),
    "user":     os.environ.get("DB_USER", "microgrid_user"),
    "password": os.environ.get("DB_PASS", "change-me"),
    "connect_timeout": 5,
}


# ==========================================
# SETUP DATABASE
# ==========================================
def setup_database():
    conn   = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id             SERIAL PRIMARY KEY,
            telemetry_id   UUID,
            timestamp      TIMESTAMP,
            ingested_at    TIMESTAMP,
            source_timestamp_hybrid TIMESTAMP,
            source_timestamp_pv     TIMESTAMP,
            source_timestamp_load   TIMESTAMP,
            grid_pactive   FLOAT,
            grid_apparent_power_va FLOAT,
            grid_frequency FLOAT,
            dc_meassoc     FLOAT,
            p_inverter     FLOAT,
            ac_frequency   FLOAT,
            a_ms_vol       FLOAT,
            a_ms_amp       FLOAT,
            b_ms_vol       FLOAT,
            b_ms_amp       FLOAT,
            pac_inverter   FLOAT,
            load_watt      FLOAT,
            gridms_hz      FLOAT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS billing_data (
            id                     SERIAL PRIMARY KEY,
            telemetry_id           UUID,
            timestamp              TIMESTAMP,
            efisiensi_biaya_rp     FLOAT,
            renewable_fraction_pct FLOAT,
            lcoe_dinamis_rp        FLOAT,
            biaya_pln_murni_rp     FLOAT,
            biaya_aktual_rp        FLOAT,
            essa_jam               FLOAT DEFAULT 0,
            co2_kg                 FLOAT DEFAULT 0,
            interval_load_kwh      FLOAT DEFAULT 0,
            interval_renewable_kwh FLOAT DEFAULT 0,
            interval_saving_rp     FLOAT DEFAULT 0,
            interval_co2_kg        FLOAT DEFAULT 0,
            interval_hours         FLOAT DEFAULT 0
        )
    ''')
    cursor.execute("""
        ALTER TABLE billing_data
        ADD COLUMN IF NOT EXISTS essa_jam FLOAT DEFAULT 0
    """)
    cursor.execute("""
        ALTER TABLE billing_data
        ADD COLUMN IF NOT EXISTS co2_kg FLOAT DEFAULT 0
    """)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS control_data (
            id                     SERIAL PRIMARY KEY,
            telemetry_id           UUID,
            timestamp              TIMESTAMP,
            status_operasi         TEXT,
            keputusan_aktif        TEXT,
            daya_pln_dihitung_watt FLOAT
        )
    ''')
    new_columns = [
        ("telemetry_id", "UUID"),
        ("ingested_at", "TIMESTAMP"),
        ("source_timestamp_hybrid", "TIMESTAMP"),
        ("source_timestamp_pv", "TIMESTAMP"),
        ("source_timestamp_load", "TIMESTAMP"),
        ("grid_apparent_power_va", "FLOAT"),
        ("grid_voltage",   "FLOAT"),
        ("grid_current",   "FLOAT"),
        ("dc_voltage",     "FLOAT"),
        ("dc_current",     "FLOAT"),
        ("bess_power_dc",  "FLOAT"),
        ("dc_temperature", "FLOAT"),
        ("ac_volt",        "FLOAT"),
        ("ac_current_si",  "FLOAT"),
        ("p_inverter",     "FLOAT"),
    ]
    for col, col_type in new_columns:
        cursor.execute(
            f"ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS {col} {col_type}"
        )
    billing_columns = [
        ("telemetry_id", "UUID"),
        ("interval_load_kwh", "FLOAT DEFAULT 0"),
        ("interval_renewable_kwh", "FLOAT DEFAULT 0"),
        ("interval_saving_rp", "FLOAT DEFAULT 0"),
        ("interval_co2_kg", "FLOAT DEFAULT 0"),
        ("interval_hours", "FLOAT DEFAULT 0"),
    ]
    for col, col_type in billing_columns:
        cursor.execute(
            f"ALTER TABLE billing_data ADD COLUMN IF NOT EXISTS {col} {col_type}"
        )
    cursor.execute("ALTER TABLE control_data ADD COLUMN IF NOT EXISTS telemetry_id UUID")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitoring_alerts (
            id           SERIAL PRIMARY KEY,
            timestamp    TIMESTAMP,
            parameter    VARCHAR(50),
            nilai_aktual FLOAT,
            jenis_alert  VARCHAR(30),
            severity     VARCHAR(10),
            pesan        TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitoring_runs (
            id            SERIAL PRIMARY KEY,
            timestamp     TIMESTAMP,
            status_global VARCHAR(10),
            jumlah_alert  INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pv_estimasi (
            timestamp     TIMESTAMP PRIMARY KEY,
            pac_estimasi  FLOAT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS load_estimasi (
            timestamp       TIMESTAMP PRIMARY KEY,
            daya_estimasi   FLOAT
        )
    ''')
    for table in ("sensor_data", "billing_data", "control_data", "monitoring_alerts", "monitoring_runs"):
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_timestamp ON {table} (timestamp DESC)"
        )
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sensor_telemetry_id
        ON sensor_data (telemetry_id) WHERE telemetry_id IS NOT NULL
    ''')
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_billing_telemetry_id
        ON billing_data (telemetry_id) WHERE telemetry_id IS NOT NULL
    ''')
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_control_telemetry_id
        ON control_data (telemetry_id) WHERE telemetry_id IS NOT NULL
    ''')
    conn.commit()
    conn.close()
    print("Database PostgreSQL siap digunakan.")


# ==========================================
# MQTT CALLBACK
# ==========================================
def on_connect(client, userdata, flags, rc):
    print("Logger terhubung ke MQTT Broker.")
    client.subscribe("microgrid/telemetry", qos=1)
    client.subscribe("microgrid/billing", qos=1)
    client.subscribe("microgrid/control", qos=1)
    client.subscribe("microgrid/monitoring")

def on_message(client, userdata, msg):
    topic = msg.topic
    conn = None
    try:
        payload        = json.loads(msg.payload.decode('utf-8'))
        waktu_sekarang = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        conn   = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        if topic == "microgrid/telemetry":
            cursor.execute('''
                INSERT INTO sensor_data (
                    telemetry_id, timestamp, ingested_at,
                    source_timestamp_hybrid, source_timestamp_pv, source_timestamp_load,
                    grid_apparent_power_va, grid_frequency,
                    grid_voltage, grid_current,
                    dc_meassoc, dc_voltage, dc_current,
                    bess_power_dc, dc_temperature,
                    p_inverter, ac_frequency,
                    a_ms_vol, a_ms_amp,
                    b_ms_vol, b_ms_amp,
                    pac_inverter, load_watt, gridms_hz
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s
                ) ON CONFLICT DO NOTHING
            ''', (
                payload.get("telemetry_id"),
                payload.get("measured_at"),
                waktu_sekarang,
                payload.get("source_timestamp_hybrid"),
                payload.get("source_timestamp_pv"),
                payload.get("source_timestamp_load"),
                payload.get("grid_apparent_power_va"),
                payload.get("grid_frequency"),
                payload.get("grid_voltage"),
                payload.get("grid_current"),
                payload.get("dc_meassoc"),
                payload.get("dc_voltage"),
                payload.get("dc_current"),
                payload.get("bess_power_dc"),
                payload.get("dc_temperature"),
                payload.get("p_inverter"),
                payload.get("ac_frequency"),
                payload.get("A.Ms.Vol"),
                payload.get("A.Ms.Amp"),
                payload.get("B.Ms.Vol"),
                payload.get("B.Ms.Amp"),
                payload.get("pac_inverter"),
                payload.get("load_watt"),
                payload.get("GridMs.Hz"),
            ))
        elif topic == "microgrid/billing":
            cursor.execute('''
                INSERT INTO billing_data (
                    telemetry_id, timestamp, efisiensi_biaya_rp, renewable_fraction_pct,
                    lcoe_dinamis_rp, biaya_pln_murni_rp, biaya_aktual_rp,
                    essa_jam, co2_kg, interval_load_kwh,
                    interval_renewable_kwh, interval_saving_rp, interval_co2_kg,
                    interval_hours
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            ''', (
                payload.get("telemetry_id"),
                payload.get("measured_at", waktu_sekarang),
                payload.get("efisiensi_biaya_rp",     0.0),
                payload.get("renewable_fraction_pct", 0.0),
                payload.get("lcoe_dinamis_rp",        0.0),
                payload.get("biaya_pln_murni_rp",     0.0),
                payload.get("biaya_aktual_rp",        0.0),
                payload.get("essa_jam",               0.0),
                payload.get("co2_kg",                 0.0),
                payload.get("interval_load_kwh",      0.0),
                payload.get("interval_renewable_kwh", 0.0),
                payload.get("interval_saving_rp",     0.0),
                payload.get("interval_co2_kg",        0.0),
                payload.get("interval_hours",         0.0),
            ))
        elif topic == "microgrid/control":
            cursor.execute('''
                INSERT INTO control_data (
                    telemetry_id, timestamp, status_operasi,
                    keputusan_aktif, daya_pln_dihitung_watt
                ) VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            ''', (
                payload.get("telemetry_id"),
                payload.get("measured_at", waktu_sekarang),
                payload.get("status_operasi",         ""),
                payload.get("keputusan_aktif",        ""),
                payload.get("daya_pln_dihitung_watt", 0.0),
            ))
        elif topic == "microgrid/monitoring":
            cursor.execute('''
                INSERT INTO monitoring_runs (
                    timestamp, status_global, jumlah_alert
                ) VALUES (%s, %s, %s)
            ''', (
                waktu_sekarang,
                payload.get("status_global", "UNKNOWN"),
                payload.get("jumlah_alert", 0),
            ))
            for alert in payload.get("alerts", []):
                cursor.execute('''
                    INSERT INTO monitoring_alerts (
                        timestamp, parameter, nilai_aktual,
                        jenis_alert, severity, pesan
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                ''', (
                    waktu_sekarang,
                    alert.get("parameter"),
                    alert.get("nilai_aktual"),
                    alert.get("jenis_alert"),
                    alert.get("severity"),
                    alert.get("pesan"),
                ))
        conn.commit()
    except Exception as e:
        print(f"Gagal merekam data dari {topic}: {e}")
    finally:
        if conn:
            conn.close()


# ==========================================
# ENTRY POINT
# ==========================================
if __name__ == "__main__":
    setup_database()
    mqtt_client = mqtt.Client(client_id="data_logger_db")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_forever()
    except Exception as e:
        print(f"Koneksi MQTT Gagal: {e}")
