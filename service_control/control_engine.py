import json
import logging
import paho.mqtt.client as mqtt
import os

# Konfigurasi
MQTT_BROKER     = os.environ.get("MQTT_BROKER", "mqtt_broker")
MQTT_PORT       = int(os.environ.get("MQTT_PORT", 1883))
TOPIC_TELEMETRY = "microgrid/telemetry"
TOPIC_CONTROL   = "microgrid/control"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')


# Rule-based EMS (DSS)
def evaluate_ems_rules(pac_inverter_w, load_watt_w, soc, p_inverter_w):
    """
    Parameter:
        pac_inverter_w : Output AC inverter PV (Pac) dalam Watt
        load_watt_w    : Beban gedung Lab ME dari sielis dalam Watt
        soc            : State of Charge BESS (%)
        p_inverter_w   : Daya AC masuk/keluar Hybrid Inverter (Vac × Iac)
                         positif → Sunny Island menyuplai ke panel (discharge)
                         negatif → Sunny Island menyerap dari panel (charging)
                         → untuk verifikasi apakah BESS benar-benar
                           berkontribusi ke busbar AC

    Mode Operasi (5 Rule Hierarkis):
        CHARGING     — PV surplus, SoC < 98%  → BESS menyerap kelebihan PV
        OPTIMUM      — PV surplus, SoC ≥ 98%  → sistem dalam kondisi terbaik
        DISCHARGING  — PV defisit, SoC > 20%, BESS aktif → BESS cover beban
        GRID SUPPORT — PV defisit, SoC > 20%, BESS standby → PLN backup
        GRID ONLY    — PV defisit, SoC ≤ 20%  → proteksi baterai aktif
    """
    SOC_MIN        = 20.0
    SOC_MAX        = 98.0
    BESS_THRESHOLD = 10.0  # Watt — toleransi noise sensor

    selisih_daya = pac_inverter_w - load_watt_w

    if selisih_daya > 0:
        # PV surplus
        if soc < SOC_MAX:
            status = "CHARGING"
            pesan  = f"Surplus PV {abs(selisih_daya):.1f} W. BESS menyerap kelebihan daya."
        else:
            status = "OPTIMUM"
            pesan  = f"Sistem dalam kondisi optimal. BESS penuh (SoC {soc:.1f}%). PV surplus {abs(selisih_daya):.1f} W."

    elif selisih_daya < 0:
        bess_aktif = p_inverter_w > BESS_THRESHOLD
        if soc > SOC_MIN and bess_aktif:
            status = "DISCHARGING"
            pesan  = f"Defisit PV {abs(selisih_daya):.1f} W. BESS men-discharge untuk cover beban."
        elif soc > SOC_MIN and not bess_aktif:
            status = "GRID SUPPORT"
            pesan  = f"Defisit PV {abs(selisih_daya):.1f} W. Grid PLN backup. BESS standby (SoC {soc:.1f}%)."
        else:
            status = "GRID ONLY"
            pesan  = f"SoC kritis ({soc:.1f}%). Proteksi baterai aktif. Grid PLN menanggung beban {abs(selisih_daya):.1f} W."

    else:
        status = "OPTIMUM"
        pesan  = "Produksi PV seimbang dengan beban gedung."

    daya_pln = max(load_watt_w - pac_inverter_w - max(p_inverter_w, 0.0), 0.0)

    return {
        "status_operasi":         status,
        "keputusan_aktif":        pesan,
        "daya_pln_dihitung_watt": daya_pln,
    }


# MQTT callback
def on_connect(client, userdata, flags, rc):
    logging.info("Service Control (DSS Rule-Based) terhubung ke MQTT Broker.")
    client.subscribe(TOPIC_TELEMETRY, qos=1)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))

        pac_inverter = float(payload.get("pac_inverter", 0.0))
        load_watt    = float(payload.get("load_watt",    0.0))
        battery_soc  = float(payload.get("dc_meassoc",  0.0))
        p_inverter   = float(payload.get("p_inverter",  0.0))

        keputusan = evaluate_ems_rules(pac_inverter, load_watt, battery_soc, p_inverter)
        keputusan["telemetry_id"] = payload.get("telemetry_id")
        keputusan["measured_at"] = payload.get("measured_at")

        result = client.publish(TOPIC_CONTROL, json.dumps(keputusan), qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Publish control gagal, rc={result.rc}")
        logging.info(f"DSS: [{keputusan['status_operasi']}] {keputusan['keputusan_aktif']}")

    except Exception as e:
        logging.error(f"Error Control Engine: {e}")


# Entry point
if __name__ == "__main__":
    client = mqtt.Client(client_id="dss_control_engine")
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except Exception as e:
        logging.error(f"Koneksi MQTT Gagal: {e}")
