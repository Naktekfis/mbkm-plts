# Base image: TensorFlow 2.7.0 dengan Python 3.8
# Wajib menggunakan versi ini karena model pv_dnn dan pv_model
# disimpan dengan TF 2.7.0 dan tidak kompatibel dengan versi lebih baru
FROM tensorflow/tensorflow:2.7.0

# Set working directory
WORKDIR /app

# Copy requirements terlebih dahulu (agar Docker cache layer ini)
COPY requirements.txt .

# Install semua dependencies Python
RUN pip install --no-cache-dir -r requirements.txt

# Copy semua file service
COPY aws_model2_openmeteo.py .
COPY pvlib_model.py .
COPY query_openmeteo.py .
COPY main.py .
COPY costheta.csv .
COPY service_estimation.py .

# Copy folder model TensorFlow
COPY pv_dnn/ ./pv_dnn/
COPY pv_model/ ./pv_model/

# Jalankan service
CMD ["python3", "service_estimation.py"]
