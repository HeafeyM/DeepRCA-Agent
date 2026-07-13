"""量化异常检测算法单元测试。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from deeprca.detection.quantile import QuantileAnomalyDetector


class TestQuantileAnomalyDetector:
    """四分位 IQR 异常检测测试。"""

    def setup_method(self):
        self.detector = QuantileAnomalyDetector()

    def test_normal_value_no_anomaly(self):
        """正常值不应触发异常。"""
        baseline = [10.0, 11.0, 10.5, 11.5, 10.2, 10.8, 11.2, 10.9, 10.3, 11.0]
        result = self.detector.detect(baseline, 10.7)
        assert not result["is_anomaly"]

    def test_high_outlier_anomaly(self):
        """远高于上界的值应触发异常。"""
        baseline = [10.0, 11.0, 10.5, 11.5, 10.2, 10.8, 11.2, 10.9, 10.3, 11.0]
        result = self.detector.detect(baseline, 100.0)
        assert result["is_anomaly"]
        assert result["score"] > 0.5

    def test_low_outlier_anomaly(self):
        """远低于下界的值应触发异常。"""
        baseline = [10.0, 11.0, 10.5, 11.5, 10.2, 10.8, 11.2, 10.9, 10.3, 11.0]
        result = self.detector.detect(baseline, -50.0)
        assert result["is_anomaly"]

    def test_empty_baseline(self):
        """空基线应安全返回。"""
        result = self.detector.detect([], 10.0)
        assert not result["is_anomaly"]

    def test_single_point_baseline(self):
        """单点基线应安全处理。"""
        result = self.detector.detect([10.0], 10.0)
        assert not result["is_anomaly"]

    def test_bounds_present(self):
        """结果应包含上下界。"""
        baseline = [10.0, 11.0, 10.5, 11.5, 10.2, 10.8, 11.2, 10.9, 10.3, 11.0]
        result = self.detector.detect(baseline, 10.7)
        assert "bounds" in result
        assert "lower" in result["bounds"]
        assert "upper" in result["bounds"]

    def test_median_present(self):
        """结果应包含中位数。"""
        baseline = [10.0, 11.0, 10.5, 11.5, 10.2, 10.8, 11.2, 10.9, 10.3, 11.0]
        result = self.detector.detect(baseline, 10.7)
        assert "median" in result

    def test_deviation_present(self):
        """结果应包含偏离度。"""
        baseline = [10.0, 11.0, 10.5, 11.5, 10.2, 10.8, 11.2, 10.9, 10.3, 11.0]
        result = self.detector.detect(baseline, 100.0)
        assert "deviation" in result
        assert result["deviation"] > 0
