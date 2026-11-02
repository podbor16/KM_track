"""Песочница siberman_demo: копия таблиц результатов из локальной siberman (спека п. 2)."""
from tools.demo.sandbox import LOCAL_HOSTS, LOCAL_PORT, _env_params, assert_local, connect  # noqa: F401
from tools.demo.sandbox import recreate as _recreate

TABLES = (
    'participants', 'checkpoints', 'checkpoint_times', 'transitions', 'stage_totals',
    'overall_results', 'race_config', 'siberman_records', 'siberman_persons',
    'siberman_person_links',
)


def recreate(src='siberman', dst='siberman_demo') -> None:
    _recreate(src, dst, TABLES)
