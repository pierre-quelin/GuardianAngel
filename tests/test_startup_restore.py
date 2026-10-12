from datetime import datetime, timezone, timedelta

import pytest

import database as db
from guardian_angel import GuardianAngel


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
        'database': {'url': database_url, 'retention_hours': 48},
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
        db.upsert_paraglider_state(session, 'restart-key', 'Landed', source='tracking')
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


def test_discord_confirmation_persists_without_tracking_point(startup_database):
    db.init_db_engine({'url': startup_database})
    session = db.SessionLocal()
    try:
        db.upsert_paraglider_state(session, 'restart-key', 'Alert', source='tracking')
    finally:
        session.close()

    config = _guardian_config(startup_database)
    angel = GuardianAngel(config)
    try:
        paraglider = angel.get_paraglider('Restart Pilot')
        assert paraglider.state == 'Alert'
        updates = angel._apply_confirmation_event({
            'type': 'landing_confirmed',
            'discord_id': 1,
            'paraglider_key': 'restart-key',
        })
        assert paraglider.state == 'Landed'
        assert updates == {'restart-key': 'Landed'}
        angel._persist_paraglider_states(updates, source='discord')
    finally:
        _remove_paragliders(angel)

    restarted = GuardianAngel(config)
    try:
        assert restarted.get_paraglider('Restart Pilot').state == 'Landed'
        session = db.SessionLocal()
        try:
            row = db.get_paraglider_machine_state(session, 'restart-key')
            assert row is not None
            assert row.state == 'Landed'
            assert row.source == 'discord'
        finally:
            session.close()
    finally:
        _remove_paragliders(restarted)


def test_purge_respects_retention_hours(startup_database):
    db.init_db_engine({'url': startup_database, 'retention_hours': 1})
    session = db.SessionLocal()
    try:
        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        recent = datetime.now(timezone.utc).replace(tzinfo=None)
        session.add(db.ParaglidersData(
            paraglider_key='restart-key',
            datetime=old,
            latitude=1.0,
            longitude=2.0,
            speed=1.0,
        ))
        session.add(db.ParaglidersData(
            paraglider_key='restart-key',
            datetime=recent,
            latitude=3.0,
            longitude=4.0,
            speed=2.0,
        ))
        session.commit()
        deleted = db.purge_old_data(session)
        assert deleted == 1
        remaining = session.query(db.ParaglidersData).all()
        assert len(remaining) == 1
        assert remaining[0].datetime == recent
    finally:
        session.close()
