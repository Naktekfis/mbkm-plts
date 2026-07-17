# Microgrid PLTS Documentation

This documentation explains how the repository's services operate as one system. Start with [Architecture](architecture.md) for the system model, or go directly to [Getting Started](getting-started.md) to configure and launch the stack.

## Documentation Map

| Page | Purpose |
|---|---|
| [Architecture](architecture.md) | Components, data flow, system boundaries, and design decisions |
| [Getting Started](getting-started.md) | Requirements, configuration, startup, and initial verification |
| [Services](services.md) | Responsibilities and active runtime paths for each service |
| [Data Contracts](data-contracts.md) | MQTT topics, payloads, PostgreSQL tables, units, and timestamps |
| [Estimation Models](estimation-models.md) | PV and load pipelines, TensorFlow models, schedules, and legacy code |
| [Operations](operations.md) | Monitoring, troubleshooting, backup, reset, and current limitations |

## System in One Minute

The system reads solar PV, BESS, utility grid, and building load measurements from laboratory MySQL databases. `service_sensor` validates and combines those measurements into one MQTT telemetry payload. The billing and control services process each payload, while `service_logger` stores telemetry and derived results in PostgreSQL. The Flask HMI reads PostgreSQL and presents current values, history, estimates, and system health in a browser.

Two estimators run daily. The PV estimator combines weather observations, a `pvlib` physical simulation, and deep neural network (DNN) models. The load estimator selects a DNN model for the current day of the week. `docker-compose.yml` orchestrates all local components.

> **Important:** The local stack includes one MQTT broker and one PostgreSQL database. Its source telemetry, weather, and load data still depend on laboratory MySQL databases outside Compose. Containers may be running while the dashboard has no current data if network access or credentials are unavailable.

## Terminology

| Term | Meaning in this project |
|---|---|
| PLTS | Indonesian abbreviation for a solar photovoltaic power plant or system |
| PV | Photovoltaic solar generation |
| BESS | Battery energy storage system |
| HMI | Human-machine interface; the operator-facing web dashboard |
| EMS | Energy management system |
| DSS | Decision support system; the rule-based operating recommendation service |
| SoC | Battery state of charge, expressed as a percentage |
| EBT | Indonesian abbreviation for renewable energy (`Energi Baru Terbarukan`) |
| RF | Renewable fraction; the percentage of load supplied by renewable power |
| ESSA | Estimated duration for which the battery can support the load |
| LCOE | Levelized cost of energy over the assumed project lifetime |
