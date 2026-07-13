"""波动检测器。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.4.3-3.4.4</td></tr>
<tr><td>0.2.0</td><td>修复: 基线排除当前窗口，避免尖峰膨胀全局 std 导致漏检</td><td>BUGFIX</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import numpy as np


class VolatilityDetector:
    """波动检测器。检测时序数据的波动异常。"""

    def detect(self, series: list[float], window: int = 5) -> list[dict]:
        """检测时序中的波动突变点。

        算法:
        1. 对每个滑动窗口计算标准差
        2. 基线 = 排除当前窗口后剩余序列的标准差（避免尖峰膨胀基线）
        3. 窗口标准差 > 3*基线标准差 → 突变点

        Returns:
            [{"index": int, "value": float, "volatility": float, "is_spike": bool}]
        """
        arr = np.array(series, dtype=float)
        n = arr.size

        if n < window * 2 or n == 0:
            return []

        results: list[dict] = []

        for i in range(n - window + 1):
            window_slice = arr[i : i + window]
            window_std = float(np.std(window_slice))

            # 基线: 排除当前窗口后的剩余序列
            mask = np.ones(n, dtype=bool)
            mask[i : i + window] = False
            baseline_data = arr[mask]
            baseline_std = float(np.std(baseline_data)) if baseline_data.size > 0 else 0.0

            if baseline_std == 0:
                # 基线完全稳定，任何非零波动都是突变
                is_spike = window_std > 0
            else:
                is_spike = window_std > 3.0 * baseline_std

            results.append(
                {
                    "index": i,
                    "value": round(float(arr[i]), 4),
                    "volatility": round(window_std, 4),
                    "is_spike": is_spike,
                }
            )

        return results
