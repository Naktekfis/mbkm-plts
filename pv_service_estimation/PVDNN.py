#!/usr/bin/env python
# coding: utf-8

# # Model DNN PLTS

# In[1]:


import tensorflow as tf
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from keras import models, layers  
from sklearn.metrics import r2_score,mean_squared_error,mean_absolute_error, mean_absolute_percentage_error
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split


# In[40]:


df = pd.read_excel('pv_master.xlsx')


# In[41]:


df.head()


# In[2]:


def read_data(data,loc):
    read = data.iloc[:,loc]
    read = read.values.tolist()
    read = np.array(read).reshape(-1,1)
    
    return read


# In[43]:


month = read_data(df,1)
day = read_data(df,2)
hour = read_data(df,3)
minute = read_data(df,4)
px = read_data(df,5)
py = read_data(df,7)


# In[44]:


sc_px = StandardScaler()
sc_py = StandardScaler()
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

px_array = np.array_split(px_scale,7)
py_array = np.array_split(py_scale,7)
month_array = np.array_split(month_scale,7)
day_array = np.array_split(day_scale,7)
hour_array = np.array_split(hour_scale,7)
minute_array = np.array_split(minute_scale,7)


# In[45]:


#define list of input features
joined_feature=list()


# In[46]:


#appending each scaled training data to list of input features
for i in range(int(7)): 
    features = np.concatenate((px_array[i],month_array[i],
                              day_array[i],hour_array[i],minute_array[i]),axis=1)
    joined_feature.append(features)


# In[47]:


data_train,target_train = (joined_feature,py_array)

data_train = [l.tolist() for l in data_train]
#data_test = [l.tolist() for l in data_test]
data_train = np.array(data_train)
#data_test = np.array(data_test)
target_train = [l.tolist() for l in target_train]
#target_test = [l.tolist() for l in target_test]
target_train = np.array(target_train)
#target_test = np.array(target_test)


# In[48]:


joined_feature


# In[49]:


# create the NN layers & neurons configuration
model = tf.keras.Sequential()
model.add(layers.Dense(64, activation='relu', input_shape=(1440,5)))
model.add(layers.Dense(72, activation='relu'))
model.add(layers.Dense(96, activation='relu'))
model.add(layers.Dense(120,activation='relu'))
model.add(layers.Dense(96, activation='relu'))
model.add(layers.Dense(72, activation='relu'))
model.add(layers.Dense(64, activation='relu'))
model.add(layers.Dense(1))
model.compile(optimizer='adam', loss='mse', metrics=['mse'])
model.summary()


# In[50]:


history=model.fit(data_train, target_train, epochs=1000, batch_size=16)


# In[18]:


mse = history.history['mse']
#val_mse = history.history['val_mse']
loss = history.history['loss']
#val_loss = history.history['val_loss']

epochs = range(len(mse))

plt.plot(epochs, mse, 'r', label='Training MSE')
#plt.plot(epochs, val_mse, 'b', label='Validation MSE')
plt.title('Training and Validation MSE')
plt.legend(loc=0)
plt.figure()


# In[64]:


py_perday = np.array_split(py,7)


# In[66]:


data_train.shape


# In[69]:


value = sc_py.inverse_transform(predY[6])


# In[70]:


plt.plot(py_perday[6])
plt.plot(value)


# In[71]:


model.save('pv_dnn')


# # Validasi

# In[43]:


from tensorflow.keras.models import load_model
model_dnn = load_model('pv_dnn')


# In[44]:


dt = pd.read_excel('pv_master.xlsx')
dt.head()


# In[45]:


month = read_data(dt,1)
day = read_data(dt,2)
hour = read_data(dt,3)
minute = read_data(dt,4)
px = read_data(dt,5)
py = read_data(dt,6)


# In[46]:


sc_px = StandardScaler()
sc_py = StandardScaler()
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

px_array = np.array_split(px_scale,7)
py_array = np.array_split(py_scale,7)
month_array = np.array_split(month_scale,7)
day_array = np.array_split(day_scale,7)
hour_array = np.array_split(hour_scale,7)
minute_array = np.array_split(minute_scale,7)


# In[47]:


joined_feature=[]


# In[48]:


#appending each scaled training data to list of input features
for i in range(int(7)): 
    features = np.concatenate((px_array[i],month_array[i],
                              day_array[i],hour_array[i],minute_array[i]),axis=1)
    joined_feature.append(features)
    
data_test= joined_feature

data_test = [l.tolist() for l in data_test]
data_test = np.array(data_test)


# In[49]:


predict_test = model_dnn.predict(data_test)


# In[50]:


#transforming DNI array data to be plotted
predict_array=[]
#target_test_seq=[]
def transform(predict):
    for o in range(len(data_test)):
        predictInverse = sc_py.inverse_transform(predict[o])
        predict_array.append(predictInverse)
        
transform(predict_test)

predict_array = np.array(predict_array)
predict_array=predict_array.flatten()
p_dnn = predict_array


# In[51]:


p_dnn = predict_array
p_pvlib = np.array(dt['P PVLib'])
pac = np.array(dt['Pac'])


# In[52]:


p_dnn2=[]
for k in range(len(p_dnn)):
    if p_dnn[k]<10:
        p_dnn2.append(0)
    else:
        p_dnn2.append(p_dnn[k])
p_dnn = p_dnn2


# In[53]:


df_pac = pd.DataFrame(pac,columns=["Pac"])
df_pvlib = pd.DataFrame(p_pvlib,columns=["P PVLib"])
df_dnn = pd.DataFrame(p_dnn,columns=["P DNN"])

df_pv_merged = pd.concat([df_pac,df_pvlib,df_dnn],axis=1,ignore_index=True)


# In[54]:


df_pv_merged.columns = ["Pac","P PVLib","P DNN"]


# In[55]:


df_pv_merged.to_csv("pv_fixed.csv")


# In[56]:


plt.figure(figsize=(16,8))
plt.title("Profil Produksi PLTS",fontsize=18)
plt.xlabel("Menit", fontsize=18)
plt.ylabel("Daya (P)",fontsize=18)
plt.plot(pac)
plt.plot(p_pvlib)
plt.plot(p_dnn)
plt.legend(["Aktual","Model PVLib","Model DNN"])
plt.grid()
plt.savefig("profil_pac_pvlib_dnn.png")


# In[57]:


plt.figure(figsize=(16,8))
plt.title("Profil Produksi PLTS",fontsize=18)
plt.xlabel("Menit", fontsize=18)
plt.ylabel("Daya (P)",fontsize=18)
plt.plot(pac)
plt.plot(p_dnn)
plt.legend(["Aktual","Model PVLib + DNN"],fontsize=16)
plt.grid()
plt.savefig("profil_pac_dnn (1 Week).png")


# In[58]:


plt.figure(figsize=(16,8))
plt.title("Profil Produksi PLTS (Minggu, 24 April 2022)",fontsize=18)
x = np.linspace(0,24,1440)
plt.xticks(np.arange(min(x),max(x)+1,1),fontsize=14)
plt.yticks(fontsize=14)
plt.xlabel("Jam", fontsize=18)
plt.ylabel("Daya (W)",fontsize=18)
plt.plot(x,pac[8640:10080])
plt.plot(x,p_dnn[8640:10080])
plt.legend(["Aktual","Model PVLib + DNN"],fontsize=16)
plt.grid()
plt.savefig("profil_pac_dnn (Minggu).png")


# In[59]:


rmse=np.sqrt(mean_squared_error(dt['Pac'],p_dnn))
MAE=mean_absolute_error(dt['Pac'], p_dnn)

print('RMSE data latih =',rmse)
print('MAE data latih  =',MAE)

