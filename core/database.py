import sqlite3
from datetime import datetime
from contextlib import contextmanager
import threading

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Alerts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    alert_type TEXT NOT NULL,
                    description TEXT,
                    image_path TEXT,
                    is_acknowledged BOOLEAN DEFAULT 0,
                    face_detected TEXT,
                    confidence REAL
                )
            ''')
            
            # Known faces table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS known_faces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    role TEXT DEFAULT 'employee',
                    image_path TEXT,
                    encoding BLOB,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # System logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    level TEXT,
                    message TEXT
                )
            ''')
            
            # Settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def add_alert(self, alert_type, description, image_path=None, 
                  face_detected=None, confidence=None):
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO alerts (alert_type, description, image_path, 
                                       face_detected, confidence)
                    VALUES (?, ?, ?, ?, ?)
                ''', (alert_type, description, image_path, face_detected, confidence))
                conn.commit()
                return cursor.lastrowid
    
    def get_alerts(self, limit=50, offset=0, unacknowledged_only=False):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM alerts"
            if unacknowledged_only:
                query += " WHERE is_acknowledged = 0"
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            cursor.execute(query, (limit, offset))
            return [dict(row) for row in cursor.fetchall()]
    
    def acknowledge_alert(self, alert_id):
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE alerts SET is_acknowledged = 1 WHERE id = ?",
                    (alert_id,)
                )
                conn.commit()

    # ✅ NEW: Alert permanently delete karo
    def delete_alert(self, alert_id: int):
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM alerts WHERE id = ?",
                    (alert_id,)
                )
                conn.commit()

    # ✅ NEW: Saare alerts ek saath delete karo
    def delete_all_alerts(self):
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM alerts")
                conn.commit()

    def add_known_face(self, name, role, image_path, encoding):
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO known_faces (name, role, image_path, encoding)
                    VALUES (?, ?, ?, ?)
                ''', (name, role, image_path, encoding))
                conn.commit()
                return cursor.lastrowid
    
    def get_known_faces(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM known_faces WHERE is_active = 1")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_alert_stats(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_acknowledged = 0 THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN alert_type = 'intrusion' THEN 1 ELSE 0 END) as intrusions,
                    SUM(CASE WHEN alert_type = 'unknown_face' THEN 1 ELSE 0 END) as unknown_faces
                FROM alerts
                WHERE timestamp > datetime('now', '-24 hours')
            ''')
            return dict(cursor.fetchone())
    
    def log_event(self, level, message):
        with self.lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO system_logs (level, message) VALUES (?, ?)",
                    (level, message)
                )
                conn.commit()