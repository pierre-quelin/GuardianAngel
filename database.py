from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session

Base = declarative_base()
SessionLocal = None  # La session sera configurée dynamiquement

class ParagliderData(Base):
    __tablename__ = 'paraglider_data'
    id = Column(Integer, primary_key=True, index=True)
    paraglider_key = Column(String, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    course = Column(Float)
    speed = Column(Float)
    altitude = Column(Float)
    state = Column(String)
    datetime = Column(DateTime, nullable=False)

def init_db_engine(database_url):
    """
    Initialize the database engine and session.

    Args:
        database_url (str): The database URL.
    """
    global SessionLocal
    engine = create_engine(database_url)
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
    paraglider_data = ParagliderData(
        paraglider_key=paraglider_key,
        latitude=point['lat'],
        longitude=point['lon'],
        course=point.get('course'),
        speed=point.get('speed'),
        altitude=point.get('alt_gps'),
        state=point.get('state'),
        datetime=point['datetime']
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
        existing_point = session.query(ParagliderData).filter_by(
            paraglider_key=paraglider_key,
            datetime=point['datetime']
        ).first()
        if not existing_point:
            save_paraglider_point(session, paraglider_key, point)
    session.commit()

def get_paraglider_history(paraglider_key):
    session = SessionLocal()
    thirty_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=30) # TODO - Time Zone
    history = session.query(ParagliderData).filter(
        ParagliderData.paraglider_key == paraglider_key,
        ParagliderData.datetime >= thirty_minutes_ago
    ).all()
    session.close()
    return history

def calculate_average_speed(session: Session, paraglider_key, minutes=5):
    """
    Calculate the average speed of a paraglider over the last X minutes.

    Args:
        session (Session): SQLAlchemy session.
        paraglider_key (str): The key of the paraglider.
        minutes (int): The time window in minutes.

    Returns:
        float: The average speed in km/h.
    """
    time_threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    points = session.query(ParagliderData).filter(
        ParagliderData.paraglider_key == paraglider_key,
        ParagliderData.datetime >= time_threshold
    ).all()

    if not points:
        return 0.0

    total_speed = sum(point.speed for point in points if point.speed is not None)
    return round(total_speed / len(points), 2)

def calculate_average_speed2(session: Session, paraglider_key, minutes=5):
    """
    Calculate the average speed of a paraglider over the last X minutes.

    Args:
        session (Session): SQLAlchemy session.
        paraglider_key (str): The key of the paraglider.
        minutes (int): The time window in minutes.

    Returns:
        float: The average speed in km/h.
    """
    time_threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    points = session.query(ParagliderData).filter(
        ParagliderData.paraglider_key == paraglider_key,
        ParagliderData.datetime >= time_threshold
    ).order_by(ParagliderData.datetime).all()

    if len(points) < 2:
        return 0.0

    total_time = 0.0
    total_speed_weighted = 0.0

    for i in range(1, len(points)):
        point1 = points[i - 1]
        point2 = points[i]

        # Calculate the time difference in hours
        time_diff = (point2.datetime - point1.datetime).total_seconds() / 3600.0

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
    time_threshold = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Delete records older than the threshold
    deleted_count = session.query(ParagliderData).filter(
        ParagliderData.datetime < time_threshold
    ).delete()

    # Commit the changes
    session.commit()

    return deleted_count