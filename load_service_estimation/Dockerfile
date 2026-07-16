FROM tensorflow/tensorflow:2.7.0

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY query.py .
COPY model_beban.py .
COPY main.py .
COPY service_estimation_load.py .
COPY model_bebanv2/model/ ./model_bebanv2/model/

CMD ["python3", "service_estimation_load.py"]
