# Operasi dan Troubleshooting

## Pemeriksaan cepat

```bash
docker compose ps
docker compose logs --tail=100 service_sensor
docker compose logs --tail=100 service_logger
docker compose logs --tail=100 service_estimation_pv service_estimation_load
```

Endpoint diagnostik:

```text
GET http://localhost:5000/api/data
GET http://localhost:5000/health/ready
GET http://localhost:5000/api/system/services
GET http://localhost:5000/api/system/validity
```

## Masalah umum

### Dashboard hidup tetapi semua nilai nol

Periksa log `service_sensor`. Penyebab paling umum adalah MySQL laboratorium tidak terjangkau, kredensial `.env` salah, schema sumber berbeda, atau tidak ada record hybrid/PV. Sensor sengaja tidak publish jika data hybrid atau PV kosong.

### Logger tidak menerima pesan

Pastikan sensor, logger, billing, control, dan validator memakai `MQTT_BROKER=mqtt_broker`, broker running, dan sensor berhasil publish. Lihat log broker dan logger:

```bash
docker compose logs mqtt_broker service_logger
```

### Estimator running tetapi prediksi kosong

Scheduler menahan exception agar container tetap hidup dan mencoba ulang setiap sepuluh menit. Baca traceback pada log. Periksa coverage data kemarin, kompatibilitas model TensorFlow, dan tabel PostgreSQL.

### HMI gagal menampilkan status container

Endpoint status membutuhkan mount `/var/run/docker.sock`. Docker Desktop harus menyediakan socket Linux kepada container. Tanpa socket, data utama HMI masih dapat bekerja, tetapi status container menjadi kosong/unknown.

### Watchdog terus me-restart service

Watchdog melaporkan data lebih tua dari 180 detik tetapi tidak me-restart producer. HMI memiliki restart budget dan cooldown. Hentikan watchdog sementara saat maintenance Docker/HMI:

```bash
docker compose stop service_watchdog
```

## Reset data lokal

Menghapus container tanpa volume tidak menghapus PostgreSQL:

```bash
docker compose down
```

Reset penuh menghapus seluruh histori lokal:

```bash
docker compose down -v
```

> [!WARNING]
> `docker compose down -v` bersifat destruktif dan menghapus volume `postgres_data`.

## Backup PostgreSQL

Contoh dump dari host:

```bash
docker compose exec postgres pg_dump -U microgrid_user microgrid_db > microgrid_backup.sql
```

Simpan backup di luar repo jika mengandung data operasional.

## Keterbatasan saat ini

- Tidak ada simulator data; sistem membutuhkan MySQL lab untuk telemetri aktual.
- HMI memuat library frontend dari CDN dan tidak sepenuhnya offline.
- MQTT tidak dikonfigurasi dengan autentikasi atau TLS.
- Database memakai kredensial default Compose; gunakan secret yang berbeda untuk deployment.
- Counter kumulatif proses billing reset saat restart; ringkasan HMI memakai metrik interval yang persisten.
- Command HMI dinonaktifkan dengan respons `501` sampai consumer/driver aktuator tersedia.
- Schema masih dikelola idempoten oleh kode, belum memakai migration framework terpisah.
- Validasi estimator belum membuktikan akurasi model; golden dataset tetap diperlukan sebelum mengubah preprocessing TensorFlow.

## Validasi sebelum perubahan

Pemeriksaan minimum yang tersedia saat ini:

```bash
python -m compileall -q service_sensor service_logger service_billing service_control service_pemantauan service_watchdog service_hmi_flask pv_service_estimation load_service_estimation
python -m unittest discover -s tests -v
docker compose config --quiet
```

Jika Docker Engine aktif, lanjutkan dengan:

```bash
docker compose build
docker compose up -d
docker compose ps
```
