import mysql.connector
import pandas as pd
from datetime import timedelta
import numpy as np
from datetime import datetime 
import time
#from datetime import date
import matplotlib.pyplot as plt
from tensorflow.keras.models import load_model
import tensorflow as tf
from pvlib_model import pvlib_instantiate
from sklearn.preprocessing import StandardScaler
from query import get_query
import time


#data preparation for input to model
def dataprep(ghi,month,day,hour,minute):
        ghi_array = np.array(ghi)
        month_array = np.array(month)
        day_array = np.array(day)
        hour_array = np.array(hour)
        minute_array = np.array(minute)
        
        #define list of input features
        joined_feature=list()

        #appending each data to list of input features
        features = np.concatenate((ghi_array,month_array,
                                day_array,hour_array,minute_array),axis=1)
        joined_feature.append(features)
                
        data_test= joined_feature
        
        data_test = [l.tolist() for l in data_test]
        data_test = np.array(data_test)
        
        return data_test

#transforming DNI array data format  
def transform(predict):
        predict_array=[]
        for o in range(len(data_test)):
                predictInverse = (predict[o])
                predict_array.append(predictInverse)
        return predict_array

#Calculating DHI from DNI and Transform data to be plotted
def plot_transform():
        thetaArray = np.array(costheta["cos theta"])
        ghiArray = np.array(df_aws["solarRad"])
        list_dhi=[]
        for t in range(len(ghiArray)):
                dhi = ghiArray[t]-(predict_array[t]*thetaArray[t])
                list_dhi.append(dhi)

        dhiPred = np.array(list_dhi)
        #dhiPred = np.array_split(dhiPred,divider)
        
        return dhiPred

def read_data(data,loc):
    read = data.iloc[:,loc]
    read = read.values.tolist()
    read = np.array(read).reshape(-1,1)
    
    return read

# Main Program
dataval = []
for x in range(0,20) :
  with tf.device('/cpu:0'):
        start = time.time()
        model_dnn = load_model("/home/energy/code/pv_deploy/pv_dnn")
        todays = datetime.now().date()
        #todays = "2022-10-31"
        #todays = datetime.strptime(todays, "%Y-%m-%d")
        #todays = todays.date()
        yesterday = todays - timedelta(days=1)
        #print(todays)
        #print(yesterday)
        df_costheta = pd.read_csv("/home/energy/code/pv_deploy/costheta.csv")
        day_lookup = todays.day
        month_lookup = todays.month
        costheta = df_costheta.query("dm ==@day_lookup and m==@month_lookup")
        date_head = yesterday
        range_date1 = '{} 00:00:10'.format(date_head)
        range_date2 = '{} 23:59:10'.format(date_head)

        hour=[]
        minute=[]
        month=[]
        day=[]
        
        result_dataFrame = get_query()

        print(result_dataFrame)
        
        for k in range(len(result_dataFrame)):
                month.append(result_dataFrame["stationDateTime"][k].month)
                day.append(result_dataFrame["stationDateTime"][k].day)
                hour.append(result_dataFrame["stationDateTime"][k].hour)
                minute.append(result_dataFrame["stationDateTime"][k].minute)
                
        df_month = pd.DataFrame(month)
        df_day = pd.DataFrame(day)
        df_hour = pd.DataFrame(hour)
        df_minute = pd.DataFrame(minute)  
        df_month.columns=["month"]
        df_day.columns=["day"]
        df_hour.columns=["hour"]
        df_minute.columns=["minute"]
        
        
        Time = pd.date_range(start=range_date1, end=range_date2, freq='min')
        df_aws = pd.concat([df_month,df_day,df_hour,df_minute,result_dataFrame],axis=1)
        df_aws.set_index("stationDateTime",inplace=True)
        df_aws.index.name = None
        df_aws = df_aws[10:]
        df_aws = df_aws[~df_aws.index.duplicated()]
        df_aws=df_aws.reindex(Time)
        Time = pd.date_range(start=range_date1, end=range_date2, freq='min',tz="Asia/Jakarta")
        df_aws=df_aws.set_index(Time).asfreq('min')
        df_aws=df_aws.interpolate()
        Time = pd.DataFrame(Time,index=None)
        Time.columns=["Time"]
        
        #read variables
        month = read_data(df_aws,0)
        day = read_data(df_aws,1)
        hour = read_data(df_aws,2)
        minute = read_data(df_aws,3)
        ghi = read_data(df_aws,6)
        
        #Calling data preparation method    
        data_test=dataprep(ghi,month,day,hour,minute)
        #Predicting
        model = load_model("/home/energy/code/pv_deploy/pv_model")
        predict_test = model.predict(data_test)
         
        #Calling transform method        
        predict_array=transform(predict_test)
        predict_array = np.array(predict_array)
        predict_array=predict_array.flatten()
        ghi = np.array(df_aws["solarRad"])
        
        #Calling plot_transform method 
        dhiPred=plot_transform()
        dniPred = predict_array
        
        ghi_array = np.array(ghi)
        dni_array = np.array(dniPred)
        dhi_array = np.array(dhiPred)
        temp_array = np.array(df_aws["outsideTemp"])
        windspeed_array = np.array(df_aws["windSpeed"])
        
        #Instantiate PVLIB Model
        def pvlib_output():
          output = pvlib_instantiate(temp_array,ghi_array,dni_array,dhi_array,windspeed_array,Time)
                  
          return output
                
        def pv_dnn(monthx,dayx,hourx,minutex):
          month = monthx
          day = dayx
          hour = hourx
          minute = minutex
          px=[]
          for k in range(len(pv_output)):
            px.append(pv_output["Pac"][k])
          px = np.array(px)
          px = np.reshape(px,(-1,1))
          
          sc_px = StandardScaler()
          sc_month = StandardScaler()
          sc_day = StandardScaler()
          sc_hour = StandardScaler()
          sc_minute = StandardScaler()
          
          px_scale = sc_px.fit_transform(px)
          month_scale = sc_month.fit_transform(month)
          day_scale = sc_day.fit_transform(day)
          hour_scale = sc_hour.fit_transform(hour)
          minute_scale = sc_minute.fit_transform(minute)
          
          px_array = px
          month_array =month
          day_array = day
          hour_array = hour
          minute_array =minute
          
          joined_feature=list()
          
          features = np.concatenate((px_array,month_array,
                                      day_array,hour_array,minute_array),axis=1)
          data_input = features
        
          data_input = [l.tolist() for l in data_input]
          data_input = np.array(data_input)
          
          data_input = np.nan_to_num(data_input,0)
          data_input = [data_input]
          data_input = np.array(data_input)
          predict_test = model_dnn.predict(data_input)
          predict_array=predict_test.flatten()
          predict_array=predict_array.flatten()
          p_dnn = predict_array
          p_dnn = np.array(p_dnn)
          #p_dnn =np.reshape(p_dnn,(-1,1))
          #p_dnn = sc_px.inverse_transform(p_dnn)
          
          
          return p_dnn
          
        pv_output = pvlib_output()   
        output_dnn = pv_dnn(month,day,hour,minute)
        df_dnn = pd.DataFrame(output_dnn)
        df_dnn = pd.DataFrame(output_dnn)
        df_dnn.columns=["Pac"]
        pv_output.drop(columns=["Pac"],inplace=True)
        pv_output =pd.concat([pv_output,df_dnn],axis=1)
        #plt.plot(pv_output["Pac"])
        #plt.savefig("test.png")
        
        #print(pv_output)
        #Reindexing
        date_head1 = todays  - timedelta(days=1)
        date_head2 = yesterday - timedelta(days=1)
        date_head = todays
        #yesterday = todays - timedelta(days=1)
        range_date1 = '{} 23:30:10'.format(date_head2)
        range_date2 = '{} 23:59:10'.format(date_head1)
        Time = pd.date_range(start=range_date1, end=range_date2, freq='min',tz="Asia/Jakarta")
        pv_output.reset_index(inplace=True)
        pv_output.set_index("Time",inplace=True)
        pv_output.drop(columns="index",inplace=True)
        pv_output.index.name=None
        pv_output=pv_output.reindex(Time,fill_value=0)
        pv_output = pv_output[30:]
        pv_output.reset_index(inplace=True)
        date_head = todays
        range_date1 = '{} 00:00:10'.format(date_head)
        range_date2 = '{} 23:59:10'.format(date_head)
        Time = pd.date_range(start=range_date1, end=range_date2, freq='min',tz="Asia/Jakarta")
        df_time = pd.DataFrame(Time)
        df_time.columns=["Time"]
        pv_output = pd.concat([df_time,pv_output],axis=1)
        pv_output.drop(columns="index",inplace=True)
        #pv_output.set_index("Time",inplace=True)
        #print(pv_output)
        pv_output.fillna(0,inplace=True)
        pv_output.columns=["Time","Pac"]
        pv_output.loc[pv_output['Pac']<0, 'Pac'] = 0
        #plt.plot(pv_output["Pac"])
        #plt.savefig("test.png")
        
        print(pv_output)
        def get_data():
          return pv_output
        
        end = time.time() - start
        dataval.append(end)
        
print(dataval)
        
        
        
        
        
        
        