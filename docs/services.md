# Service

Halaman ini membahas kode yang benar-benar dipanggil oleh Compose. Skrip eksperimen dan maintenance dibahas terpisah di [model estimasi](estimation-models.md#kode-non-runtime).

## `service_sensor`

Entry point: `service_sensor/kirim.py`

Fungsi `ambil_data_terkini()` membuka koneksi MySQL, mengambil record terbaru, memvalidasi umur dan selisih timestamp sumber, lalu mengembalikan satu dictionary telemetri. Snapshot yang sama menghasilkan `telemetry_id` yang sama. Data kosong, stale, terlalu jauh selisih waktunya, atau berada di masa depan tidak dipublikasikan.

Perhitungan utama:

- Daya semu grid: `ExtVtg * ExtCur` dalam VA.
- Daya BESS DC: `BatVtg * TotBatCur` dalam W.
- Daya hybrid inverter: `TotInvPwrAt * 1000`, dari kW ke W.
- Daya beban tiga fasa: jumlah `V * A * PF` tiap fasa.

Konvensi `p_inverter`: positif berarti baterai menyuplai panel, negatif berarti charging.

## `service_logger`

Entry point: `service_logger/monitor.py`

`setup_database()` membuat tabel, kolom migrasi, unique index `telemetry_id`, dan index timestamp secara idempoten. Logger memakai QoS 1 dan insert `ON CONFLICT DO NOTHING` untuk menahan duplikasi delivery MQTT.

Kolom `timestamp` menyimpan `measured_at`, sedangkan `ingested_at` menyimpan waktu pesan diterima. Timestamp asli hybrid, PV, dan load juga disimpan terpisah.

## `service_billing`

Entry point: `service_billing/billing_engine.py`

`kalkulasi_ekonomi_mikrogrid()` menghitung:

- Energi beban dan EBT per interval.
- Penghematan terhadap tarif PLN Rp955/kWh.
- Renewable fraction.
- LCOE dinamis dari CAPEX, OPEX, suku bunga, dan umur proyek.
- ESSA dari kapasitas BESS 20.480 Wh, SoC, dan beban.
- Reduksi CO2 dengan faktor 0,87 kg/kWh.

Akumulator tampilan disimpan dalam proses dan reset saat restart. Metrik interval tetap disimpan sehingga ringkasan HMI tidak ikut reset. Interval non-monoton atau lebih dari lima menit tidak diakumulasikan.

## `service_control`

Entry point: `service_control/control_engine.py`

`evaluate_ems_rules()` adalah DSS rule-based dengan lima status:

| Kondisi ringkas | Status |
|---|---|
| PV surplus, SoC di bawah 98% | `CHARGING` |
| PV surplus, SoC minimal 98% | `OPTIMUM` |
| PV defisit, SoC di atas 20%, BESS discharge | `DISCHARGING` |
| PV defisit, SoC di atas 20%, BESS standby | `GRID SUPPORT` |
| PV defisit, SoC maksimal 20% | `GRID ONLY` |

Service ini menghasilkan rekomendasi/status. Ia tidak mengirim command ke inverter atau aktuator fisik.
`daya_pln_dihitung_watt` adalah sisa beban setelah PV dan discharge BESS, sehingga partial discharge tidak lagi membuat kontribusi PLN menjadi nol.

## `service_pemantauan`

Entry point: `service_pemantauan/validator.py`

Setiap 60 detik service membaca 25 baris sensor terakhir dan menjalankan:

- Validasi batas minimum/maksimum.
- Staleness lebih dari 120 detik.
- Nilai identik selama 20 pembacaan.
- Urutan timestamp.

SoC, tegangan DC, dan suhu DC dikecualikan dari frozen check. Nilai PV/hybrid nol pada malam hari juga dianggap normal.

## `service_hmi`

Entry point backend: `service_hmi_flask/app.py`

Frontend:

- `service_hmi_flask/templates/index.html`
- `service_hmi_flask/static/js/main.js`
- `service_hmi_flask/static/img/`

API utama:

| Method dan path | Fungsi |
|---|---|
| `GET /` | Halaman dashboard |
| `GET /api/data` | Snapshot sensor, billing, DSS, dan estimasi terbaru |
| `GET /api/sensor/history` | 60 record sensor terakhir |
| `GET /api/control/history` | 20 keputusan DSS terakhir |
| `GET /api/history` | Analisis berdasarkan rentang tanggal |
| `GET /api/history/export` | Ekspor CSV |
| `GET /api/system/services` | Status container melalui Docker API |
| `GET /api/system/validity` | Freshness dan alert kualitas data |
| `GET /health/ready` | Readiness HMI dan PostgreSQL |
| `POST /api/control` | Mengembalikan `501` karena aktuator belum tersedia |

HMI dijalankan oleh Gunicorn. Frontend melakukan polling data setiap 30 detik; status container tetap dipoll lewat endpoint terpisah.

## `service_watchdog`

Entry point: `service_watchdog/watchdog.py`

Setelah startup grace 180 detik, watchdog memeriksa freshness tabel setiap dua menit sebagai sinyal diagnostik. Data stale tidak memicu restart producer. HMI hanya di-restart jika `/health/ready` gagal, maksimal tiga kali dengan cooldown sepuluh menit.

Mount Docker socket memberi akses administratif ke Docker host. Jalankan hanya pada host tepercaya.

## Estimator

- `service_estimation_pv` menjalankan `pv_service_estimation/service_estimation.py` saat startup dan setiap hari pukul 00:05.
- `service_estimation_load` menjalankan `load_service_estimation/service_estimation_load.py` saat startup dan setiap hari pukul 00:10.

Job yang gagal dicoba ulang setiap sepuluh menit. Input harus memenuhi coverage minimum dan jumlah output diverifikasi sebelum batch disimpan.

Rincian pipeline ada di [model estimasi](estimation-models.md).
