import threading
import time
from config import config
from logger import get_logger
import puretrack_api as ptrk
# from database import save_data, load_data
# from monitoring import evaluate_status
# from alert_notification import send_alert
# from web_interface import start_web_interface

logger = get_logger(__name__)

def puretrack_polling():
    puretrack_cfg = config.get('puretrack')
    paragliders_cfg = config.get('paragliders')

    while True:
        # Obtain all known last positions of paragliders in the group
        grpLive = ptrk.getPureTrackGroupLive(puretrack_cfg.get('group'))
        for data in grpLive:
            member = ptrk.parse_puretrack_record(data)
            logger.debug(member)
            # If member is a paraglider
            if paraglider := paragliders_cfg.get(member.get('key')):
                name = paraglider.get('name')
                datetime = member.get('datetime')
                position = { member.get('lat'), member.get('long') }
                logger.info(f"'{name}' last known position {position} at {datetime}")

        # Obtain all known tracks of paragliders in the group
        if group := ptrk.getPureTrackGroup(puretrack_cfg.get('group')):
            logger.debug(f"Group name: '{group.get('name')}'")
            for member in group.get('members'):
                logger.debug(f"Member: label:'{member.get('label')}' key:'{member.get('key')}'")
                if tails := ptrk.getPureTrackTails(member.get('key')):
                    tracks = tails.get('tracks')
                    if tracks[0].get('count') != 0:
                        # last = trk.parse_puretrack_record(tracks[0].get('last'))
                        # logger.debug(f"Last Point: {last}")
                        last_timestamp = 0
                        points = tracks[0].get('points')
                        # Revesed, the last first
                        for point in reversed(points):
                            p = ptrk.parse_puretrack_record(point)
                            # If timestamp is the same, the last one is the only true
                            if p.get('timestamp') == last_timestamp:
                                continue
                            last_timestamp = p.get('timestamp')
                            logger.debug(f"Point: {p}")
                            # speed = calculate_speed(p, last)
                            # logger.info(f"Calculated speed: {speed} m/s")
                            last = p
                            pass
        else:
            logger.warning("Failed to retrieve group data.")
        time.sleep(30)

# def monitoring():
#     while True:
#         data = load_data()
#         status = evaluate_status(data)
#         if status:
#             send_alert(status)
#         time.sleep(60)  # Check every minute

def main():
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


# from flask import Flask, render_template, request, redirect, url_for
# from flask_mail import Mail
# from flask_sqlalchemy import SQLAlchemy
# from apscheduler.schedulers.background import BackgroundScheduler
# from datetime import datetime
# import os
#
# # Création de l'application Flask
# app = Flask(__name__)
# app.config.from_pyfile('config.py')  # Contient la configuration (DB, SMTP, etc.)
#
# db.init_app(app)
# mail = Mail(app)
#
# # Importer les modèles
# from models import User, Alert
#
# # Création de la base (si non existante)
# with app.app_context():
#     db.create_all()
#
# @app.route("/")
# def index():
#     users = User.query.all()
#     return render_template("index.html", users=users)
#
# @app.route("/add", methods=["GET", "POST"])
# def add_user():
#     if request.method == "POST":
#         new_user = User(
#             puretrack_account=request.form["puretrack_account"],
#             name=request.form["name"],
#             email=request.form["email"],
#             phone=request.form["phone"]
#         )
#         db.session.add(new_user)
#         db.session.commit()
#         return redirect(url_for("index"))
#     return render_template("add_user.html")
#
# @app.route("/delete/<int:user_id>")
# def delete_user(user_id):
#     user = User.query.get(user_id)
#     if user:
#         db.session.delete(user)
#         db.session.commit()
#     return redirect(url_for("index"))
#
# # Exemple de route pour afficher les alertes
# @app.route("/alerts")
# def alerts():
#     alerts = Alert.query.order_by(Alert.triggered_at.desc()).all()
#     return render_template("alerts.html", alerts=alerts)
#
# @app.route("/verify/<int:alert_id>", methods=["GET", "POST"])
# def verify_alert(alert_id):
#     alert = Alert.query.get_or_404(alert_id)
#     if request.method == "POST":
#         verifier = request.form["verifier"]
#         comment = request.form.get("comment", "")
#         alert.checked_at = datetime.utcnow()
#         alert.verified_by = verifier
#         alert.comment = comment
#         alert.checked = True
#         db.session.commit()
#         return redirect(url_for("alerts"))
#     return render_template("verify_alert.html", alert=alert)
#
# # Scheduler pour la vérification automatique de l'API PureTrack
# from tasks import check_aventuriers
# scheduler = BackgroundScheduler()
# scheduler.add_job(func=check_aventuriers, trigger="interval", minutes=1)
# scheduler.start()
#
# if __name__ == "__main__":
#     app.run(debug=True)

