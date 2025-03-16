# import pytz
from config import config
import datetime
import math
from logger import logger
import requests
import time

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
    'T': 'timestamp',           # Timestamp Epoch Unix Timestamp
    'L': 'lat',                 # Latitude
    'G': 'long',                # Longitude
    'K': 'key',                 # PureTrack key, to uniquely identify this object in PureTrack.
                                # If matching an aircraft, it is prefixed with Y- plus rego.
                                # If matches a PureTrack target, prefixed wtih X- or Z-.
                                # For unknown items, prefixed with source type ID number and tracker_uid e.g. a FLARM target will be 0-ABC123.
    'A': 'alt_gps',             # Altitude GPS in meters, altitude returned by most devices.
                                # ADSB calculated from local pressure. See also 't' for standard pressure altitude from ADSB.
    'P': 'pressure',            # The current latest 6 hour pressure for nearest location, used to calibrate ADSB altitude.
    'C': 'course',              # course in degrees 0-360
    'S': 'speed',               # Speed in m/s !? doubt xcontest:km/h flarm:m/s !?
    'V': 'v_speed',             # Vertical speed in m/s
    'O': 'object_type',         # Object type (see list of types at https://puretrack.io/types.json)
    'Z': 'timezone',            # Not used at the moment (Timestamp returned is Unixtime).
    'D': 'tracker_uid',         # The ID of the original tracker. In the case of FLARM FlarmID or ADSB ICAO hex code.
    'H': 'stealth',             # If this item is stealth or not from flarm.
    'Q': 'no_tracking',         # If this item is stealth or not from flarm
    'I': 'signal_quality',      # Signal quality
    'R': 'receiver_name',       # Receiver name
    'U': 'source_type_id',      # ID of source of this point. List below of source IDs
    'J': 'target_id',           # The PureTrack target ID. A 'target' matches an item to a map marker and other user configured options.
    'B': 'label',               # Label, either returned from the tracking service, or added from what the user has configured via the target
    'N': 'name',                # Actual name of a pilot if provided
    'E': 'rego',                # If an aircraft, the full rego e.g. ZK-GOP
    'M': 'model',               # Aircraft model.
    's': 'speed_calc',          # Not used
    'd': 'dist_calc',           # Not used
    'v': 'v_speed_calc',        # Not used
    'f': 'flying',              # Not used
    'x': 'ignore',              # Not used
    'g': 'ground_level',        # Ground level at this point
    'i': 'tracker_id',          # Internal puretrack ID
    'e': 'comp',                # Not used?
    'c': 'colour',              # Colour selected by user to use on map. Generated randomly if not provided.
    'a': 'aircraft_id',         # Aircraft ID
    'j': 'target_key',          # Target key
    'k': 'inreach_id',          # InReach ID
    'l': 'spot_id',             # Spot ID
    'h': 'accuracy_horizontal', # Horizontal accuracy
    'z': 'accuracy_vertical',   # Vertical accuracy
    'u': 'username',            # Username provided by some services e.g. Skylines, Flymaster etc
    'm': 'callsign',            # Not used
    'n': 'comp_name',           # Contest name
    'b': 'comp_class',          # Name of the contest class
    'q': 'comp_class_id',       # ID of the contest class
    't': 'alt_standard',        # Standard pressure altitude in meters
    'r': 'thermal_climb_rate',  # Taux de montée thermique calculé depuis le début de la montée jusqu'à l'heure actuelle in m/s
    'p': 'phone',               # User's phone number
    'F': 'ffvl_key',            # If the target has an FFVL key
    '!': 'random',              # If the item is a randomly generated ID from FLARM
    'W': 'W_unknown',           # ?
    'o': 'o_unknown',           # ?
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
                if prefix == 'T':
                    parsed_record[key_mapping[prefix]] = int(value)
                    # Convert Unix timestamp to readable local time
                    timestamp = int(value)
                    # local_time = datetime.datetime.fromtimestamp(timestamp, pytz.timezone('Europe/Paris')).strftime('%Y-%m-%d %H:%M:%S')
                    local_time = datetime.datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M:%S')
                    parsed_record['datetime'] = local_time
                elif prefix == 'L' or prefix == 'G':
                    parsed_record[key_mapping[prefix]] = float(value)
                elif prefix == 'U' and value in source_mapping:
                    parsed_record[key_mapping[prefix]] = source_mapping[value]
                else:
                    parsed_record[key_mapping[prefix]] = value
            else:
                print(f'{element} - {prefix} not found')

    return parsed_record

def getPureTrackGroup(group):
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
            print(f"Data recovery error")
    except Exception as e:
        print("Data recovery error :", e)
    
    return None

def getPureTrackGroupLive(group):
    # Étape 1 : Obtenir le jeton CSRF
    url_get_token = 'https://puretrack.io/?l=44.68131,4.62335&z=15&group={group}'
    try:
        response = requests.get(url_get_token)
        response.raise_for_status()

        # Vérifiez si la requête a réussi
        if response.status_code == 200:
            # Étape 2 : Extraire le jeton CSRF et les cookies
            csrf_token = response.cookies.get('XSRF-TOKEN')
            session_cookie = response.cookies.get('puretrack_session')

            # Étape 3 : Préparer la requête POST avec le jeton CSRF et les cookies
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
                print(f"Data recovery error")

        else:
            print("Error in obtaining CSRF token.")

    except Exception as e:
        print("Data recovery error :", e)
    
    return None

def getPureTrackTails(key):
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
        'limit': 10, # Number of records requested. Default 14000
        'maxage': 1440 # Maximum age of records in minutes. Default 1440 (24h)
    }
  
    try:
        response = requests.post(url, headers=headers, json=data, params=params)
        response.raise_for_status()
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Data recovery error")
    except Exception as e:
        print("Data recovery error :", e)

    return None

if __name__ == "__main__":
    puretrack_cfg = config.get('puretrack')

    while True:    
        grp2 = getPureTrackGroupLive(puretrack_cfg.get('group'))
        # All known last positions
        for data in grp2:
            logger.debug(parse_puretrack_record(data))

        # All members
        group = getPureTrackGroup(puretrack_cfg.get('group'))
        if group:
            logger.debug(f"Group name: '{group.get('name')}'")
            for member in group.get('members'):
                logger.debug(f"Member: label:'{member.get('label')}' key:'{member.get('key')}'")
                tails = getPureTrackTails(member.get('key'))
                tracks = tails.get('tracks')
                if tracks[0].get('count') != 0:
                    # last = parse_puretrack_record(tracks[0].get('last'))
                    # logger.debug(f"Last Point: {last}")
                    last_timestamp = 0
                    points = tracks[0].get('points')
                    # Revesed, the last first
                    for point in reversed(points):
                        p = parse_puretrack_record(point)
                        # If timestamp is the same, the last one is the only true
                        if p.get('timestamp') == last_timestamp:
                            continue
                        last_timestamp = last.get('timestamp')
                        logger.debug(f"Point: {p}")
                        # speed = calculate_speed(p, last)
                        # logger.info(f"Calculated speed: {speed} m/s")
                        last = p
                        pass
        else:
            logger.warning("Failed to retrieve group data.")
        time.sleep(30)
