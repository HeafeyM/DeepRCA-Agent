"""多维度对比器。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.4.3-3.4.4</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations


class MultiDimensionComparator:
    """多维度对比器。周同比、日环比。"""

    def compare_week_over_week(self, current: float, last_week: float) -> dict:
        """周同比: (current - last_week) / last_week * 100%"""
        if last_week == 0:
            change_pct = 0.0 if current == 0 else float("inf")
        else:
            change_pct = (current - last_week) / last_week * 100.0

        is_significant = abs(change_pct) > 30.0

        return {
            "week_change": round(change_pct, 2),
            "is_significant": is_significant,
        }

    def compare_day_over_day(self, current: float, yesterday: float) -> dict:
        """日环比: (current - yesterday) / yesterday * 100%"""
        if yesterday == 0:
            change_pct = 0.0 if current == 0 else float("inf")
        else:
            change_pct = (current - yesterday) / yesterday * 100.0

        is_significant = abs(change_pct) > 30.0

        return {
            "day_change": round(change_pct, 2),
            "is_significant": is_significant,
        }

    def compare(self, current: float, baselines: dict) -> dict:
        """综合对比。

        Args:
            current: 当前值
            baselines: {"last_week": float, "yesterday": float}

        Returns:
            {"week_change": float, "day_change": float, "is_significant": bool,
             "is_anomaly": bool}
            显著性判断: 变化幅度 > 30% 视为显著
        """
        last_week = baselines.get("last_week")
        yesterday = baselines.get("yesterday")

        # None / 缺失基线安全处理
        if last_week is None:
            week_result = {"week_change": None, "is_significant": False}
        else:
            week_result = self.compare_week_over_week(current, float(last_week))

        if yesterday is None:
            day_result = {"day_change": None, "is_significant": False}
        else:
            day_result = self.compare_day_over_day(current, float(yesterday))

        is_significant = week_result["is_significant"] or day_result["is_significant"]

        return {
            "week_change": week_result["week_change"],
            "day_change": day_result["day_change"],
            "is_significant": is_significant,
            "is_anomaly": is_significant,
        }