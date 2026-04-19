import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import cv2
import os
from datetime import datetime
import threading
from queue import Queue
import time

class AlertSystem:
    def __init__(self, config, database):
        self.config = config
        self.database = database
        
        self.alert_queue = Queue()
        self.running = False
        self.alert_thread = None
        
        self.last_alert_time = {}
        self.cooldown = config.DETECTION_COOLDOWN
        
        # WebSocket callback for real-time updates
        self.on_alert = None
    
    def start(self):
        self.running = True
        self.alert_thread = threading.Thread(target=self._process_alerts, daemon=True)
        self.alert_thread.start()
    
    def stop(self):
        self.running = False
        if self.alert_thread:
            self.alert_thread.join(timeout=2)
    
    def _can_send_alert(self, alert_type):
        """Check if enough time has passed since last alert of this type"""
        now = time.time()
        last_time = self.last_alert_time.get(alert_type, 0)
        
        if now - last_time >= self.cooldown:
            self.last_alert_time[alert_type] = now
            return True
        return False
    
    def trigger_alert(self, alert_type, description, frame=None, face_info=None):
        """Queue an alert for processing"""
        if not self._can_send_alert(alert_type):
            return None
        
        alert_data = {
            'type': alert_type,
            'description': description,
            'frame': frame,
            'face_info': face_info,
            'timestamp': datetime.now()
        }
        
        self.alert_queue.put(alert_data)
        return alert_data
    
    def _process_alerts(self):
        """Background thread to process alerts"""
        while self.running:
            try:
                if not self.alert_queue.empty():
                    alert = self.alert_queue.get(timeout=1)
                    self._handle_alert(alert)
                else:
                    time.sleep(0.1)
            except Exception as e:
                print(f"Alert processing error: {e}")
    
    def _handle_alert(self, alert):
        """Process a single alert"""
        # Save capture image
        image_path = None
        if alert['frame'] is not None:
            image_path = self._save_capture(alert['frame'], alert['type'])
        
        # Get face info
        face_name = None
        confidence = None
        if alert['face_info']:
            face_name = alert['face_info'].get('name')
            confidence = alert['face_info'].get('confidence')
        
        # Save to database
        alert_id = self.database.add_alert(
            alert_type=alert['type'],
            description=alert['description'],
            image_path=image_path,
            face_detected=face_name,
            confidence=confidence
        )
        
        # Send email notification
        if self.config.ENABLE_EMAIL_ALERTS:
            self._send_email_alert(alert, image_path)
        
        # Trigger real-time callback (for WebSocket)
        if self.on_alert:
            self.on_alert({
                'id': alert_id,
                'type': alert['type'],
                'description': alert['description'],
                'timestamp': alert['timestamp'].isoformat(),
                'image_path': image_path,
                'face_detected': face_name
            })
        
        # Log event
        self.database.log_event('ALERT', f"{alert['type']}: {alert['description']}")
    
    def _save_capture(self, frame, alert_type):
        """Save frame as image file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{alert_type}_{timestamp}.jpg"
        filepath = os.path.join(self.config.CAPTURES_DIR, filename)
        
        cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        
        return filepath
    
    def _send_email_alert(self, alert, image_path=None):
        """Send email notification"""
        if not self.config.EMAIL_SENDER or not self.config.EMAIL_RECIPIENTS:
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config.EMAIL_SENDER
            msg['To'] = ', '.join(self.config.EMAIL_RECIPIENTS)
            msg['Subject'] = f"🚨 Security Alert: {alert['type'].upper()}"
            
            # Email body
            body = f"""
            <html>
            <body>
            <h2>Security Alert</h2>
            <p><strong>Type:</strong> {alert['type']}</p>
            <p><strong>Time:</strong> {alert['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>Description:</strong> {alert['description']}</p>
            """
            
            if alert['face_info']:
                body += f"""
                <p><strong>Face Detected:</strong> {alert['face_info'].get('name', 'Unknown')}</p>
                <p><strong>Confidence:</strong> {alert['face_info'].get('confidence', 0):.1%}</p>
                """
            
            body += """
            <p>Please check the security dashboard for more details.</p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(body, 'html'))
            
            # Attach image if available
            if image_path and os.path.exists(image_path):
                with open(image_path, 'rb') as f:
                    img = MIMEImage(f.read())
                    img.add_header('Content-Disposition', 'attachment', 
                                  filename=os.path.basename(image_path))
                    msg.attach(img)
            
            # Send email
            with smtplib.SMTP(self.config.SMTP_SERVER, self.config.SMTP_PORT) as server:
                server.starttls()
                server.login(self.config.EMAIL_SENDER, self.config.EMAIL_PASSWORD)
                server.send_message(msg)
            
            print(f"Email alert sent for {alert['type']}")
            
        except Exception as e:
            print(f"Failed to send email: {e}")
