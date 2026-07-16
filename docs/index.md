# Dokumentasi Microgrid PLTS

Dokumentasi ini menjelaskan cara bagian-bagian repo bekerja sebagai satu sistem. Mulai dari [arsitektur](architecture.md) jika ingin memahami gambaran besar, atau langsung ke [panduan menjalankan](getting-started.md) jika ingin menyalakan stack.

## Peta dokumentasi

| Halaman | Isi |
|---|---|
| [Arsitektur](architecture.md) | Komponen, alur utama, dan alasan pemisahan service |
| [Menjalankan sistem](getting-started.md) | Prasyarat, konfigurasi, startup, dan pemeriksaan awal |
| [Service](services.md) | Tanggung jawab dan alur kode setiap service aktif |
| [Kontrak data](data-contracts.md) | Topic MQTT, payload, tabel PostgreSQL, dan satuan |
| [Model estimasi](estimation-models.md) | Pipeline PV/load, model TensorFlow, dan kode legacy |
| [Operasi](operations.md) | Monitoring, troubleshooting, keterbatasan, dan reset |

## Ringkasan satu menit

Sistem mengambil telemetri PLTS, baterai, grid, dan beban dari MySQL laboratorium. `service_sensor` menyatukannya menjadi satu payload MQTT. Service lain menghitung ekonomi dan keputusan operasi, sedangkan `service_logger` menyimpan semua hasil ke PostgreSQL. HMI Flask membaca PostgreSQL dan menampilkannya di browser.

Dua estimator berjalan harian. Estimator PV menggabungkan data cuaca, simulasi `pvlib`, dan model DNN. Estimator beban memilih model DNN sesuai hari dalam minggu. Seluruh komponen lokal diorkestrasi oleh `docker-compose.yml`.

> [!IMPORTANT]
> Stack lokal sudah memiliki satu broker MQTT dan satu PostgreSQL, tetapi data sumber tetap bergantung pada MySQL laboratorium yang berada di luar Compose. Tanpa akses jaringan dan kredensial yang benar, container dapat hidup tetapi dashboard tidak memperoleh data aktual.

## Istilah singkat

| Istilah | Arti di repo ini |
|---|---|
| PLTS/PV | Sistem pembangkit listrik tenaga surya |
| BESS | Penyimpanan energi baterai |
| HMI | Dashboard web untuk operator |
| EMS/DSS | Aturan pengambilan keputusan operasi microgrid |
| SoC | Persentase muatan baterai |
| EBT | Energi baru terbarukan |
| RF | Renewable fraction, persentase beban yang ditopang EBT |
| ESSA | Perkiraan lama baterai menopang beban |
| LCOE | Perkiraan biaya energi sepanjang umur sistem |
