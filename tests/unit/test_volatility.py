"""波动突变检测算法单元测试。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from deeprca.detection.volatility import VolatilityDetector


class TestVolatilityDetector:
    """波动性突变检测测试。"""

    def setup_method(self):
        self.detector = VolatilityDetector()

    def test_stable_series_no_spike(self):
        """稳定序列不应检测到突变。"""
        series = [10.0] * 20
        results = self.detector.detect(series)
        spikes = [r for r in results if r["is_spike"]]
        assert len(spikes) == 0

    def test_sudden_spike_detected(self):
        """突然放大的波动应检测到突变。"""
        series = [10.0] * 10 + [100.0, 10.0, 10.0, 10.0, 10.0]
        results = self.detector.detect(series)
        spikes = [r for r in results if r["is_spike"]]
        assert len(spikes) > 0

    def test_empty_series(self):
        """空序列应安全返回。"""
        results = self.detector.detect([])
        assert len(results) == 0

    def test_short_series(self):
        """过短序列应安全返回。"""
        results = self.detector.detect([1.0, 2.0, 3.0])
        assert len(results) == 0

    def test_result_fields(self):
        """结果应包含必要字段。"""
        series = [10.0] * 10 + [100.0, 10.0, 10.0, 10.0, 10.0]
        results = self.detector.detect(series)
        if results:
            r = results[0]
            assert "is_spike" in r
