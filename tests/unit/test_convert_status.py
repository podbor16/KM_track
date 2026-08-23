"""Тесты для convert_status() — маппинг статуса участника из Copernico в
формат БД. Найдено на живых данных Жары 21.1км 2026-08-23: Copernico
реально присылает 'retired' для сошедших с дистанции (не 'dnf'), это
значение не было в маппинге и тихо попадало в дефолт 'Not started' —
15 реально сошедших участников показывались как "не стартовавшие"."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from load_race_results import convert_status


class TestConvertStatus:
    def test_retired_maps_to_dnf(self):
        """Реальное значение Copernico для сошедших — 'retired', не 'dnf'."""
        assert convert_status('retired') == 'DNF'

    def test_retired_case_insensitive(self):
        assert convert_status('Retired') == 'DNF'

    def test_dnf_still_works(self):
        assert convert_status('dnf') == 'DNF'

    def test_disqualified_maps_to_dsq(self):
        assert convert_status('disqualified') == 'DSQ'

    def test_dsq_still_works(self):
        assert convert_status('dsq') == 'DSQ'

    def test_finished(self):
        assert convert_status('finished') == 'Finished'

    def test_running(self):
        assert convert_status('running') == 'Running'

    def test_notstarted(self):
        assert convert_status('notstarted') == 'Not started'

    def test_withdrawn(self):
        assert convert_status('withdrawn') == 'Withdrawn'

    def test_unknown_status_defaults_to_not_started(self):
        assert convert_status('some_new_copernico_status') == 'Not started'

    def test_none_defaults_to_not_started(self):
        assert convert_status(None) == 'Not started'

    def test_empty_string_defaults_to_not_started(self):
        assert convert_status('') == 'Not started'
