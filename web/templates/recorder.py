import cv2
import os
import threading
from datetime import datetime

class VideoRecorder:
    def __init__(self, captures_dir):
        self.captures_dir = str(captures_dir)
        self.recording = False
        self.writer = None
        self.thread = None
        self.current_file = None
        self.lock = threading.Lock()
        self.fps = 20
        self.frame_size = (640, 480)

    def start_recording(self, frame_size=None):
        with self.lock:
            if self.recording:
                return self.current_file
            if frame_size:
                self.frame_size = frame_size
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"recording_{timestamp}.avi"
            filepath = os.path.join(self.captures_dir, filename)
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            self.writer = cv2.VideoWriter(filepath, fourcc, self.fps, self.frame_size)
            self.recording = True
            self.current_file = filename
            return filename

    def write_frame(self, frame):
        with self.lock:
            if self.recording and self.writer:
                resized = cv2.resize(frame, self.frame_size)
                self.writer.write(resized)

    def stop_recording(self):
        with self.lock:
            if not self.recording:
                return None
            self.recording = False
            if self.writer:
                self.writer.release()
                self.writer = None
            fname = self.current_file
            self.current_file = None
            return fname

    def is_recording(self):
        return self.recording