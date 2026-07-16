import tensorflow as tf
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from keras import models, layers 
from sklearn.preprocessing import StandardScaler

 #transforming DNI array data to be plotted
 #target_test_seq=[]
def transform(predict):
  for o in range(len(data_test)):
    predictInverse = sc_px.inverse_transform(predict[o])
    predict_array.append(predictInverse)
     
pv_output = pvlib_output()
def predict(monthx,dayx,hourx,minutex,pxx):
  month = month_dnn
  day = day_dnn
  hour = hour_dnn
  minute = minute_dnn
  px=[]
  for k in range(len(pv_output)):
    px.append(pv_output["Pac"][k])
    
  sc_px = StandardScaler()
  sc_month = StandardScaler()
  sc_day = StandardScaler()
  sc_hour = StandardScaler()
  sc_minute = StandardScaler()
  
  px_scale = sc_px.fit_transform(px)
  py_scale = sc_py.fit_transform(py)
  month_scale = sc_month.fit_transform(month)
  day_scale = sc_day.fit_transform(day)
  hour_scale = sc_hour.fit_transform(hour)
  minute_scale = sc_minute.fit_transform(minute)
  
  px_array = px_scale
  py_array =py_scale
  month_array =month_scale
  day_array = day_scale
  hour_array = hour_scale
  minute_array =minute_scale
  
  joined_feature=list()
  
  features = np.concatenate((px_array,month_array,
                              day_array,hour_array,minute_array),axis=1)
  data_test= joined_feature

  data_test = [l.tolist() for l in data_test]
  data_test = np.array(data_test)
  
  model_dnn = load_model("pv_dnn")
  predict_test = model_dnn.predict(data_test)
  predict_array=[]
  transform(predict_test)
  
  predict_array = np.array(predict_array)
  predict_array=predict_array.flatten()
  p_dnn = predict_array
  
  return p_dnn
                              
                              
  