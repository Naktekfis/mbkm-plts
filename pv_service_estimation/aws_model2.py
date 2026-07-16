from sklearn.preprocessing import StandardScaler
import pandas as pd
from datetime import timedelta, datetime
import numpy as np
import matplotlib.pyplot as plt
from tensorflow.keras.models import load_model
import tensorflow as tf
from pvlib_model import pvlib_instantiate
from query import get_query

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
    with tf.device('/cpu:0'):

        # ── Tanggal dikalkulasi di dalam fungsi ──
        todays    = datetime.now().date()
        yesterday = todays - timedelta(days=1)

        print(f"[get_data] Dipanggil pada: {datetime.now()}")
        print(f"[get_data] todays   : {todays}")
        print(f"[get_data] yesterday: {yesterday}")

        # costheta lookup untuk hari ini
        df_costheta  = pd.read_csv("/app/costheta.csv")
        day_lookup   = todays.day
        month_lookup = todays.month
        costheta     = df_costheta.query("dm == @day_lookup and m == @month_lookup")

        # Range waktu kemarin untuk query cuaca
        range_date1 = '{} 00:00:00'.format(yesterday)
        range_date2 = '{} 23:59:00'.format(yesterday)

        hour   = []
        minute = []
        month  = []
        day    = []

        result_dataFrame = get_query()
        print(result_dataFrame)

        for k in range(len(result_dataFrame)):
            month.append(result_dataFrame["stationDateTime"][k].month)
            day.append(result_dataFrame["stationDateTime"][k].day)
            hour.append(result_dataFrame["stationDateTime"][k].hour)
            minute.append(result_dataFrame["stationDateTime"][k].minute)

        df_month = pd.DataFrame(month);   df_month.columns = ["month"]
        df_day   = pd.DataFrame(day);     df_day.columns   = ["day"]
        df_hour  = pd.DataFrame(hour);    df_hour.columns  = ["hour"]
        df_minute= pd.DataFrame(minute);  df_minute.columns= ["minute"]

        Time = pd.date_range(start=range_date1, end=range_date2, freq='min')
        df_aws = pd.concat(
            [df_month, df_day, df_hour, df_minute, result_dataFrame], axis=1
        )
        df_aws.set_index("stationDateTime", inplace=True)
        df_aws.index.name = None
        df_aws = df_aws[10:]
        df_aws = df_aws[~df_aws.index.duplicated()]
        df_aws = df_aws.reindex(Time)

        Time_tz = pd.date_range(
            start=range_date1, end=range_date2,
            freq='min', tz="Asia/Jakarta"
        )
        df_aws = df_aws.set_index(Time_tz).asfreq('min')
        df_aws = df_aws.interpolate()
        df_aws = df_aws.fillna(0)

        Time_df = pd.DataFrame(Time_tz, index=None)
        Time_df.columns = ["Time"]

        # Baca variabel input
        month_arr  = read_data(df_aws, 0)
        day_arr    = read_data(df_aws, 1)
        hour_arr   = read_data(df_aws, 2)
        minute_arr = read_data(df_aws, 3)
        ghi        = read_data(df_aws, 6)

        # ── Model DNI (pv_dnn) ──
        model_dnn = load_model("/app/pv_dnn")

        ghi_array    = np.array(ghi)
        month_array  = np.array(month_arr)
        day_array    = np.array(day_arr)
        hour_array   = np.array(hour_arr)
        minute_array = np.array(minute_arr)

        joined_feature = list()
        features = np.concatenate(
            (ghi_array, month_array, day_array, hour_array, minute_array), axis=1
        )
        joined_feature.append(features)
        data_test = [l.tolist() for l in joined_feature]
        data_test = np.array(data_test)

        # ── Model koreksi (pv_model) ──
        model = load_model("/app/pv_model")
        predict_test  = model.predict(data_test)

        predict_array = []
        for o in range(len(data_test)):
            predict_array.append(predict_test[o])
        predict_array = np.array(predict_array).flatten()

        # Hitung DHI
        thetaArray = np.array(costheta["cos theta"])
        ghiArray   = np.array(df_aws["solarRad"])
        list_dhi   = []
        for t in range(len(ghiArray)):
            dhi = ghiArray[t] - (predict_array[t] * thetaArray[t])
            list_dhi.append(dhi)
        dhiPred = np.array(list_dhi)

        ghi_array_flat      = np.array(df_aws["solarRad"])
        dni_array_flat      = predict_array
        dhi_array_flat      = dhiPred
        temp_array_flat     = np.array(df_aws["outsideTemp"])
        windspeed_array_flat= np.array(df_aws["windSpeed"])

        # ── pvlib — simulasi fisika panel surya ──
        pv_output = pvlib_instantiate(
            temp_array_flat, ghi_array_flat, dni_array_flat,
            dhi_array_flat, windspeed_array_flat, Time_df
        )

        # ── DNN koreksi output pvlib ──
        px = []
        for k in range(len(pv_output)):
            px.append(pv_output["Pac"][k])
        px = np.array(px).reshape(-1, 1)

        sc_px     = StandardScaler()
        sc_month  = StandardScaler()
        sc_day    = StandardScaler()
        sc_hour   = StandardScaler()
        sc_minute = StandardScaler()

        sc_px.fit_transform(px)
        sc_month.fit_transform(month_arr)
        sc_day.fit_transform(day_arr)
        sc_hour.fit_transform(hour_arr)
        sc_minute.fit_transform(minute_arr)

        features_dnn = np.concatenate(
            (px, month_arr, day_arr, hour_arr, minute_arr), axis=1
        )
        data_input = [features_dnn.tolist()]
        data_input = np.array(data_input)
        data_input = np.nan_to_num(data_input, 0)

        predict_dnn   = model_dnn.predict(data_input)
        output_dnn    = predict_dnn.flatten()

        df_dnn = pd.DataFrame(output_dnn, columns=["Pac"])
        pv_output.drop(columns=["Pac"], inplace=True)
        pv_output = pd.concat([pv_output, df_dnn], axis=1)

        # ── Reindexing ke hari ini (todays) ──
        range_today1 = '{} 00:00:00'.format(todays)
        range_today2 = '{} 23:59:00'.format(todays)
        Time_today   = pd.date_range(
            start=range_today1, end=range_today2,
            freq='min', tz="Asia/Jakarta"
        )

        pac_values = pv_output["Pac"].values
        min_len    = min(len(pac_values), len(Time_today))

        df_result = pd.DataFrame({
            "Time": Time_today[:min_len],
            "Pac":  pac_values[:min_len]
        })
        df_result["Pac"] = df_result["Pac"].fillna(0)
        df_result.loc[df_result["Pac"] < 0, "Pac"] = 0

        print(df_result)
        return df_result