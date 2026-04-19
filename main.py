"""
main.py — SecureGuard Pro Entry Point
"""

import logging
import logging.handlers
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from config import Config

def setup_logging():
    logger = logging.getLogger("secureguard")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s — %(message)s", "%H:%M:%S")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    try:
        fh = logging.handlers.RotatingFileHandler(
            Config.LOG_FILE, maxBytes=10*1024*1024, backupCount=5
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    return logger

def main():
    logger = setup_logging()
    logger.info("SecureGuard Pro — Starting Up")

    # --- Database ---
    db = None
    try:
        from core.database import Database
        db = Database(db_path=str(Config.DATABASE_PATH))
        logger.info("Database ready.")
    except Exception as e:
        logger.error(f"Database error: {e}")

    # --- Alert System ---
    class AlertConfig:
        DETECTION_COOLDOWN   = Config.DETECTION_COOLDOWN
        ENABLE_EMAIL_ALERTS  = Config.ENABLE_EMAIL_ALERTS
        EMAIL_SENDER         = Config.EMAIL_SENDER
        EMAIL_PASSWORD       = Config.EMAIL_PASSWORD
        EMAIL_RECIPIENTS     = Config.EMAIL_RECIPIENTS
        SMTP_SERVER          = Config.SMTP_SERVER
        SMTP_PORT            = Config.SMTP_PORT
        CAPTURES_DIR         = str(Config.CAPTURES_DIR)
        EMAIL_PASSWORD       = Config.EMAIL_PASSWORD if hasattr(Config, 'EMAIL_PASSWORD') else ''

    alert_system = None
    try:
        from core.alert_system import AlertSystem
        alert_system = AlertSystem(config=AlertConfig, database=db)
        alert_system.start()
        logger.info("Alert system ready.")
    except Exception as e:
        logger.warning(f"Alert system skipped: {e}")

    # --- Camera ---
    camera = None
    try:
        from core.camera import Camera
        camera = Camera(
            source=Config.CAMERA_SOURCE,
            width=Config.CAMERA_WIDTH,
            height=Config.CAMERA_HEIGHT,
            fps=Config.FPS
        )
        camera.start()
        logger.info("Camera started.")
    except Exception as e:
        logger.warning(f"Camera init skipped: {e}")

    # --- Motion Detector ---
    motion_detector = None
    try:
        from core.motion_detector import MotionDetector
        motion_detector = MotionDetector(
            threshold=Config.MOTION_THRESHOLD,
            min_area=Config.MOTION_MIN_AREA
        )
        if alert_system:
            def on_motion(frame, regions):
                alert_system.trigger_alert(
                    alert_type="motion",
                    description=f"Motion detected in {len(regions)} region(s)",
                    frame=frame
                )
            motion_detector.on_motion_start = on_motion
        logger.info("Motion detector ready.")
    except Exception as e:
        logger.warning(f"Motion init skipped: {e}")

    # --- Face Recognizer ---
    face_recognizer = None
    try:
        from core.face_recognizer import FaceRecognizer
        face_recognizer = FaceRecognizer(
            known_faces_dir=str(Config.KNOWN_FACES_DIR),
            use_deepface=True,
            deepface_model="VGG-Face",
            deepface_detector="opencv"
        )
        if alert_system and face_recognizer:
            def on_unknown_face(frame, result):
                analysis = result.get('deepface_analysis')
                extra = ""
                if analysis:
                    parts = []
                    if analysis.get('age'):
                        parts.append(f"Age~{analysis['age']}")
                    if analysis.get('gender'):
                        parts.append(analysis['gender'])
                    if analysis.get('emotion'):
                        parts.append(analysis['emotion'])
                    if parts:
                        extra = " | " + ", ".join(parts)
                alert_system.trigger_alert(
                    alert_type="unknown_face",
                    description=f"Unknown person detected!{extra}",
                    frame=frame
                )
            def on_known_face(frame, result):
                analysis = result.get('deepface_analysis')
                extra = ""
                if analysis:
                    parts = []
                    if analysis.get('age'):
                        parts.append(f"Age~{analysis['age']}")
                    if analysis.get('emotion'):
                        parts.append(analysis['emotion'])
                    if parts:
                        extra = " | " + ", ".join(parts)
                alert_system.trigger_alert(
                    alert_type="face",
                    description=f"Known person: {result['name']} ({result['role']}){extra}",
                    frame=frame
                )
            face_recognizer.on_unknown_face = on_unknown_face
            face_recognizer.on_known_face   = on_known_face
        logger.info("Face recognizer ready.")
    except Exception as e:
        logger.warning(f"Face recognition skipped: {e}")

   
   
    # --- People Counter ---
    people_counter = None
    try:
        from core.people_counter import PeopleCounter
        people_counter = PeopleCounter(
            line_position=0.5,       # frame ke middle me line
            direction='horizontal',
            min_track_frames=3,
            max_disappeared=20
        )
        if alert_system:
            def on_entry(name):
                alert_system.trigger_alert(
                    alert_type="entry",
                    description=f"Person entered: {name}",
                    frame=None
                )
            def on_exit(name):
                alert_system.trigger_alert(
                    alert_type="exit",
                    description=f"Person exited: {name}",
                    frame=None
                )
            people_counter.on_entry = on_entry
            people_counter.on_exit  = on_exit
        logger.info("People counter ready.")
    except Exception as e:
        logger.warning(f"People counter skipped: {e}")

    # --- Flask App ---
    try:
        from web.app import create_app
        app, socketio = create_app(
            config=Config,
            camera=camera,
            motion_detector=motion_detector,
            face_recognizer=face_recognizer,
            alert_system=alert_system,
            database=db,
           
            people_counter=people_counter
        )
        host = Config.WEB_HOST
        port = Config.WEB_PORT
        logger.info(f"Dashboard: http://localhost:{port}")
        logger.info("System ready. Access dashboard at localhost:5000")
        socketio.run(app, host=host, port=port, debug=False)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}")
        raise

if __name__ == "__main__":
    main()