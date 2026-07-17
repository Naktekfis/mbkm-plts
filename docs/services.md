# Services

This page covers the code paths invoked by the active Compose stack. Experimental, training, benchmark, and maintenance scripts are listed separately under [Non-Runtime Code](estimation-models.md#non-runtime-code).

## `service_sensor`

Entry point: `service_sensor/kirim.py`

`ambil_data_terkini()` connects to MySQL and reads the latest rows for the hybrid inverter, PV inverter, and meter 6 load data. It rejects a snapshot when a source is missing, older than `MAX_SOURCE_AGE_SECONDS`, more than `MAX_SOURCE_SKEW_SECONDS` away from another source, or too far in the future. Accepted snapshots are published every 60 seconds.

The service separates timestamp validation into `_validate_source_timestamps()` and payload conversion into `_build_telemetry_payload()`. A UUID generated from the three source timestamps becomes `telemetry_id`, so an unchanged source snapshot produces the same ID.

Key calculations:

- Grid apparent power: `ExtVtg * ExtCur`, in VA.
- BESS DC power: `BatVtg * TotBatCur`, in W.
- Hybrid inverter power: `TotInvPwrAt * 1000`, converting the source value from kW to W.
- Three-phase load power: the sum of `V * A * PF` for all three phases, in W.

For `p_inverter`, a positive value means that the BESS or hybrid inverter supplies the AC panel (discharge); a negative value means that it absorbs power (charging).

## `service_logger`

Entry point: `service_logger/monitor.py`

`setup_database()` creates runtime, estimation, and monitoring tables; adds missing columns; and creates timestamp and partial unique indexes. Its `CREATE ... IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS` operations make setup safe to repeat.

The logger subscribes to telemetry, billing, and control with MQTT QoS 1. It uses unique `telemetry_id` indexes and `ON CONFLICT DO NOTHING` to prevent duplicate rows when MQTT redelivers those messages. Monitoring messages use the default QoS and record every validator run plus its individual alerts.

`sensor_data.timestamp` stores `measured_at`, while `ingested_at` records when the logger received the MQTT message. The original hybrid, PV, and load timestamps are retained in separate `source_timestamp_*` columns.

## `service_billing`

Entry point: `service_billing/billing_engine.py`

`kalkulasi_ekonomi_mikrogrid()` calculates:

- Load and renewable energy for each accepted interval.
- Savings against the PLN tariff of Rp955/kWh.
- Renewable fraction.
- Dynamic LCOE from CAPEX, OPEX, a 5% interest rate, and a 15-year project life.
- ESSA from the 20,480 Wh BESS capacity, SoC, and current or last valid load.
- Avoided CO2 using an emission factor of 0.87 kg/kWh.

The public calculation function returns a 12-value tuple consumed by `on_message()`. Cumulative counters remain in process memory and reset when the service restarts. Persistent interval billing metrics allow the HMI's current-day billing totals to survive billing restarts. The `/api/history` date-range analysis instead derives energy, renewable fraction, savings, and CO2 from sensor samples and their valid time intervals.

The first message initializes the interval clock and records no energy. Repeated or backward timestamps and gaps longer than `MAX_INTERVAL_SECONDS` also record zero interval energy, preventing duplicates, clock changes, or outages from creating fictitious consumption. In all four cases, interval calculation is unavailable and the returned `essa_jam` is `0.0`; this value does not mean that the battery is empty.

## `service_control`

Entry point: `service_control/control_engine.py`

`evaluate_ems_rules()` implements a rule-based energy management DSS with five statuses:

| Condition | `status_operasi` |
|---|---|
| PV surplus and SoC below 98% | `CHARGING` |
| PV surplus and SoC at least 98%, or PV exactly matches load | `OPTIMUM` |
| PV deficit, SoC above 20%, and BESS discharge above 10 W | `DISCHARGING` |
| PV deficit, SoC above 20%, and BESS not discharging above 10 W | `GRID SUPPORT` |
| PV deficit and SoC at or below 20% | `GRID ONLY` |

`daya_pln_dihitung_watt` is the remaining load after PV output and positive BESS discharge are subtracted. The service publishes a recommendation and operating status; it does not send commands to an inverter or physical actuator.

## `service_pemantauan`

Entry point: `service_pemantauan/validator.py`

Every 60 seconds, the validator reads the latest 25 `sensor_data` rows and checks:

- Configured minimum and maximum ranges on the latest row.
- Data staleness beyond 120 seconds and timestamps more than 60 seconds in the future.
- Identical values across the latest 20 readings.
- Timestamp ordering.

SoC, DC voltage, and DC temperature are excluded from frozen-value detection. Zero `pac_inverter` and `p_inverter` values are accepted at night, defined as outside 06:00 through 17:59 WIB.

`run_validasi()` produces `OK`, `WARNING`, or `ERROR` in `status_global` and publishes the result to `microgrid/monitoring`. `load_latest_data()` contains the database access and closes its cursor and connection after each read.

## `service_hmi`

Backend entry point: `service_hmi_flask/app.py`

Frontend paths:

- `service_hmi_flask/templates/index.html`
- `service_hmi_flask/static/js/main.js`
- `service_hmi_flask/static/img/`

Primary API routes:

| Method and path | Purpose |
|---|---|
| `GET /` | Dashboard page |
| `GET /api/data` | Latest sensor, billing, DSS, and estimation snapshot |
| `GET /api/sensor/history` | Latest 60 sensor records |
| `GET /api/control/history` | Latest 20 DSS decisions |
| `GET /api/history` | Date-range analysis; requires `start` and `end` query parameters |
| `GET /api/history/export` | Date-range CSV export; requires `start` and `end` query parameters |
| `GET /api/system/services` | Container status through the Docker API |
| `GET /api/system/validity` | Source freshness and latest data-quality alerts |
| `GET /health/ready` | PostgreSQL connectivity and ability to query `sensor_data` |
| `POST /api/control` | Returns `501`; no actuator integration is available |

Gunicorn runs the HMI in Compose. The frontend polls primary data every 30 seconds and obtains container status through a separate endpoint.

For real-time data, route orchestration, database queries, and response construction are separated into helpers. For history, `api_history()` reads the requested range and passes rows to `history.py::summarize_history_rows()` for interval metrics, summaries, charts, and table data.

## `service_watchdog`

Entry point: `service_watchdog/watchdog.py`

After a 180-second startup grace period, `run_checks()` executes every 120 seconds. Each table check fails when the table has no timestamp, the query fails, the latest timestamp is more than 60 seconds in the future, or the latest row is older than 180 seconds. These results are diagnostic only; they do not trigger producer restarts.

Only `service_hmi_flask` is restarted when `http://service_hmi:5000/health/ready` fails. Recovery is limited to three attempts by default, with a ten-minute cooldown. A successful readiness check resets the HMI restart counter.

The mounted Docker socket gives this container administrative access to the Docker host. Run it only on a trusted host.

## Estimators

- `service_estimation_pv` runs `pv_service_estimation/service_estimation.py` at startup and daily at 00:05 WIB.
- `service_estimation_load` runs `load_service_estimation/service_estimation_load.py` at startup and daily at 00:10 WIB.

If the current day's job has not succeeded, the scheduler retries at `ESTIMATOR_RETRY_MINUTES`, ten minutes by default. Each pipeline validates source coverage and output length before batch-upserting its result.

See [Estimation Models](estimation-models.md) for pipeline and model details.
