# Model Estimasi

Kedua estimator memakai TensorFlow 2.7.0 karena SavedModel dibuat dengan versi tersebut. Dockerfile sengaja memakai `tensorflow/tensorflow:2.7.0`; upgrade TensorFlow perlu pengujian atau ekspor ulang model.

## Estimasi PV

Jalur runtime:

```text
service_estimation.py
  -> main.py
  -> aws_model2_openmeteo.py
  -> query_openmeteo.py
  -> pvlib_model.py
  -> pv_model/ dan pv_dnn/
```

Alurnya:

1. `query_openmeteo.get_query()` mengambil data cuaca kemarin dari tabel `smartgrid_cas.weather`.
2. Timestamp dinormalisasi per menit; data harus mencakup minimal 18 jam unik, rentang 20 jam, dan tidak memiliki gap di atas 3 jam.
3. Model `pv_model/` memprediksi DNI dari GHI dan fitur waktu.
4. `pvlib_model.pvlib_instantiate()` mensimulasikan sistem PV fisik di Bandung.
5. Model `pv_dnn/` mengoreksi keluaran AC dari `pvlib`.
6. Output diambil menjadi 24 titik per jam untuk hari ini.
7. `main.run()` memvalidasi 24 output lalu melakukan satu batch upsert ke `pv_estimasi`.

Tahap interpolasi cuaca, pembentukan fitur waktu, prediksi DNI, simulasi `pvlib`, koreksi DNN, dan pembentukan output per jam dipisahkan sebagai helper internal agar kontrak numeriknya dapat diuji tanpa memuat model TensorFlow.

Model dan parameter fisik berada langsung di repo. Lokasi simulasi adalah sekitar Bandung (`-6.89`, `107.61`, 770 m), panel menghadap timur dengan tilt 2 derajat, 16 modul per string, dan 2 string.

## Estimasi load

Jalur runtime:

```text
service_estimation_load.py
  -> main.py
  -> model_beban.py
  -> query.py
  -> model_bebanv2/model/modelbeban_<Day>/
```

Alurnya:

1. `query.get_query()` mengambil beban meter 6 untuk hari kemarin dan mengagregasi data per menit.
2. Input harus memiliki minimal 1.200 menit, rentang 22 jam, dan gap maksimum 15 menit sebelum direindex dan diinterpolasi.
3. Daya dihitung sebagai `3 * A * PF * VLN`.
4. Kode membentuk moving average dan fitur bulan, tanggal, jam, serta menit.
5. Model dipilih berdasarkan nama hari ini, misalnya `modelbeban_Monday`.
6. Prediksi 1.440 menit dari 00:00 sampai 23:59 divalidasi lalu di-upsert dalam satu batch.

Penyiapan input per menit, perhitungan daya, moving average, penyusunan fitur, prediksi, dan pembentukan output dipisahkan sebagai helper internal agar preprocessing dapat diuji tanpa memuat SavedModel TensorFlow.

Folder `model_bebanv2/training/` berisi CSV training per hari. Runtime tidak melakukan training ulang.

Uji unit helper estimator memakai fake dan mock terkontrol. Hasilnya tidak membuktikan kompatibilitas runtime dengan SavedModel TensorFlow atau instalasi `pvlib` yang sebenarnya.

## Jadwal

| Service | Saat container start | Jadwal berikutnya |
|---|---|---|
| PV | Langsung menjalankan satu job | Setiap hari 00:05 WIB |
| Load | Langsung menjalankan satu job | Setiap hari 00:10 WIB |

Exception job dicatat dan dicoba ulang setiap sepuluh menit sampai target hari berhasil. Status container `running` tetap belum membuktikan prediksi berhasil; periksa log dan tabel estimasi.

Cuaca kemarin dipakai sebagai profil untuk estimasi hari ini. Ini adalah asumsi persistence forecast pada model saat ini, bukan prakiraan cuaca masa depan.

## Kode non-runtime

File berikut tidak dipanggil oleh Dockerfile/entry point aktif:

- `pv_service_estimation/aws_model.py`: pipeline PV lama dengan path host-spesifik.
- `pv_service_estimation/aws_model2.py` dan `query.py`: alternatif sebelum jalur cuaca aktif.
- `pv_service_estimation/PVDNN.py`: skrip training/eksperimen.
- `pv_service_estimation/pvlib_dnn.py`: eksperimen yang belum lengkap.
- `pv_service_estimation/time_pv.py` dan `load_service_estimation/time_load.py`: benchmark.
- `pv_service_estimation/pv_hourly.py` dan `fixpac.py`: maintenance database lama.
- `load_service_estimation/delete.py`: maintenance destruktif.

Jangan memasukkan file tersebut ke jalur runtime tanpa memastikan path, schema, kredensial, dan asumsi modelnya masih valid.
