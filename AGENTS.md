# AGENTS.md

Panduan ini berlaku untuk seluruh repository.

## Tujuan sistem

Repo menjalankan pipeline microgrid PLTS sebagai kumpulan microservice Docker. Jangan melebur folder service menjadi satu proses tanpa alasan operasional yang terukur. Batas service dipakai karena dependensi ringan (sensor/logger/HMI) dan berat (TensorFlow estimator) berbeda.

## Sumber kebenaran

- Orkestrasi: `docker-compose.yml`.
- Kontrak telemetri: dictionary keluaran `service_sensor/kirim.py`.
- Schema runtime: `service_logger/monitor.py::setup_database`.
- Aturan EMS: `service_control/control_engine.py::evaluate_ems_rules`.
- Perhitungan ekonomi: `service_billing/billing_engine.py::kalkulasi_ekonomi_mikrogrid`.
- API HMI: route pada `service_hmi_flask/app.py`.
- Dokumentasi teknis: `docs/index.md`.

Jika mengubah payload, periksa seluruh producer dan consumer terkait serta perbarui `docs/data-contracts.md`.

## Jalur runtime

File Python aktif:

- `service_sensor/kirim.py`
- `service_logger/monitor.py`
- `service_billing/billing_engine.py`
- `service_control/control_engine.py`
- `service_pemantauan/validator.py`
- `service_watchdog/watchdog.py`
- `service_hmi_flask/app.py`
- `service_hmi_flask/history.py`
- `pv_service_estimation/service_estimation.py`
- `pv_service_estimation/main.py`
- `pv_service_estimation/aws_model2_openmeteo.py`
- `pv_service_estimation/query_openmeteo.py`
- `pv_service_estimation/pvlib_model.py`
- `load_service_estimation/service_estimation_load.py`
- `load_service_estimation/main.py`
- `load_service_estimation/model_beban.py`
- `load_service_estimation/query.py`

File lain di folder estimator adalah legacy, eksperimen, training, benchmark, atau maintenance. Jangan menghubungkannya ke runtime hanya karena namanya mirip. Lihat `docs/estimation-models.md`.

## Aturan perubahan

- Pertahankan Watt sebagai satuan daya runtime. Konversi kW hanya di batas sumber yang memang menyimpan kW.
- Pertahankan konvensi `p_inverter`: positif untuk discharge, negatif untuk charging.
- Gunakan hostname Compose (`mqtt_broker`, `postgres`, `service_hmi`) untuk komunikasi internal.
- Konfigurasi host/kredensial eksternal harus melalui environment, bukan literal baru di source.
- Jangan commit `.env`, dump database, credential nyata, atau data operasional.
- Jangan upgrade TensorFlow 2.7 atau format SavedModel tanpa menguji kedua estimator.
- Jangan menghapus model/CSV training sebagai cleanup tanpa konfirmasi; ukurannya besar tetapi merupakan artefak domain.
- Pertahankan proses setup database idempoten (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).
- Jangan mengubah topic MQTT tanpa memperbarui semua producer/consumer dan dokumentasi.
- Hindari memasukkan driver aktuator ke `service_control` tanpa batas keamanan, autentikasi, validasi command, dan persetujuan eksplisit.

## Pemeriksaan minimum

Jalankan setelah perubahan Python atau Compose:

```bash
python -m compileall -q service_sensor service_logger service_billing service_control service_pemantauan service_watchdog service_hmi_flask pv_service_estimation load_service_estimation
python -m unittest discover -s tests -v
docker compose config --quiet
```

Jika Docker Engine dan jaringan lab tersedia:

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100
```

Untuk perubahan DSS, uji setidaknya kelima cabang status. Untuk billing, uji charging/discharging, beban nol, panggilan pertama, gap waktu, dan interval normal. Tambahkan regression test kecil berbasis `unittest` jika mengubah logika nontrivial.

## Review manual

- Perubahan sensor: cocokkan nama kolom MySQL dan key payload.
- Perubahan logger: pastikan jumlah kolom INSERT sama dengan placeholder dan nilai.
- Perubahan HMI: periksa endpoint real-time, histori, ekspor CSV, dan satuan yang ditampilkan.
- Perubahan estimator: periksa shape 1.440 menit, timezone WIB, pemilihan model hari, dan upsert timestamp.
- Perubahan watchdog: hindari restart loop saat startup atau maintenance sumber eksternal.

## Dokumentasi

Semua filename Markdown di `docs/` harus lowercase. Gunakan bahasa Indonesia yang langsung, definisikan istilah domain saat pertama dipakai, dan jangan menyatakan build/runtime berhasil jika hanya syntax/config yang diverifikasi.

Setiap perubahan kode wajib disertai pembaruan pada README atau dokumen di `docs/` yang menjelaskan perilaku, konfigurasi, kontrak data, atau prosedur operasi yang ikut berubah. Jika perubahan tidak memengaruhi dokumentasi, nyatakan alasannya pada ringkasan perubahan.
