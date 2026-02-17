# KM_track/main.py - FastAPI Server Entry Point
"""
FastAPI сервер для трекинга бегов и аналитики
Запускает сервер на http://localhost:8000
"""
import datetime
import uvicorn
import sys
import os
from pathlib import Path

# Добавляем src директорию в путь Python
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

if __name__ == "__main__":
    # Запускаем FastAPI сервер
    uvicorn.run(
        "tracker.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Отключаем hot-reload для продакшена
        log_level="info",
    )



    def ensure_directories(self):
        """Создает необходимые директории, если они не существуют"""
        self.reports_dir.mkdir(exist_ok=True)
        (self.reports_dir / "json").mkdir(exist_ok=True)
        (self.reports_dir / "history").mkdir(exist_ok=True)
        (self.reports_dir / "summary").mkdir(exist_ok=True)

    def get_current_report_filename(self, format_type: str = "json") -> str:
        """
        Возвращает имя файла для текущего отчета

        Args:
            format_type: тип файла (json, txt, html)

        Returns:
            Имя файла
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if format_type == "json":
            return f"business_report_{timestamp}.json"
        elif format_type == "txt":
            return f"business_report_{timestamp}.txt"
        elif format_type == "html":
            return f"business_report_{timestamp}.html"
        else:
            return f"business_report_{timestamp}.json"

    def save_json_report(self, report: Dict[str, Any], filename: str = None):
        """
        Сохраняет отчет в формате JSON

        Args:
            report: данные отчета
            filename: имя файла (если None, генерируется автоматически)
        """
        if filename is None:
            filename = self.get_current_report_filename("json")

        # Путь для текущего отчета
        current_path = self.reports_dir / "json" / filename

        # Путь для обновляемого отчета
        latest_path = self.reports_dir / "json" / "business_report_latest.json"

        # Сохраняем текущий отчет
        with open(current_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)

        # Обновляем последний отчет
        with open(latest_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"Отчет сохранен в JSON: {current_path}")
        logger.info(f"Обновлен последний отчет: {latest_path}")

        return str(current_path), str(latest_path)

    def save_text_summary(self, report: Dict[str, Any], filename: str = None):
        """
        Сохраняет текстовую сводку отчета

        Args:
            report: данные отчета
            filename: имя файла (если None, генерируется автоматически)
        """
        if filename is None:
            filename = self.get_current_report_filename("txt")

        # Путь для текущей сводки
        current_path = self.reports_dir / "summary" / filename

        # Путь для обновляемой сводки
        latest_path = self.reports_dir / "summary" / "business_summary_latest.txt"

        # Генерируем текстовую сводку
        summary = self.generate_text_summary(report)

        # Сохраняем текущую сводку
        with open(current_path, 'w', encoding='utf-8') as f:
            f.write(summary)

        # Обновляем последнюю сводку
        with open(latest_path, 'w', encoding='utf-8') as f:
            f.write(summary)

        logger.info(f"Текстовая сводка сохранена: {current_path}")

        return str(current_path)

    def generate_text_summary(self, report: Dict[str, Any]) -> str:
        """
        Генерирует текстовую сводку отчета

        Args:
            report: данные отчета

        Returns:
            Текстовая сводка
        """
        summary_lines = []
        summary_lines.append("=" * 80)
        summary_lines.append("БИЗНЕС-АНАЛИТИКА: СВОДНЫЙ ОТЧЕТ")
        summary_lines.append(f"Сгенерирован: {report.get('generated_at', datetime.now().isoformat())}")
        summary_lines.append("=" * 80)

        # Новые пользователи
        new_users = report.get('new_users', {})
        summary_lines.append("\n1. НОВЫЕ ПОЛЬЗОВАТЕЛИ:")
        summary_lines.append(f"   - Новых пользователей: {new_users.get('new_users_count', 0)}")
        summary_lines.append(f"   - Период: {new_users.get('start_date', 'N/A')} - {new_users.get('end_date', 'N/A')}")
        if 'growth_percentage' in new_users:
            summary_lines.append(f"   - Рост: {new_users.get('growth_percentage', 0):.1f}%")

        # Жизненный цикл клиента
        lifecycle = report.get('customer_lifecycle', {})
        summary_lines.append("\n2. ЖИЗНЕННЫЙ ЦИКЛ КЛИЕНТА:")
        summary_lines.append(f"   - Всего клиентов: {lifecycle.get('total_customers', 0)}")
        summary_lines.append(
            f"   - Активных: {lifecycle.get('active_customers', 0)} ({lifecycle.get('active_percentage', 0):.1f}%)")
        summary_lines.append(
            f"   - Неактивных: {lifecycle.get('inactive_customers', 0)} ({lifecycle.get('inactive_percentage', 0):.1f}%)")
        summary_lines.append(f"   - Средний цикл: {lifecycle.get('average_lifecycle_days', 0):.1f} дней")

        # Статистика по забегам
        race_stats = report.get('race_statistics', {}).get('all_time', {})
        summary_lines.append("\n3. СТАТИСТИКА ПО ЗАБЕГАМ:")
        summary_lines.append(f"   - Всего забегов: {race_stats.get('total_races', 0)}")
        summary_lines.append(f"   - Всего регистраций: {race_stats.get('total_registrations', 0)}")
        summary_lines.append(f"   - Уникальных участников: {race_stats.get('total_participants', 0)}")

        # Исправляем обработку среднего забегов на клиента
        avg_races = report.get('race_statistics', {}).get('average_races_per_customer', 0)

        # Проверяем, является ли avg_races словарем
        if isinstance(avg_races, dict):
            # Если это словарь, берем значение по ключу 'average_races' или 'average'
            avg_races_value = avg_races.get('average_races', avg_races.get('average', 0))
        else:
            avg_races_value = avg_races

        # Форматируем значение
        try:
            avg_races_formatted = f"{float(avg_races_value):.1f}"
        except (ValueError, TypeError):
            avg_races_formatted = str(avg_races_value)

        summary_lines.append(f"   - Среднее забегов на клиента: {avg_races_formatted}")

        # Иногородние участники
        out_of_town = report.get('out_of_town', {}).get('overall', {})
        summary_lines.append("\n4. ИНОГОРОДНИЕ УЧАСТНИКИ:")
        summary_lines.append(f"   - Всего иногородних: {out_of_town.get('total_out_of_town', 0)}")

        # Безопасное форматирование процента
        percentage = out_of_town.get('percentage', 0)
        try:
            percentage_formatted = f"{float(percentage):.1f}%"
        except (ValueError, TypeError):
            percentage_formatted = f"{percentage}%"

        summary_lines.append(f"   - Процент от общего числа: {percentage_formatted}")

        summary_lines.append("\n" + "=" * 80)
        summary_lines.append("СИСТЕМНАЯ ИНФОРМАЦИЯ:")
        summary_lines.append(f"   - Время генерации: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        summary_lines.append(f"   - Версия отчета: {report.get('report_version', '1.0')}")

        if 'error' in report:
            summary_lines.append(f"\n⚠️ ОШИБКИ: {report['error']}")

        return "\n".join(summary_lines)

    def save_to_history(self, report: Dict[str, Any]):
        """
        Сохраняет отчет в историю

        Args:
            report: данные отчета
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_history_{timestamp}.json"
        history_path = self.reports_dir / "history" / filename

        # Добавляем метаданные
        history_report = report.copy()
        history_report['_metadata'] = {
            'saved_at': datetime.now().isoformat(),
            'version': '1.0',
            'source': 'business_analytics'
        }

        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history_report, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"Отчет сохранен в историю: {history_path}")

        # Очистка старых отчетов (сохраняем только последние 30)
        self.cleanup_old_reports(keep_last=30)

    def cleanup_old_reports(self, keep_last: int = 30):
        """
        Удаляет старые отчеты, оставляя только указанное количество

        Args:
            keep_last: сколько отчетов оставить
        """
        try:
            history_files = list((self.reports_dir / "history").glob("report_history_*.json"))
            json_files = list((self.reports_dir / "json").glob("business_report_*.json"))
            summary_files = list((self.reports_dir / "summary").glob("business_report_*.txt"))

            # Сортируем по времени создания (новые первые)
            for files, directory in [
                (history_files, self.reports_dir / "history"),
                (json_files, self.reports_dir / "json"),
                (summary_files, self.reports_dir / "summary")
            ]:
                files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

                # Удаляем старые файлы
                for old_file in files[keep_last:]:
                    old_file.unlink()
                    logger.debug(f"Удален старый файл: {old_file}")

        except Exception as e:
            logger.warning(f"Ошибка при очистке старых отчетов: {e}")

    def print_report_to_console(self, report: Dict[str, Any]):
        """Выводит сводку отчета в консоль"""
        summary = self.generate_text_summary(report)
        print("\n" + summary)


def get_date_input(prompt: str, default_date: Optional[date] = None) -> Optional[date]:
    """
    Получает дату от пользователя

    Args:
        prompt: текст подсказки
        default_date: дата по умолчанию

    Returns:
        Дата или None
    """
    try:
        date_str = input(f"{prompt} (YYYY-MM-DD или Enter для пропуска): ").strip()
        if not date_str:
            return default_date
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        print("Ошибка формата даты. Используйте YYYY-MM-DD")
        return get_date_input(prompt, default_date)


def main():
    """Основная функция"""
    logger.info("=" * 80)
    logger.info("ЗАПУСК СИСТЕМЫ БИЗНЕС-АНАЛИТИКИ")
    logger.info("=" * 80)

    # Инициализация менеджера отчетов
    report_manager = ReportManager()

    try:
        # Запрашиваем параметры у пользователя
        print("\n" + "=" * 80)
        print("НАСТРОЙКА ПАРАМЕТРОВ ОТЧЕТА")
        print("=" * 80)

        # Даты для анализа новых пользователей
        use_custom_dates = input("Использовать кастомные даты для анализа новых пользователей? (y/N): ").lower() == 'y'

        start_date = None
        end_date = None

        if use_custom_dates:
            today = date.today()
            start_date_input = get_date_input("Начальная дата", date(today.year, 1, 1))
            end_date_input = get_date_input("Конечная дата", today)

            if start_date_input and end_date_input:
                start_date = datetime.combine(start_date_input, datetime.min.time())
                end_date = datetime.combine(end_date_input, datetime.max.time())

        # Год для статистики по забегам
        year_input = input(f"Год для статистики по забегам (Enter для текущего {datetime.now().year}): ").strip()
        year = int(year_input) if year_input else datetime.now().year

        # Инициализация аналитики
        logger.info("Инициализация модуля бизнес-аналитики...")
        analytics = BusinessAnalytics()

        # Генерация отчета
        logger.info("Генерация полного отчета...")
        report = analytics.get_full_report(
            start_date=start_date,
            end_date=end_date,
            year=year
        )

        # Добавляем метаданные
        report['report_version'] = '1.0'
        report['generation_parameters'] = {
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'year': year,
            'generated_at': datetime.now().isoformat()
        }

        # Сохранение отчетов
        logger.info("Сохранение отчетов...")

        # JSON отчет
        json_current, json_latest = report_manager.save_json_report(report)

        # Текстовая сводка
        text_summary = report_manager.save_text_summary(report)

        # Сохранение в историю
        report_manager.save_to_history(report)

        # Вывод в консоль
        report_manager.print_report_to_console(report)

        # Статистика файлов
        logger.info("=" * 80)
        logger.info("СТАТИСТИКА СОХРАНЕННЫХ ФАЙЛОВ:")
        logger.info(f"  • Полный отчет (JSON): {json_current}")
        logger.info(f"  • Последний отчет (JSON): {json_latest}")
        logger.info(f"  • Текстовая сводка: {text_summary}")
        logger.info(f"  • Логи: analytics.log")
        logger.info("=" * 80)

        print(f"\n✅ Отчет успешно сгенерирован и сохранен!")
        print(f"📊 Для просмотра откройте файл: {json_latest}")

        # Дополнительные опции
        print("\n" + "=" * 80)
        print("ДОПОЛНИТЕЛЬНЫЕ ОПЦИИ:")
        print("=" * 80)
        print("1 - Создать отчет по новым пользователям")
        print("2 - Создать отчет по жизненному циклу")
        print("3 - Создать отчет по забегам")
        print("4 - Создать отчет по иногородним")
        print("0 - Выйти")

        choice = input("\nВыберите опцию (0-4): ").strip()

        if choice == "1":
            create_new_users_report(analytics, report_manager)
        elif choice == "2":
            create_lifecycle_report(analytics, report_manager)
        elif choice == "3":
            create_race_report(analytics, report_manager)
        elif choice == "4":
            create_out_of_town_report(analytics, report_manager)

    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении: {e}", exc_info=True)
        print(f"\n❌ Произошла ошибка: {e}")
        print("Подробности смотрите в файле analytics.log")


def create_new_users_report(analytics: BusinessAnalytics, report_manager: ReportManager):
    """Создает отчет по новым пользователям"""
    print("\n" + "=" * 80)
    print("ОТЧЕТ ПО НОВЫМ ПОЛЬЗОВАТЕЛЯМ")
    print("=" * 80)

    start_date_input = get_date_input("Начальная дата")
    end_date_input = get_date_input("Конечная дата")

    start_date = None
    end_date = None

    if start_date_input and end_date_input:
        start_date = datetime.combine(start_date_input, datetime.min.time())
        end_date = datetime.combine(end_date_input, datetime.max.time())

    report = analytics.get_new_users_report(start_date=start_date, end_date=end_date)

    # Сохранение
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"new_users_{timestamp}.json"
    path = report_manager.reports_dir / "json" / filename

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n✅ Отчет по новым пользователям сохранен: {path}")


def create_lifecycle_report(analytics: BusinessAnalytics, report_manager: ReportManager):
    """Создает отчет по жизненному циклу"""
    print("\n" + "=" * 80)
    print("ОТЧЕТ ПО ЖИЗНЕННОМУ ЦИКЛУ КЛИЕНТОВ")
    print("=" * 80)

    print("Для отчета по всем клиентам оставьте поля пустыми")
    name = input("Имя клиента (Enter для пропуска): ").strip() or None
    surname = input("Фамилия клиента (Enter для пропуска): ").strip() or None
    birthday = input("Дата рождения (YYYY-MM-DD, Enter для пропуска): ").strip() or None

    report = analytics.get_customer_lifecycle_report(
        user_name=name,
        user_surname=surname,
        user_birthday=birthday
    )

    # Сохранение
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"lifecycle_{timestamp}.json"
    path = report_manager.reports_dir / "json" / filename

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n✅ Отчет по жизненному циклу сохранен: {path}")


def create_race_report(analytics: BusinessAnalytics, report_manager: ReportManager):
    """Создает отчет по забегам"""
    print("\n" + "=" * 80)
    print("ОТЧЕТ ПО ЗАБЕГАМ")
    print("=" * 80)

    race_name = input("Название забега (Enter для всех): ").strip() or None
    name = input("Имя участника (Enter для пропуска): ").strip() or None
    surname = input("Фамилия участника (Enter для пропуска): ").strip() or None
    birthday = input("Дата рождения участника (YYYY-MM-DD, Enter для пропуска): ").strip() or None

    year_input = input(f"Год (Enter для текущего {datetime.now().year}): ").strip()
    year = int(year_input) if year_input else None

    report = analytics.get_race_statistics_report(
        race_name=race_name,
        user_name=name,
        user_surname=surname,
        user_birthday=birthday,
        year=year
    )

    # Сохранение
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"races_{timestamp}.json"
    path = report_manager.reports_dir / "json" / filename

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n✅ Отчет по забегам сохранен: {path}")


def create_out_of_town_report(analytics: BusinessAnalytics, report_manager: ReportManager):
    """Создает отчет по иногородним участникам"""
    print("\n" + "=" * 80)
    print("ОТЧЕТ ПО ИНОГОРОДНИМ УЧАСТНИКАМ")
    print("=" * 80)

    race_name = input("Название забега (Enter для всех): ").strip() or None

    report = analytics.get_out_of_town_report(race_name=race_name)

    # Сохранение
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"out_of_town_{timestamp}.json"
    path = report_manager.reports_dir / "json" / filename

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n✅ Отчет по иногородним участникам сохранен: {path}")


if __name__ == "__main__":
    main()