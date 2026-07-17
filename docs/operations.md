# Operations and Troubleshooting

## Quick Health Check

Check container state and recent logs:

```bash
docker compose ps
docker compose logs --tail=100 service_sensor
docker compose logs --tail=100 service_logger
docker compose logs --tail=100 service_estimation_pv service_estimation_load
```

Diagnostic endpoints:

```text
GET http://localhost:5000/api/data
GET http://localhost:5000/health/ready
GET http://localhost:5000/api/system/services
GET http://localhost:5000/api/system/validity
```

`/health/ready` verifies that the HMI can query `sensor_data`; it does not check data freshness. `/api/system/validity` reports freshness and the latest validator result.

## Common Problems

### The Dashboard Runs but All Values Are Zero

Inspect `service_sensor` logs. Common causes are an unreachable laboratory MySQL server, incorrect `.env` credentials, a source schema mismatch, or missing hybrid, PV, or load rows. The sensor deliberately skips publication when any required source is absent or fails timestamp validation.

The HMI can also show default values when its database query fails. Check HMI and PostgreSQL logs if the sensor and logger appear healthy:

```bash
docker compose logs service_hmi postgres
```

### The Logger Receives No Messages

Confirm that the sensor, logger, billing, control, and validator use the Compose hostname `mqtt_broker`, that the broker is running, and that sensor logs show successful publication:

```bash
docker compose logs mqtt_broker service_sensor service_logger
```

The exact sensor success prefix is `PUBLISH [microgrid/telemetry]`.

### An Estimator Is Running but Predictions Are Empty

The scheduler catches job exceptions and retries, so container state alone is not a success signal. Read the traceback in estimator logs. Check source-data coverage, MySQL connectivity, TensorFlow SavedModel compatibility, and PostgreSQL access.

```bash
docker compose logs --tail=200 service_estimation_pv service_estimation_load
```

Successful output contains exactly 24 PV rows or 1,440 load rows for the current day.

### The HMI Cannot Display Container Status

`GET /api/system/services` requires the `/var/run/docker.sock` mount. Docker Desktop must expose its Linux socket to the container. Without the socket, the main dashboard data can still work, but the service-status endpoint returns an error and an empty array.

### The Watchdog Reports Stale Services

The watchdog reports data older than 180 seconds but does not restart sensor, billing, or control producers. It only restarts the HMI after a failed readiness request, subject to its cooldown and restart budget.

Stop the watchdog during planned Docker or HMI maintenance to prevent HMI recovery attempts:

```bash
docker compose stop service_watchdog
```

## Reset Local Data

Stopping and removing containers without removing volumes preserves PostgreSQL data:

```bash
docker compose down
```

A full reset removes all local PostgreSQL history:

```bash
docker compose down -v
```

> **Warning:** `docker compose down -v` is destructive. It removes the `postgres_data` volume and all data stored in it. Create and verify a backup first if the history is needed.

## Back Up PostgreSQL

Use `-T` to disable pseudo-TTY allocation and create a custom-format dump. On Bash:

```bash
docker compose exec -T postgres pg_dump -U microgrid_user -d microgrid_db --format=custom > microgrid_backup.dump
```

On Windows Command Prompt:

```bat
docker compose exec -T postgres pg_dump -U microgrid_user -d microgrid_db --format=custom > microgrid_backup.dump
```

From Windows PowerShell, delegate binary redirection to `cmd.exe`:

```powershell
cmd /c "docker compose exec -T postgres pg_dump -U microgrid_user -d microgrid_db --format=custom > microgrid_backup.dump"
```

Store backups outside the repository when they contain operational data. Verify the file and test restoration in a separate environment before relying on it.

### Restore a Backup

> **Warning:** The following restore uses `--clean --if-exists`. It drops database objects included in the archive before recreating them and can overwrite local history. Stop application services that write to PostgreSQL, confirm the target database, and preserve another backup first.

On Bash:

```bash
docker compose exec -T postgres pg_restore -U microgrid_user -d microgrid_db --clean --if-exists < microgrid_backup.dump
```

On Windows Command Prompt:

```bat
docker compose exec -T postgres pg_restore -U microgrid_user -d microgrid_db --clean --if-exists < microgrid_backup.dump
```

From Windows PowerShell:

```powershell
cmd /c "docker compose exec -T postgres pg_restore -U microgrid_user -d microgrid_db --clean --if-exists < microgrid_backup.dump"
```

These backup and restore commands were checked against the repository's Compose service, database name, and user, but were not run against a live database.

## Current Limitations

- There is no data simulator; current telemetry requires access to the laboratory MySQL databases.
- The HMI loads some frontend libraries from a CDN and is not fully offline.
- MQTT has no authentication or TLS configuration.
- Compose supplies development defaults for database identity and fallback passwords; use deployment-specific secrets.
- Billing process-cumulative counters reset on restart. The HMI's current-day billing totals use persistent billing intervals, while `/api/history` derives date-range analysis from sensor samples and valid time intervals.
- `POST /api/control` returns `501` until an authenticated and safety-bounded actuator consumer exists.
- Runtime schema setup is idempotent application code rather than a separate migration framework.
- Unit tests do not establish estimator model accuracy or full SavedModel and `pvlib` runtime compatibility.
- Mounting the Docker socket into HMI and watchdog containers grants powerful host-level Docker access.

## Repository Validation

Run the minimum checks after Python or Compose changes:

```bash
python -m compileall -q service_sensor service_logger service_billing service_control service_pemantauan service_watchdog service_hmi_flask pv_service_estimation load_service_estimation
python -m unittest discover -s tests -v
docker compose config --quiet
```

With Docker Engine and the required network access available, continue with:

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100
```

Do not interpret syntax, unit-test, or Compose configuration success as proof that the full stack can reach external MySQL sources or load both TensorFlow models.
