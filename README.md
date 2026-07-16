# Microgrid PLTS

Sistem monitoring dan analisis microgrid PLTS berbasis Python, MQTT, PostgreSQL, Flask, serta model TensorFlow. Repo ini menggabungkan telemetri PV, BESS, grid, dan beban; menghitung metrik ekonomi; menjalankan DSS rule-based; membuat estimasi PV/load; dan menampilkannya pada HMI web.

## Arsitektur singkat

```text
MySQL Lab -> Sensor -> MQTT -> Billing / Control / Logger -> PostgreSQL -> HMI
                 MySQL Cuaca/Beban -> Estimator PV/Load ---^
```

Setiap folder adalah service terpisah, sedangkan `docker-compose.yml` menjalankannya sebagai satu stack. Lihat [dokumentasi arsitektur](docs/architecture.md) untuk alur lengkap.

## Menjalankan

Prasyarat: Docker Compose v2 dan akses ke database MySQL laboratorium.

```powershell
Copy-Item .env.example .env
```

Isi kredensial MySQL pada `.env`, lalu:

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Buka <http://localhost:5000>.

> [!IMPORTANT]
> MQTT dan PostgreSQL berjalan lokal di Compose, tetapi sumber telemetri/cuaca tetap berada di MySQL eksternal. Tanpa akses ke sumber tersebut, dashboard dapat hidup namun tidak berisi data aktual.

## Service utama

| Service | Peran |
|---|---|
| `service_sensor` | Menggabungkan data MySQL yang fresh dan sinkron |
| `service_logger` | Membuat schema dan menyimpan event MQTT |
| `service_billing` | Menghitung RF, biaya, LCOE, ESSA, dan CO2 |
| `service_control` | Menentukan status operasi dengan aturan EMS |
| `service_estimation_pv` | Memperkirakan produksi PV harian |
| `service_estimation_load` | Memperkirakan beban harian |
| `service_pemantauan` | Memvalidasi range, freshness, dan frozen data |
| `service_hmi` | Menyediakan dashboard dan API Flask |
| `service_watchdog` | Memantau freshness dan readiness dengan restart terbatas |

## Dokumentasi

- [Mulai dari sini](docs/index.md)
- [Panduan menjalankan](docs/getting-started.md)
- [Penjelasan setiap service](docs/services.md)
- [Topic, payload, dan tabel](docs/data-contracts.md)
- [Model estimasi](docs/estimation-models.md)
- [Operasi dan troubleshooting](docs/operations.md)

## Validasi lokal

```bash
python -m compileall -q service_sensor service_logger service_billing service_control service_pemantauan service_watchdog service_hmi_flask pv_service_estimation load_service_estimation
python -m unittest discover -s tests -v
docker compose config --quiet
```

Saat dokumentasi ini dibuat, validasi sintaks Python, tujuh regression test, dan konfigurasi Compose berhasil. Build/run container penuh tetap perlu dilakukan dengan Docker Engine aktif dan jaringan MySQL lab tersedia.
