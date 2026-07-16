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
        host=os.environ.get("MYSQL_WEATHER_HOST", "192.168.1.147"),
        port=int(os.environ.get("MYSQL_WEATHER_PORT", 3306)),
        user=os.environ.get("MYSQL_WEATHER_USER", "mahasiswa"),
        password=os.environ.get("MYSQL_WEATHER_PASS", "change-me"),
        database="smartgrid_cas",
        connection_timeout=5,
    )

    query = """
        SELECT 
            timestamp as stationDateTime,
            Irradiance as solarRad,
            Temperature as outsideTemp,
            WindSpeed as windSpeed
        FROM weather
        WHERE timestamp >= %s AND timestamp < %s
        AND Temperature > 0
        ORDER BY timestamp ASC
    """

    df = pd.read_sql(query, conn, params=(str(yesterday), str(todays)))
    conn.close()

    df["stationDateTime"] = pd.to_datetime(df["stationDateTime"])
    df["stationDateTime"] = df["stationDateTime"].dt.floor("min")
    df = df.groupby("stationDateTime", as_index=False).mean(numeric_only=True)
    covered_hours = df["stationDateTime"].dt.floor("h").nunique()
    if covered_hours < 18:
        raise ValueError(f"Cakupan data cuaca hanya {covered_hours} jam (minimum 18)")
    coverage_hours = (df["stationDateTime"].max() - df["stationDateTime"].min()).total_seconds() / 3600
    if coverage_hours < 20:
        raise ValueError(f"Cakupan data cuaca hanya {coverage_hours:.1f} jam")
    max_gap_hours = df["stationDateTime"].sort_values().diff().dt.total_seconds().max() / 3600
    if max_gap_hours > 3:
        raise ValueError(f"Gap data cuaca terlalu besar: {max_gap_hours:.1f} jam")
    df["stationDateTime"] = df["stationDateTime"].dt.tz_localize("Asia/Jakarta")
    df["solarRad"]    = df["solarRad"].clip(lower=0, upper=1400).fillna(0)
    df["outsideTemp"] = df["outsideTemp"].fillna(df["outsideTemp"].mean())
    df["windSpeed"]   = df["windSpeed"].clip(lower=0).fillna(0)

    print(f"[WeatherDB] Data ditemukan   : {len(df)} baris")
    print(df[["stationDateTime","solarRad","outsideTemp","windSpeed"]].to_string())
    return df
