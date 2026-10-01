from datetime import datetime, timezone

import pytest

import database as db
from guardian_angel import GuardianAngel
from paraglider import Paraglider


@pytest.fixture
def startup_database(tmp_path, monkeypatch):
    engines = []
    original_init_db_engine = db.init_db_engine
    monkeypatch.setattr(db, 'SessionLocal', db.SessionLocal)

    def init_db_engine(cfg):
        engine = original_init_db_engine(cfg)
        engines.append(engine)
        return engine

    monkeypatch.setattr(db, 'init_db_engine', init_db_engine)
    database_url = f'sqlite:///{tmp_path / "startup.db"}'
    yield database_url

    for engine in engines:
        engine.dispose()


def _guardian_config(database_url):
    return {
        'database': {'url': database_url},
        'paragliders': [
            {'name': 'Restart Pilot', 'puretrack_key': 'restart-key'},
            {'name': 'No History Pilot', 'puretrack_key': 'missing-key'},
        ],
    }


def _remove_paragliders(angel):
    for paraglider in list(angel._paragliders):
        angel.remove_paraglider(paraglider.name)


def test_paraglider_state_is_restored_after_restart(startup_database):
    db.init_db_engine({'url': startup_database})
    session = db.SessionLocal()
    try:
        session.add(db.ParaglidersData(
            paraglider_key='restart-key',
            datetime=datetime.now(timezone.utc).replace(tzinfo=None),
            state='Landed',
        ))
        session.commit()
    finally:
        session.close()

    config = _guardian_config(startup_database)
    first_angel = GuardianAngel(config)
    try:
        assert first_angel.get_paraglider('Restart Pilot').state == 'Landed'
        assert first_angel.get_paraglider('No History Pilot').state == 'Unknown'
        first_angel._persist_paraglider_states({'restart-key': 'Flying'})
    finally:
        _remove_paragliders(first_angel)

    restarted_angel = GuardianAngel(config)
    try:
        assert restarted_angel.get_paraglider('Restart Pilot').state == 'Flying'
        assert restarted_angel.get_paraglider('No History Pilot').state == 'Unknown'
    finally:
        _remove_paragliders(restarted_angel)