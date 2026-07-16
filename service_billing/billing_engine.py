import json
import math
import logging
import paho.mqtt.client as mqtt
import os
from datetime import datetime

# Konfigurasi jaringan
MQTT_BROKER     = os.environ.get("MQTT_BROKER", "mqtt_broker")
MQTT_PORT       = int(os.environ.get("MQTT_PORT", 1883))
TOPIC_TELEMETRY = "microgrid/telemetry"
TOPIC_BILLING   = "microgrid/billing"

# Parameter keekonomian
TARIF_PLN_PER_KWH = 955.0
CAPEX_TOTAL_RP    = 282_300_935.0
OPEX_PER_TAHUN    = 102_600_000.0 / 15
OPEX_PERCENT_YR   = OPEX_PER_TAHUN / CAPEX_TOTAL_RP
SUKU_BUNGA_I      = 0.05
UMUR_PROYEK_N     = 15

BESS_KAPASITAS_WH = 20_480.0   # Wh Gotion ESD51-05C20, 51.2V LFP
BATTERY_MIN_SOC   = 20.0      # %

# Sumber: RUPTL PLN 2021-2030
FAKTOR_EMISI_CO2  = 0.87      # kg CO2/kWh

_pow = math.pow(1 + SUKU_BUNGA_I, UMUR_PROYEK_N)
CRF  = (SUKU_BUNGA_I * _pow) / (_pow - 1)

ANNUALIZED_CAPEX      = CAPEX_TOTAL_RP * CRF
ANNUALIZED_OPEX       = OPEX_PER_TAHUN
TOTAL_ANNUALIZED_COST = ANNUALIZED_CAPEX + ANNUALIZED_OPEX
HOURLY_SYSTEM_COST    = TOTAL_ANNUALIZED_COST / 8760.0

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logging.info(f"  CAPEX         : Rp {CAPEX_TOTAL_RP:,.0f}")
logging.info(f"  OPEX/tahun    : Rp {OPEX_PER_TAHUN:,.0f}")
logging.info(f"  CRF           : {CRF:.6f}")
logging.info(f"  Hourly cost   : Rp {HOURLY_SYSTEM_COST:,.4f}/jam")
logging.info(f"  BESS kapasitas: {BESS_KAPASITAS_WH:.0f} Wh")
logging.info(f"  Faktor emisi  : {FAKTOR_EMISI_CO2} kg CO2/kWh (RUPTL PLN 2021-2030)")

# State akumulator
akumulasi_beban_kwh      = 0.0
akumulasi_ebt_kwh        = 0.0
akumulasi_jam_operasi    = 0.0
total_efisiensi_biaya_rp = 0.0
total_co2_tereduksi_kg   = 0.0
last_timestamp           = None
last_load_w              = 0.0
MAX_INTERVAL_SECONDS     = int(os.environ.get("MAX_INTERVAL_SECONDS", 300))


def _cumulative_metrics(load_kwh, rf_renewable_kwh, lcoe_renewable_kwh,
                        operating_hours, saving_rp):
    renewable_fraction = rf_renewable_kwh / load_kwh * 100 if load_kwh > 0 else 0.0
    lcoe_rp = (
        HOURLY_SYSTEM_COST * operating_hours / lcoe_renewable_kwh
        if lcoe_renewable_kwh > 0 else 0.0
    )
    grid_cost_rp = load_kwh * TARIF_PLN_PER_KWH
    actual_cost_rp = max(grid_cost_rp - saving_rp, 0.0)
    return renewable_fraction, lcoe_rp, grid_cost_rp, actual_cost_rp


def _empty_interval_result(cumulative_metrics, saving_rp, co2_kg):
    renewable_fraction, lcoe_rp, grid_cost_rp, actual_cost_rp = cumulative_metrics
    return (
        saving_rp, renewable_fraction, lcoe_rp, grid_cost_rp,
        actual_cost_rp, 0.0, co2_kg, 0.0, 0.0, 0.0, 0.0, 0.0,
    )


def _renewable_power(pac_inverter_w, bess_power_w, load_power_w):
    available_w = pac_inverter_w + max(bess_power_w, 0)
    if load_power_w <= 0.5:
        return 0.0
    return max(min(available_w, load_power_w), 0)


def _essa_hours(soc_pct, load_power_w, fallback_load_w):
    reference_load_w = load_power_w if load_power_w > 0.5 else fallback_load_w
    if reference_load_w <= 0.5:
        return 0.0
    essa_hours = BESS_KAPASITAS_WH * (soc_pct / 100.0) / reference_load_w
    return round(max(essa_hours, 0.0), 3)


def kalkulasi_ekonomi_mikrogrid(pv_dc_power_w, pac_inverter_w,
                                 bess_power_w, load_power_w, soc_pct,
                                 measurement_time=None):
    global akumulasi_beban_kwh, akumulasi_ebt_kwh, akumulasi_jam_operasi
    global total_efisiensi_biaya_rp, total_co2_tereduksi_kg
    global last_timestamp, last_load_w

    current_time = measurement_time or datetime.now()
    if last_timestamp is None:
        last_timestamp = current_time
        if load_power_w > 0.5:
            last_load_w = load_power_w
        return _empty_interval_result((0.0, 0.0, 0.0, 0.0), 0.0, 0.0)

    delta_seconds = (current_time - last_timestamp).total_seconds()
    if delta_seconds <= 0 or delta_seconds > MAX_INTERVAL_SECONDS:
        logging.warning(f"Interval telemetri tidak valid ({delta_seconds:.1f}s), energi tidak diakumulasi.")
        if delta_seconds > MAX_INTERVAL_SECONDS:
            last_timestamp = current_time
        cumulative_metrics = _cumulative_metrics(
            akumulasi_beban_kwh, akumulasi_ebt_kwh, akumulasi_ebt_kwh,
            akumulasi_jam_operasi, total_efisiensi_biaya_rp,
        )
        return _empty_interval_result(
            cumulative_metrics, total_efisiensi_biaya_rp,
            total_co2_tereduksi_kg,
        )
    delta_jam = delta_seconds / 3600.0

    ebt_terpakai_w = _renewable_power(pac_inverter_w, bess_power_w, load_power_w)

    energi_beban_kwh = (load_power_w   / 1000.0) * delta_jam
    energi_ebt_kwh   = (ebt_terpakai_w / 1000.0) * delta_jam
    energi_pv_dc_kwh = (pv_dc_power_w  / 1000.0) * delta_jam

    akumulasi_jam_operasi    += delta_jam
    akumulasi_beban_kwh      += energi_beban_kwh
    akumulasi_ebt_kwh        += energi_ebt_kwh
    total_efisiensi_biaya_rp += energi_ebt_kwh * TARIF_PLN_PER_KWH
    total_co2_tereduksi_kg   += energi_ebt_kwh * FAKTOR_EMISI_CO2

    akumulasi_ebt_terpakai_kwh = total_efisiensi_biaya_rp / TARIF_PLN_PER_KWH
    (renewable_fraction, lcoe_dinamis_rp,
     biaya_pln_murni_rp, biaya_aktual_rp) = _cumulative_metrics(
        akumulasi_beban_kwh, akumulasi_ebt_terpakai_kwh, akumulasi_ebt_kwh,
        akumulasi_jam_operasi, total_efisiensi_biaya_rp,
    )
    renewable_fraction = max(0.0, min(100.0, renewable_fraction))

    # Formula: (Kapasitas BESS x SoC%) / Load_W
    # Asumsi: efisiensi discharge 100%
    # Referensi load: load saat ini, fallback ke load terakhir yang valid
    essa_jam = _essa_hours(soc_pct, load_power_w, last_load_w)

    last_timestamp = current_time
    if load_power_w > 0.5:
        last_load_w = load_power_w

    return (
        total_efisiensi_biaya_rp,
        renewable_fraction,
        lcoe_dinamis_rp,
        biaya_pln_murni_rp,
        biaya_aktual_rp,
        essa_jam,
        total_co2_tereduksi_kg,
        energi_beban_kwh,
        energi_ebt_kwh,
        energi_ebt_kwh * TARIF_PLN_PER_KWH,
        energi_ebt_kwh * FAKTOR_EMISI_CO2,
        delta_jam,
    )


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Billing Engine terhubung ke MQTT Broker.")
        client.subscribe(TOPIC_TELEMETRY, qos=1)
    else:
        logging.error(f"Gagal terhubung ke MQTT, kode: {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))

        pv_dc_power = (
            float(payload.get("A.Ms.Vol", 0)) * float(payload.get("A.Ms.Amp", 0)) +
            float(payload.get("B.Ms.Vol", 0)) * float(payload.get("B.Ms.Amp", 0))
        )
        pac_inverter_w = float(payload.get("pac_inverter", 0.0))
        bess_power_w   = float(payload.get("p_inverter",   0.0))
        load_power_w   = float(payload.get("load_watt",    0.0))
        soc_pct        = float(payload.get("dc_meassoc",   0.0))
        measurement_time = datetime.fromisoformat(payload["measured_at"])

        (efisiensi_rp, rf_pct, lcoe_rp,
         biaya_pln, biaya_aktual,
         essa_jam, co2_kg, interval_load_kwh,
         interval_renewable_kwh, interval_saving_rp,
         interval_co2_kg, interval_hours) = kalkulasi_ekonomi_mikrogrid(
            pv_dc_power, pac_inverter_w,
            bess_power_w, load_power_w, soc_pct, measurement_time,
        )

        billing_payload = {
            "telemetry_id":            payload.get("telemetry_id"),
            "measured_at":             payload.get("measured_at"),
            "efisiensi_biaya_rp":     round(efisiensi_rp, 2),
            "renewable_fraction_pct": round(rf_pct,        2),
            "lcoe_dinamis_rp":        round(lcoe_rp,       2),
            "biaya_pln_murni_rp":     round(biaya_pln,     2),
            "biaya_aktual_rp":        round(biaya_aktual,   2),
            "essa_jam":               round(essa_jam,       3),
            "co2_kg":                 round(co2_kg,         4),
            "interval_load_kwh":      round(interval_load_kwh, 6),
            "interval_renewable_kwh": round(interval_renewable_kwh, 6),
            "interval_saving_rp":     round(interval_saving_rp, 4),
            "interval_co2_kg":        round(interval_co2_kg, 6),
            "interval_hours":         round(interval_hours, 6),
        }

        result = client.publish(TOPIC_BILLING, json.dumps(billing_payload), qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Publish billing gagal, rc={result.rc}")
        logging.info(
            f"Billing => "
            f"RE Save: Rp {efisiensi_rp:,.2f} | "
            f"RF: {rf_pct:.1f}% | "
            f"ESSA: {essa_jam:.2f} jam | "
            f"CO2: {co2_kg:.4f} kg"
        )

    except Exception as e:
        logging.error(f"Error billing: {e}")


def main():
    client = mqtt.Client(client_id="billing_engine")
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        logging.info("Memulai Billing Engine (CRF Model + ESSA + CO2)...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except Exception as e:
        logging.error(f"Koneksi MQTT Gagal: {e}")

if __name__ == "__main__":
    main()
