import json
import re
import sys
import types
import unittest
from datetime import datetime, timedelta
from unittest import mock
from uuid import NAMESPACE_URL, uuid5


def install_dependency_stubs():
    if "paho.mqtt.client" not in sys.modules:
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

    mysql = types.ModuleType("mysql")
    mysql_connector = types.ModuleType("mysql.connector")
    mysql_connector.Error = type("MySQLError", (Exception,), {})
    mysql_connector.connect = None
    mysql.connector = mysql_connector
    sys.modules.update({"mysql": mysql, "mysql.connector": mysql_connector})
    psycopg2 = sys.modules.setdefault("psycopg2", types.ModuleType("psycopg2"))
    if not hasattr(psycopg2, "connect"):
        psycopg2.connect = None


install_dependency_stubs()

from service_logger import monitor
from service_sensor import kirim


class SensorTelemetryTest(unittest.TestCase):
    def test_source_fetch_order_and_connection_cleanup(self):
        class FixedDateTime(datetime):
            @classmethod
            def now(cls):
                return cls(2026, 1, 2, 12, 0, 0)

        hybrid = {
            "source_timestamp": FixedDateTime(2026, 1, 2, 11, 59, 59),
            "ExtVtg": 230, "ExtCur": 2, "ExtFrq": 50, "BatVtg": 50,
            "TotBatCur": 1, "BatSoc": 70, "BatTmp": 30,
            "TotInvPwrAt": 1, "Fac": 50,
        }
        pv = {
            "source_timestamp": FixedDateTime(2026, 1, 2, 11, 59, 59),
            "A.Ms.Vol": 400, "A.Ms.Amp": 2, "B.Ms.Vol": 400,
            "B.Ms.Amp": 2, "Pac": 1500, "GridMs.Hz": 50,
        }
        load = {
            "source_timestamp": FixedDateTime(2026, 1, 2, 11, 59, 59),
            "load_watt": 1800,
        }
        smartgrid_cursor = mock.Mock()
        smartgrid_cursor.fetchone.side_effect = [hybrid, pv]
        sielis_cursor = mock.Mock()
        sielis_cursor.fetchone.return_value = load
        smartgrid = mock.Mock()
        smartgrid.cursor.return_value = smartgrid_cursor
        smartgrid.is_connected.return_value = True
        sielis = mock.Mock()
        sielis.cursor.return_value = sielis_cursor
        sielis.is_connected.return_value = True

        with mock.patch.object(kirim, "datetime", FixedDateTime), mock.patch.object(
            kirim.mysql.connector, "connect", side_effect=[smartgrid, sielis]
        ) as connect_mock:
            result = kirim.ambil_data_terkini()

        self.assertEqual(result["p_inverter"], 1000.0)
        self.assertEqual([call.kwargs["database"] for call in connect_mock.call_args_list], ["smartgrid", "sielis"])
        self.assertEqual(smartgrid.cursor.call_count, 1)
        self.assertEqual(smartgrid_cursor.execute.call_count, 2)
        self.assertIn("FROM datapengukuran", smartgrid_cursor.execute.call_args_list[0].args[0])
        self.assertIn("FROM pv_datapengukuran", smartgrid_cursor.execute.call_args_list[1].args[0])
        self.assertIn("WHERE meter_id = 6", sielis_cursor.execute.call_args.args[0])
        smartgrid.close.assert_called_once_with()
        sielis.close.assert_called_once_with()

    def test_payload_contract_and_calculations(self):
        source_times = {
            "hybrid": datetime(2026, 1, 2, 3, 4, 5),
            "pv": datetime(2026, 1, 2, 3, 4, 6),
            "load": datetime(2026, 1, 2, 3, 4, 7),
        }
        hybrid = {
            "ExtVtg": "230", "ExtCur": "2.5", "ExtFrq": "50.1",
            "BatVtg": "51.2", "TotBatCur": "-4", "BatSoc": "72.5",
            "BatTmp": "31", "TotInvPwrAt": "-1.25", "Fac": "49.9",
        }
        pv = {
            "A.Ms.Vol": "400", "A.Ms.Amp": "3", "B.Ms.Vol": "410",
            "B.Ms.Amp": "2.5", "Pac": "1900", "GridMs.Hz": "50.05",
        }
        telemetry_key = "|".join(ts.isoformat() for ts in source_times.values())

        result = kirim._build_telemetry_payload(
            hybrid, pv, {"load_watt": "2150.5"}, source_times
        )

        self.assertEqual(result, {
            "telemetry_id": str(uuid5(NAMESPACE_URL, telemetry_key)),
            "measured_at": "2026-01-02T03:04:07",
            "source_timestamp_hybrid": "2026-01-02T03:04:05",
            "source_timestamp_pv": "2026-01-02T03:04:06",
            "source_timestamp_load": "2026-01-02T03:04:07",
            "grid_voltage": 230.0,
            "grid_current": 2.5,
            "grid_apparent_power_va": 575.0,
            "grid_frequency": 50.1,
            "dc_voltage": 51.2,
            "dc_current": -4.0,
            "bess_power_dc": -204.8,
            "dc_meassoc": 72.5,
            "dc_temperature": 31.0,
            "p_inverter": -1250.0,
            "ac_frequency": 49.9,
            "A.Ms.Vol": 400.0,
            "A.Ms.Amp": 3.0,
            "B.Ms.Vol": 410.0,
            "B.Ms.Amp": 2.5,
            "pac_inverter": 1900.0,
            "GridMs.Hz": 50.05,
            "load_watt": 2150.5,
        })

    def test_timestamp_freshness_future_and_skew_policies(self):
        class FixedDateTime(datetime):
            @classmethod
            def now(cls):
                return cls(2026, 1, 2, 12, 0, 0)

        now = FixedDateTime.now()
        cases = [
            (now - timedelta(seconds=181), now, now),
            (now + timedelta(seconds=121), now, now),
            (now - timedelta(seconds=121), now, now),
        ]
        with mock.patch.object(kirim, "datetime", FixedDateTime):
            for hybrid_ts, pv_ts, load_ts in cases:
                with self.subTest(times=(hybrid_ts, pv_ts, load_ts)):
                    self.assertIsNone(kirim._validate_source_timestamps(
                        {"source_timestamp": hybrid_ts},
                        {"source_timestamp": pv_ts},
                        {"source_timestamp": load_ts},
                    ))


class LoggerInsertTest(unittest.TestCase):
    def test_telemetry_parameter_order_and_placeholder_count(self):
        column_sources = [
            ("telemetry_id", "telemetry_id"),
            ("timestamp", "measured_at"),
            ("ingested_at", None),
            ("source_timestamp_hybrid", "source_timestamp_hybrid"),
            ("source_timestamp_pv", "source_timestamp_pv"),
            ("source_timestamp_load", "source_timestamp_load"),
            ("grid_apparent_power_va", "grid_apparent_power_va"),
            ("grid_frequency", "grid_frequency"),
            ("grid_voltage", "grid_voltage"),
            ("grid_current", "grid_current"),
            ("dc_meassoc", "dc_meassoc"),
            ("dc_voltage", "dc_voltage"),
            ("dc_current", "dc_current"),
            ("bess_power_dc", "bess_power_dc"),
            ("dc_temperature", "dc_temperature"),
            ("p_inverter", "p_inverter"),
            ("ac_frequency", "ac_frequency"),
            ("a_ms_vol", "A.Ms.Vol"),
            ("a_ms_amp", "A.Ms.Amp"),
            ("b_ms_vol", "B.Ms.Vol"),
            ("b_ms_amp", "B.Ms.Amp"),
            ("pac_inverter", "pac_inverter"),
            ("load_watt", "load_watt"),
            ("gridms_hz", "GridMs.Hz"),
        ]
        payload = {source: source for _, source in column_sources if source}
        cursor = mock.Mock()

        monitor._insert_telemetry(cursor, payload, "ingested")

        sql, params = cursor.execute.call_args.args
        columns_sql = sql.split("INSERT INTO sensor_data (", 1)[1].split(") VALUES", 1)[0]
        columns = [column.strip() for column in columns_sql.split(",")]
        expected_params = tuple(
            payload[source] if source else "ingested"
            for _, source in column_sources
        )
        self.assertEqual(columns, [column for column, _ in column_sources])
        self.assertEqual(params, expected_params)
        self.assertEqual(sql.count("%s"), len(params))

    def test_on_message_keeps_transaction_and_connection_ownership(self):
        connection = mock.Mock()
        msg = types.SimpleNamespace(
            topic="microgrid/telemetry",
            payload=json.dumps({"telemetry_id": "id"}).encode("utf-8"),
        )

        with mock.patch.object(monitor.psycopg2, "connect", return_value=connection):
            monitor.on_message(None, None, msg)

        connection.commit.assert_called_once_with()
        connection.close.assert_called_once_with()

    @mock.patch("builtins.print")
    def test_setup_database_preserves_statement_groups_and_output(self, print_mock):
        connection = mock.Mock()

        with mock.patch.object(monitor.psycopg2, "connect", return_value=connection):
            monitor.setup_database()

        statements = [
            " ".join(call.args[0].split())
            for call in connection.cursor.return_value.execute.call_args_list
        ]

        def statement_label(statement):
            for pattern, label in (
                (r"CREATE TABLE IF NOT EXISTS (\w+)", "table:{}"),
                (r"ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+)", "column:{}.{}"),
                (r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+)", "index:{}"),
            ):
                match = re.match(pattern, statement)
                if match:
                    return label.format(*match.groups())
            self.fail(f"Pernyataan setup tidak dikenali: {statement}")

        actual_order = [statement_label(statement) for statement in statements]
        expected_groups = [
            ("runtime tables", [
                "table:sensor_data",
                "table:billing_data",
                "column:billing_data.essa_jam",
                "column:billing_data.co2_kg",
                "table:control_data",
            ]),
            ("runtime migrations", [
                "column:sensor_data.telemetry_id",
                "column:sensor_data.ingested_at",
                "column:sensor_data.source_timestamp_hybrid",
                "column:sensor_data.source_timestamp_pv",
                "column:sensor_data.source_timestamp_load",
                "column:sensor_data.grid_apparent_power_va",
                "column:sensor_data.grid_voltage",
                "column:sensor_data.grid_current",
                "column:sensor_data.dc_voltage",
                "column:sensor_data.dc_current",
                "column:sensor_data.bess_power_dc",
                "column:sensor_data.dc_temperature",
                "column:sensor_data.ac_volt",
                "column:sensor_data.ac_current_si",
                "column:sensor_data.p_inverter",
                "column:billing_data.telemetry_id",
                "column:billing_data.interval_load_kwh",
                "column:billing_data.interval_renewable_kwh",
                "column:billing_data.interval_saving_rp",
                "column:billing_data.interval_co2_kg",
                "column:billing_data.interval_hours",
                "column:control_data.telemetry_id",
            ]),
            ("support tables", [
                "table:monitoring_alerts",
                "table:monitoring_runs",
                "table:pv_estimasi",
                "table:load_estimasi",
            ]),
            ("indexes", [
                "index:idx_sensor_data_timestamp",
                "index:idx_billing_data_timestamp",
                "index:idx_control_data_timestamp",
                "index:idx_monitoring_alerts_timestamp",
                "index:idx_monitoring_runs_timestamp",
                "index:idx_sensor_telemetry_id",
                "index:idx_billing_telemetry_id",
                "index:idx_control_telemetry_id",
            ]),
        ]
        offset = 0
        for group, expected_order in expected_groups:
            with self.subTest(group=group):
                end = offset + len(expected_order)
                self.assertEqual(actual_order[offset:end], expected_order)
                offset = end
        self.assertEqual(offset, len(actual_order))
        connection.commit.assert_called_once_with()
        connection.close.assert_called_once_with()
        print_mock.assert_called_once_with("Database PostgreSQL siap digunakan.")


if __name__ == "__main__":
    unittest.main()
