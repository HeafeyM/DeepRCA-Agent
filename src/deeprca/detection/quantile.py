"""四分位 IQR 异常检测器。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.4.3-3.4.4</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import numpy as np


class QuantileAnomalyDetector:
    """四分位 IQR 异常检测器。确定性算法，不依赖 LLM。"""

    def detect(self, baseline: list[float], current: float) -> dict:
        """检测当前值是否异常。

        算法:
        1. Q1=25th percentile, Q3=75th percentile
        2. IQR = Q3 - Q1
        3. lower = Q1 - 1.5*IQR, upper = Q3 + 1.5*IQR
        4. median = np.median(baseline)
        5. deviation_ratio = current/median (if median != 0)
        6. is_anomaly = current > upper OR current < lower OR deviation_ratio > 3.0

        Returns:
            {"is_anomaly": bool, "score": float, "deviation": float,
             "bounds": {"lower": float, "upper": float}, "median": float}
        """
        arr = np.array(baseline, dtype=float)

        if arr.size == 0:
            return {
                "is_anomaly": False,
                "score": 0.0,
                "deviation": 0.0,
                "bounds": {"lower": 0.0, "upper": 0.0},
                "median": 0.0,
            }

        q1 = float(np.percentile(arr, 25))
        q3 = float(np.percentile(arr, 75))
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        median = float(np.median(arr))

        # 偏离比率
        if median != 0:
            deviation_ratio = abs(current / median)
        else:
            deviation_ratio = 0.0 if current == 0 else float("inf")

        # 异常判定
        is_anomaly = (
            current > upper
            or current < lower
            or deviation_ratio > 3.0
        )

        # 异常分数: 基于偏离 IQR 边界的距离，归一化到 0.0~1.0
        if iqr > 0:
            if current > upper:
                score = min((current - upper) / (iqr * 3.0) + 0.5, 1.0)
            elif current < lower:
                score = min((lower - current) / (iqr * 3.0) + 0.5, 1.0)
            else:
                # 在 IQR 范围内，基于偏离 median 的程度
                score = min(deviation_ratio / 3.0 * 0.5, 0.5) if deviation_ratio > 1.0 else deviation_ratio * 0.5
        else:
            # IQR=0 时所有基线值相同，任何偏离即为异常
            score = 1.0 if current != median else 0.0

        score = max(0.0, min(1.0, score))

        return {
            "is_anomaly": is_anomaly,
            "score": round(score, 4),
            "deviation": round(deviation_ratio, 4),
            "bounds": {"lower": round(lower, 4), "upper": round(upper, 4)},
            "median": round(median, 4),
        }
