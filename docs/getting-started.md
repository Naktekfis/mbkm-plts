# Menjalankan Sistem

## Prasyarat

- Docker Desktop atau Docker Engine dengan Compose v2.
- Akses jaringan dari container ke MySQL laboratorium.
- Kredensial read-only untuk database sumber.
- Port host `1883`, `5000`, dan `5432` tersedia.
- RAM dan ruang disk yang memadai untuk dua image TensorFlow 2.7 beserta modelnya.

## Konfigurasi

Salin template environment:

```powershell
Copy-Item .env.example .env
```

Pada Linux/macOS:

```bash
cp .env.example .env
```

Isi nilai `change-me` di `.env`. Variabel yang tersedia:

| Variabel | Dipakai oleh | Default host |
|---|---|---|
| `POSTGRES_PASSWORD` | Seluruh service yang memakai PostgreSQL | Lokal Compose |
| `MYSQL_SENSOR_*` | Sensor hybrid, PV, dan beban real-time | `192.168.1.147` |
| `MYSQL_WEATHER_*` | Estimator PV | `192.168.1.147` |
| `MYSQL_LOAD_*` | Estimator load | `192.168.1.149` |

Parameter operasi opsional:

| Variabel | Default | Fungsi |
|---|---:|---|
| `MAX_SOURCE_AGE_SECONDS` | 180 | Umur maksimum data sumber |
| `MAX_SOURCE_SKEW_SECONDS` | 120 | Selisih maksimum timestamp antarsumber |
| `MAX_INTERVAL_SECONDS` | 300 | Gap maksimum billing dan histori HMI |
| `ESTIMATOR_RETRY_MINUTES` | 10 | Jeda retry estimator gagal |
| `RESTART_COOLDOWN_SECONDS` | 600 | Cooldown restart HMI |
| `MAX_RESTARTS` | 3 | Restart budget HMI |

Nama database masih menjadi bagian kontrak kode:

- Sensor: `smartgrid` dan `sielis`.
- Cuaca: `smartgrid_cas`.
- Estimator beban: `sielis`.

> [!CAUTION]
> Jangan commit `.env`. Kredensial pada deployment sebaiknya memakai user MySQL read-only dan dibatasi ke host yang membutuhkan akses.

## Menyalakan stack

Validasi konfigurasi lebih dahulu:

```bash
docker compose config --quiet
```

Build dan jalankan seluruh service:

```bash
docker compose up --build -d
```

Build pertama estimator dapat lama karena image TensorFlow dan model cukup besar. Lihat status:

```bash
docker compose ps
```

Ikuti log pipeline utama:

```bash
docker compose logs -f service_sensor service_logger service_billing service_control
```

Buka HMI di <http://localhost:5000>.

## Tanda sistem bekerja

1. `mqtt_broker` dan `postgres` berstatus running; PostgreSQL healthy.
2. Log sensor berisi `PUBLISH [microgrid/telemetry]`.
3. Log logger berisi `Database PostgreSQL siap digunakan` tanpa error koneksi MQTT.
4. Log billing dan control muncul setelah payload sensor diterbitkan.
5. `GET http://localhost:5000/health/ready` mengembalikan `200`.
6. `GET http://localhost:5000/api/data` memiliki `data_status: OK`.
7. Halaman System Health menampilkan freshness sumber data.

## Menjalankan sebagian

Untuk mengembangkan dashboard tanpa pipeline sensor, jalankan infrastruktur, logger, dan HMI:

```bash
docker compose up --build postgres mqtt_broker service_logger service_hmi
```

Dashboard akan hidup, tetapi menampilkan nilai default sampai tabel berisi data.

## Menghentikan

```bash
docker compose down
```

Perintah tersebut mempertahankan data PostgreSQL. Untuk reset database lihat [operasi](operations.md#reset-data-lokal).
