import pandas as pd
from datetime import timedelta, datetime
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model
from pvlib_model import pvlib_instantiate
from query_openmeteo import get_query

def read_data(data, loc):
    read = data.iloc[:, loc]
    read = read.values.tolist()
    read = np.array(read).reshape(-1, 1)
    return read

def get_data():
    with tf.device('/cpu:0'):

        todays    = datetime.now().date()
        yesterday = todays - timedelta(days=1)

        print(f"[get_data] Dipanggil pada: {datetime.now()}")
        print(f"[get_data] todays        : {todays}")
        print(f"[get_data] yesterday     : {yesterday}")

        # ── Ambil data cuaca dari Open-Meteo (24 titik per jam) ──
        df_weather = get_query()

        # ── Interpolasi 24 jam → 1440 menit untuk input model ──
        range_date1 = f'{yesterday} 00:00:00'
        range_date2 = f'{yesterday} 23:59:00'
        Time_minutely = pd.date_range(
            start=range_date1, end=range_date2,
            freq='min', tz="Asia/Jakarta"
        )

        df_weather = df_weather.set_index("stationDateTime").sort_index()
        df_weather = df_weather.reindex(Time_minutely)
        df_weather = df_weather.interpolate(method='time').ffill().bfill()
        if df_weather[["solarRad", "outsideTemp", "windSpeed"]].isna().any().any():
            raise ValueError("Data cuaca masih memiliki nilai kosong setelah interpolasi")

        # Fitur waktu (1440 titik)
        month_arr  = np.array(Time_minutely.month).reshape(-1, 1)
        day_arr    = np.array(Time_minutely.day).reshape(-1, 1)
        hour_arr   = np.array(Time_minutely.hour).reshape(-1, 1)
        minute_arr = np.array(Time_minutely.minute).reshape(-1, 1)

        # Variabel cuaca (1440 titik)
        ghi             = np.array(df_weather["solarRad"]).reshape(-1, 1)
        temp_array_flat = np.array(df_weather["outsideTemp"])
        windspeed_flat  = np.array(df_weather["windSpeed"])
        ghi_array_flat  = np.array(df_weather["solarRad"])

        # ── Model DNI (pv_model) ──
        model = load_model("/app/pv_model")
        features  = np.concatenate((ghi, month_arr, day_arr, hour_arr, minute_arr), axis=1)
        data_test = np.array([features.tolist()])
        predict_test  = model.predict(data_test)
        predict_array = np.array(predict_test).flatten()

        # Hitung DNI dan DHI
        dni_array_flat = predict_array
        dhi_array_flat = np.maximum(ghi_array_flat - dni_array_flat, 0)

        # ── pvlib simulasi fisika panel surya ──
        Time_df   = pd.DataFrame(Time_minutely, columns=["Time"])
        pv_output = pvlib_instantiate(
            temp_array_flat, ghi_array_flat, dni_array_flat,
            dhi_array_flat, windspeed_flat, Time_df
        )

        # ── DNN koreksi output pvlib (pv_dnn) ──
        model_dnn = load_model("/app/pv_dnn")
        px = np.array([pv_output["Pac"][k] for k in range(len(pv_output))]).reshape(-1, 1)

        features_dnn = np.concatenate((px, month_arr, day_arr, hour_arr, minute_arr), axis=1)
        data_input   = np.nan_to_num(np.array([features_dnn.tolist()]), 0)

        predict_dnn = model_dnn.predict(data_input)
        output_dnn  = predict_dnn.flatten()

        df_dnn = pd.DataFrame(output_dnn, columns=["Pac"])
        pv_output.drop(columns=["Pac"], inplace=True)
        pv_output = pd.concat([pv_output, df_dnn], axis=1)

        # ── Resample output Pac ke per jam ──
        range_today1 = f'{todays} 00:00:00'
        range_today2 = f'{todays} 23:00:00'
        Time_today_hourly = pd.date_range(
            start=range_today1, end=range_today2,
            freq='h', tz="Asia/Jakarta"
        )

        # pv_output 1440 titik → ambil menit ke-0 tiap jam
        pac_values = pv_output["Pac"].values
        pac_hourly = pac_values[::60][:24]

        min_len = min(len(pac_hourly), len(Time_today_hourly))
        df_result = pd.DataFrame({
            "Time": Time_today_hourly[:min_len],
            "Pac":  pac_hourly[:min_len]
        })
        df_result["Pac"] = df_result["Pac"].fillna(0)
        df_result.loc[df_result["Pac"] < 0, "Pac"] = 0

        print(f"[get_data] Output {len(df_result)} baris per jam:")
        print(df_result.to_string())
        return df_result
