import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock


def install_hmi_stubs():
    flask = types.ModuleType("flask")

    class Flask:
        def __init__(self, name):
            self.name = name

        def route(self, *args, **kwargs):
            return lambda function: function

        def run(self, **kwargs):
            pass

    flask.Flask = Flask
    flask.render_template = lambda *args, **kwargs: None
    flask.jsonify = lambda value: value
    flask.request = types.SimpleNamespace(args={})
    flask.Response = object
    sys.modules["flask"] = flask

    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.connect = None
    extras = types.ModuleType("psycopg2.extras")
    extras.RealDictCursor = object
    psycopg2.extras = extras
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = extras


install_hmi_stubs()
from service_hmi_flask import history

sys.modules["history"] = history
from service_hmi_flask import app as hmi


class ValidityHelpersTest(unittest.TestCase):
    def test_staleness_handles_missing_naive_and_aware_timestamps(self):
        wib = timezone(timedelta(hours=7))
        now = datetime(2026, 1, 1, 12, 0, tzinfo=wib)
        self.assertIsNone(hmi._staleness_seconds(None, now))
        self.assertEqual(
            hmi._staleness_seconds(datetime(2026, 1, 1, 11, 59), now), 60
        )
        self.assertEqual(
            hmi._staleness_seconds(
                datetime(2026, 1, 1, 4, 59, tzinfo=timezone.utc), now
            ),
            60,
        )

    def test_status_boundaries_and_pv_thresholds(self):
        cases = [
            (None, "NO DATA"),
            (-61, "FUTURE"),
            (-60, "FRESH"),
            (119, "FRESH"),
            (120, "WARNING"),
            (299, "WARNING"),
            (300, "STALE"),
        ]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(hmi._status_label(seconds), expected)
        self.assertEqual(hmi._status_label(3899, 3900, 7200), "FRESH")
        self.assertEqual(hmi._status_label(3900, 3900, 7200), "WARNING")
        self.assertEqual(hmi._status_label(7200, 3900, 7200), "STALE")

    def test_source_age_and_status_use_independent_staleness_calls(self):
        timestamp = datetime(2026, 1, 1, 12, 0)
        with mock.patch.object(
            hmi, "_staleness_seconds", side_effect=[10, 130]
        ) as staleness:
            result = hmi._validity_source("Sensor", timestamp)

        self.assertEqual(result, {
            "name": "Sensor",
            "timestamp": "2026-01-01 12:00:00",
            "staleness_s": 10,
            "status": "WARNING",
        })
        self.assertEqual(staleness.call_args_list, [mock.call(timestamp), mock.call(timestamp)])


class RealtimeEndpointTest(unittest.TestCase):
    def test_no_sensor_row_returns_exact_default_contract(self):
        connection = mock.Mock()
        with mock.patch.object(hmi, "get_db", return_value=connection), mock.patch.object(
            hmi, "_fetch_realtime_data", return_value=(None, None, None, None)
        ):
            result = hmi.api_data()

        self.assertEqual(result, hmi.default_data())
        connection.close.assert_called_once_with()

    def test_sensor_row_keeps_keys_and_missing_related_data_defaults(self):
        row = {
            "grid_apparent_power_va": None,
            "grid_frequency": None,
            "grid_voltage": None,
            "grid_current": None,
            "dc_meassoc": 50,
            "dc_voltage": None,
            "dc_current": None,
            "bess_power_dc": None,
            "dc_temperature": None,
            "p_inverter": -5,
            "ac_frequency": None,
            "a_ms_vol": 2,
            "a_ms_amp": 3,
            "b_ms_vol": 4,
            "b_ms_amp": 5,
            "pac_inverter": 10,
            "load_watt": 20,
            "gridms_hz": None,
        }
        connection = mock.Mock()
        with mock.patch.object(hmi, "get_db", return_value=connection), mock.patch.object(
            hmi, "_fetch_realtime_data", return_value=(row, None, None, None)
        ):
            result = hmi.api_data()

        self.assertEqual(set(result), set(hmi.default_data()))
        self.assertEqual(result["pac_estimasi"], None)
        self.assertEqual(result["load_estimasi"], None)
        self.assertEqual(result["dss_status"], "MENUNGGU DATA")
        self.assertEqual(result["dss_pesan"], "Menganalisis sistem...")
        self.assertEqual(result["data_status"], "OK")
        self.assertEqual(result["grid_va"], 0)
        self.assertEqual(result["rf_instan"], 50.0)
        self.assertEqual(result["p_inverter"], -5)


class HistoryEndpointTest(unittest.TestCase):
    def test_empty_history_response_is_unchanged(self):
        cursor = mock.Mock()
        cursor.fetchall.return_value = []
        connection = mock.Mock()
        connection.cursor.return_value = cursor
        hmi.request.args = {"start": "2026-01-01", "end": "2026-01-02"}

        with mock.patch.object(hmi, "get_db", return_value=connection):
            result = hmi.api_history()

        self.assertEqual(result, {"summary": {}, "rows": [], "charts": {}})
        connection.close.assert_called_once_with()

    def test_csv_preserves_date_status_and_schema_contract(self):
        cursor = mock.Mock()
        cursor.fetchall.return_value = [{
            "timestamp": datetime(2026, 1, 1, 12, 0),
            "pv_dc_w": 100,
            "pac_inverter_w": 90,
            "grid_va": 20,
            "p_inverter_w": -10,
            "soc_pct": 75,
            "load_w": 100,
            "rf_pct": 90,
            "re_saving_rp": 1.5,
            "dss_status": "CHARGING",
        }]
        connection = mock.Mock()
        connection.cursor.return_value = cursor
        hmi.request.args = {"start": "2026-01-01", "end": "2026-01-02"}

        def response(body, mimetype, headers):
            return {"body": body, "mimetype": mimetype, "headers": headers}

        with mock.patch.object(hmi, "get_db", return_value=connection), mock.patch.object(
            hmi, "Response", side_effect=response
        ):
            result = hmi.export_history_csv()

        sql, params = cursor.execute.call_args.args
        self.assertEqual(params, ("2026-01-01 00:00:00", "2026-01-02 23:59:59"))
        self.assertIn("WHERE s.timestamp BETWEEN %s AND %s", sql)
        self.assertIn("COALESCE(c.status_operasi, '-') AS dss_status", sql)
        self.assertIn("c.telemetry_id = s.telemetry_id", sql)
        self.assertEqual(result["mimetype"], "text/csv")
        self.assertEqual(
            result["headers"],
            {"Content-Disposition": "attachment; filename=microgrid_history_2026-01-01_to_2026-01-02.csv"},
        )
        self.assertEqual(
            result["body"],
            "Timestamp,PV DC (W),AC Inverter PV (W),Grid PLN (VA),P Inverter Hybrid (W),SoC (%),Load (W),Renewable Fraction (%),RE Saving (Rp),DSS Status\r\n"
            "2026-01-01 12:00:00,100,90,20,-10,75,100,90,1.5,CHARGING\r\n",
        )


if __name__ == "__main__":
    unittest.main()
