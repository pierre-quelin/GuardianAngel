from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session

Base = declarative_base()
SessionLocal = None  # La session sera configurée dynamiquement

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
    state = Column(String)

def init_db_engine(cfg):
    """
    Initialize the database engine and session.

    Args:
        cfg (dict): Configuration for the db engine
    """
    global SessionLocal
    engine = create_engine(cfg.get('url'))
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Crée les tables si elles n'existent pas
    Base.metadata.create_all(engine)
    return engine

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
        state=point.get('state') # cf. Paraglider.states
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
        # Vérifiez si le point existe déjà dans la base
        existing_point = session.query(ParaglidersData).filter_by(
            paraglider_key=paraglider_key,
            datetime=point['datetime']
        ).first()
        if not existing_point:
            save_paraglider_point(session, paraglider_key, point)
    session.commit()

def get_last_paraglider_state(session, paraglider_key):
    """
    Get the last known state of a paraglider.

    Args:
        session (Session): SQLAlchemy session.
        paraglider_key (str): The key of the paraglider.

    Returns:
        ParaglidersData: The last known state of the paraglider.
    """
    last_state = session.query(ParaglidersData).filter(
        ParaglidersData.paraglider_key == paraglider_key
    ).order_by(ParaglidersData.datetime.desc()).first()

    return last_state

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

def purge_old_data(session: Session, hours=48):
    """
    Purge data older than the specified number of hours from the database.

    Args:
        session (Session): SQLAlchemy session.
        hours (int): The age threshold in hours for purging data. Default is 48 hours.

    Returns:
        int: The number of records deleted.
    """
    # Calculate the time threshold
    time_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

    # Delete records older than the threshold
    deleted_count = session.query(ParaglidersData).filter(
        ParaglidersData.datetime < time_threshold
    ).delete()

    # Commit the changes
    session.commit()

    return deleted_count