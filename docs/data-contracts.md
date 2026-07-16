# Kontrak Data

Daya aktif memakai Watt. `grid_apparent_power_va` adalah daya semu dan memakai VA. Energi memakai kWh, sedangkan SoC dan renewable fraction memakai persen.

## Topic MQTT

| Topic | Producer | Consumer | Bentuk data |
|---|---|---|---|
| `microgrid/telemetry` | Sensor | Logger, billing, control | JSON object telemetri |
| `microgrid/billing` | Billing | Logger | JSON hasil ekonomi |
| `microgrid/control` | Control | Logger | JSON keputusan DSS |
| `microgrid/monitoring` | Validator | Logger | JSON status dan array alert |

Telemetri, billing, dan control memakai QoS 1. `telemetry_id` dan unique index membuat insert idempoten saat broker mengirim ulang pesan. Estimator menulis langsung ke PostgreSQL dan tidak memakai MQTT.

## Payload telemetri

Contoh disederhanakan:

```json
{
  "telemetry_id": "7bb3d733-c0b3-5e2e-a80d-5de0270b404c",
  "measured_at": "2026-07-16T12:00:00",
  "source_timestamp_hybrid": "2026-07-16T12:00:00",
  "source_timestamp_pv": "2026-07-16T11:59:55",
  "source_timestamp_load": "2026-07-16T11:59:50",
  "grid_voltage": 220.0,
  "grid_current": 2.5,
  "grid_apparent_power_va": 550.0,
  "grid_frequency": 50.0,
  "dc_voltage": 51.2,
  "dc_current": 10.0,
  "bess_power_dc": 512.0,
  "dc_meassoc": 75.0,
  "dc_temperature": 30.0,
  "p_inverter": 500.0,
  "ac_frequency": 50.0,
  "A.Ms.Vol": 300.0,
  "A.Ms.Amp": 4.0,
  "B.Ms.Vol": 300.0,
  "B.Ms.Amp": 4.0,
  "pac_inverter": 2200.0,
  "GridMs.Hz": 50.0,
  "load_watt": 1800.0
}
```

`A.Ms.*`, `B.Ms.*`, dan `GridMs.Hz` mempertahankan nama kolom sumber. Logger mengubahnya menjadi nama PostgreSQL `a_ms_*`, `b_ms_*`, dan `gridms_hz`.

`telemetry_id` dibentuk secara deterministik dari tiga timestamp sumber. Snapshot sumber yang sama menghasilkan ID sama. Sensor tidak menerbitkan payload jika salah satu sumber kosong, terlalu tua, terlalu jauh selisih waktunya, atau berada di masa depan.

## Payload billing

```json
{
  "telemetry_id": "7bb3d733-c0b3-5e2e-a80d-5de0270b404c",
  "measured_at": "2026-07-16T12:00:00",
  "efisiensi_biaya_rp": 1250.5,
  "renewable_fraction_pct": 72.4,
  "lcoe_dinamis_rp": 1100.0,
  "biaya_pln_murni_rp": 1800.0,
  "biaya_aktual_rp": 549.5,
  "essa_jam": 4.2,
  "co2_kg": 1.14,
  "interval_load_kwh": 0.03,
  "interval_renewable_kwh": 0.02,
  "interval_saving_rp": 19.1,
  "interval_co2_kg": 0.0174,
  "interval_hours": 0.016667
}
```

## Payload control

```json
{
  "telemetry_id": "7bb3d733-c0b3-5e2e-a80d-5de0270b404c",
  "measured_at": "2026-07-16T12:00:00",
  "status_operasi": "DISCHARGING",
  "keputusan_aktif": "Defisit PV 500.0 W. BESS men-discharge untuk cover beban.",
  "daya_pln_dihitung_watt": 1400.0
}
```

## Tabel PostgreSQL

| Tabel | Isi | Penulis utama |
|---|---|---|
| `sensor_data` | Telemetri gabungan | Logger |
| `billing_data` | Metrik ekonomi kumulatif proses | Logger |
| `control_data` | Status dan pesan DSS | Logger |
| `monitoring_alerts` | Alert per parameter | Logger |
| `monitoring_runs` | Status setiap eksekusi validator, termasuk `OK` | Logger |
| `pv_estimasi` | Prediksi PV per jam | Estimator PV |
| `load_estimasi` | Prediksi load per menit | Estimator load |

`pv_estimasi.timestamp` dan `load_estimasi.timestamp` adalah primary key. Estimator memakai `ON CONFLICT` sehingga prediksi untuk timestamp yang sama diperbarui, bukan diduplikasi.

## Konvensi tanda

| Field | Positif | Negatif |
|---|---|---|
| `p_inverter` | BESS/hybrid inverter menyuplai panel | BESS menyerap daya untuk charging |
| `bess_power_dc` | BESS discharge | BESS charging |

Billing dan DSS menggunakan `p_inverter` untuk menentukan kontribusi discharge.

## Timestamp

Container memakai `TZ=Asia/Jakarta`. Tabel saat ini menggunakan `TIMESTAMP` tanpa timezone. `sensor_data.timestamp` adalah waktu ukur gabungan, `ingested_at` adalah waktu logger menerima pesan, dan tiga kolom `source_timestamp_*` mempertahankan waktu masing-masing sumber. Hindari mengubah timezone host/container secara terpisah karena perhitungan freshness mengasumsikan WIB.

Billing hanya mengakumulasi interval monoton sampai 300 detik. Gap lebih besar, timestamp berulang, dan timestamp mundur menghasilkan energi interval nol agar outage tidak berubah menjadi konsumsi fiktif.
