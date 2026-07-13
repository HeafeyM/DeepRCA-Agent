"""满意度推送中间件 — 分析完成后延迟触发满意度反馈。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.2</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from deeprca.config import get_settings

logger = logging.getLogger(__name__)

__all__ = ["SatisfactionPushMiddleware"]


class SatisfactionPushMiddleware:
    """满意度推送中间件。

    在 Agent 循环的 after_agent 阶段（分析完成后），
    发送 Kafka 延迟消息触发满意度推送。
    使用 kafka-python 的 KafkaProducer（同步客户端），
    通过 run_in_executor 包装为异步调用。
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._producer = None
        self._executor: asyncio.ThreadPoolExecutor | None = None

    async def after_agent(self, state: dict[str, Any]) -> dict[str, Any]:
        """分析完成后发送 Kafka 延迟满意度推送消息。

        Args:
            state: LangGraph 状态字典

        Returns:
            状态更新字典（包含推送状态信息）
        """
        trace_id = state.get("trace_id", "")
        alert = state.get("alert", {})
        alert_id = alert.get("alert_id", "")

        if not trace_id:
            logger.warning("Cannot push satisfaction: missing trace_id")
            return {}

        # 计算推送时间（当前时间 + 延迟）
        delay_seconds = self._settings.satisfaction_push_delay
        push_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)

        message: dict[str, Any] = {
            "trace_id": trace_id,
            "alert_id": alert_id,
            "push_time": push_time.isoformat(),
            "push_delay_ms": self._settings.kafka_feedback_delay_ms,
            "type": "satisfaction_survey",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            await self._send_kafka_message(message)
            logger.info(
                "Satisfaction push scheduled for trace_id=%s, push_time=%s",
                trace_id,
                push_time.isoformat(),
            )
            return {
                "messages": [
                    {
                        "role": "system",
                        "content": f"满意度推送已调度，将在 {push_time.isoformat()} 触发。",
                    }
                ]
            }
        except Exception as e:
            logger.error("Failed to send satisfaction push for trace_id=%s: %s", trace_id, e)
            return {
                "messages": [
                    {
                        "role": "system",
                        "content": f"满意度推送调度失败: {e}",
                    }
                ]
            }

    async def _send_kafka_message(self, message: dict[str, Any]) -> None:
        """通过 KafkaProducer 发送延迟消息（异步包装）。

        KafkaProducer 是同步的，使用 run_in_executor 避免阻塞事件循环。

        Args:
            message: 要发送的消息字典
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._get_executor(), self._sync_send, message)

    def _sync_send(self, message: dict[str, Any]) -> None:
        """同步发送 Kafka 消息。

        Args:
            message: 要发送的消息字典
        """
        from kafka import KafkaProducer  # type: ignore[import-untyped]

        if self._producer is None:
            self._producer = KafkaProducer(
                bootstrap_servers=self._settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks=1,
                retries=3,
            )

        future = self._producer.send(
            self._settings.kafka_feedback_topic,
            key=message.get("trace_id", ""),
            value=message,
        )
        # 等待发送完成（带超时）
        future.get(timeout=10)

    def _get_executor(self) -> asyncio.ThreadPoolExecutor:
        """获取或创建线程池执行器。"""
        if self._executor is None:
            self._executor = asyncio.ThreadPoolExecutor(max_workers=2, thread_name_prefix="kafka-producer")
        return self._executor

    def close(self) -> None:
        """清理资源。"""
        if self._producer is not None:
            try:
                self._producer.flush(timeout=5)
                self._producer.close()
            except Exception as e:
                logger.error("Error closing Kafka producer: %s", e)
            finally:
                self._producer = None

        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None
