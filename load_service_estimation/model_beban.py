from sklearn.preprocessing import StandardScaler
import time
import pandas as pd
from datetime import timedelta, datetime
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model
import math
from query import get_query, get_date


def read_data(data, loc):
    read = data.iloc[:, loc]
    read = read.values.tolist()
    read = np.array(read).reshape(-1, 1)
    return read


def get_data():
    """
    Semua kalkulasi tanggal di dalam fungsi agar
    selalu menggunakan tanggal aktual saat dipanggil
    """
    # ── Tanggal dikalkulasi di dalam fungsi ──
    todays    = datetime.now().date()
    yesterday = todays - timedelta(days=1)
    tomorrow  = todays + timedelta(days=1)

    print(f"[get_data] Dipanggil pada: {datetime.now()}")
    print(f"[get_data] todays   : {todays}")
    print(f"[get_data] yesterday: {yesterday}")

    today = pd.to_datetime(todays).day_name()
    print(f"[get_data] Hari     : {today}")

    # Load model sesuai hari ini
    model = load_model('/app/model_bebanv2/model/modelbeban_{}'.format(today))

    result_dataFrame = get_query()
    df = result_dataFrame
    format_str = "%Y-%m-%d %H:%M"
    date_list = []
    for k in range(len(df)):
        dt = df["timestamp"][k]
        date_formatted = dt.strftime(format_str)
        date_list.append(date_formatted)

    df_date = pd.DataFrame(date_list)
    df_date.columns = ["timestamp"]
    df.drop(columns=["timestamp"], inplace=True)
    df = pd.concat([df_date, df], axis=1)
    df.set_index("timestamp", inplace=True)

    df_index = pd.date_range(
        start=yesterday, end=todays, freq="min"
    ).strftime("%Y-%m-%d %H:%M")
    df = df.reindex(df_index)
    df = df.interpolate().ffill().bfill()
    df = df.reset_index()

    if df[["A", "VLN", "PF"]].isna().any().any():
        raise ValueError("Data beban masih memiliki nilai kosong setelah interpolasi")

    date_format = pd.to_datetime(df["index"])

    month_list  = []
    day_list    = []
    hour_list   = []
    minute_list = []

    for k in range(len(date_format)):
        month_list.append(date_format[k].month)
        day_list.append(date_format[k].day)
        hour_list.append(date_format[k].hour)
        minute_list.append(date_format[k].minute)

    time_array = list(zip(month_list, day_list, hour_list, minute_list))
    df_time    = pd.DataFrame(time_array, columns=["month", "day", "hour", "minute"])
    df_final   = pd.concat([df_time, df], axis=1)
    df_final   = df_final[0:1440]

    # Moving average 60 menit
    df_power_day1   = 3 * df_final['A'] * df_final['PF'] * df_final['VLN']
    array_power_day1 = np.array(df_power_day1)
    avg_power_day1  = []
    for j in range(len(array_power_day1) - 59):
        mean_value = sum(array_power_day1[j:60 + j]) / 60
        avg_power_day1.append(mean_value)

    df_avgpower_day1 = pd.DataFrame(avg_power_day1)
    df_avgleft       = df_power_day1[1381:]
    df_avgleft_array = np.array(df_avgleft)
    avg_list = []
    for j in range(len(df_avgleft_array)):
        if j == 59:
            mean_value = sum(df_avgleft_array[j:]) / 1
            avg_list.append(mean_value)
        else:
            mean_value = sum(df_avgleft_array[j:]) / (59 - j)
            avg_list.append(mean_value)

    df_meanleft       = pd.DataFrame(avg_list)
    df_totalmean_day1 = pd.concat([df_avgpower_day1, df_meanleft], ignore_index=True)
    df_final_clean    = pd.concat(
        [df_final, df_power_day1, df_totalmean_day1], axis=1, ignore_index=True
    )

    # Input untuk model
    all_data   = df_final_clean
    load_data  = read_data(all_data, 10)
    day_data   = read_data(all_data, 1)
    month_data = read_data(all_data, 0)
    hour_data  = read_data(all_data, 2)
    minute_data= read_data(all_data, 3)
    divider    = len(load_data) / 1440

    # Scaling
    sc_load   = StandardScaler()
    sc_day    = StandardScaler()
    sc_month  = StandardScaler()
    sc_hour   = StandardScaler()
    sc_minute = StandardScaler()

    load_scale   = sc_load.fit_transform(load_data)
    day_scale    = sc_day.fit_transform(day_data)
    month_scale  = sc_month.fit_transform(month_data)
    hour_scale   = sc_hour.fit_transform(hour_data)
    minute_scale = sc_minute.fit_transform(minute_data)

    splitted_feature  = np.array_split(load_scale,  divider)
    splitted_feature2 = np.array_split(day_scale,   divider)
    splitted_feature4 = np.array_split(month_scale, divider)
    splitted_feature6 = np.array_split(hour_scale,  divider)
    splitted_feature8 = np.array_split(minute_scale,divider)

    joined_feature = list()
    for i in range(int(divider)):
        features = np.concatenate((
            splitted_feature[i],  splitted_feature2[i],
            splitted_feature4[i], splitted_feature6[i],
            splitted_feature8[i]
        ), axis=1)
        joined_feature.append(features)

    data_test = [l.tolist() for l in joined_feature]
    data_test = np.array(data_test)

    # Prediksi
    predict = model.predict(data_test)
    predict = sc_load.inverse_transform(predict[0])
    if len(predict) != 1440:
        raise ValueError(f"Output model load harus 1440 titik, diterima {len(predict)}")

    # Output dengan timestamp hari ini
    Time = pd.date_range(start=todays, periods=1440, freq='min', tz="Asia/Jakarta")

    df_predict = pd.DataFrame(predict, index=Time)
    df_predict.reset_index(inplace=True)
    df_predict.columns = ["timestamp", "daya"]
    df_predict = df_predict.replace(np.nan, 0)
    df_predict.loc[df_predict["daya"] < 0, "daya"] = 0

    print(f"[get_data] Output {len(df_predict)} baris, {Time[0]} s/d {Time[-1]}")
    return df_predict
