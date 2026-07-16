import mysql.connector
import time
import pandas as pd
from datetime import timedelta
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model
from datetime import datetime 
import time
from datetime import date
import matplotlib.pyplot as plt
import math
from sklearn.preprocessing import StandardScaler
from query import get_query,get_date
import time
#function to read dataframe data
def read_data(data, loc):
    read = data.iloc[:,loc]
    read = read.values.tolist()
    read = np.array(read).reshape(-1,1)
    
    
    return read
dataval = []
for x in range (0,20):
  start = time.time()
  #Setting up today's variable
  todays = get_date(0)
  yesterday =get_date(delta=-1)
  tomorrow = get_date(delta=1)
  result_dataFrame = get_query()
  print(result_dataFrame)
  today = pd.to_datetime(todays).day_name()
  day1 = pd.to_datetime(yesterday).day_name()
  model = load_model('/home/energy/code/load_deploy/model_bebanv2/model_bebanv2/model/modelbeban_{}'.format(today))
  
      
  df = result_dataFrame
  format = "%Y-%m-%d %H:%M"
  date_list=[]
  for k in range(len(df)):
    datetime =  df["timestamp"][k]
    date_formatted = datetime.strftime(format)
    date_list.append(date_formatted)
    
  df_date = pd.DataFrame(date_list)
  df_date.columns=["timestamp"]
  df.drop(columns=["timestamp"],inplace=True)
  df = pd.concat([df_date,df],axis=1)
  df.set_index("timestamp",inplace=True)
  df_index = pd.date_range(start=yesterday, end=todays,freq="min").strftime("%Y-%m-%d %H:%M")
  df=df.reindex(df_index)
  df = df.interpolate()
  df = df.reset_index()
  
  
  date_format =  pd.to_datetime(df["index"])
  
  month_list=[]
  day_list=[]
  hour_list=[]
  minute_list=[]
  
  for k in range(len(date_format)):
    month = date_format[k].month
    day = date_format[k].day
    hour = date_format[k].hour
    minute = date_format[k].minute
    month_list.append(month)
    day_list.append(day)
    hour_list.append(hour)
    minute_list.append(minute)
    
  time_array = list(zip(month_list,day_list,hour_list,minute_list))
  
  df_time = pd.DataFrame(time_array,columns=["month","day","hour","minute"])
  df_final = pd.concat([df_time,df],axis=1)
  df_final = df_final[0:1440]
  
  #mathematical operation for moving average
  df_power_day1 = 3*df_final['A']*df_final['PF']*df_final['VLN']
  array_power_day1 = np.array(df_power_day1)
  avg_power_day1=[]
  for j in range(len(array_power_day1)-59):
      mean_value = sum(array_power_day1[j:60+j])/60
      avg_power_day1.append(mean_value)
  df_avgpower_day1 = pd.DataFrame(avg_power_day1)
  df_avgleft = df_power_day1[1381:]
  df_avgleft_array = np.array(df_avgleft)
  avg_list=[]
  for j in range(len(df_avgleft_array)):
      if j==59:
        mean_value = sum(df_avgleft_array[j:])/1
        avg_list.append(mean_value)
      else:
        mean_value = sum(df_avgleft_array[j:])/(59-j)
        avg_list.append(mean_value)
  df_meanleft = pd.DataFrame(avg_list)
  df_totalmean_day1 = pd.concat([df_avgpower_day1,df_meanleft],ignore_index=True)
  df_final_clean = pd.concat([df_final,df_power_day1,df_totalmean_day1],axis=1,ignore_index=True)
  
  # Input initialization for prediction input
  all_data = df_final_clean
  load_data = read_data(all_data, 10)
  #week_data = read_data(all_data, 0)
  day_data = read_data(all_data, 1)
  month_data = read_data(all_data, 0)
  hour_data = read_data(all_data, 2)
  minute_data = read_data(all_data,3)
  divider = len(load_data)/1440
  
  # Scaling the input variables
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
  
  # Reshaping input arrays to match ann model
  splitted_feature = np.array_split(load_scale,divider)
  splitted_feature2 = np.array_split(day_scale,divider)
  splitted_feature4 = np.array_split(month_scale,divider)
  splitted_feature6 = np.array_split(hour_scale,divider)
  splitted_feature8 = np.array_split(minute_scale,divider)
  
  joined_feature=list()
  
  for i in range(int(divider)): 
      features = np.concatenate((splitted_feature[i],splitted_feature2[i],splitted_feature4[i],
                                splitted_feature6[i],
                                 splitted_feature8[i]),axis=1)
      joined_feature.append(features)
      
  data_test= joined_feature
  data_test=[l.tolist() for l in data_test]
  data_test = np.array(data_test)
  
  
  # Initialize Prediciton
  predict = model.predict(data_test)
  predict = sc_load.inverse_transform(predict[0])
  Time = pd.date_range(start=todays, end=tomorrow, freq='min',tz="Asia/Jakarta")
  Time = Time[1:]
  df_predict = pd.DataFrame(predict,index=Time)
  df_predict.reset_index(inplace=True)
  df_predict.columns=["timestamp","daya"]
  df_predict = df_predict.replace(np.nan, 0)
  
  
  def get_data():
    return df_predict


  end = time.time() - start
  dataval.append(end)
  
print(dataval)




