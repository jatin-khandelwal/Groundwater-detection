from backend.app.services.model_service import ModelService


def test_saved_interval_is_marked_as_historical_calibration():
    service = ModelService()
    service.interval = {"edges": [10, 20, 30, 40], "res_low": [-2, -3, -4, -5, -6],
                        "res_high": [2, 3, 4, 5, 6]}
    result = service.prediction_interval(25)
    assert result["lower_m"] == 21
    assert result["upper_m"] == 29
    assert result["calibration_status"].startswith("historical_neighbor_inputs")
