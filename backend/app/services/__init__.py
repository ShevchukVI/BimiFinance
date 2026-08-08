"""Bank provider abstraction — minimal interface for banking integrations.

Future providers: PrivatBank, Sense Bank, etc.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class BankAccount:
    external_id: str
    name: str
    balance: float
    credit_limit: float = 0.0

@dataclass
class BankTransaction:
    external_id: str
    amount: float
    description: str
    timestamp: str


class BankProvider(ABC):
    @abstractmethod
    async def get_accounts(self, token: str) -> List[BankAccount]:
        """Fetch all accounts for this bank token."""

    @abstractmethod
    async def get_balance(self, token: str) -> float:
        """Aggregate balance across all accounts (in hryvnia)."""

    @abstractmethod
    async def register_webhook(self, token: str, webhook_url: str) -> bool:
        """Register a webhook for statement updates."""

    @abstractmethod
    async def get_recent_transactions(self, token: str, account_id: str, limit: int = 50) -> List[BankTransaction]:
        """Pull recent transactions (used for polling-based sync)."""
