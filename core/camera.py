import cv2
import threading
import time
from queue import Queue
import numpy as np

class Camera:
    def __init__(self, source=0, width=640, height=480, fps=15):
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps
        
        self.cap = None
        self.frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.thread = None
        
        self.frame_queue = Queue(maxsize=10)
        self.subscribers = []
    
    def start(self):
        if self.running:
            return True
        
        # CAP_DSHOW fixes Windows webcam hang issue
        self.cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
        
        if not self.cap.isOpened():
            # Fallback without DSHOW
            self.cap = cv2.VideoCapture(self.source)
            if not self.cap.isOpened():
                raise RuntimeError(f"Cannot open camera source: {self.source}")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        
        # Wait for first frame
        for _ in range(30):
            if self.frame is not None:
                break
            time.sleep(0.1)
        
        return True
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()
            self.cap = None
    
    def _capture_loop(self):
        while self.running:
            try:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.frame_lock:
                        self.frame = frame.copy()
                    
                    for callback in self.subscribers:
                        try:
                            callback(frame)
                        except Exception as e:
                            print(f"Subscriber error: {e}")
                    
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
                else:
                    time.sleep(0.05)
            except Exception as e:
                print(f"Capture error: {e}")
                time.sleep(0.1)
            
            time.sleep(1 / self.fps)
    
    def get_frame(self):
        with self.frame_lock:
            return self.frame.copy() if self.frame is not None else None
    
    def get_jpeg_frame(self, quality=80):
        frame = self.get_frame()
        if frame is None:
            return None
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        _, jpeg = cv2.imencode('.jpg', frame, encode_params)
        return jpeg.tobytes()
    
    def subscribe(self, callback):
        self.subscribers.append(callback)
    
    def unsubscribe(self, callback):
        if callback in self.subscribers:
            self.subscribers.remove(callback)
    
    @property
    def is_running(self):
        return self.running