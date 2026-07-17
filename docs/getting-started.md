# Getting Started

## Requirements

- Docker Desktop or Docker Engine with Docker Compose v2.
- Network access from containers to the laboratory MySQL servers.
- Read-only credentials for the source databases.
- Available host ports `1883`, `5000`, and `5432`.
- Enough memory and disk space for two TensorFlow 2.7 images and their bundled models.

## Configuration

Create a local environment file on Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

On Linux or macOS:

```bash
cp .env.example .env
```

Replace every `change-me` value in `.env`. The connection variables are:

| Variable | Used by | Default target |
|---|---|---|
| `POSTGRES_PASSWORD` | All services that connect to PostgreSQL | Local Compose database |
| `MYSQL_SENSOR_HOST`, `MYSQL_SENSOR_PORT`, `MYSQL_SENSOR_USER`, `MYSQL_SENSOR_PASS` | Real-time hybrid inverter, PV, and load sensor queries | `192.168.1.147:3306` |
| `MYSQL_WEATHER_HOST`, `MYSQL_WEATHER_PORT`, `MYSQL_WEATHER_USER`, `MYSQL_WEATHER_PASS` | PV estimator weather query | `192.168.1.147:3306` |
| `MYSQL_LOAD_HOST`, `MYSQL_LOAD_PORT`, `MYSQL_LOAD_USER`, `MYSQL_LOAD_PASS` | Load estimator query | `192.168.1.149:3306` |

Optional operating parameters:

| Variable | Default | Purpose |
|---|---:|---|
| `MAX_SOURCE_AGE_SECONDS` | 180 | Maximum accepted age of the oldest source record |
| `MAX_SOURCE_SKEW_SECONDS` | 120 | Maximum timestamp difference among source records; also bounds accepted future skew |
| `MAX_INTERVAL_SECONDS` | 300 | Maximum interval accumulated by billing and HMI history calculations |
| `ESTIMATOR_RETRY_MINUTES` | 10 | Retry interval after an estimator has not succeeded for the current day |
| `RESTART_COOLDOWN_SECONDS` | 600 | Minimum delay between HMI restart attempts |
| `MAX_RESTARTS` | 3 | HMI restart budget before recovery is suppressed |

The source database names are fixed in the runtime code:

- `service_sensor`: `smartgrid` and `sielis`.
- PV weather source: `smartgrid_cas`.
- Load estimator source: `sielis`.

> **Caution:** Do not commit `.env`. For deployments, use restricted read-only MySQL users and limit their access to only the required hosts and databases.

## Network Exposure

The default Compose file publishes MQTT `1883`, HMI `5000`, and PostgreSQL `5432` on host interfaces. MQTT has no authentication or TLS, and the HMI has no documented authentication. Use the default stack only on a trusted network or a firewalled host; do not expose these ports directly to an untrusted network or the public internet.

If access should be limited to the local host, replace the existing `ports` entries in `docker-compose.yml` rather than appending mappings in an override. Bind `mqtt_broker` as `127.0.0.1:1883:1883`, `service_hmi` as `127.0.0.1:5000:5000`, and `postgres` as `127.0.0.1:5432:5432`. Run `docker compose config` afterward and confirm that no wildcard mappings remain before starting the stack.

## Start the Stack

Validate the resolved configuration first:

```bash
docker compose config --quiet
```

Build and start all services:

```bash
docker compose up --build -d
```

The first estimator build can take time because the TensorFlow images and model artifacts are large. Check container status with:

```bash
docker compose ps
```

Follow the primary pipeline logs:

```bash
docker compose logs -f service_sensor service_logger service_billing service_control
```

Open the HMI at <http://localhost:5000>.

## Verify the Startup

1. `mqtt_broker` and `postgres` are running, and PostgreSQL is healthy.
2. Sensor logs contain `PUBLISH [microgrid/telemetry]`.
3. Logger output contains the exact runtime message `Database PostgreSQL siap digunakan.` and no MQTT connection error.
4. Billing and control logs appear after the sensor publishes telemetry.
5. `GET http://localhost:5000/health/ready` returns HTTP `200` with `{"status":"ready"}`.
6. `GET http://localhost:5000/api/data` returns `"data_status":"OK"` after at least one sensor row is available.
7. The HMI System Health view reports source freshness.

The readiness endpoint confirms that the HMI can query the `sensor_data` table. It does not guarantee that the latest row is fresh; use `/api/system/validity` for freshness information.

## Start a Partial Stack

To work on the dashboard without the sensor pipeline, start the infrastructure, logger, and HMI:

```bash
docker compose up --build postgres mqtt_broker service_logger service_hmi
```

The dashboard starts with default values until the database contains data.

## Stop the Stack

```bash
docker compose down
```

This command preserves PostgreSQL data. See [Reset Local Data](operations.md#reset-local-data) for a destructive reset.
