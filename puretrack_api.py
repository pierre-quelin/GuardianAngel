# import pytz
from config import config
import datetime
import math
from logger import get_logger
import requests
import srtm
import time

logger = get_logger(__name__)

def get_elevation(lat=None, lon=None, position=None):
    """
    Fetches the elevation (altitude) for a given latitude and longitude using SRTM (Shuttle Radar Topography Mission) data.

    Args:
        lat (float, optional): Latitude of the location in decimal degrees. Ignored if `position` is provided.
        lon (float, optional): Longitude of the location in decimal degrees. Ignored if `position` is provided.
        position (dict or tuple, optional): A dictionary or tuple containing latitude and longitude.
            If a dictionary, it should have keys 'lat' and 'long'.
            If a tuple, it should be in the form (lat, long).

    Returns:
        int or None: The elevation (altitude) in meters above sea level if available, otherwise None.

    Raises:
        ValueError: If neither `lat`/`lon` nor `position` is provided, or if `position` is invalid.
        Exception: If there is an issue retrieving the SRTM data or calculating the elevation.
    """
    # Extract latitude and longitude from position if provided
    if position:
        if isinstance(position, dict):
            lat = position.get('lat')
            lon = position.get('long')
        elif isinstance(position, tuple) and len(position) == 2:
            lat, lon = position
        else:
            raise ValueError("Invalid position format. Must be a dictionary with 'lat' and 'long' keys or a tuple (lat, long).")

    # Ensure lat and lon are provided
    if lat is None or lon is None:
        raise ValueError("Latitude and longitude must be provided either directly or via the `position` parameter.")

    # Fetch elevation using SRTM data
    srtm_data = srtm.get_data()
    elevation = srtm_data.get_elevation(lat, lon)
    return elevation

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculates the distance between two points on a sphere using the haversine formula.

    Args:
        lat1 (float): Latitude of the first point in degrees.
        lon1 (float): Longitude of the first point in degrees.
        lat2 (float): Latitude of the second point in degrees.
        lon2 (float): Longitude of the second point in degrees.

    Returns:
        float: Distance between the two points in meters.
    """
    # Convert coordinates from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Calculating differences
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    # Haversine formula
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))

    # Radius of the Earth in meters
    r = 6371000

    # Distance in meters
    return c * r

def calculate_speed(previous_point, current_point):
    """
    Calculates the speed between two points in meters per second.

    Args:
        previous_point (dict): Dictionary containing the previous point's data (latitude, longitude, timestamp).
        current_point (dict): Dictionary containing the current point's data (latitude, longitude, timestamp).

    Returns:
        float: Speed between the two points in meters per second.
    """
    # Calculate the distance between the two points
    distance = haversine(previous_point['lat'], previous_point['long'], current_point['lat'], current_point['long'])
    # Calculate the time difference in seconds
    time_diff_seconds = current_point['timestamp'] - previous_point['timestamp']

    if time_diff_seconds > 0:  # Éviter la division par zéro
        speed = distance / time_diff_seconds
    else:
        speed = 0  # If time is zero or negative, speed is 0
    # Calculate speed in m/s
    return speed

# Dictionary for mapping prefixes to keys
key_mapping = {
    'T': {'name': 'timestamp', 'type': int},            # Timestamp Epoch Unix Timestamp
    'L': {'name': 'lat', 'type': float},                # Latitude
    'G': {'name': 'long', 'type': float},               # Longitude
    'K': {'name': 'key', 'type': str},                  # PureTrack key, to uniquely identify this object in PureTrack.
                                                        # If matching an aircraft, it is prefixed with Y- plus rego.
                                                        # If matches a PureTrack target, prefixed wtih X- or Z-.
                                                        # For unknown items, prefixed with source type ID number and tracker_uid e.g. a FLARM target will be 0-ABC123.
    'A': {'name': 'alt_gps', 'type': float},            # Altitude GPS in meters, altitude returned by most devices.
                                                        # ADSB calculated from local pressure. See also 't' for standard pressure altitude from ADSB.
    'P': {'name': 'pressure', 'type': float},           # The current latest 6 hour pressure for nearest location, used to calibrate ADSB altitude.
    'C': {'name': 'course',  'type': float},            # course in degrees 0-360
    'S': {'name': 'speed', 'type': float},              # Speed in m/s !? doubt xcontest:km/h flarm:m/s !?
    'V': {'name': 'v_speed', 'type': float},            # Vertical speed in m/s
    'O': {'name': 'object_type', 'type': str},          # Object type (see list of types at https://puretrack.io/types.json)
    'Z': {'name': 'timezone', 'type': str},             # Not used at the moment (Timestamp returned is Unixtime).
    'D': {'name': 'tracker_uid', 'type': str},          # The ID of the original tracker. In the case of FLARM FlarmID or ADSB ICAO hex code.
    'H': {'name': 'stealth', 'type': str},              # If this item is stealth or not from flarm.
    'Q': {'name': 'no_tracking', 'type': str},          # If this item is stealth or not from flarm
    'I': {'name': 'signal_quality', 'type': str},       # Signal quality
    'R': {'name': 'receiver_name', 'type': str},        # Receiver name
    'U': {'name': 'source_type_id', 'type': str},       # ID of source of this point. List below of source IDs
    'J': {'name': 'target_id', 'type': str},            # The PureTrack target ID. A 'target' matches an item to a map marker and other user configured options.
    'B': {'name': 'label', 'type': str},                # Label, either returned from the tracking service, or added from what the user has configured via the target
    'N': {'name': 'name', 'type': str},                 # Actual name of a pilot if provided
    'E': {'name': 'rego', 'type': str},                 # If an aircraft, the full rego e.g. ZK-GOP
    'M': {'name': 'model', 'type': str},                # Aircraft model.
    's': {'name': 'speed_calc', 'type': float},         # Not used
    'd': {'name': 'dist_calc', 'type': float},          # Not used
    'v': {'name': 'v_speed_calc', 'type': float},       # Not used
    'f': {'name': 'flying', 'type': str},               # Not used
    'x': {'name': 'ignore', 'type': str},               # Not used
    'g': {'name': 'ground_level', 'type': str},         # Ground level at this point
    'i': {'name': 'tracker_id', 'type': str},           # Internal puretrack ID
    'e': {'name': 'comp', 'type': str},                 # Not used?
    'c': {'name': 'colour', 'type': str},               # Colour selected by user to use on map. Generated randomly if not provided.
    'a': {'name': 'aircraft_id', 'type': str},          # Aircraft ID
    'j': {'name': 'target_key', 'type': str},           # Target key
    'k': {'name': 'inreach_id', 'type': str},           # InReach ID
    'l': {'name': 'spot_id', 'type': str},              # Spot ID
    'h': {'name': 'accuracy_horizontal', 'type': str},  # Horizontal accuracy
    'z': {'name': 'accuracy_vertical', 'type': str},    # Vertical accuracy
    'u': {'name': 'username', 'type': str},             # Username provided by some services e.g. Skylines, Flymaster etc
    'm': {'name': 'callsign', 'type': str},             # Not used
    'n': {'name': 'comp_name', 'type': str},            # Contest name
    'b': {'name': 'comp_class', 'type': str},           # Name of the contest class
    'q': {'name': 'comp_class_id', 'type': str},        # ID of the contest class
    't': {'name': 'alt_standard', 'type': str},         # Standard pressure altitude in meters
    'r': {'name': 'thermal_climb_rate', 'type': str},   # Taux de montée thermique calculé depuis le début de la montée jusqu'à l'heure actuelle in m/s
    'p': {'name': 'phone', 'type': str},                # User's phone number
    'F': {'name': 'ffvl_key', 'type': str},             # If the target has an FFVL key
    '!': {'name': 'random', 'type': str},               # If the item is a randomly generated ID from FLARM
    'W': {'name': 'W_unknown', 'type': str},            # ?
    'o': {'name': 'o_unknown', 'type': str},            # ?
}

# 'U': 'source_type_id', ID of source of this point
source_mapping = {
    '0': 'flarm',
    '1': 'spot',
    '2': 'particle',
    '3': 'overland',
    '4': 'spotnz',
    '5': 'inreachnz',
    '6': 'btraced',
    '7': 'api',
    '8': 'mt600-l-gnz',
    '9': 'inreach',
    '10': 'igc',
    '11': 'pi',
    '12': 'adsb',
    '13': 'igcdroid',
    '14': 'navigator',
    '16': 'puretrack',
    '17': 'teltonika',
    '18': 'celltracker',
    '19': 'mt600',
    '20': 'mt600-l',
    '21': 'api',
    '22': 'fr24',
    '23': 'xcontest',
    '24': 'skylines',
    '25': 'flymaster',
    '26': 'livegliding',
    '27': 'ADSBExchange',
    '28': 'adsb.lol',
    '29': 'adsb.fi',
    '30': 'SportsTrackLive',
    '31': 'FFVL Tracking',
    '32': 'Zoleo',
    '33': 'Total Vario',
    '34': 'Tracker App',
    '35': 'OGN ICAO',
    '36': 'XC Guide',
    '37': 'Bircom'
}

def parse_puretrack_record(record):
    # Dividing the line into elements
    elements = record.split(',')

    # Initialize a dictionary to store parsed data
    parsed_record = {}

    for element in elements:
        if element:
            prefix = element[0]
            value = element[1:]
            if prefix in key_mapping:
                key_info = key_mapping[prefix]
                key_name = key_info['name']
                key_type = key_info['type']

                try:
                    # Convert the value to the specified type
                    parsed_value = key_type(value)
                    # Special handling for timestamps
                    if prefix == 'T':
                        parsed_record[key_name] = parsed_value
                        # Convert Unix timestamp to readable local time
                        # local_time = datetime.datetime.fromtimestamp(timestamp, pytz.timezone('Europe/Paris')).strftime('%Y-%m-%d %H:%M:%S')
                        local_time = datetime.datetime.fromtimestamp(parsed_value).strftime('%d/%m/%Y %H:%M:%S')
                        parsed_record['datetime'] = local_time
                    elif prefix == 'U' and value in source_mapping:
                        parsed_record[key_name] = source_mapping[parsed_value]
                    else:
                        parsed_record[key_name] = parsed_value
                except ValueError:
                    logger.warning(f"Failed to convert value '{value}' for key '{key_name}' to type {key_type.__name__}")
            else:
                logger.warning(f"Unknown prefix '{prefix}' in element '{element}'")

    return parsed_record

def getPureTrackGroup(group):
    """
    Fetches the details of a PureTrack group by its slug.

    Args:
        group (str): The slug (unique identifier) of the PureTrack group.

    Returns:
        dict: The JSON response containing group details if successful, otherwise None.

    Raises:
        requests.exceptions.RequestException: If the HTTP request fails.
    """
    url = f'https://puretrack.io/api/groups/byslug/{group}'
    headers = {
        'Content-Type': 'application/json',
        'Accept-Encoding': 'gzip, deflate, br, zstd'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        if response.status_code == 200:
            return response.json().get('data')
        else:
            logger.error(f"Data recovery error")
    except Exception as e:
        logger.error("Data recovery error :", e)

    return None

def getPureTrackGroupLive(group):
    """
    Fetches live data for a PureTrack group.

    Args:
        group (str): The slug (unique identifier) of the PureTrack group.

    Returns:
        dict: The JSON response containing live data if successful, otherwise None.

    Raises:
        requests.exceptions.RequestException: If the HTTP request fails.
    """
    # Step 1: Obtain the CSRF token
    url_get_token = 'https://puretrack.io/?l=44.68131,4.62335&z=15&group={group}'
    try:
        response = requests.get(url_get_token)
        response.raise_for_status()

        # Check if the request was successful
        if response.status_code == 200:
            # Step 2: Extract the CSRF token and cookies
            csrf_token = response.cookies.get('XSRF-TOKEN')
            session_cookie = response.cookies.get('puretrack_session')

            # Step 3: Preparing the POST request with CSRF token and cookies
            url_post = 'https://puretrack.io/api/live'
            headers_post = {
                # 'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
                # 'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                # 'X-Requested-With': 'XMLHttpRequest',
                'X-XSRF-TOKEN': csrf_token,  # Utiliser le jeton CSRF obtenu
                # 'Cookie': f'XSRF-TOKEN={csrf_token}; puretrack_session={session_cookie}',
            }

            data = {
                # "b1l": "44.68863",
                # "b1g": "4.62388",
                # "b2l": "44.67457",
                # "b2g": "4.60979",
                # "s": "X-key,X-key",
                # "o": [63, 6, 7, 17, 20],
                "t": 360,
                "a": None,
                "i": 1,
                "g": 22,
                "l": True
            }

            response_post = requests.post(url_post, headers=headers_post, json=data)
            response_post.raise_for_status()

            if response_post.status_code == 200:
                return response_post.json().get('data')
            else:
                logger.error(f"Data recovery error")

        else:
            logger.error("Error in obtaining CSRF token.")

    except Exception as e:
        logger.error("Data recovery error :", e)

    return None

def getPureTrackTails(key, limit=10):
    """
    Fetches the trail data for a given key from the PureTrack API.

    Args:
        key (str): The unique key for the PureTrack object.
        limit (int, optional): The number of records to request. Default is 10.

    Returns:
        dict: The JSON response from the API if successful, otherwise None.
    """
    url = 'https://puretrack.io/api/trails'
    headers = {
        'Content-Type': 'application/json',
        'Accept-Encoding': 'gzip, deflate, br, zstd'
    }
    data = [
        {
            "id": f'{key}',
            "from": 0
        }
    ]

    params = {
        'limit': limit, # Number of records requested. Default 14000
        'maxage': 1440 # Maximum age of records in minutes. Default 1440 (24h)
    }

    try:
        response = requests.post(url, headers=headers, json=data, params=params)
        response.raise_for_status()
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Data recovery error")
    except Exception as e:
        logger.error("Data recovery error :", e)

    return None
