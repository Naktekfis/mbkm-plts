#!/usr/bin/env python
# coding: utf-8

# # Prediksi Luaran Daya AC harian sistem PLTS
# ### Muhammad Satrio Athiffardi Prasiddha / 13318032

# built-in python modules
import os
import inspect

# scientific python add-ons
import numpy as np
import pandas as pd

# plotting stuff
# first line makes the plots appear in the notebook
import mysql.connector
from mysql.connector import Error
import time
from datetime import timedelta
from datetime import datetime 
from datetime import date
import math

# finally, we import the pvlib library
import pvlib
from pvlib.location import Location
from pvlib.modelchain import ModelChain


# ## Definisikan parameter sistem PV & lokasi

def pvlib_instantiate(temp_array,ghi_array,dni_array,dhi_array,windspeed_array,Time):
    surface_tilt = 2
    surface_azimuth = 90 # pvlib uses 0=North, 90=East, 180=South, 270=West convention
    albedo = 0.2 # asumsi permukaan

    latitude = -6.89
    longitude = 107.61
    altitude = 770

    # create pvlib Location object
    bandung = pvlib.location.Location(latitude, longitude, tz='Asia/Jakarta', 
                                        altitude=altitude, name='Bandung')


    thermal_params = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_polymer']

    # spesifikasi modul PV

    #panggil library module dari CEC / Sandia
    cec_modules = pvlib.pvsystem.retrieve_sam('CECMod')
    sandia_modules = pvlib.pvsystem.retrieve_sam('SandiaMod')

    # ### Spesifikasi modul, format database CEC

    #pilih jenis modul surya berdasarkan library yang tersedia
    cecmodule = cec_modules.Atlantis_Energy_Systems_TS125GM

    # Input manual spesifikasi modul PV Skytech SAM-210 yang digunakan di Labtek VI
    
    # copy modul Atlantis TS125GM
    module = cecmodule.copy()
    module["Technology"] = 'Multi-c-Si'
    module["STC"] = 210.1009
    module["PTC"] = 186.5117
    module["A_c"] = 1.30679
    module["Length"] = 1.324
    module["Width"] = 0.987
    module["N_s"] = 36
    module["I_sc_ref"] = 8.8
    module["V_oc_ref"] = 30.58
    module["I_mp_ref"] = 8.26
    module["V_mp_ref"] = 25.58
    module["alpha_sc"] = 0.065
    module["beta_oc"] = -0.12357
    module["T_NOCT"] = 46.57922
    module["a_ref"] = 1.5372
    module["I_L_ref"] = 8.161
    module["I_o_ref"] = 0.00000000277507
    module["R_s"] = 0.34947
    module["R_sh_ref"] = 898.4149
    module["Adjust"] = 12.6281
    module["gamma_r"] = -0.5
    module["BIPV"] = 'N'
    module["Version"] = 'SAM 2021.12.02'
    module["Date"] = '12/1/2021'

    module.name = "Skytech_SIM_210" # rename the Series appropriately




    # ### Spesifikasi modul, format database Sandia

    sapm = sandia_modules.Canadian_Solar_CS5P_220M___2009_


    # Input manual spesifikasi modul PV Skytech SAM-210 yang digunakan di Labtek VI



    # copy modul Atlantis TS125GM
    s_module = sapm.copy()


    # insert spesifikasi modul Skytech SIM-210
    s_module["Vintage"] = '2020'
    s_module["Area"] = 1.30679
    s_module["Material"] = 'mc-Si'
    s_module["Cells_in_Series"] = 36
    s_module["Parallel_Strings"] = 1
    s_module["Isco"] = 8.8
    s_module["Voco"] = 30.58
    s_module["Impo"] = 8.26
    s_module["Vmpo"] = 25.58
    s_module["Aisc"] = 0.065
    s_module["Aimp"] = -0.000183
    s_module["C0"] = 0.9637
    s_module["C1"] = 0.03633
    s_module["Bvoco"] = -0.13067
    s_module["Mbvoc"] = 0
    s_module["Bvmpo"] = -0.13433
    s_module["Mbvmp"] = 0
    s_module["N"] = 1.421
    s_module["C2"] = -0.25207
    s_module["C3"] = -9.95547
    s_module["A0"] = 0.916833
    s_module["A1"] = 0.07917
    s_module["A2"] = -0.01838
    s_module["A3"] = 0.001923
    s_module["A4"] = -0.0000823
    s_module["B0"] = 1
    s_module["B1"] = -0.00244
    s_module["B2"] = 0.00031
    s_module["B3"] = 0.00001246
    s_module["B4"] = 0.000000211
    s_module["B5"] = 0.00000000136
    s_module["DTC"] = 3
    s_module["FD"] = 1
    s_module["A"] = -3.51
    s_module["B"] = -0.07367
    s_module["C4"] = 0.980667
    s_module["C5"] = 0.019333
    s_module["IXO"] = 8.71
    s_module["IXXO"] = 5.66
    s_module["C6"] = 1.097667
    s_module["C7"] = -0.09767

    s_module.name = "Skytech_SIM_210" # rename the Series appropriately


    sapm = s_module



    # ### Spesifikasi inverter



    # spesifikasi inverter

    #panggil library inverter Sandia
    sapm_inverters = pvlib.pvsystem.retrieve_sam('sandiainverter')

    #pilih jenis inverter berdasarkan library inverter Sandia
    sapm_inverter = sapm_inverters['SMA_America__SB2000HFUS_30__240V_']



    # Input manual spesifikasi inverter Sunny Boy SB5.0-1AV-41 yang digunakan di Labtek VI

    # copy inverter Sunny Boy 2000 HFUS
    inverter = sapm_inverter.copy()
    

    # insert spesifikasi modul Skytech SIM-210
    inverter["Vac"] = 240
    inverter["Pso"] = 32.2376
    inverter["Paco"] = 5000
    inverter["Pdco"] = 5155.06
    inverter["Vdco"] = 365
    inverter["C0"] = -0.00000327495
    inverter["C1"] = -0.0000363102
    inverter["C2"] = 0.0017554
    inverter["C3"] = 0.000115302
    inverter["Pnt"] = 5.21
    inverter["Vdcmax"] = 500
    inverter["Idcmax"] = 15
    inverter["Mppt_low"] = 175
    inverter["Mppt_high"] = 500
    inverter["CEC_Date"] = 'NaN'
    inverter["CEC_Type"] = 'Utility Interactive'

    inverter.name = "SMA_America__SB5_0_1AV_41" # rename the Series appropriately


    sapm_inverter = inverter

    modules_per_string = 16
    strings_per_inverter = 2
    
    # rugi rugi sistem
    d = {k: module[k] for k in ['alpha_sc', 'a_ref', 'I_L_ref', 'I_o_ref', 'R_sh_ref', 'R_s', 'Adjust']}

    losses = pvlib.pvsystem.pvwatts_losses(soiling=2, shading=3, snow=0, mismatch=3,
                                        wiring=2, connections=0.5, lid=1.5,
                                        nameplate_rating=1, age=0, availability=3)


    losses_parameters = {
        "soiling" : 2,
        "shading" : 3,
        "snow" : 0,
        "mismatch": 3,
        "wiring": 2,
        "connections": 0.5,
        "lid": 1.5,
        "nameplate_rating": 1,
        "age": 0,
        "availability": 3
    }


    # ## Pendefinisian sistem




    # definisikan keseluruhan sistem
    system = pvlib.pvsystem.PVSystem(surface_tilt=surface_tilt,
                                    surface_azimuth=surface_azimuth, albedo=albedo,
                                    module=sapm, module_parameters=sapm,
                                    temperature_model_parameters=thermal_params,
                                    modules_per_string=modules_per_string,
                                    strings_per_inverter=strings_per_inverter,
                                    inverter=sapm_inverter,
                                    inverter_parameters=sapm_inverter,
                                    racking_model='open_rack',
                                    losses_parameters=losses_parameters)

    temp_air = pd.DataFrame(temp_array)
    ghi = pd.DataFrame(ghi_array)
    dni = pd.DataFrame(dni_array)
    dhi = pd.DataFrame(dhi_array)
    wind_speed = pd.DataFrame(windspeed_array)
    
    temp_air.columns=["temp_air"]
    ghi.columns=["ghi"]
    dni.columns=["dni"]
    dhi.columns=["dhi"]
    wind_speed.columns=["wind_speed"]
    

    epw_data = pd.concat([Time,temp_air,ghi,dni,dhi,wind_speed],axis=1)
    epw_data = epw_data.set_index("Time")
        
    epw_data=epw_data.fillna(0)
    epw_data = epw_data.shift(freq='-30min')



    # Hitung *solar position* untuk seluruh waktu berdasarkan data cuaca

    solpos = pvlib.solarposition.get_solarposition(epw_data.index, bandung.latitude, bandung.longitude)



    # # ### DNI ET
    # # 
    # # Hitung radiasi terestrial ekstra. Perhitungan ini diperlukan untuk banyak bidang array model iradiasi difus.

    dni_extra = pvlib.irradiance.get_extra_radiation(epw_data.index)
    dni_extra = pd.Series(dni_extra, index=epw_data.index)

    # # Hitung massa udara
    
    airmass = pvlib.atmosphere.get_relative_airmass(solpos['apparent_zenith'])

    # # ### Plane of array (POA) sky diffuse

    poa_sky_diffuse = pvlib.irradiance.haydavies(surface_tilt, surface_azimuth,
                                             epw_data['dhi'], epw_data['dni'], dni_extra,
                                            solpos['apparent_zenith'], solpos['azimuth'])

    # # ### POA ground diffuse

    poa_ground_diffuse = pvlib.irradiance.get_ground_diffuse(surface_tilt, epw_data['ghi'], albedo=albedo)

    # # ### Angle of incidence (AOI)
    aoi = pvlib.irradiance.aoi(surface_tilt, surface_azimuth, solpos['apparent_zenith'], solpos['azimuth'])

    # # ### POA Total
    poa_irrad = pvlib.irradiance.poa_components(aoi, epw_data['dni'], poa_sky_diffuse, poa_ground_diffuse)
    
    # # ### Temperatur sel surya
    pvtemps = pvlib.temperature.sapm_cell(poa_irrad['poa_global'], epw_data['temp_air'], epw_data['wind_speed'], **thermal_params)
    pvtemps = pvlib.temperature.sapm_cell(poa_irrad['poa_global'], epw_data['temp_air'], epw_data['wind_speed'], **thermal_params)

    # # # Kalkulasi luaran daya PLTS

    # # ## Metode ModelChain

    mc = ModelChain(system, bandung, losses_model='pvwatts')
    mc.run_model(epw_data)
    mc.results.ac
    
    df_ac = mc.results.ac.fillna(0)
    df_ac = pd.DataFrame(df_ac)
    df_ac.columns=["Pac"]
    df_ac = df_ac.reset_index()
    #print(df_ac)
    # plt.figure(figsize=(16,8),dpi=100)
    # df_ac.plot()
    # plt.ylabel('AC power (W)')
    # plt.title('AC power output (W), 1 day')
    #print(epw_data)   
     
    return df_ac



