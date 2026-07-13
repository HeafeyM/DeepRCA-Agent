"""多维度对比器单元测试。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from deeprca.detection.comparator import MultiDimensionComparator


class TestMultiDimensionComparator:
    """周同比 + 日环比对比器测试。"""

    def setup_method(self):
        self.comparator = MultiDimensionComparator()

    def test_normal_comparison(self):
        """正常波动不应标记异常。"""
        result = self.comparator.compare(
            current=100.0,
            baselines={"last_week": 95.0, "yesterday": 98.0},
        )
        assert not result.get("is_anomaly", False)

    def test_significant_increase(self):
        """显著增长应标记异常。"""
        result = self.comparator.compare(
            current=200.0,
            baselines={"last_week": 100.0, "yesterday": 105.0},
        )
        assert result.get("is_anomaly", False)

    def test_significant_decrease(self):
        """显著下降应标记异常。"""
        result = self.comparator.compare(
            current=10.0,
            baselines={"last_week": 100.0, "yesterday": 95.0},
        )
        assert result.get("is_anomaly", False)

    def test_missing_baseline(self):
        """缺失基线应安全处理。"""
        result = self.comparator.compare(
            current=100.0,
            baselines={"last_week": None, "yesterday": None},
        )
        assert not result.get("is_anomaly", False)

    def test_zero_baseline(self):
        """基线为零时应安全处理。"""
        result = self.comparator.compare(
            current=100.0,
            baselines={"last_week": 0.0, "yesterday": 0.0},
        )
        assert result is not None

    def test_result_not_none(self):
        """结果不应为 None。"""
        result = self.comparator.compare(
            current=150.0,
            baselines={"last_week": 100.0, "yesterday": 120.0},
        )
        assert result is not None
