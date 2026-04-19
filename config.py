import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Camera Settings
    CAMERA_SOURCE = int(os.getenv("CAMERA_SOURCE", 0))
    CAMERA_WIDTH = 320
    CAMERA_HEIGHT = 248
    FPS = 10
    
    # Detection Settings
    MOTION_THRESHOLD = 25
    MOTION_MIN_AREA = 5000
    FACE_RECOGNITION_TOLERANCE = 0.5
    DETECTION_COOLDOWN = 10  # seconds between alerts
    
    # Alert Settings
    ENABLE_EMAIL_ALERTS = os.getenv("ENABLE_EMAIL_ALERTS", "true").lower() == "true"
    ENABLE_SOUND_ALERTS = os.getenv("ENABLE_SOUND_ALERTS", "true").lower() == "true"
    
    # Email Configuration
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
    EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS", "").split(",")
    
    # Web Server
    WEB_HOST = "0.0.0.0"
    WEB_PORT = 5000
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
    
    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    KNOWN_FACES_DIR = os.path.join(DATA_DIR, "known_faces")
    CAPTURES_DIR = os.path.join(DATA_DIR, "captures")
    DATABASE_PATH = os.path.join(DATA_DIR, "database.db")
    LOG_FILE = os.path.join(BASE_DIR, "logs", "security.log")
    
    @classmethod
    def ensure_directories(cls):
        """Create necessary directories if they don't exist"""
        dirs = [cls.DATA_DIR, cls.KNOWN_FACES_DIR, cls.CAPTURES_DIR, 
                os.path.dirname(cls.LOG_FILE)]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
