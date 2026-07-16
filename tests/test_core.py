import sys
import types
import unittest
from datetime import datetime, timedelta


def install_paho_stub():
    paho = types.ModuleType("paho")
    mqtt_package = types.ModuleType("paho.mqtt")
    mqtt_client = types.ModuleType("paho.mqtt.client")
    mqtt_client.MQTT_ERR_SUCCESS = 0
    mqtt_package.client = mqtt_client
    paho.mqtt = mqtt_package
    sys.modules.update({
        "paho": paho,
        "paho.mqtt": mqtt_package,
        "paho.mqtt.client": mqtt_client,
    })


install_paho_stub()

from service_billing import billing_engine as billing
from service_control.control_engine import evaluate_ems_rules
from service_hmi_flask.history import summarize_history_rows


class ControlRulesTest(unittest.TestCase):
    def test_five_operating_modes(self):
        cases = [
            ((3000, 1000, 50, -500), "CHARGING"),
            ((3000, 1000, 99, 0), "OPTIMUM"),
            ((500, 2000, 50, 500), "DISCHARGING"),
            ((500, 2000, 50, 0), "GRID SUPPORT"),
            ((500, 2000, 20, 0), "GRID ONLY"),
        ]
        for inputs, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(evaluate_ems_rules(*inputs)["status_operasi"], expected)

    def test_partial_bess_keeps_residual_grid_power(self):
        result = evaluate_ems_rules(500, 2000, 50, 100)
        self.assertEqual(result["daya_pln_dihitung_watt"], 1400)


class BillingTest(unittest.TestCase):
    def setUp(self):
        billing.akumulasi_beban_kwh = 0.0
        billing.akumulasi_ebt_kwh = 0.0
        billing.akumulasi_jam_operasi = 0.0
        billing.total_efisiensi_biaya_rp = 0.0
        billing.total_co2_tereduksi_kg = 0.0
        billing.last_timestamp = None
        billing.last_load_w = 0.0

    def test_first_sample_does_not_invent_energy(self):
        result = billing.kalkulasi_ekonomi_mikrogrid(
            1000, 800, 200, 1000, 50, datetime(2026, 1, 1, 12, 0)
        )
        self.assertEqual(result, (0.0,) * 12)

    def test_normal_interval_uses_measurement_timestamp(self):
        start = datetime(2026, 1, 1, 12, 0)
        billing.kalkulasi_ekonomi_mikrogrid(1000, 800, 200, 1000, 50, start)
        result = billing.kalkulasi_ekonomi_mikrogrid(
            1000, 800, 200, 1000, 50, start + timedelta(seconds=60)
        )
        self.assertAlmostEqual(result[7], 1 / 60, places=6)
        self.assertAlmostEqual(result[8], 1 / 60, places=6)
        self.assertAlmostEqual(result[11], 1 / 60, places=6)

    def test_large_gap_is_not_accumulated(self):
        start = datetime(2026, 1, 1, 12, 0)
        billing.kalkulasi_ekonomi_mikrogrid(1000, 800, 0, 1000, 50, start)
        result = billing.kalkulasi_ekonomi_mikrogrid(
            1000, 800, 0, 1000, 50, start + timedelta(hours=2)
        )
        self.assertEqual(result, (0.0,) * 12)

    def test_repeated_timestamp_preserves_cumulative_metrics(self):
        start = datetime(2026, 1, 1, 12, 0)
        billing.kalkulasi_ekonomi_mikrogrid(1000, 800, 200, 1000, 50, start)
        accumulated = billing.kalkulasi_ekonomi_mikrogrid(
            1000, 800, 200, 1000, 50, start + timedelta(seconds=60)
        )
        repeated = billing.kalkulasi_ekonomi_mikrogrid(
            1000, 800, 200, 1000, 50, start + timedelta(seconds=60)
        )
        self.assertEqual(repeated[0], accumulated[0])
        self.assertEqual(repeated[6], accumulated[6])
        self.assertEqual(repeated[7:], (0.0,) * 5)


class HistorySummaryTest(unittest.TestCase):
    def test_summary_uses_actual_interval(self):
        rows = [
            {
                "timestamp": datetime(2026, 1, 1, 12, 0),
                "interval_hours": 1 / 60,
                "pv_dc": 1000,
                "pac_inverter": 1000,
                "p_inverter": 500,
                "load_w": 2000,
                "soc": 50,
                "dss_status": "DISCHARGING",
            },
            {
                "timestamp": datetime(2026, 1, 1, 12, 2),
                "interval_hours": 0,
                "pv_dc": 1000,
                "pac_inverter": 1000,
                "p_inverter": 500,
                "load_w": 2000,
                "soc": 50,
                "dss_status": "DISCHARGING",
            },
        ]
        summary, _, table = summarize_history_rows(rows, 955, 0.87, 20480)
        self.assertEqual(summary["total_pv_kwh"], 0.017)
        self.assertEqual(summary["total_load_kwh"], 0.033)
        self.assertEqual(summary["avg_rf_pct"], 75.0)
        self.assertEqual(summary["total_re_saving"], 23.88)
        self.assertEqual(summary["total_co2_kg"], 0.0218)
        self.assertEqual(table[0]["rf_pct"], 75.0)


if __name__ == "__main__":
    unittest.main()
