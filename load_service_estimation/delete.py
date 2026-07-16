import mysql.connector
#from model_beban import get_data
import datetime

try:
      connection = mysql.connector.connect(host="192.168.1.149",
      user="energy",
      password="change-me",
      database="prediksi")
      query = """DELETE FROM bebanv3 WHERE id>64800 and id<66240"""
      cursor = connection.cursor()
      cursor.execute(query)
      connection.commit()
      connection.close()

except mysql.connector.Error as error:
    print("Failed to insert")
