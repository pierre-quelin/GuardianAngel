import threading
import time
from config import config
from logger import get_logger
import puretrack_api as ptrk
import database as db
from guardian_angel import GuardianAngel

logger = get_logger(__name__)

def puretrack_polling():
    database_cfg = config.get('database')
    puretrack_cfg = config.get('puretrack')
    paragliders_cfg = config.get('paragliders')

    db.init_db_engine(database_cfg.get('url'))

    while True:
        start = time.monotonic()
        polling_period = 15
        session = db.SessionLocal()

        # # Obtain all known last positions of paragliders in the group
        # grpLive = ptrk.getPureTrackGroupLive(puretrack_cfg.get('group'))
        # for data in grpLive:
        #     record_member = ptrk.parse_puretrack_record(data)
        #     logger.debug(record_member)
        #     # If member is a paraglider
        #     if paraglider := paragliders_cfg.get(record_member.get('key')):
        #         name = paraglider.get('name')
        #         datetime = record_member.get('datetime')
        #         if position := ( record_member.get('lat'), record_member.get('lon') ):
        #             alt_gnd = record_member.get('alt_gps') - ptrk.get_elevation(position=position)
        #             logger.info(f"'{name}' last known position {position} and altitude {alt_gnd} at {datetime}")

        # # Obtain all known tracks of paragliders in the group
        # if group := ptrk.getPureTrackGroup(puretrack_cfg.get('group')):
        #     logger.debug(f"Group name: '{group.get('name')}'")
        #     for record_member in group.get('members'):
        #         logger.debug(f"Member: label:'{record_member.get('label')}' key:'{record_member.get('key')}'")
        #         if tails := ptrk.getPureTrackTails(record_member.get('key'), polling_period):
        #             tracks = tails.get('tracks')
        #             if tracks[0].get('count') != 0:
        #                 last = ptrk.parse_puretrack_record(tracks[0].get('last'))
        #                 # logger.debug(f"Last Point: {last}")
        #                 last_timestamp = 0
        #                 points = tracks[0].get('points')
        #                 # Revesed, the last first
        #                 for point in reversed(points):
        #                     p = ptrk.parse_puretrack_record(point)
        #                     if p.get('timestamp') == last_timestamp:
        #                         # If timestamp is the same, the first one is the only true
        #                         continue

        #                     last_timestamp = p.get('timestamp')
        #                     logger.debug(f"Point: {p}")
        #                     alt_gnd = p.get('alt_gps') - ptrk.get_elevation(p.get('lat'), p.get('lon'))
        #                     speed = ptrk.calculate_speed(p, last)
        #                     logger.info(f"Calculated altitude: {alt_gnd}m speed: {speed} m/s")
        #                     last = p
        #                     pass
        # else:
        #     logger.warning("Failed to retrieve group data.")

        # Obtain all known tracks of paragliders in the configuration file
        for paraglider_key in paragliders_cfg:
            if tails := ptrk.get_puretrack_tails(paraglider_key, polling_period+2): # +2 to ensure we get the last point
                tracks = tails.get('tracks')
                if tracks[0].get('count') != 0:
                    parsed_points = []
                    last_parsed_point = ptrk.parse_puretrack_record(tracks[0].get('last'))
                    points = tracks[0].get('points')
                    # Revesed, the last first
                    for point in reversed(points):
                        parsed_point = ptrk.parse_puretrack_record(point)
                        if parsed_point.get('timestamp') == last_parsed_point.get('timestamp'):
                            # If timestamp is the same, the first record is the only true
                            logger.debug("Point: not used. Always registered the first one.")
                            continue
                        if (last_parsed_point.get('speed_calc') == None):
                            last_parsed_point['speed_calc'] = round(ptrk.calculate_speed(parsed_point, last_parsed_point), 2)
                        logger.info(f"Point: {last_parsed_point}")
                        parsed_points.append(last_parsed_point)
                        last_parsed_point = parsed_point
                        pass

                    # Add the new points to the database
                    db.update_paraglider_data(session, paraglider_key, parsed_points)

                    # Calculate the average speed over the last 5 minutes
                    avg_speed = db.calculate_average_speed(session, paraglider_key, minutes=5)
                    avg_speed2 = db.calculate_average_speed2(session, paraglider_key, minutes=5)
                    logger.info(f"Average speed for {paraglider_key} over the last 5 minutes: {avg_speed*3.6} {avg_speed2*3.6} km/h")

        # Purge old points
        db.purge_old_data(session)

        session.close()

        end = time.monotonic()
        elsapsed = end - start
        if elsapsed < polling_period:
            time.sleep(polling_period - elsapsed)
        else:
            logger.warning(f"Polling took too long: {elsapsed} seconds")

# def monitoring():
#     while True:
#         data = load_data()
#         status = evaluate_status(data)
#         if status:
#             send_alert(status)
#         time.sleep(60)  # Check every minute

def main():
    guardian_angel = GuardianAngel(cfg = config.get('guardian_angel'))

    while True:
        time.sleep(10)



    # Start threads
    puretrack_polling_thread = threading.Thread(target=puretrack_polling)
    # monitoring_thread = threading.Thread(target=monitoring)
    # web_thread = threading.Thread(target=start_web_interface)

    puretrack_polling_thread.start()
    # monitoring_thread.start()
    # web_thread.start()

    # Join threads
    puretrack_polling_thread.join()
    # monitoring_thread.join()
    # web_thread.join()

if __name__ == "__main__":
    main()
