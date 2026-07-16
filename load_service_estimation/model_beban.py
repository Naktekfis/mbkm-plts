from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.models import load_model

from query import get_query


def _read_column(data, loc):
    read = data.iloc[:, loc]
    read = read.values.tolist()
    return np.array(read).reshape(-1, 1)


def _prepare_minute_input(todays, yesterday):
    df = get_query()
    format_str = "%Y-%m-%d %H:%M"
    date_list = []
    for k in range(len(df)):
        dt = df["timestamp"][k]
        date_list.append(dt.strftime(format_str))

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
    time_array = list(zip(
        [value.month for value in date_format],
        [value.day for value in date_format],
        [value.hour for value in date_format],
        [value.minute for value in date_format],
    ))
    df_time = pd.DataFrame(time_array, columns=["month", "day", "hour", "minute"])
    return pd.concat([df_time, df], axis=1)[0:1440]


def _power_series(minute_input):
    return 3 * minute_input["A"] * minute_input["PF"] * minute_input["VLN"]


def _legacy_moving_average(power):
    array_power_day1 = np.array(power)
    avg_power_day1 = []
    for j in range(len(array_power_day1) - 59):
        mean_value = sum(array_power_day1[j:60 + j]) / 60
        avg_power_day1.append(mean_value)

    df_avgpower_day1 = pd.DataFrame(avg_power_day1)
    df_avgleft = power[1381:]
    df_avgleft_array = np.array(df_avgleft)
    avg_list = []
    for j in range(len(df_avgleft_array)):
        if j == 59:
            mean_value = sum(df_avgleft_array[j:]) / 1
        else:
            mean_value = sum(df_avgleft_array[j:]) / (59 - j)
        avg_list.append(mean_value)

    df_meanleft = pd.DataFrame(avg_list)
    return pd.concat([df_avgpower_day1, df_meanleft], ignore_index=True)


def _assemble_model_features(minute_input, power, moving_average):
    all_data = pd.concat(
        [minute_input, power, moving_average], axis=1, ignore_index=True
    )
    load_data = _read_column(all_data, 10)
    day_data = _read_column(all_data, 1)
    month_data = _read_column(all_data, 0)
    hour_data = _read_column(all_data, 2)
    minute_data = _read_column(all_data, 3)
    divider = len(load_data) / 1440

    sc_load = StandardScaler()
    sc_day = StandardScaler()
    sc_month = StandardScaler()
    sc_hour = StandardScaler()
    sc_minute = StandardScaler()

    load_scale = sc_load.fit_transform(load_data)
    day_scale = sc_day.fit_transform(day_data)
    month_scale = sc_month.fit_transform(month_data)
    hour_scale = sc_hour.fit_transform(hour_data)
    minute_scale = sc_minute.fit_transform(minute_data)

    splitted_feature = np.array_split(load_scale, divider)
    splitted_feature2 = np.array_split(day_scale, divider)
    splitted_feature4 = np.array_split(month_scale, divider)
    splitted_feature6 = np.array_split(hour_scale, divider)
    splitted_feature8 = np.array_split(minute_scale, divider)

    joined_feature = []
    for i in range(int(divider)):
        features = np.concatenate((
            splitted_feature[i], splitted_feature2[i],
            splitted_feature4[i], splitted_feature6[i],
            splitted_feature8[i],
        ), axis=1)
        joined_feature.append(features)

    data_test = np.array([feature.tolist() for feature in joined_feature])
    return data_test, sc_load


def _predict(model, data_test, load_scaler):
    predict = model.predict(data_test)
    predict = load_scaler.inverse_transform(predict[0])
    if len(predict) != 1440:
        raise ValueError(f"Output model load harus 1440 titik, diterima {len(predict)}")
    return predict


def _output_frame(predict, todays):
    timestamps = pd.date_range(
        start=todays, periods=1440, freq="min", tz="Asia/Jakarta"
    )
    result = pd.DataFrame(predict, index=timestamps)
    result.reset_index(inplace=True)
    result.columns = ["timestamp", "daya"]
    result = result.replace(np.nan, 0)
    result.loc[result["daya"] < 0, "daya"] = 0
    return result


def get_data():
    """Hitung estimasi dengan tanggal aktual pada waktu pemanggilan."""
    todays = datetime.now().date()
    yesterday = todays - timedelta(days=1)

    print(f"[get_data] Dipanggil pada: {datetime.now()}")
    print(f"[get_data] todays   : {todays}")
    print(f"[get_data] yesterday: {yesterday}")

    today = pd.to_datetime(todays).day_name()
    print(f"[get_data] Hari     : {today}")

    model = load_model("/app/model_bebanv2/model/modelbeban_{}".format(today))
    minute_input = _prepare_minute_input(todays, yesterday)
    power = _power_series(minute_input)
    moving_average = _legacy_moving_average(power)
    data_test, load_scaler = _assemble_model_features(
        minute_input, power, moving_average
    )
    predict = _predict(model, data_test, load_scaler)
    result = _output_frame(predict, todays)

    print(
        f"[get_data] Output {len(result)} baris, "
        f"{result['timestamp'].iloc[0]} s/d {result['timestamp'].iloc[-1]}"
    )
    return result
