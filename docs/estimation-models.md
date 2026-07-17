# Estimation Models

Both estimator Dockerfiles pin `tensorflow/tensorflow:2.7.0`. The PV Dockerfile explicitly attributes this pin to compatibility with `pv_model` and `pv_dnn`; the repository does not independently document how the load SavedModel artifacts were produced. Treat TensorFlow 2.7.0 as the tested repository baseline, and do not upgrade TensorFlow or convert either model format without testing both estimator pipelines.

## PV Estimation

Active runtime path:

```text
service_estimation.py
  -> main.py
  -> aws_model2_openmeteo.py
  -> query_openmeteo.py
  -> pvlib_model.py
  -> pv_model/ and pv_dnn/
```

Pipeline:

1. `query_openmeteo.get_query()` reads the previous day's weather records from `smartgrid_cas.weather`.
2. The query groups observations by minute. It requires at least 18 distinct covered hours, a span of at least 20 hours, and no gap longer than 3 hours.
3. `_prepare_minutely_weather()` creates a complete 1,440-minute WIB index and interpolates irradiance, temperature, and wind speed.
4. The SavedModel in `pv_model/` predicts direct normal irradiance (DNI) from global horizontal irradiance (GHI) and time features.
5. `pvlib_model.pvlib_instantiate()` simulates the physical PV system in Bandung.
6. The SavedModel in `pv_dnn/` corrects the simulated AC output.
7. The pipeline samples 24 hourly values and assigns them to the current day.
8. `main.run()` validates the 24-row output and batch-upserts it into `pv_estimasi`.

The physical model uses a Bandung location near latitude `-6.89`, longitude `107.61`, and altitude 770 m. The array faces east at a 2-degree tilt, with 16 modules per string and 2 strings per inverter.

The model treats yesterday's observed weather as today's profile. This is a persistence assumption in the current estimator, not a future weather forecast.

## Load Estimation

Active runtime path:

```text
service_estimation_load.py
  -> main.py
  -> model_beban.py
  -> query.py
  -> model_bebanv2/model/modelbeban_<Day>/
```

Pipeline:

1. `query.get_query()` reads the previous day's meter 6 records from `sielis.datapengukuran` and aggregates them by minute.
2. Input requires at least 1,200 rows, a span of at least 22 hours, and no gap longer than 15 minutes.
3. `_prepare_minute_input()` reindexes and interpolates a complete minute series.
4. Power is calculated as `3 * A * PF * VLN`.
5. The code builds its legacy moving-average feature and month, day, hour, and minute features.
6. It selects the SavedModel for the current weekday, such as `modelbeban_Monday`.
7. The model produces 1,440 values from 00:00 through 23:59 WIB for the current day.
8. `main.run()` validates the row count and batch-upserts the output into `load_estimasi`.

`model_bebanv2/training/` contains weekday training CSV files. Runtime jobs perform inference only and do not retrain the models.

## Schedule and Retry Behavior

| Service | At container startup | Daily schedule |
|---|---|---|
| PV estimator | Runs one job immediately | 00:05 WIB |
| Load estimator | Runs one job immediately | 00:10 WIB |

Each scheduler catches job exceptions so the container remains running. If the current day's output has not succeeded, it retries every `ESTIMATOR_RETRY_MINUTES`, ten minutes by default. A `running` container therefore does not prove that predictions were generated; inspect the logs and estimation tables.

## Validation Scope

Estimator helper tests use controlled fakes and mocks. They can validate preprocessing and output contracts without loading TensorFlow. They do not prove compatibility with the bundled SavedModel artifacts, the installed `pvlib` runtime, source database data, or model accuracy. Use a representative golden dataset before changing TensorFlow, `pvlib`, scaling, interpolation, feature order, or time handling.

## Non-Runtime Code

The active Dockerfiles and entry points do not call these files:

- `pv_service_estimation/aws_model.py`: older PV pipeline with host-specific paths.
- `pv_service_estimation/aws_model2.py` and `pv_service_estimation/query.py`: alternatives that predate the active weather path.
- `pv_service_estimation/PVDNN.py`: training and experiment script.
- `pv_service_estimation/pvlib_dnn.py`: incomplete experiment.
- `pv_service_estimation/time_pv.py` and `load_service_estimation/time_load.py`: benchmarks.
- `pv_service_estimation/pv_hourly.py` and `pv_service_estimation/fixpac.py`: older database maintenance scripts.
- `load_service_estimation/delete.py`: destructive maintenance script.

Do not add these files to the runtime path without revalidating their filesystem paths, schemas, credentials, dependencies, and model assumptions.
