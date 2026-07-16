import pandas as pd
import mysql.connector
import os
from datetime import datetime, timedelta

def get_query():
    todays    = datetime.now().date()
    yesterday = todays - timedelta(days=1)
    print(f"[WeatherDB] Tanggal aktual   : {todays}")
    print(f"[WeatherDB] Ambil data untuk : {yesterday}")

    conn = mysql.connector.connect(
        host="192.168.1.147",
        user="mahasiswa",
        password=os.environ.get("MYSQL_WEATHER_PASS", "change-me"),
        database="smartgrid_cas"
    )

    query = f"""
        SELECT 
            timestamp as stationDateTime,
            Irradiance as solarRad,
            Temperature as outsideTemp,
            WindSpeed as windSpeed
        FROM weather
        WHERE DATE(timestamp) = "{yesterday}"
        AND Temperature > 0
        ORDER BY timestamp ASC
    """

    df = pd.read_sql(query, conn)
    conn.close()

    df["stationDateTime"] = pd.to_datetime(df["stationDateTime"])
    df["stationDateTime"] = df["stationDateTime"].dt.tz_localize("Asia/Jakarta")
    df["solarRad"]    = df["solarRad"].clip(lower=0, upper=1400).fillna(0)
    df["outsideTemp"] = df["outsideTemp"].fillna(df["outsideTemp"].mean())
    df["windSpeed"]   = df["windSpeed"].clip(lower=0).fillna(0)

    print(f"[WeatherDB] Data ditemukan   : {len(df)} baris")
    print(df[["stationDateTime","solarRad","outsideTemp","windSpeed"]].to_string())
    return df
