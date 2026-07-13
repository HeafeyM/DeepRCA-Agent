"""告警队列中间件 — 检查 Redis 关联告警注入。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.2</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from deeprca.config import get_settings

logger = logging.getLogger(__name__)

__all__ = ["AlertQueueMiddleware"]


class AlertQueueMiddleware:
    """告警队列中间件。

    在 Agent 循环的 before_model 阶段检查 Redis 队列，
    如果发现与当前分析服务关联的新告警，注入到 state 中
    以补充分析上下文。
    """

    KEY_PREFIX = "deeprca:alert_queue"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """获取或创建 Redis 异步连接。"""
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=self._settings.redis_host,
                port=self._settings.redis_port,
                db=self._settings.redis_db,
                password=self._settings.redis_password or None,
                decode_responses=True,
            )
        return self._redis

    async def before_model(self, state: dict[str, Any]) -> dict[str, Any]:
        """检查 Redis 中是否有新到达的关联告警。

        如果有关联告警，将其追加到 state["messages"] 中，
        供后续 Agent 节点参考。

        Args:
            state: LangGraph 状态字典

        Returns:
            状态更新字典（可能包含新增的 messages）
        """
        alert: dict[str, Any] = state.get("alert", {})
        service_name: str = alert.get("service_name", "")

        if not service_name:
            return {}

        redis_key = f"{self.KEY_PREFIX}:{service_name}"
        try:
            redis_client = await self._get_redis()
            # LPOP 所有待处理告警（最多取 5 条，避免过多）
            raw_alerts: list[str] = []
            for _ in range(5):
                raw = await redis_client.lpop(redis_key)
                if raw is None:
                    break
                raw_alerts.append(raw)

            if not raw_alerts:
                return {}

            related_alerts: list[dict] = []
            for raw in raw_alerts:
                try:
                    related_alerts.append(json.loads(raw))
                except json.JSONDecodeError:
                    logger.warning("Invalid alert JSON in Redis key %s", redis_key)

            if not related_alerts:
                return {}

            logger.info(
                "Found %d related alerts for service %s",
                len(related_alerts),
                service_name,
            )

            return {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"检测到 {len(related_alerts)} 条关联告警，"
                            f"可能提供额外故障线索: {json.dumps(related_alerts, ensure_ascii=False)}"
                        ),
                    }
                ]
            }
        except Exception as e:
            logger.error("Failed to check alert queue for %s: %s", service_name, e)
            return {}

    async def close(self) -> None:
        """关闭 Redis 连接。"""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
