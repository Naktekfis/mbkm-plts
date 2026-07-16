import sys
import types
import unittest
from contextlib import contextmanager, redirect_stdout
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, call, patch

import numpy as np
import pandas as pd


pvlib = types.ModuleType("pvlib")
pvlib.location = types.ModuleType("pvlib.location")
pvlib.location.Location = Mock()
pvlib.modelchain = types.ModuleType("pvlib.modelchain")
pvlib.modelchain.ModelChain = Mock()
pvlib.pvsystem = types.SimpleNamespace()
pvlib.temperature = types.SimpleNamespace(
    TEMPERATURE_MODEL_PARAMETERS={
        "sapm": {"open_rack_glass_polymer": {"a": -3.56, "b": -0.075}}
    }
)
pvlib.solarposition = types.SimpleNamespace()
pvlib.irradiance = types.SimpleNamespace()
pvlib.atmosphere = types.SimpleNamespace()

tensorflow = types.ModuleType("tensorflow")
tensorflow_keras = types.ModuleType("tensorflow.keras")
tensorflow_models = types.ModuleType("tensorflow.keras.models")
tensorflow_models.load_model = lambda path: None
tensorflow_keras.models = tensorflow_models
tensorflow.keras = tensorflow_keras
tensorflow.device = lambda name: contextmanager(lambda: (yield))()

query_openmeteo = types.ModuleType("query_openmeteo")
query_openmeteo.get_query = lambda: None

mysql = types.ModuleType("mysql")
mysql_connector = types.ModuleType("mysql.connector")
mysql_connector.Error = Exception
mysql.connector = mysql_connector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(sys.modules, {
    "pvlib": pvlib,
    "pvlib.location": pvlib.location,
    "pvlib.modelchain": pvlib.modelchain,
    "mysql": mysql,
    "mysql.connector": mysql_connector,
}):
    from pv_service_estimation import pvlib_model

with patch.dict(sys.modules, {
    "tensorflow": tensorflow,
    "tensorflow.keras": tensorflow_keras,
    "tensorflow.keras.models": tensorflow_models,
    "pvlib_model": pvlib_model,
    "query_openmeteo": query_openmeteo,
}):
    from pv_service_estimation import aws_model2_openmeteo as estimator


class NamedParameters(dict):
    name = None

    def copy(self):
        return NamedParameters(self)


class PvEstimatorPreprocessingTest(unittest.TestCase):
    def test_minutely_weather_time_features_and_dni_tensor(self):
        source = pd.DataFrame({
            "stationDateTime": pd.to_datetime([
                "2026-07-16 00:00", "2026-07-16 01:00", "2026-07-16 23:00"
            ]).tz_localize("Asia/Jakarta"),
            "solarRad": [0.0, 60.0, 1380.0],
            "outsideTemp": [20.0, 26.0, 30.0],
            "windSpeed": [1.0, 2.0, 3.0],
        })

        minutes, weather = estimator._prepare_minutely_weather(
            source, date(2026, 7, 16)
        )
        features = estimator._time_features(minutes)
        captured = {}

        class FakeModel:
            def predict(self, values):
                captured["values"] = values
                return np.arange(1440.0).reshape(1, 1440, 1)

        with patch.object(estimator, "load_model", return_value=FakeModel()) as loader:
            result = estimator._predict_dni(
                weather["solarRad"].to_numpy().reshape(-1, 1), features
            )

        self.assertEqual(len(weather), 1440)
        self.assertEqual(str(minutes[0]), "2026-07-16 00:00:00+07:00")
        self.assertEqual(str(minutes[-1]), "2026-07-16 23:59:00+07:00")
        self.assertEqual(weather.columns.tolist(), ["solarRad", "outsideTemp", "windSpeed"])
        self.assertEqual(weather["solarRad"].iloc[30], 30.0)
        self.assertEqual(weather["solarRad"].iloc[-1], 1380.0)
        self.assertEqual([value.shape for value in features], [(1440, 1)] * 4)
        loader.assert_called_once_with("/app/pv_model")
        self.assertEqual(captured["values"].shape, (1, 1440, 5))
        np.testing.assert_array_equal(
            captured["values"][0, 61], [61.0, 7.0, 16.0, 1.0, 1.0]
        )
        np.testing.assert_array_equal(result, np.arange(1440.0))

    def test_pvlib_formula_dnn_feature_order_and_hourly_today_output(self):
        minutes = pd.date_range(
            "2026-07-16", periods=1440, freq="min", tz="Asia/Jakarta"
        )
        weather = pd.DataFrame({
            "solarRad": np.arange(1440.0),
            "outsideTemp": np.full(1440, 25.0),
            "windSpeed": np.full(1440, 2.0),
        }, index=minutes)
        dni = np.arange(1440.0) + np.where(np.arange(1440) % 2, 10, -10)
        pv_output = pd.DataFrame({"Time": minutes, "Pac": np.arange(1440.0)})

        with patch.object(estimator, "pvlib_instantiate", return_value=pv_output) as invoke:
            result = estimator._run_pvlib(weather, minutes, dni)

        self.assertIs(result, pv_output)
        args = invoke.call_args.args
        np.testing.assert_array_equal(args[0], np.full(1440, 25.0))
        np.testing.assert_array_equal(args[1], np.arange(1440.0))
        np.testing.assert_array_equal(args[2], dni)
        np.testing.assert_array_equal(args[3][:4], [10.0, 0.0, 10.0, 0.0])
        np.testing.assert_array_equal(args[4], np.full(1440, 2.0))
        self.assertEqual(args[5].columns.tolist(), ["Time"])

        model = Mock()
        model.predict.return_value = np.arange(1440.0).reshape(1, 1440, 1)
        time_features = estimator._time_features(minutes)
        pv_output.loc[0, "Pac"] = np.nan
        with patch.object(estimator, "load_model", return_value=model) as loader:
            corrected = estimator._correct_pvlib_output(pv_output.copy(), time_features)

        loader.assert_called_once_with("/app/pv_dnn")
        tensor = model.predict.call_args.args[0]
        self.assertEqual(tensor.shape, (1, 1440, 5))
        self.assertEqual(tensor[0, 0, 0], 0)
        np.testing.assert_array_equal(tensor[0, 61], [61.0, 7.0, 16.0, 1.0, 1.0])
        hourly = estimator._hourly_today(corrected, date(2026, 7, 17))
        self.assertEqual(hourly.columns.tolist(), ["Time", "Pac"])
        self.assertEqual(len(hourly), 24)
        self.assertEqual(str(hourly["Time"].iloc[0]), "2026-07-17 00:00:00+07:00")
        self.assertEqual(str(hourly["Time"].iloc[-1]), "2026-07-17 23:00:00+07:00")
        np.testing.assert_array_equal(hourly["Pac"], np.arange(24) * 60.0)

    def test_hourly_output_clips_nan_and_negative(self):
        values = np.arange(1440.0)
        values[0] = np.nan
        values[60] = -1
        result = estimator._hourly_today(pd.DataFrame({"Pac": values}), date(2026, 7, 17))
        np.testing.assert_array_equal(result["Pac"].iloc[:3], [0.0, 0.0, 120.0])

    def test_get_data_orchestrates_helpers_on_cpu(self):
        trace = []
        source = object()
        minutes = object()
        weather = {"solarRad": pd.Series([4.0])}
        features = object()
        dni = object()
        physical = object()
        corrected = object()
        output = pd.DataFrame({
            "Time": pd.to_datetime(["2026-07-17 00:00"]).tz_localize("Asia/Jakarta"),
            "Pac": [2],
        })

        class FixedDateTime:
            @classmethod
            def now(cls):
                return datetime(2026, 7, 17, 8, 30)

        @contextmanager
        def device(name):
            trace.append(("device_enter", name))
            yield
            trace.append(("device_exit", name))

        def record(name, result):
            def fake(*args):
                trace.append((name,) + args)
                return result
            return fake

        stdout = StringIO()
        with redirect_stdout(stdout), \
                patch.object(estimator, "datetime", FixedDateTime), \
                patch.object(estimator.tf, "device", device), \
                patch.object(estimator, "get_query", record("query", source)), \
                patch.object(estimator, "_prepare_minutely_weather", record("prepare", (minutes, weather))), \
                patch.object(estimator, "_time_features", record("features", features)), \
                patch.object(estimator, "_predict_dni", record("dni", dni)), \
                patch.object(estimator, "_run_pvlib", record("pvlib", physical)), \
                patch.object(estimator, "_correct_pvlib_output", record("correct", corrected)), \
                patch.object(estimator, "_hourly_today", record("hourly", output)):
            result = estimator.get_data()

        self.assertIs(result, output)
        self.assertEqual(trace, [
            ("device_enter", "/cpu:0"),
            ("query",),
            ("prepare", source, date(2026, 7, 16)),
            ("features", minutes),
            ("dni", weather["solarRad"].to_numpy().reshape(-1, 1), features),
            ("pvlib", weather, minutes, dni),
            ("correct", physical, features),
            ("hourly", corrected, date(2026, 7, 17)),
            ("device_exit", "/cpu:0"),
        ])
        log = stdout.getvalue()
        self.assertRegex(log, r"(?m)^\[get_data\] Dipanggil pada: .+$")
        self.assertIn("[get_data] todays        : 2026-07-17", log)
        self.assertIn("[get_data] yesterday     : 2026-07-16", log)
        self.assertIn("[get_data] Output 1 baris per jam:", log)
        self.assertIn("2026-07-17 00:00:00+07:00", log)


class PvlibBuilderTest(unittest.TestCase):
    def test_module_and_inverter_parameters_match_runtime_constants(self):
        cec = types.SimpleNamespace(Atlantis_Energy_Systems_TS125GM=NamedParameters())
        sandia = types.SimpleNamespace(Canadian_Solar_CS5P_220M___2009_=NamedParameters())
        inverters = {"SMA_America__SB2000HFUS_30__240V_": NamedParameters()}
        retrieve = Mock(side_effect=[cec, sandia, inverters])

        with patch.object(pvlib_model.pvlib.pvsystem, "retrieve_sam", retrieve, create=True):
            module, sapm = pvlib_model._build_module_parameters()
            inverter = pvlib_model._build_inverter_parameters()

        self.assertEqual(retrieve.call_args_list, [call("CECMod"), call("SandiaMod"), call("sandiainverter")])
        self.assertEqual(module, {
            "Technology": "Multi-c-Si", "STC": 210.1009, "PTC": 186.5117,
            "A_c": 1.30679, "Length": 1.324, "Width": 0.987, "N_s": 36,
            "I_sc_ref": 8.8, "V_oc_ref": 30.58, "I_mp_ref": 8.26,
            "V_mp_ref": 25.58, "alpha_sc": 0.065, "beta_oc": -0.12357,
            "T_NOCT": 46.57922, "a_ref": 1.5372, "I_L_ref": 8.161,
            "I_o_ref": 0.00000000277507, "R_s": 0.34947,
            "R_sh_ref": 898.4149, "Adjust": 12.6281, "gamma_r": -0.5,
            "BIPV": "N", "Version": "SAM 2021.12.02", "Date": "12/1/2021",
        })
        self.assertEqual(sapm, {
            "Vintage": "2020", "Area": 1.30679, "Material": "mc-Si",
            "Cells_in_Series": 36, "Parallel_Strings": 1, "Isco": 8.8,
            "Voco": 30.58, "Impo": 8.26, "Vmpo": 25.58, "Aisc": 0.065,
            "Aimp": -0.000183, "C0": 0.9637, "C1": 0.03633,
            "Bvoco": -0.13067, "Mbvoc": 0, "Bvmpo": -0.13433,
            "Mbvmp": 0, "N": 1.421, "C2": -0.25207, "C3": -9.95547,
            "A0": 0.916833, "A1": 0.07917, "A2": -0.01838,
            "A3": 0.001923, "A4": -0.0000823, "B0": 1,
            "B1": -0.00244, "B2": 0.00031, "B3": 0.00001246,
            "B4": 0.000000211, "B5": 0.00000000136, "DTC": 3, "FD": 1,
            "A": -3.51, "B": -0.07367, "C4": 0.980667,
            "C5": 0.019333, "IXO": 8.71, "IXXO": 5.66,
            "C6": 1.097667, "C7": -0.09767,
        })
        self.assertEqual(inverter, {
            "Vac": 240, "Pso": 32.2376, "Paco": 5000, "Pdco": 5155.06,
            "Vdco": 365, "C0": -0.00000327495, "C1": -0.0000363102,
            "C2": 0.0017554, "C3": 0.000115302, "Pnt": 5.21,
            "Vdcmax": 500, "Idcmax": 15, "Mppt_low": 175,
            "Mppt_high": 500, "CEC_Date": "NaN",
            "CEC_Type": "Utility Interactive",
        })
        self.assertEqual((module.name, sapm.name, inverter.name), (
            "Skytech_SIM_210", "Skytech_SIM_210", "SMA_America__SB5_0_1AV_41"
        ))

    def test_location_system_and_weather_builder_configuration(self):
        module = {key: index for index, key in enumerate(
            ['alpha_sc', 'a_ref', 'I_L_ref', 'I_o_ref', 'R_sh_ref', 'R_s', 'Adjust']
        )}
        sapm = object()
        inverter = object()
        thermal = {"a": -3.56}
        location = Mock(return_value=object())
        system = Mock(return_value=object())
        losses = Mock(return_value=12.3)

        with patch.object(pvlib_model.pvlib.location, "Location", location), \
                patch.object(pvlib_model.pvlib.pvsystem, "PVSystem", system, create=True), \
                patch.object(pvlib_model.pvlib.pvsystem, "pvwatts_losses", losses, create=True):
            pvlib_model._build_location()
            pvlib_model._build_system(module, sapm, inverter, thermal)

        location.assert_called_once_with(
            -6.89, 107.61, tz="Asia/Jakarta", altitude=770, name="Bandung"
        )
        expected_losses = {
            "soiling": 2, "shading": 3, "snow": 0, "mismatch": 3,
            "wiring": 2, "connections": 0.5, "lid": 1.5,
            "nameplate_rating": 1, "age": 0, "availability": 3,
        }
        losses.assert_called_once_with(**expected_losses)
        system.assert_called_once_with(
            surface_tilt=2, surface_azimuth=90, albedo=0.2,
            module=sapm, module_parameters=sapm,
            temperature_model_parameters=thermal, modules_per_string=16,
            strings_per_inverter=2, inverter=inverter,
            inverter_parameters=inverter, racking_model="open_rack",
            losses_parameters=expected_losses,
        )

        times = pd.DataFrame({"Time": pd.date_range(
            "2026-07-16", periods=2, freq="h", tz="Asia/Jakarta"
        )})
        weather = pvlib_model._build_weather_frame(
            [25, np.nan], [100, 200], [80, 160], [20, 40], [1, 2], times
        )
        self.assertEqual(weather.columns.tolist(), ["temp_air", "ghi", "dni", "dhi", "wind_speed"])
        self.assertEqual(str(weather.index[0]), "2026-07-15 23:30:00+07:00")
        self.assertEqual(weather["temp_air"].iloc[1], 0)

    def test_pvlib_instantiate_runs_modelchain_and_zeroes_nan(self):
        stages = []
        times = pd.DataFrame({"Time": pd.date_range(
            "2026-07-16", periods=2, freq="h", tz="Asia/Jakarta"
        )})
        weather = pvlib_model._build_weather_frame(
            [25, 26], [100, 200], [80, 160], [20, 40], [1, 2], times
        )
        location = types.SimpleNamespace(latitude=-6.89, longitude=107.61)
        model_chain = Mock()
        model_chain.results.ac = pd.Series([np.nan, 42.0], index=weather.index)
        model_chain_type = Mock(return_value=model_chain)
        solpos = pd.DataFrame({
            "apparent_zenith": [10.0, 20.0], "azimuth": [90.0, 91.0]
        }, index=weather.index)
        extra = [11.0, 12.0]
        relative_airmass = pd.Series([1.1, 1.2], index=weather.index)
        sky_diffuse = pd.Series([21.0, 22.0], index=weather.index)
        ground_diffuse = pd.Series([31.0, 32.0], index=weather.index)
        incidence = pd.Series([41.0, 42.0], index=weather.index)
        poa_global = pd.Series([51.0, 52.0], index=weather.index)
        poa = {"poa_global": poa_global}
        cell_temperature = pd.Series([61.0, 62.0], index=weather.index)

        def staged(name, result):
            def invoke(*args, **kwargs):
                stages.append(name)
                return result
            return Mock(side_effect=invoke)

        build_location = staged("location", location)
        build_modules = staged("modules", ("cec", "sapm"))
        build_inverter = staged("inverter", "inverter")
        build_system = staged("system", "system")
        build_weather = staged("weather", weather)
        solarposition = staged("solarposition", solpos)
        extra_radiation = staged("extra_radiation", extra)
        relative = staged("relative_airmass", relative_airmass)
        absolute = Mock()
        haydavies = staged("haydavies", sky_diffuse)
        ground = staged("ground_diffuse", ground_diffuse)
        aoi = staged("aoi", incidence)
        poa_components = staged("poa_components", poa)
        sapm_cell = staged("sapm_cell", cell_temperature)

        def create_model_chain(*args, **kwargs):
            stages.append("modelchain")
            return model_chain

        model_chain_type.side_effect = create_model_chain
        model_chain.run_model.side_effect = lambda frame: stages.append("run_model")

        with patch.object(pvlib_model, "_build_module_parameters", build_modules), \
                patch.object(pvlib_model, "_build_inverter_parameters", build_inverter), \
                patch.object(pvlib_model, "_build_location", build_location), \
                patch.object(pvlib_model, "_build_system", build_system), \
                patch.object(pvlib_model, "_build_weather_frame", build_weather), \
                patch.object(pvlib_model, "ModelChain", model_chain_type), \
                patch.object(pvlib_model.pvlib.solarposition, "get_solarposition", solarposition, create=True), \
                patch.object(pvlib_model.pvlib.irradiance, "get_extra_radiation", extra_radiation, create=True), \
                patch.object(pvlib_model.pvlib.atmosphere, "get_relative_airmass", relative, create=True), \
                patch.object(pvlib_model.pvlib.atmosphere, "get_absolute_airmass", absolute, create=True), \
                patch.object(pvlib_model.pvlib.irradiance, "haydavies", haydavies, create=True), \
                patch.object(pvlib_model.pvlib.irradiance, "get_ground_diffuse", ground, create=True), \
                patch.object(pvlib_model.pvlib.irradiance, "aoi", aoi, create=True), \
                patch.object(pvlib_model.pvlib.irradiance, "poa_components", poa_components, create=True), \
                patch.object(pvlib_model.pvlib.temperature, "sapm_cell", sapm_cell, create=True):
            result = pvlib_model.pvlib_instantiate(
                [25, 26], [100, 200], [80, 160], [20, 40], [1, 2], times
            )

        self.assertEqual(stages, [
            "location", "modules", "inverter", "system", "weather",
            "solarposition", "extra_radiation", "relative_airmass",
            "haydavies", "ground_diffuse", "aoi", "poa_components",
            "sapm_cell", "sapm_cell", "modelchain", "run_model",
        ])
        build_location.assert_called_once_with()
        build_modules.assert_called_once_with()
        build_inverter.assert_called_once_with()
        build_system.assert_called_once_with(
            "cec", "sapm", "inverter",
            {"a": -3.56, "b": -0.075},
        )
        weather_args = build_weather.call_args.args
        self.assertEqual(weather_args[:5], (
            [25, 26], [100, 200], [80, 160], [20, 40], [1, 2]
        ))
        self.assertIs(weather_args[5], times)
        solar_args = solarposition.call_args.args
        self.assertIs(solar_args[0], weather.index)
        self.assertEqual(solar_args[1:], (-6.89, 107.61))
        self.assertIs(extra_radiation.call_args.args[0], weather.index)
        pd.testing.assert_series_equal(
            relative.call_args.args[0], solpos["apparent_zenith"]
        )
        absolute.assert_not_called()

        hay_args = haydavies.call_args.args
        self.assertEqual(hay_args[:2], (2, 90))
        pd.testing.assert_series_equal(hay_args[2], weather["dhi"])
        pd.testing.assert_series_equal(hay_args[3], weather["dni"])
        pd.testing.assert_series_equal(
            hay_args[4], pd.Series(extra, index=weather.index)
        )
        pd.testing.assert_series_equal(hay_args[5], solpos["apparent_zenith"])
        pd.testing.assert_series_equal(hay_args[6], solpos["azimuth"])

        ground_args = ground.call_args.args
        self.assertEqual(ground_args[0], 2)
        pd.testing.assert_series_equal(ground_args[1], weather["ghi"])
        self.assertEqual(ground.call_args.kwargs, {"albedo": 0.2})
        aoi_args = aoi.call_args.args
        self.assertEqual(aoi_args[:2], (2, 90))
        pd.testing.assert_series_equal(aoi_args[2], solpos["apparent_zenith"])
        pd.testing.assert_series_equal(aoi_args[3], solpos["azimuth"])
        poa_args = poa_components.call_args.args
        self.assertIs(poa_args[0], incidence)
        pd.testing.assert_series_equal(poa_args[1], weather["dni"])
        self.assertIs(poa_args[2], sky_diffuse)
        self.assertIs(poa_args[3], ground_diffuse)

        self.assertEqual(sapm_cell.call_count, 2)
        for cell_call in sapm_cell.call_args_list:
            self.assertIs(cell_call.args[0], poa_global)
            pd.testing.assert_series_equal(cell_call.args[1], weather["temp_air"])
            pd.testing.assert_series_equal(cell_call.args[2], weather["wind_speed"])
            self.assertEqual(cell_call.kwargs, {"a": -3.56, "b": -0.075})
        model_chain_type.assert_called_once_with("system", location, losses_model="pvwatts")
        model_chain.run_model.assert_called_once_with(weather)
        self.assertEqual(result.columns.tolist(), ["Time", "Pac"])
        np.testing.assert_array_equal(result["Pac"], [0.0, 42.0])


if __name__ == "__main__":
    unittest.main()
