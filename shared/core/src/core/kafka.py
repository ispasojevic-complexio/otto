"""Kafka producer abstraction (async)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class KafkaProducer(Protocol):
    """Async Kafka producer. Implementation-agnostic."""

    async def send(
        self,
        topic: str,
        value: bytes,
        key: bytes | None = None,
    ) -> None:
        """Send a message to the topic. Key is optional (for partitioning)."""
        ...

    async def close(self) -> None:
        """Close the producer and release resources."""
        ...


class AIOKafkaProducer:
    """Thin wrapper around aiokafka.AIOKafkaProducer."""

    def __init__(self, bootstrap_servers: str) -> None:
        from aiokafka import AIOKafkaProducer as _AIOKafkaProducer

        self._bootstrap_servers = bootstrap_servers
        self._producer: _AIOKafkaProducer | None = None

    async def start(self) -> None:
        from aiokafka import AIOKafkaProducer as _AIOKafkaProducer

        if self._producer is not None:
            return
        self._producer = _AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers)
        await self._producer.start()

    async def send(
        self,
        topic: str,
        value: bytes,
        key: bytes | None = None,
    ) -> None:
        if self._producer is None:
            await self.start()
        assert self._producer is not None
        await self._producer.send_and_wait(topic, value=value, key=key)

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
