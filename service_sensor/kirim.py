import mysql.connector
import paho.mqtt.client as mqtt
import time
import json
import logging
import os
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

# ================= KONFIGURASI =================
MYSQL_HOST     = os.environ.get("MYSQL_HOST", "192.168.1.147")
MYSQL_PORT     = int(os.environ.get("MYSQL_PORT", 3306))
MYSQL_USER     = os.environ.get("MYSQL_USER", "mahasiswa")
MYSQL_PASS     = os.environ.get("MYSQL_PASS", "change-me")
MQTT_BROKER    = os.environ.get("MQTT_BROKER", "mqtt_broker")
MQTT_PORT      = int(os.environ.get("MQTT_PORT", 1883))
MQTT_TOPIC     = "microgrid/telemetry"
INTERVAL_DETIK = 60
MAX_SOURCE_AGE_SECONDS = int(os.environ.get("MAX_SOURCE_AGE_SECONDS", 180))
MAX_SOURCE_SKEW_SECONDS = int(os.environ.get("MAX_SOURCE_SKEW_SECONDS", 120))
# ================================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')


def ambil_data_terkini():
    db_smartgrid = None
    db_sielis = None
    try:
        # ─────────────────────────────────────────────
        # KONEKSI 1 : smartgrid (Hybrid Inverter + PV)
        # ─────────────────────────────────────────────
        db_smartgrid = mysql.connector.connect(
            host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
            password=MYSQL_PASS, database="smartgrid",
            connection_timeout=5
        )
        cursor_sg = db_smartgrid.cursor(dictionary=True)

        # 1a. Data Hybrid Inverter (Sunny Island) — raw data dari .147
        #     ExtVtg, ExtCur, ExtFrq : parameter PLN masuk ke Sunny Island
        #     BatVtg, TotBatCur      : parameter sisi DC baterai Lithium 
        #     BatSoc, BatTmp         : SoC dan suhu baterai
        #     TotInvPwrAt, Fac       : daya total & frekuensi sisi AC Hybrid Inverter
        cursor_sg.execute("""
            SELECT
                ExtVtg, ExtCur, ExtFrq,
                BatVtg, TotBatCur, BatSoc, BatTmp,
                TotInvPwrAt, Fac,
                timestamp AS source_timestamp
            FROM datapengukuran
            ORDER BY timestamp DESC LIMIT 1
        """)
        data_hybrid = cursor_sg.fetchone()

        # 1b. Data PV Inverter (Sunny Boy) — struktur sama dengan .149
        #     A.Ms.Vol, A.Ms.Amp → String A DC
        #     B.Ms.Vol, B.Ms.Amp → String B DC
        #     Pac                → output AC PV inverter (W)
        #     GridMs.Hz          → frekuensi sisi AC PV inverter
        cursor_sg.execute("""
            SELECT
                `A.Ms.Vol`, `A.Ms.Amp`,
                `B.Ms.Vol`, `B.Ms.Amp`,
                Pac, `GridMs.Hz`,
                timestamp AS source_timestamp
            FROM pv_datapengukuran
            ORDER BY timestamp DESC LIMIT 1
        """)
        data_pv = cursor_sg.fetchone()

        # ─────────────────────────────────────────────
        # KONEKSI 2 : sielis (Beban Gedung Lab ME)
        #   meter_id = 6 → Lab Manajemen Energi
        #   P_beban = (V1×A1×PF1) + (V2×A2×PF2) + (V3×A3×PF3)
        # ─────────────────────────────────────────────
        db_sielis = mysql.connector.connect(
            host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
            password=MYSQL_PASS, database="sielis",
            connection_timeout=5
        )
        cursor_sl = db_sielis.cursor(dictionary=True)

        cursor_sl.execute("""
            SELECT
                (V1 * A1 * PF1) + (V2 * A2 * PF2) + (V3 * A3 * PF3) AS load_watt,
                timestamp AS source_timestamp
            FROM datapengukuran
            WHERE meter_id = 6
            ORDER BY timestamp DESC LIMIT 1
        """)
        data_load = cursor_sl.fetchone()

        # ─────────────────────────────────────────────
        # GABUNGKAN SEMUA DATA → PAKET MQTT
        # ─────────────────────────────────────────────
        if data_hybrid and data_pv and data_load:
            source_times = {
                "hybrid": data_hybrid.get("source_timestamp"),
                "pv": data_pv.get("source_timestamp"),
                "load": data_load.get("source_timestamp"),
            }
            if not all(isinstance(ts, datetime) for ts in source_times.values()):
                logging.warning("Timestamp sumber tidak lengkap, skip publish.")
                return None

            now = datetime.now()
            source_ages = [(now - ts).total_seconds() for ts in source_times.values()]
            oldest_age = max(source_ages)
            source_skew = (max(source_times.values()) - min(source_times.values())).total_seconds()
            if oldest_age > MAX_SOURCE_AGE_SECONDS:
                logging.warning(f"Data sumber stale ({oldest_age:.0f}s), skip publish.")
                return None
            if min(source_ages) < -MAX_SOURCE_SKEW_SECONDS:
                logging.warning(f"Timestamp sumber berada di masa depan ({-min(source_ages):.0f}s), skip publish.")
                return None
            if source_skew > MAX_SOURCE_SKEW_SECONDS:
                logging.warning(f"Timestamp sumber tidak sinkron ({source_skew:.0f}s), skip publish.")
                return None

            def required_float(data, key):
                value = data.get(key)
                if value is None:
                    raise ValueError(f"Nilai wajib {key} kosong")
                return float(value)

            # ── Kalkulasi P_PLN ──
            # PPLN = ExtVtg × ExtCur (raw data, daya semu VA)
            ext_vtg = required_float(data_hybrid, 'ExtVtg')
            ext_cur = required_float(data_hybrid, 'ExtCur')
            p_pln_va = ext_vtg * ext_cur

            # ── Kalkulasi P_BESS sisi DC ──
            # PBatDC = BatVtg × TotBatCur
            # positif → discharge (BESS menyuplai beban via Sunny Island)
            # negatif → charging (BESS sedang diisi)
            dc_v      = required_float(data_hybrid, 'BatVtg')
            dc_i      = required_float(data_hybrid, 'TotBatCur')
            p_bess_dc = dc_v * dc_i

            # ── Kalkulasi P_Inverter (daya masuk/keluar Hybrid Inverter) ──
            # PInverter = TotInvPwrAt × 1000 (konversi kW → W)
            # positif → Sunny Island menyuplai ke Distribution Panel (discharge)
            # negatif → Sunny Island menyerap dari Distribution Panel (charging)
            # = 0     → Sunny Island standby
            tot_inv_pwr_at = required_float(data_hybrid, 'TotInvPwrAt')
            p_inverter     = tot_inv_pwr_at * 1000

            telemetry_key = "|".join(ts.isoformat() for ts in source_times.values())
            return {
                "telemetry_id": str(uuid5(NAMESPACE_URL, telemetry_key)),
                "measured_at": max(source_times.values()).isoformat(),
                "source_timestamp_hybrid": source_times["hybrid"].isoformat(),
                "source_timestamp_pv": source_times["pv"].isoformat(),
                "source_timestamp_load": source_times["load"].isoformat(),
                # ── Grid PLN (via Sunny Island) ──
                "grid_voltage":   ext_vtg,
                "grid_current":   ext_cur,
                "grid_apparent_power_va": p_pln_va,
                "grid_frequency": required_float(data_hybrid, 'ExtFrq'),

                # ── BESS Lithium  (sisi DC) ──
                "dc_voltage":     dc_v,
                "dc_current":     dc_i,
                "bess_power_dc":  p_bess_dc,
                "dc_meassoc":     required_float(data_hybrid, 'BatSoc'),
                "dc_temperature": required_float(data_hybrid, 'BatTmp'),

                # ── Hybrid Inverter AC (daya masuk/keluar ke Distribution Panel) ──
                "p_inverter":     p_inverter,
                "ac_frequency":   required_float(data_hybrid, 'Fac'),

                # ── PV DC String (Sunny Boy) ──
                # PVDC = V × I per string
                "A.Ms.Vol":   required_float(data_pv, 'A.Ms.Vol'),
                "A.Ms.Amp":   required_float(data_pv, 'A.Ms.Amp'),
                "B.Ms.Vol":   required_float(data_pv, 'B.Ms.Vol'),
                "B.Ms.Amp":   required_float(data_pv, 'B.Ms.Amp'),

                # ── PV AC Output Sunny Boy ──
                # PVAC = Pac (daya AC terukur langsung oleh inverter)
                "pac_inverter": required_float(data_pv, 'Pac'),
                "GridMs.Hz":    required_float(data_pv, 'GridMs.Hz'),

                # ── Beban Gedung Lab ME (Sielis meter_id=6) ──
                # P_beban = (V1×A1×PF1) + (V2×A2×PF2) + (V3×A3×PF3)
                "load_watt": required_float(data_load, 'load_watt'),
            }

        logging.warning("Data hybrid, PV, atau load kosong, skip publish.")
        return None

    except mysql.connector.Error as e:
        logging.error(f"MySQL Error: {e}")
        return None
    except Exception as e:
        logging.error(f"Error tidak terduga: {e}")
        return None
    finally:
        for connection in (db_smartgrid, db_sielis):
            if connection and connection.is_connected():
                connection.close()


def main():
    client = mqtt.Client(client_id="mysql_gateway_sensor")

    try:
        logging.info(f"Menghubungkan ke MQTT Broker {MQTT_BROKER}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        logging.info("Terhubung ke MQTT Broker!")
    except Exception as e:
        logging.error(f"Gagal terhubung ke MQTT: {e}")
        return

    logging.info(f"Mulai polling MySQL setiap {INTERVAL_DETIK} detik...")

    while True:
        sensor_data = ambil_data_terkini()

        if sensor_data:
            payload = json.dumps(sensor_data)
            result = client.publish(MQTT_TOPIC, payload, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logging.info(f"PUBLISH [{MQTT_TOPIC}] telemetry_id={sensor_data['telemetry_id']}")
            else:
                logging.error(f"Publish MQTT gagal, rc={result.rc}")
        else:
            logging.warning("Data kosong, tidak publish.")

        time.sleep(INTERVAL_DETIK)


if __name__ == "__main__":
    main()
