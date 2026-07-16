import sys
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


tensorflow = types.ModuleType("tensorflow")
tensorflow_keras = types.ModuleType("tensorflow.keras")
tensorflow_models = types.ModuleType("tensorflow.keras.models")
tensorflow_models.load_model = lambda path: None
tensorflow_keras.models = tensorflow_models
tensorflow.keras = tensorflow_keras

query = types.ModuleType("query")
query.get_query = lambda: None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(sys.modules, {
    "tensorflow": tensorflow,
    "tensorflow.keras": tensorflow_keras,
    "tensorflow.keras.models": tensorflow_models,
    "query": query,
}):
    from load_service_estimation import model_beban


class LoadEstimatorTest(unittest.TestCase):
    def test_prepare_minute_input_interpolates_and_keeps_yesterday_boundaries(self):
        source = pd.DataFrame({
            "timestamp": pd.to_datetime([
                "2026-07-16 00:01",
                "2026-07-16 00:03",
                "2026-07-16 23:59",
            ]),
            "meter_id": [6, 6, 6],
            "A": [10.0, 30.0, 90.0],
            "VLN": [200.0, 220.0, 240.0],
            "PF": [0.5, 0.7, 0.9],
        })

        with patch.object(
            model_beban, "get_query", return_value=source.copy()
        ) as get_query:
            result = model_beban._prepare_minute_input(
                date(2026, 7, 17), date(2026, 7, 16)
            )

        get_query.assert_called_once_with()
        self.assertEqual(len(result), 1440)
        self.assertEqual(result["index"].iloc[0], "2026-07-16 00:00")
        self.assertEqual(result["index"].iloc[-1], "2026-07-16 23:59")
        self.assertEqual(result.loc[0, ["A", "VLN", "PF"]].tolist(), [10.0, 200.0, 0.5])
        self.assertEqual(result.loc[2, ["A", "VLN", "PF"]].tolist(), [20.0, 210.0, 0.6])
        self.assertEqual(result.loc[1439, ["A", "VLN", "PF"]].tolist(), [90.0, 240.0, 0.9])
        self.assertEqual(result.loc[0, ["month", "day", "hour", "minute"]].tolist(), [7, 16, 0, 0])
        self.assertEqual(result.loc[1439, ["month", "day", "hour", "minute"]].tolist(), [7, 16, 23, 59])

    def test_power_series_uses_exact_three_phase_formula(self):
        minute_input = pd.DataFrame({
            "A": [2.0, -1.0, 0.0],
            "PF": [0.5, 0.25, 0.9],
            "VLN": [20.0, 48.0, 230.0],
        })

        result = model_beban._power_series(minute_input)

        np.testing.assert_array_equal(result, [60.0, -36.0, 0.0])

    def test_legacy_moving_average_preserves_tail_math(self):
        power = pd.Series(np.arange(1.0, 1441.0))

        result = model_beban._legacy_moving_average(power).iloc[:, 0]

        self.assertEqual(len(result), 1440)
        self.assertEqual(result.iloc[0], 30.5)
        self.assertEqual(result.iloc[1380], 1410.5)
        self.assertEqual(result.iloc[1381], 1411.0)
        self.assertEqual(result.iloc[1382], 1411.5)
        self.assertEqual(result.iloc[-1], 1440.0)

        constant = model_beban._legacy_moving_average(
            pd.Series(np.full(1440, 7.0))
        )
        np.testing.assert_array_equal(constant.iloc[:, 0], np.full(1440, 7.0))

    def test_independent_scaler_transforms_reach_tensor_and_load_scaler_inverts(self):
        minute_input = pd.DataFrame({
            "month": np.full(1440, 7.0),
            "day": np.full(1440, 17.0),
            "hour": np.arange(1440) // 60,
            "minute": np.arange(1440) % 60,
            "index": np.arange(1440),
            "meter_id": np.full(1440, 6),
            "A": np.ones(1440),
            "VLN": np.ones(1440),
            "PF": np.ones(1440),
        })
        power = pd.Series(np.full(1440, 3.0))
        moving_average = pd.DataFrame(np.arange(1440.0).reshape(-1, 1))
        scaler_instances = []

        class StatefulScaler:
            def __init__(self):
                self.number = len(scaler_instances) + 1
                self.shift = None
                self.fit_values = None
                self.inverse_values = None
                scaler_instances.append(self)

            def fit_transform(self, values):
                self.fit_values = values.copy()
                self.shift = self.number * 1000
                return values + self.shift

            def inverse_transform(self, values):
                if self.shift is None:
                    raise AssertionError("Scaler must be fitted before inverse_transform")
                self.inverse_values = values.copy()
                return values - self.shift

        class FakeModel:
            def predict(self, values):
                self.values = values
                return values[:, :, :1]

        with patch.object(model_beban, "StandardScaler", StatefulScaler):
            features, load_scaler = model_beban._assemble_model_features(
                minute_input, power, moving_average
            )
        model = FakeModel()
        prediction = model_beban._predict(model, features, load_scaler)

        self.assertEqual(len(scaler_instances), 5)
        self.assertIs(load_scaler, scaler_instances[0])
        self.assertEqual(features.shape, (1, 1440, 5))
        expected_columns = [
            np.arange(1440.0),
            np.full(1440, 17.0),
            np.full(1440, 7.0),
            np.arange(1440) // 60,
            np.arange(1440) % 60,
        ]
        for index, (scaler, expected) in enumerate(
            zip(scaler_instances, expected_columns)
        ):
            np.testing.assert_array_equal(scaler.fit_values[:, 0], expected)
            np.testing.assert_array_equal(
                features[0, :, index], expected + ((index + 1) * 1000)
            )
        self.assertIs(model.values, features)
        np.testing.assert_array_equal(
            load_scaler.inverse_values, features[0, :, :1]
        )
        for scaler in scaler_instances[1:]:
            self.assertIsNone(scaler.inverse_values)
        np.testing.assert_array_equal(prediction[:, 0], expected_columns[0])

    def test_output_has_1440_wib_minutes_and_clips_nan_and_negative(self):
        predict = np.ones((1440, 1))
        predict[0, 0] = np.nan
        predict[1, 0] = -2

        result = model_beban._output_frame(predict, date(2026, 7, 17))

        self.assertEqual(len(result), 1440)
        self.assertEqual(str(result["timestamp"].iloc[0]), "2026-07-17 00:00:00+07:00")
        self.assertEqual(str(result["timestamp"].iloc[-1]), "2026-07-17 23:59:00+07:00")
        self.assertEqual(result["daya"].iloc[0], 0)
        self.assertEqual(result["daya"].iloc[1], 0)
        self.assertEqual(result["daya"].iloc[2], 1)

    def test_get_data_selects_weekday_model_and_sequences_helpers(self):
        trace = []
        loaded_model = object()
        minute_input = object()
        power = object()
        moving_average = object()
        features = object()
        load_scaler = object()
        prediction = object()
        output = pd.DataFrame({
            "timestamp": pd.to_datetime([
                "2026-07-17 00:00",
                "2026-07-17 23:59",
            ])
        })

        class FixedDateTime:
            @classmethod
            def now(cls):
                return datetime(2026, 7, 17, 8, 30)

        def fake_load_model(path):
            trace.append(("load_model", path))
            return loaded_model

        def fake_prepare(todays, yesterday):
            trace.append(("prepare", todays, yesterday))
            return minute_input

        def fake_power(value):
            trace.append(("power", value))
            return power

        def fake_moving_average(value):
            trace.append(("moving_average", value))
            return moving_average

        def fake_assemble(input_value, power_value, average_value):
            trace.append(("assemble", input_value, power_value, average_value))
            return features, load_scaler

        def fake_predict(model, tensor, scaler):
            trace.append(("predict", model, tensor, scaler))
            return prediction

        def fake_output(value, todays):
            trace.append(("output", value, todays))
            return output

        with patch.object(model_beban, "datetime", FixedDateTime), \
                patch.object(model_beban, "load_model", fake_load_model), \
                patch.object(model_beban, "_prepare_minute_input", fake_prepare), \
                patch.object(model_beban, "_power_series", fake_power), \
                patch.object(model_beban, "_legacy_moving_average", fake_moving_average), \
                patch.object(model_beban, "_assemble_model_features", fake_assemble), \
                patch.object(model_beban, "_predict", fake_predict), \
                patch.object(model_beban, "_output_frame", fake_output):
            result = model_beban.get_data()

        self.assertIs(result, output)
        self.assertEqual(trace, [
            ("load_model", "/app/model_bebanv2/model/modelbeban_Friday"),
            ("prepare", date(2026, 7, 17), date(2026, 7, 16)),
            ("power", minute_input),
            ("moving_average", power),
            ("assemble", minute_input, power, moving_average),
            ("predict", loaded_model, features, load_scaler),
            ("output", prediction, date(2026, 7, 17)),
        ])


if __name__ == "__main__":
    unittest.main()
