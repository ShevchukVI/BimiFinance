"""Gamification: achievements and streaks for user engagement.

Lightweight — no complex event tracking. Predefined achievement types
are checked on-demand when user views stats.
"""
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class Achievement:
    key: str
    name: str
    icon: str
    description: str

    def check(self, stats: Dict[str, Any]) -> bool:
        """Override in subclasses."""
        return False


class TransactionCountAchievement(Achievement):
    def __init__(self, key: str, name: str, icon: str, description: str, threshold: int):
        super().__init__(key, name, icon, description)
        self.threshold = threshold

    def check(self, stats: Dict[str, Any]) -> bool:
        return stats.get("total_transactions", 0) >= self.threshold


class StreakAchievement(Achievement):
    def __init__(self, key: str, name: str, icon: str, description: str, threshold_days: int):
        super().__init__(key, name, icon, description)
        self.threshold_days = threshold_days

    def check(self, stats: Dict[str, Any]) -> bool:
        return stats.get("current_streak_days", 0) >= self.threshold_days


class SavingsAchievement(Achievement):
    def __init__(self, key: str, name: str, icon: str, description: str, threshold: float):
        super().__init__(key, name, icon, description)
        self.threshold = threshold

    def check(self, stats: Dict[str, Any]) -> bool:
        return stats.get("total_saved", 0) >= self.threshold


ALL_ACHIEVEMENTS: List[Achievement] = [
    TransactionCountAchievement("tx_1", "Перша транзакція", "🌟", "Додано першу транзакцію", 1),
    TransactionCountAchievement("tx_10", "Досвідчений", "📊", "Додано 10 транзакцій", 10),
    TransactionCountAchievement("tx_50", "Фінансист", "🏆", "Додано 50 транзакцій", 50),
    TransactionCountAchievement("tx_100", "Маестро бюджету", "👑", "Додано 100 транзакцій", 100),
    StreakAchievement("streak_7", "Тиждень підряд", "🔥", "Активність 7 днів підряд", 7),
    SavingsAchievement("save_1000", "Перша тисяча", "💰", "Накопичено 1000 грн", 1000),
    SavingsAchievement("save_10000", "Фінансова подушка", "🏦", "Накопичено 10000 грн", 10000),
]


def get_earned_achievements(stats: Dict[str, Any]) -> List[Achievement]:
    return [a for a in ALL_ACHIEVEMENTS if a.check(stats)]
