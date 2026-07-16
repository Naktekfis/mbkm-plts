# 1. Gunakan sistem operasi Linux dasar yang sudah ada Python 3.10
FROM python:3.10-slim

# 2. Tentukan folder kerja di dalam container
WORKDIR /app

# 2.5. Buat direktori untuk database
RUN mkdir -p /data

# 3. Salin file requirements.txt ke dalam container
COPY requirements.txt .

# 4. Install semua library yang dibutuhkan
RUN pip install --no-cache-dir -r requirements.txt

# 5. Salin script python Anda ke dalam container
COPY monitor.py .

# 6. Perintah yang dijalankan saat container menyala
CMD ["python", "monitor.py"]