# from config import CONFIG
# import pytz
import datetime
import math
import requests

# returns the distance between two points on a spere, using the haversine formula
def haversine(lat1, lon1, lat2, lon2):
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

# Returns speed between 2 points en m/s
def calculate_speed(previous_point, current_point):
    # Calculate the distance between the two points
    distance = haversine(previous_point['lat'], previous_point['long'], current_point['lat'], current_point['long'])
    # Calculate the time difference in seconds
    time_diff_seconds = current_point['timestamp'] - previous_point['timestamp']

    if time_diff_seconds > 0:  # Éviter la division par zéro
        speed = distance / time_diff_seconds
        print(f'd:{distance}m v:{speed}m/s')
      
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
    'S': 'speed',               # Speed in m/s
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

    if 'speed' in parsed_record:
        print(f"speed : {parsed_record.get('speed')}m/s")
    if 'speed_calc' in parsed_record:
        print(f"calc speed {parsed_record.get('speed_calc')}m/s")
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
#   data = {
#     "keys": [
#         "X-fred-c1624", "X-tam1289", "X-sarahc1295", "X-brierre-philippe1433",
#         "23-SHc607h5jeOFmjS4XfXVpXb26OPR", "X-lionel-pascale1428", "X-arnaud261454",
#         "X-eric-lac", "X-joseph-bada1458", "23-qiwDsTbmqPhDdh6q6WUVXNWwtWjk",
#         "X-lionelb-3", "X-stephane-mariton1605", "23-PEfdIkyiyl96BgwTYE4xx6p7aLu8",
#         "X-muyor1776", "X-etienne-jkmo1704", "X-sonja-o1865", "23-Gjm3MhRIpxgk9QqzLR2r8kIQm6Cl",
#         "X-seb261429", "X-olivier-brsm", "23-hyKRCWKxqXCLHVLCB7l2yRgiyDLt",
#         "X-fabricej"
#     ]
# }

    params = {
        'limit': 10, # default 14000
        'maxage': 1440 # default 1440
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


if __name__ == "__main__":
    # group = getPureTrackGroup('a_grp')
    # print(f"name: '{group.get('name')}'")
    # for member in group.get('members'):
    #     print(f"member: label:'{member.get('label')}' key:'{member.get('key')}'")
    #     tails = getPureTrackTails(member.get('key'))
    #     tracks = tails.get('tracks')
    #     if tracks[0].get('count') != 0:
    #         last = parse_puretrack_record(tracks[0].get('last'))
    #         points = tracks[0].get('points')
    #         for point in points:
    #             p = parse_puretrack_record(point)
    #             last = p
    #             pass
    
    tails = getPureTrackTails('0-FE0913')
    tracks = tails.get('tracks')
    if tracks[0].get('count') != 0:
        last = parse_puretrack_record(tracks[0].get('last'))
        points = tracks[0].get('points')
        for point in points:
            p = parse_puretrack_record(point)
            speed = calculate_speed(p, last)
            last = p
            pass
    
