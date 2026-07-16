import mysql.connector
from datetime import timedelta, datetime
import pandas as pd
import os


def get_date(delta):
    date = datetime.now().date()
    date = date + timedelta(days=delta)
    return date


def get_query():
    todays    = datetime.now().date()
    yesterday = todays - timedelta(days=1)

    today_str     = str(todays)
    yesterday_str = str(yesterday)

    print(f"Tanggal aktual   : {todays}")
    print(f"Query data beban : {yesterday_str} s/d {today_str}")

    # Koneksi ke MySQL Lab — database sielis
    mydb = mysql.connector.connect(
        host=os.environ.get("MYSQL_LOAD_HOST", "192.168.1.149"),
        port=int(os.environ.get("MYSQL_LOAD_PORT", 3306)),
        user=os.environ.get("MYSQL_LOAD_USER", "mahasiswa"),
        password=os.environ.get("MYSQL_LOAD_PASS", "change-me"),
        database="sielis",
        connection_timeout=5,
    )

    query = """
        SELECT MIN(timestamp) AS timestamp,
               meter_id,
               AVG(A) AS A,
               AVG(VLN) AS VLN,
               AVG(PF) AS PF
        FROM datapengukuran
        WHERE timestamp >= %s AND timestamp < %s
        AND meter_id = 6
        GROUP BY meter_id, DATE_FORMAT(timestamp, '%%Y-%%m-%%d %%H:%%i')
        ORDER BY timestamp ASC
    """

    print(query)
    result_dataFrame = pd.read_sql(query, mydb, params=(yesterday_str, today_str))
    mydb.close()

    if len(result_dataFrame) < 1200:
        raise ValueError(f"Data beban tidak cukup: {len(result_dataFrame)} baris (minimum 1200)")
    coverage_hours = (
        result_dataFrame["timestamp"].max() - result_dataFrame["timestamp"].min()
    ).total_seconds() / 3600
    if coverage_hours < 22:
        raise ValueError(f"Cakupan data beban hanya {coverage_hours:.1f} jam")
    max_gap_minutes = (
        result_dataFrame["timestamp"].sort_values().diff().dt.total_seconds().max() / 60
    )
    if max_gap_minutes > 15:
        raise ValueError(f"Gap data beban terlalu besar: {max_gap_minutes:.1f} menit")

    print(f"Data beban ditemukan: {len(result_dataFrame)} baris")
    return result_dataFrame
