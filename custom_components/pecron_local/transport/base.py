# custom_components/pecron_local/transport/base.py
from __future__ import annotations
from abc import ABC, abstractmethod


class TransportError(Exception):
    """Raised when a transport operation fails."""


class PecronTransport(ABC):
    """Abstract transport interface for Pecron local communication."""

    @property
    @abstractmethod
    def connected(self) -> bool:
        """True if transport has an active authenticated session."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection and perform handshake. Raises TransportError on failure."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""

    @abstractmethod
    async def read(self) -> dict:
        """Send read command and return parsed kv dict. Raises TransportError on failure."""

    @abstractmethod
    async def write(self, data_point_id: int, value: object, ctrl_type: str) -> None:
        """Send write command. Raises TransportError on failure."""
