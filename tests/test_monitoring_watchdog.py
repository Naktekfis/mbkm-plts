import sys
import types
import unittest
from unittest import mock


def install_dependency_stubs():
    psycopg2 = sys.modules.setdefault("psycopg2", types.ModuleType("psycopg2"))
    if not hasattr(psycopg2, "connect"):
        psycopg2.connect = None

    if "paho.mqtt.client" not in sys.modules:
        paho = types.ModuleType("paho")
        mqtt_package = types.ModuleType("paho.mqtt")
        mqtt_client = types.ModuleType("paho.mqtt.client")
        mqtt_package.client = mqtt_client
        paho.mqtt = mqtt_package
        sys.modules.update({
            "paho": paho,
            "paho.mqtt": mqtt_package,
            "paho.mqtt.client": mqtt_client,
        })

    if "docker" not in sys.modules:
        docker = types.ModuleType("docker")
        docker.errors = types.SimpleNamespace(NotFound=type("NotFound", (Exception,), {}))
        docker.from_env = None
        sys.modules["docker"] = docker

    if "requests" not in sys.modules:
        requests = types.ModuleType("requests")
        requests.get = None
        sys.modules["requests"] = requests


install_dependency_stubs()

from service_pemantauan import validator
from service_watchdog import watchdog


class ValidatorCleanupTest(unittest.TestCase):
    def test_load_latest_data_closes_cursor_and_connection_on_query_failure(self):
        cursor = mock.Mock()
        cursor.execute.side_effect = RuntimeError("query failed")
        connection = mock.Mock()
        connection.cursor.return_value = cursor

        with mock.patch.object(validator, "get_db", return_value=connection):
            self.assertEqual(validator.load_latest_data(), [])

        cursor.close.assert_called_once_with()
        connection.close.assert_called_once_with()


class WatchdogPolicyTest(unittest.TestCase):
    def test_stale_source_does_not_restart_when_hmi_is_ready(self):
        restart_count = {"service_hmi_flask": 2}
        with mock.patch.object(watchdog, "cek_data_freshness", return_value=False), \
                mock.patch.object(watchdog, "cek_hmi", return_value=True), \
                mock.patch.object(watchdog, "restart_container") as restart:
            watchdog.run_checks(mock.sentinel.client, restart_count, {})

        restart.assert_not_called()
        self.assertEqual(restart_count["service_hmi_flask"], 0)

    def test_failed_hmi_observes_cooldown_and_restart_budget(self):
        name = "service_hmi_flask"
        cases = [
            ({name: 1}, {name: 999}),
            ({name: 3}, {name: 0}),
        ]
        with mock.patch.object(watchdog, "cek_hmi", return_value=False), \
                mock.patch.object(watchdog.time, "time", return_value=1000), \
                mock.patch.object(watchdog, "RESTART_COOLDOWN", 600), \
                mock.patch.object(watchdog, "MAX_RESTARTS", 3), \
                mock.patch.object(watchdog, "restart_container") as restart:
            for restart_count, last_restart in cases:
                with self.subTest(restart_count=restart_count, last_restart=last_restart):
                    watchdog.handle_hmi(mock.sentinel.client, restart_count, last_restart)

        restart.assert_not_called()

    def test_successful_hmi_resets_restart_count(self):
        restart_count = {"service_hmi_flask": 2}
        with mock.patch.object(watchdog, "cek_hmi", return_value=True):
            watchdog.handle_hmi(mock.sentinel.client, restart_count, {})
        self.assertEqual(restart_count["service_hmi_flask"], 0)

    def test_startup_grace_precedes_first_check(self):
        with mock.patch.object(watchdog.docker, "from_env", return_value=mock.sentinel.client), \
                mock.patch.object(watchdog.time, "sleep", side_effect=KeyboardInterrupt) as sleep, \
                mock.patch.object(watchdog, "run_checks") as run_checks:
            with self.assertRaises(KeyboardInterrupt):
                watchdog.main()

        sleep.assert_called_once_with(watchdog.STARTUP_GRACE)
        run_checks.assert_not_called()


if __name__ == "__main__":
    unittest.main()
