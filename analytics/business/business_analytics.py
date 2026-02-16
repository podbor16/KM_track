"""
Главный модуль бизнес-аналитики, объединяющий все функции
Работает с таблицей Все заявки
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from .new_users_analytics import NewUsersAnalytics
from .customer_lifecycle import CustomerLifecycleAnalytics
from .race_statistics import RaceStatisticsAnalytics
from .out_of_town_analytics import OutOfTownAnalytics

logger = logging.getLogger(__name__)


class BusinessAnalytics:
    """
    Главный класс для бизнес-аналитики
    Объединяет все модули аналитики
    Работает с таблицей Все заявки, где каждая строка = одна регистрация на забег
    """
    
    def __init__(self, 
                 # Настройки таблицы
                 table_name: str = 'Все заявки',
                 # Настройки колонок
                 registration_date_column: str = 'created_at',
                 name_column: str = 'name',
                 surname_column: str = 'surname',
                 birthday_column: str = 'birthday',
                 city_column: str = 'city',
                 race_column: str = 'products',
                 products_column: str = 'products',
                 local_city: str = 'Красноярск'):
        """
        Инициализация модуля бизнес-аналитики
        
        Args:
            table_name: название таблицы (по умолчанию 'Все заявки')
            registration_date_column: название колонки с датой регистрации
            name_column: название колонки с именем
            surname_column: название колонки с фамилией
            birthday_column: название колонки с датой рождения
            city_column: название колонки с городом
            race_column: название колонки с названием забега (products)
            local_city: название локального города
        """
        # Инициализируем модули аналитики
        self.new_users = NewUsersAnalytics(
            table_name=table_name,
            registration_date_column=registration_date_column,
            name_column=name_column,
            surname_column=surname_column,
            birthday_column=birthday_column
        )
        
        self.customer_lifecycle = CustomerLifecycleAnalytics(
            table_name=table_name,
            registration_date_column=registration_date_column,
            name_column=name_column,
            surname_column=surname_column,
            birthday_column=birthday_column,
            products_column=products_column
        )
        
        self.race_statistics = RaceStatisticsAnalytics(
            table_name=table_name,
            race_column=race_column,
            registration_date_column=registration_date_column,
            name_column=name_column,
            surname_column=surname_column,
            birthday_column=birthday_column
        )
        
        self.out_of_town = OutOfTownAnalytics(
            table_name=table_name,
            city_column=city_column,
            race_column=race_column,
            local_city=local_city
        )
    
    def get_full_report(self, 
                       start_date: Optional[datetime] = None,
                       end_date: Optional[datetime] = None,
                       year: Optional[int] = None) -> Dict[str, Any]:
        """
        Получить полный отчет по бизнес-аналитике
        
        Args:
            start_date: начальная дата для анализа новых пользователей
            end_date: конечная дата для анализа новых пользователей
            year: год для статистики по забегам
        
        Returns:
            Полный отчет со всеми метриками
        """
        logger.info("Генерация полного отчета по бизнес-аналитике")
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'new_users': {},
            'customer_lifecycle': {},
            'race_statistics': {},
            'out_of_town': {}
        }
        
        try:
            # а) Новые пользователи
            logger.info("Анализ новых пользователей...")
            report['new_users'] = self.new_users.get_new_users_count(
                start_date=start_date,
                end_date=end_date
            )
            
            # б) Жизненный цикл клиента
            logger.info("Анализ жизненного цикла клиентов...")
            lifecycle_data = self.customer_lifecycle.calculate_customer_lifecycle()
            status_flags = self.customer_lifecycle.get_customer_status_flags()
            
            report['customer_lifecycle'] = {
                'average_lifecycle_days': lifecycle_data.get('average_lifecycle_days', 0),
                'average_lifecycle_months': lifecycle_data.get('average_lifecycle_months', 0),
                'active_customers': lifecycle_data.get('active_customers', 0),
                'inactive_customers': lifecycle_data.get('inactive_customers', 0),
                'total_customers': lifecycle_data.get('total_customers', 0),
                'active_percentage': lifecycle_data.get('active_percentage', 0),
                'inactive_percentage': lifecycle_data.get('inactive_percentage', 0),
                'status_flags_summary': {
                    'total': status_flags.get('total_customers', 0),
                    'active': status_flags.get('active_customers', 0),
                    'inactive': status_flags.get('inactive_customers', 0),
                    'active_percentage': status_flags.get('active_percentage', 0),
                    'inactive_percentage': status_flags.get('inactive_percentage', 0)
                }
            }
            
            # в) Статистика по забегам
            logger.info("Анализ статистики по забегам...")
            all_races_stats = self.race_statistics.get_race_statistics()
            avg_races_per_customer = self.race_statistics.get_average_races_per_customer()
            
            yearly_stats = None
            if year:
                yearly_stats = self.race_statistics.get_yearly_race_statistics(year=year)
            
            report['race_statistics'] = {
                'all_time': {
                    'total_races': all_races_stats.get('total_races', 0),
                    'total_participants': all_races_stats.get('total_participants', 0),
                    'total_registrations': all_races_stats.get('total_registrations', 0),
                    'average_participants_per_race': all_races_stats.get('average_participants_per_race', 0),
                    'statistics_by_year': all_races_stats.get('statistics_by_year', {})
                },
                'average_races_per_customer': avg_races_per_customer,
                'yearly_statistics': yearly_stats
            }
            
            # г) Иногородние участники
            logger.info("Анализ иногородних участников...")
            out_of_town_stats = self.out_of_town.get_out_of_town_statistics()
            out_of_town_by_race = self.out_of_town.get_out_of_town_by_race()
            
            report['out_of_town'] = {
                'overall': out_of_town_stats,
                'by_race': out_of_town_by_race
            }
            
            logger.info("Отчет успешно сгенерирован")
            
        except Exception as e:
            logger.error(f"Ошибка при генерации отчета: {e}")
            report['error'] = str(e)
        
        return report
    
    def get_new_users_report(self, 
                            start_date: Optional[datetime] = None,
                            end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Получить отчет по новым пользователям
        
        Args:
            start_date: начальная дата
            end_date: конечная дата
        
        Returns:
            Отчет по новым пользователям
        """
        return self.new_users.get_new_users_count(
            start_date=start_date,
            end_date=end_date
        )
    
    def get_customer_lifecycle_report(self, 
                                     user_name: Optional[str] = None,
                                     user_surname: Optional[str] = None,
                                     user_birthday: Optional[str] = None) -> Dict[str, Any]:
        """
        Получить отчет по жизненному циклу клиента(ов)
        
        Args:
            user_name: имя клиента (если None, то для всех)
            user_surname: фамилия клиента
            user_birthday: дата рождения клиента (формат: 'YYYY-MM-DD')
        
        Returns:
            Отчет по жизненному циклу
        """
        lifecycle = self.customer_lifecycle.calculate_customer_lifecycle(
            user_name=user_name,
            user_surname=user_surname,
            user_birthday=user_birthday
        )
        if not (user_name and user_surname and user_birthday):
            status_flags = self.customer_lifecycle.get_customer_status_flags()
            lifecycle['status_flags'] = status_flags
        return lifecycle
    
    def get_race_statistics_report(self, 
                                   race_name: Optional[str] = None,
                                   user_name: Optional[str] = None,
                                   user_surname: Optional[str] = None,
                                   user_birthday: Optional[str] = None,
                                   year: Optional[int] = None) -> Dict[str, Any]:
        """
        Получить отчет по статистике забегов
        
        Args:
            race_name: название забега
            user_name: имя клиента
            user_surname: фамилия клиента
            user_birthday: дата рождения клиента (формат: 'YYYY-MM-DD')
            year: год
        
        Returns:
            Отчет по статистике забегов
        """
        report = {}
        
        if user_name and user_surname and user_birthday:
            report['customer_statistics'] = self.race_statistics.get_customer_race_statistics(
                user_name=user_name,
                user_surname=user_surname,
                user_birthday=user_birthday
            )
        
        if race_name:
            report['race_statistics'] = self.race_statistics.get_race_statistics(race_name=race_name)
        else:
            report['all_races_statistics'] = self.race_statistics.get_race_statistics()
        
        if year:
            report['yearly_statistics'] = self.race_statistics.get_yearly_race_statistics(year=year)
        
        report['average_races_per_customer'] = self.race_statistics.get_average_races_per_customer()
        
        return report
    
    def get_out_of_town_report(self, race_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Получить отчет по иногородним участникам
        
        Args:
            race_name: название забега (если None, то по всем)
        
        Returns:
            Отчет по иногородним участникам
        """
        return self.out_of_town.get_out_of_town_statistics(race_name=race_name)
