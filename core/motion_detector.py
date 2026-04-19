import cv2
import numpy as np
from datetime import datetime
import threading

class MotionDetector:
    def __init__(self, threshold=25, min_area=5000, history=500):
        self.threshold = threshold
        self.min_area = min_area
        
        # Background subtractor
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=threshold,
            detectShadows=True
        )
        
        self.last_motion_time = None
        self.motion_detected = False
        self.motion_regions = []
        self.lock = threading.Lock()
        
        # Callbacks
        self.on_motion_start = None
        self.on_motion_end = None
    
    def detect(self, frame):
        """Process frame and detect motion"""
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(frame, (21, 21), 0)
        
        # Apply background subtraction
        fg_mask = self.bg_subtractor.apply(blurred)
        
        # Remove shadows (shadows are marked as 127)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        
        # Morphological operations to clean up the mask
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        
        # Dilate to fill gaps
        fg_mask = cv2.dilate(fg_mask, kernel, iterations=2)
        
        # Find contours
        contours, _ = cv2.findContours(
            fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        motion_regions = []
        total_motion_area = 0
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > self.min_area:
                x, y, w, h = cv2.boundingRect(contour)
                motion_regions.append({
                    'bbox': (x, y, w, h),
                    'area': area,
                    'contour': contour
                })
                total_motion_area += area
        
        with self.lock:
            previous_state = self.motion_detected
            self.motion_detected = len(motion_regions) > 0
            self.motion_regions = motion_regions
            
            if self.motion_detected:
                self.last_motion_time = datetime.now()
                
                # Trigger callback on motion start
                if not previous_state and self.on_motion_start:
                    self.on_motion_start(frame, motion_regions)
            
            elif previous_state and self.on_motion_end:
                self.on_motion_end()
        
        return self.motion_detected, motion_regions, fg_mask
    
    def draw_motion(self, frame, regions=None):
        """Draw motion regions on frame"""
        if regions is None:
            regions = self.motion_regions
        
        annotated = frame.copy()
        
        for region in regions:
            x, y, w, h = region['bbox']
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 0, 255), 2)
            
            # Add label
            label = f"Motion: {region['area']}px"
            cv2.putText(annotated, label, (x, y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(annotated, timestamp, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Add motion status
        status = "MOTION DETECTED" if self.motion_detected else "No Motion"
        color = (0, 0, 255) if self.motion_detected else (0, 255, 0)
        cv2.putText(annotated, status, (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        return annotated
    
    def reset(self):
        """Reset background model"""
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=self.threshold,
            detectShadows=True
        )
