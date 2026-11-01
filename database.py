from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

Base = declarative_base()
SessionLocal = None  # La session sera configurée dynamiquement
_retention_hours = 48


class ParaglidersData(Base):
    __tablename__ = 'paraglider_data'
    id = Column(Integer, primary_key=True, index=True)
    paraglider_key = Column(String, index=True)
    datetime = Column(DateTime, nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    course = Column(Float)
    speed = Column(Float)
    speed_calc = Column(Float)
    altitude = Column(Float)
    altitude_gnd_calc = Column(Float)


class ParagliderState(Base):
    __tablename__ = 'paraglider_state'
    paraglider_key = Column(String, primary_key=True)
    state = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    source = Column(String, nullable=False, default='tracking')


def init_db_engine(cfg):
    """
    Initialize the database engine and session.

    Args:
        cfg (dict): Configuration for the db engine
    """
    global SessionLocal, _retention_hours
    cfg = cfg or {}
    url = cfg.get('url')
    _retention_hours = int(cfg.get('retention_hours', 48))
    engine_kwargs = {}
    # SQLite connections are thread-bound by default. GuardianAngel runs DB work
    # via asyncio.to_thread, so disable the check and avoid pooled reuse across
    # worker threads (NullPool = one connection per checkout).
    if url and url.startswith('sqlite'):
        engine_kwargs['connect_args'] = {'check_same_thread': False}
        engine_kwargs['poolclass'] = NullPool

    engine = create_engine(url, **engine_kwargs)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(engine)
    _migrate_legacy_state_column(engine)
    return engine


def get_retention_hours():
    return _retention_hours


def _migrate_legacy_state_column(engine):
    """Move state off paraglider_data into paraglider_state when upgrading an old DB."""
    inspector = inspect(engine)
    if 'paraglider_data' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('paraglider_data')}
    if 'state' not in columns:
        return

    with engine.begin() as connection:
        rows = connection.execute(text(
            """
            SELECT paraglider_key, state, datetime
            FROM paraglider_data
            WHERE state IS NOT NULL
            ORDER BY datetime ASC
            """
        )).fetchall()
        latest_by_key = {}
        for paraglider_key, state, point_datetime in rows:
            latest_by_key[paraglider_key] = (state, point_datetime)
        for paraglider_key, (state, point_datetime) in latest_by_key.items():
            connection.execute(
                text(
                    """
                    INSERT INTO paraglider_state (paraglider_key, state, updated_at, source)
                    VALUES (:key, :state, :updated_at, :source)
                    ON CONFLICT(paraglider_key) DO UPDATE SET
                        state=excluded.state,
                        updated_at=excluded.updated_at,
                        source=excluded.source
                    """
                ),
                {
                    'key': paraglider_key,
                    'state': state,
                    'updated_at': point_datetime or datetime.now(timezone.utc).replace(tzinfo=None),
                    'source': 'tracking',
                },
            )
        # SQLite 3.35+ supports DROP COLUMN; leave the column if unsupported.
        try:
            connection.execute(text('ALTER TABLE paraglider_data DROP COLUMN state'))
        except Exception:
            pass


def save_paraglider_point(session: Session, paraglider_key, point):
    """
    Save a single paraglider point to the database.

    Args:
        session (Session): SQLAlchemy session.
        point (dict): A dictionary containing the point data.
    """
    paraglider_data = ParaglidersData(
        paraglider_key=paraglider_key,
        datetime=point['datetime'],
        latitude=point['lat'],
        longitude=point['lon'],
        course=point.get('course'),
        speed=point.get('speed'),
        speed_calc=point.get('speed_calc'),
        altitude=point.get('alt_gps'),
        altitude_gnd_calc=point.get('alt_gnd_calc'),
    )
    session.add(paraglider_data)


def update_paraglider_data(session: Session, paraglider_key, points):
    """
    Update the database with the latest paraglider points.

    Args:
        session (Session): SQLAlchemy session.
        points (list): A list of points to update.
    """
    for point in points:
        existing_point = session.query(ParaglidersData).filter_by(
            paraglider_key=paraglider_key,
            datetime=point['datetime']
        ).first()
        if not existing_point:
            save_paraglider_point(session, paraglider_key, point)
    session.commit()


def get_last_paraglider_point(session, paraglider_key):
    """Return the latest tracking point for a paraglider, or None."""
    return session.query(ParaglidersData).filter(
        ParaglidersData.paraglider_key == paraglider_key
    ).order_by(ParaglidersData.datetime.desc()).first()


# Backward-compatible alias used by older call sites / tests during transition.
get_last_paraglider_state = get_last_paraglider_point


def get_paraglider_machine_state(session, paraglider_key):
    """Return the persisted machine state row, or None."""
    return session.query(ParagliderState).filter(
        ParagliderState.paraglider_key == paraglider_key
    ).first()


def upsert_paraglider_state(session: Session, paraglider_key, state, source='tracking'):
    """Persist the current machine state independently of tracking points."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = get_paraglider_machine_state(session, paraglider_key)
    if row is None:
        session.add(ParagliderState(
            paraglider_key=paraglider_key,
            state=state,
            updated_at=now,
            source=source,
        ))
    else:
        row.state = state
        row.updated_at = now
        row.source = source
    session.commit()


def update_last_paraglider_state(session: Session, paraglider_key, state, source='tracking'):
    """Persist machine state (replaces writing state onto the latest GPS row)."""
    upsert_paraglider_state(session, paraglider_key, state, source=source)


def get_paraglider_history(paraglider_key):
    """
    Get the history of a paraglider.
    Args:
        paraglider_key (str): The key of the paraglider.
    Returns:
        list: A list of ParaglidersData objects representing the history.
    """
    session = SessionLocal()
    thirty_minutes_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30) # TODO - Time Zone
    history = session.query(ParaglidersData).filter(
        ParaglidersData.paraglider_key == paraglider_key,
        ParaglidersData.datetime >= thirty_minutes_ago
    ).all()
    session.close()
    return history


def calculate_average_speed_old(session: Session, paraglider_key, minutes=5):
    """
    Calculate the average speed of a paraglider over the last X minutes.

    Args:
        session (Session): SQLAlchemy session.
        paraglider_key (str): The key of the paraglider.
        minutes (int): The time window in minutes.

    Returns:
        float: The average speed in m/s.
    """
    time_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes)
    points = session.query(ParaglidersData).filter(
        ParaglidersData.paraglider_key == paraglider_key,
        ParaglidersData.datetime >= time_threshold
    ).all()

    if not points:
        return 0.0

    # TODO - Check if the speed is None. If so, use the calculated speed
    total_speed = sum(point.speed for point in points if point.speed is not None)
    return round(total_speed / len(points), 2)


def calculate_average_speed(session: Session, paraglider_key, minutes=5):
    """
    Calculate the average speed of a paraglider over the last X minutes.

    Args:
        session (Session): SQLAlchemy session.
        paraglider_key (str): The key of the paraglider.
        minutes (int): The time window in minutes.

    Returns:
        float: The average speed in m/s.
    """
    time_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes)
    points = session.query(ParaglidersData).filter(
        ParaglidersData.paraglider_key == paraglider_key,
        ParaglidersData.datetime >= time_threshold
    ).order_by(ParaglidersData.datetime).all()

    if len(points) < 2:
        return 0.0

    total_time = 0.0
    total_speed_weighted = 0.0

    for i in range(1, len(points)):
        point1 = points[i - 1]
        point2 = points[i]

        # Calculate the time difference in s
        time_diff = (point2.datetime - point1.datetime).total_seconds()

        if time_diff > 0:
            total_time += time_diff
            if point2.speed is not None:
                total_speed_weighted += point2.speed * time_diff

    if total_time == 0:
        return 0.0

    average_speed = total_speed_weighted / total_time
    return round(average_speed, 2)


def purge_old_data(session: Session, hours=None):
    """
    Purge tracking points older than the specified number of hours.

    Args:
        session (Session): SQLAlchemy session.
        hours (int): Age threshold in hours. Defaults to configured retention_hours (48).

    Returns:
        int: The number of records deleted.
    """
    if hours is None:
        hours = _retention_hours
    time_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

    deleted_count = session.query(ParaglidersData).filter(
        ParaglidersData.datetime < time_threshold
    ).delete()

    session.commit()

    return deleted_count
