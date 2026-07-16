import mysql.connector
import datetime

mydb = mysql.connector.connect(host = '192.168.1.185',port=20002,user="energy",password='change-me',database="prediksi")
mycursor = mydb.cursor()
def test() :
#month = ["07","08","09","10"]
  month = ["01"]
  day = ["01"]
  hour = ["00","01","02","03","04","05","06","07","08","09","10","11","12","13","14","15","16","17","18","19","20","21","22","23"]
  #day = ["01","02","03","04","05","06","07","08","09","10","11","12","13","14","15","16","17","18","19","20","21","22","23","24","25","26","27","28","29","30","31"]
  
  list_value = []
  
  for z in month :
    for y in day :
      for x in hour :
    
        start = "2023-"+z+"-"+y+" "+x+":00:00"
        end = "2023-"+z+"-"+y+" "+x+":59:59"
        print(start)
        start = "'{}'".format(start)
        end = "'{}'".format(end)
        
        try :
          mycursor.execute("SELECT "+start+" as timestamp,avg(Pac) FROM pv WHERE timestamp > "+start+" AND timestamp < "+end)
          value = mycursor.fetchall()
          if value[0][1] is not None :
            list_value.append(value[0])
          
        except :
          pass
  
  print(list_value)        
  sql="INSERT INTO `pv_perjam` (`timestamp`,`Pac`) VALUES (%s,%s)"
  mycursor.executemany(sql, list_value)
  mydb.commit()
  print("insert")

 

def test2() :
  list_value = []
  now = datetime.datetime.now()
  dt_string = now.strftime("%Y-%m-%d ")
  start = dt_string+"00:00:00"
  end = dt_string+"23:59:59"
  
  start = "'{}'".format(start)
  end = "'{}'".format(end)
  
  mycursor.execute("SELECT timestamp,avg(Pac) FROM pv WHERE timestamp > "+start+" AND timestamp < "+end+" group by hour(timestamp)")
  value = mycursor.fetchall()
  
  for x in value :
    if x[1] is not None :
      list_value.append(x)
  
  
  print(list_value)  
  sql="INSERT INTO `pv_perjam` (`timestamp`,`Pac`) VALUES (%s,%s)"
  mycursor.executemany(sql, list_value)
  mydb.commit()
  print("insert")
  
test2()
