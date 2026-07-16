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


def _prepare_minutely_weather(df_weather, yesterday):
    time_minutely = pd.date_range(
        start=f'{yesterday} 00:00:00',
        end=f'{yesterday} 23:59:00',
        freq='min',
        tz="Asia/Jakarta",
    )
    df_weather = df_weather.set_index("stationDateTime").sort_index()
    df_weather = df_weather.reindex(time_minutely)
    df_weather = df_weather.interpolate(method='time').ffill().bfill()
    if df_weather[["solarRad", "outsideTemp", "windSpeed"]].isna().any().any():
        raise ValueError("Data cuaca masih memiliki nilai kosong setelah interpolasi")
    return time_minutely, df_weather


def _time_features(time_minutely):
    return tuple(
        np.array(values).reshape(-1, 1)
        for values in (
            time_minutely.month,
            time_minutely.day,
            time_minutely.hour,
            time_minutely.minute,
        )
    )


def _predict_dni(ghi, time_features):
    model = load_model("/app/pv_model")
    features = np.concatenate((ghi,) + time_features, axis=1)
    data_test = np.array([features.tolist()])
    return np.array(model.predict(data_test)).flatten()


def _run_pvlib(df_weather, time_minutely, dni_array_flat):
    temp_array_flat = np.array(df_weather["outsideTemp"])
    ghi_array_flat = np.array(df_weather["solarRad"])
    windspeed_flat = np.array(df_weather["windSpeed"])
    dhi_array_flat = np.maximum(ghi_array_flat - dni_array_flat, 0)
    time_df = pd.DataFrame(time_minutely, columns=["Time"])
    return pvlib_instantiate(
        temp_array_flat,
        ghi_array_flat,
        dni_array_flat,
        dhi_array_flat,
        windspeed_flat,
        time_df,
    )


def _correct_pvlib_output(pv_output, time_features):
    model_dnn = load_model("/app/pv_dnn")
    px = np.array([pv_output["Pac"][k] for k in range(len(pv_output))]).reshape(-1, 1)
    features_dnn = np.concatenate((px,) + time_features, axis=1)
    data_input = np.nan_to_num(np.array([features_dnn.tolist()]), 0)
    output_dnn = model_dnn.predict(data_input).flatten()

    df_dnn = pd.DataFrame(output_dnn, columns=["Pac"])
    pv_output.drop(columns=["Pac"], inplace=True)
    return pd.concat([pv_output, df_dnn], axis=1)


def _hourly_today(pv_output, todays):
    time_today_hourly = pd.date_range(
        start=f'{todays} 00:00:00',
        end=f'{todays} 23:00:00',
        freq='h',
        tz="Asia/Jakarta",
    )
    pac_hourly = pv_output["Pac"].values[::60][:24]
    min_len = min(len(pac_hourly), len(time_today_hourly))
    df_result = pd.DataFrame({
        "Time": time_today_hourly[:min_len],
        "Pac": pac_hourly[:min_len],
    })
    df_result["Pac"] = df_result["Pac"].fillna(0)
    df_result.loc[df_result["Pac"] < 0, "Pac"] = 0
    return df_result


def get_data():
    with tf.device('/cpu:0'):
        todays = datetime.now().date()
        yesterday = todays - timedelta(days=1)

        print(f"[get_data] Dipanggil pada: {datetime.now()}")
        print(f"[get_data] todays        : {todays}")
        print(f"[get_data] yesterday     : {yesterday}")

        # Profil cuaca kemarin digunakan untuk estimasi hari ini.
        df_weather = get_query()
        time_minutely, df_weather = _prepare_minutely_weather(df_weather, yesterday)
        time_features = _time_features(time_minutely)
        ghi = np.array(df_weather["solarRad"]).reshape(-1, 1)
        dni_array_flat = _predict_dni(ghi, time_features)
        pv_output = _run_pvlib(df_weather, time_minutely, dni_array_flat)
        pv_output = _correct_pvlib_output(pv_output, time_features)
        df_result = _hourly_today(pv_output, todays)

        print(f"[get_data] Output {len(df_result)} baris per jam:")
        print(df_result.to_string())
        return df_result
