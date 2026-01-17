"""
Модуль бизнес-аналитики для проекта КМ
"""

from .new_users_analytics import NewUsersAnalytics
from .customer_lifecycle import CustomerLifecycleAnalytics
from .race_statistics import RaceStatisticsAnalytics
from .out_of_town_analytics import OutOfTownAnalytics
from .business_analytics import BusinessAnalytics

__all__ = [
    'NewUsersAnalytics',
    'CustomerLifecycleAnalytics',
    'RaceStatisticsAnalytics',
    'OutOfTownAnalytics',
    'BusinessAnalytics'
]
