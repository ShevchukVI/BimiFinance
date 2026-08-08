"""Entitlement model: feature flags, limits, and subscription tiers.

Plan tiers (CURRENT: everyone is FREE until payment integration exists):

FREE_TIER:
- unlimited manual transactions
- 2 family members
- 20 AI receipts/month
- 3 jars
- 6 months transaction history
- basic statistics

PREMIUM_TIER:
- unlimited family members
- unlimited AI receipts
- unlimited jars
- unlimited history
- advanced reports
- CSV export
- AI insights
- smart utilities (future)
"""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class TierLimits:
    max_family_members: int = 2
    max_ai_receipts_per_month: int = 20
    max_jars: int = 3
    max_history_months: int = 6


TIERS: Dict[str, TierLimits] = {
    "free": TierLimits(),
    "premium": TierLimits(
        max_family_members=999,
        max_ai_receipts_per_month=999,
        max_jars=50,
        max_history_months=999,
    ),
}


def get_user_tier(user_id: int, db=None) -> str:
    """Currently all users are FREE. Future: check db for subscription."""
    return "free"


def get_limits(user_id: int, db=None) -> TierLimits:
    return TIERS[get_user_tier(user_id, db)]


def check_ai_receipt_quota(user_id: int, used_this_month: int, db=None) -> bool:
    return used_this_month < get_limits(user_id, db).max_ai_receipts_per_month


def can_add_member(family_id: int, current_members: int, db=None) -> bool:
    return current_members < TIERS["free"].max_family_members
