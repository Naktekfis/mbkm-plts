import mysql.connector

mydb = mysql.connector.connect(host = '192.168.1.149',user="energy",password='change-me',database="prediksi")
mycursor = mydb.cursor()
mycursor.execute("UPDATE `pv` SET `Pac` = 0 WHERE `Pac` < 0")
mydb.close()
print('updated')
