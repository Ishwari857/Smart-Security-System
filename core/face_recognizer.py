import face_recognition
import cv2
import numpy as np
import pickle
import os
from datetime import datetime
import threading
from queue import Queue, Empty
import time

try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
    print("DeepFace loaded successfully.")
except ImportError:
    DEEPFACE_AVAILABLE = False
    print("WARNING: DeepFace not installed. Run: pip install deepface tf-keras")


class PeopleTracker:
    """
    Tracks people properly — ek person ek baar entry, ek baar exit.
    Face ID se track karta hai, frame-by-frame count nahi karta.
    """
    def __init__(self, exit_timeout=3.0):
        self.exit_timeout = exit_timeout  # seconds before marking as exited
        self.active_people = {}   # {person_id: {'name', 'last_seen', 'entry_time', 'age', 'gender'}}
        self.entry_log = []       # [{name, entry_time, exit_time, age, gender}]
        self.total_entries = 0
        self.total_exits = 0
        self.lock = threading.Lock()

        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _cleanup_loop(self):
        """Remove people who haven't been seen for exit_timeout seconds."""
        while True:
            time.sleep(1.0)
            now = time.time()
            with self.lock:
                to_remove = []
                for pid, info in self.active_people.items():
                    if now - info['last_seen'] > self.exit_timeout:
                        to_remove.append(pid)

                for pid in to_remove:
                    info = self.active_people.pop(pid)
                    self.total_exits += 1
                    # Update log entry
                    for log in reversed(self.entry_log):
                        if log['person_id'] == pid and log['exit_time'] is None:
                            log['exit_time'] = datetime.now().strftime('%H:%M:%S')
                            break

    def update(self, detected_faces):
        """
        Update tracker with currently detected faces.
        Returns: list of new entries this frame
        """
        now = time.time()
        new_entries = []

        with self.lock:
            seen_ids = set()

            for face in detected_faces:
                name = face.get('name', 'Unknown')
                age = face.get('age')
                gender = face.get('gender')

                # Use name as person_id (for known) or bbox hash (for unknown)
                if name != 'Unknown':
                    person_id = name
                else:
                    # For unknown — use bbox position as rough ID
                    bbox = face.get('bbox', (0, 0, 0, 0))
                    person_id = f"Unknown_{bbox[0]//50}_{bbox[1]//50}"

                seen_ids.add(person_id)

                if person_id not in self.active_people:
                    # NEW ENTRY
                    self.active_people[person_id] = {
                        'name': name,
                        'last_seen': now,
                        'entry_time': datetime.now().strftime('%H:%M:%S'),
                        'age': age,
                        'gender': gender
                    }
                    self.total_entries += 1
                    new_entries.append(person_id)

                    # Add to log
                    self.entry_log.append({
                        'person_id': person_id,
                        'name': name,
                        'entry_time': datetime.now().strftime('%H:%M:%S'),
                        'exit_time': None,
                        'age': age,
                        'gender': gender,
                        'date': datetime.now().strftime('%d %b %Y')
                    })

                    # Keep log max 200 entries
                    if len(self.entry_log) > 200:
                        self.entry_log.pop(0)
                else:
                    # Update last seen
                    self.active_people[person_id]['last_seen'] = now
                    if age:
                        self.active_people[person_id]['age'] = age
                    if gender:
                        self.active_people[person_id]['gender'] = gender

        return new_entries

    def get_stats(self):
        with self.lock:
            current = len(self.active_people)
            active_list = [
                {
                    'name': v['name'],
                    'entry_time': v['entry_time'],
                    'age': v.get('age'),
                    'gender': v.get('gender')
                }
                for v in self.active_people.values()
            ]
            # Recent log (last 50)
            recent_log = list(reversed(self.entry_log[-50:]))

            # Gender breakdown
            genders = {'Male': 0, 'Female': 0, 'Unknown': 0}
            for log in self.entry_log:
                g = log.get('gender') or 'Unknown'
                if g in genders:
                    genders[g] += 1
                else:
                    genders['Unknown'] += 1

        return {
            'current': current,
            'total_entries': self.total_entries,
            'total_exits': self.total_exits,
            'active_people': active_list,
            'log': recent_log,
            'gender_breakdown': genders
        }

    def reset(self):
        with self.lock:
            self.active_people.clear()
            self.entry_log.clear()
            self.total_entries = 0
            self.total_exits = 0


class FaceRecognizer:
    def __init__(self, known_faces_dir, tolerance=0.6, use_deepface=True,
                 deepface_model="VGG-Face", deepface_detector="skip"):
        self.known_faces_dir = known_faces_dir
        self.tolerance = tolerance
        self.use_deepface = use_deepface and DEEPFACE_AVAILABLE
        self.deepface_model = deepface_model
        self.deepface_detector = deepface_detector

        self.known_encodings = []
        self.known_names = []
        self.known_roles = []
        self.known_image_paths = {}
        self.lock = threading.Lock()

        # Background DeepFace thread
        self._df_queue = Queue(maxsize=2)
        self._df_results = {}
        self._df_lock = threading.Lock()
        self._df_thread = threading.Thread(target=self._deepface_worker, daemon=True)
        self._df_thread.start()

        # People tracker
        self.people_tracker = PeopleTracker(exit_timeout=3.0)

        # Current frame count
        self.frame_count = 0
        self.people_count = 0

        # Age/gender stats (from DeepFace)
        self.gender_count = {'Male': 0, 'Female': 0, 'Unknown': 0}
        self.age_groups = {
            'Child (0-12)': 0, 'Teen (13-19)': 0,
            'Adult (20-40)': 0, 'Middle (41-60)': 0, 'Senior (60+)': 0
        }

        self.load_known_faces()
        self.on_unknown_face = None
        self.on_known_face = None

    def _deepface_worker(self):
        while True:
            try:
                job = self._df_queue.get(timeout=1)
                if job is None:
                    break
                face_key = job['key']
                face_crop = job['crop']
                candidate = job['candidate']
                action = job['action']

                if action == 'verify' and candidate:
                    known_path = self.known_image_paths.get(candidate)
                    if known_path and os.path.exists(known_path):
                        try:
                            result = DeepFace.verify(
                                img1_path=face_crop,
                                img2_path=known_path,
                                model_name=self.deepface_model,
                                detector_backend=self.deepface_detector,
                                enforce_detection=False,
                                silent=True
                            )
                            with self._df_lock:
                                self._df_results[face_key] = {
                                    'verified': result['verified'],
                                    'distance': result['distance'],
                                    'analysis': None
                                }
                        except Exception:
                            pass

                elif action == 'analyze':
                    try:
                        analysis = DeepFace.analyze(
                            img_path=face_crop,
                            actions=['age', 'gender', 'emotion'],
                            detector_backend=self.deepface_detector,
                            enforce_detection=False,
                            silent=True
                        )
                        if isinstance(analysis, list):
                            analysis = analysis[0]
                        age = analysis.get('age')
                        gender = analysis.get('dominant_gender')
                        emotion = analysis.get('dominant_emotion')
                        if gender and gender in self.gender_count:
                            self.gender_count[gender] += 1
                        if age:
                            ag = self._get_age_group(age)
                            self.age_groups[ag] = self.age_groups.get(ag, 0) + 1
                        with self._df_lock:
                            existing = self._df_results.get(face_key, {})
                            existing['analysis'] = {'age': age, 'gender': gender, 'emotion': emotion}
                            self._df_results[face_key] = existing
                    except Exception:
                        pass

                self._df_queue.task_done()
            except Empty:
                continue
            except Exception:
                continue

    def _submit_deepface_job(self, face_key, face_crop, candidate=None, action='analyze'):
        if not self.use_deepface:
            return
        if face_crop is None or face_crop.size == 0:
            return
        try:
            self._df_queue.put_nowait({
                'key': face_key, 'crop': face_crop.copy(),
                'candidate': candidate, 'action': action
            })
        except Exception:
            pass

    def _get_deepface_result(self, face_key):
        with self._df_lock:
            return self._df_results.get(face_key)

    def load_known_faces(self):
        if not os.path.exists(self.known_faces_dir):
            os.makedirs(self.known_faces_dir)
            return
        encodings_file = os.path.join(self.known_faces_dir, "encodings.pkl")
        if os.path.exists(encodings_file):
            with open(encodings_file, 'rb') as f:
                data = pickle.load(f)
                self.known_encodings = data['encodings']
                self.known_names = data['names']
                self.known_roles = data.get('roles', ['unknown'] * len(self.known_names))
                self.known_image_paths = data.get('image_paths', {})
            print(f"Loaded {len(self.known_names)} known faces")
            return
        self._load_from_images()

    def _load_from_images(self):
        encodings, names, roles, image_paths = [], [], [], {}
        for filename in os.listdir(self.known_faces_dir):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                name_parts = os.path.splitext(filename)[0].split('_')
                name = name_parts[0]
                role = name_parts[1] if len(name_parts) > 1 else 'employee'
                image_path = os.path.join(self.known_faces_dir, filename)
                image = face_recognition.load_image_file(image_path)
                face_encodings = face_recognition.face_encodings(image)
                if face_encodings:
                    encodings.append(face_encodings[0])
                    names.append(name)
                    roles.append(role)
                    image_paths[name] = image_path
                    print(f"Loaded face: {name} ({role})")
        self.known_encodings = encodings
        self.known_names = names
        self.known_roles = roles
        self.known_image_paths = image_paths
        self.save_encodings()

    def save_encodings(self):
        encodings_file = os.path.join(self.known_faces_dir, "encodings.pkl")
        with open(encodings_file, 'wb') as f:
            pickle.dump({
                'encodings': self.known_encodings,
                'names': self.known_names,
                'roles': self.known_roles,
                'image_paths': self.known_image_paths
            }, f)

    def add_face(self, image, name, role='employee'):
        image_path_to_save = None
        if isinstance(image, str):
            image_path_to_save = image
            image = face_recognition.load_image_file(image)
        elif isinstance(image, np.ndarray) and len(image.shape) == 3 and image.shape[2] == 3:
            if image.dtype == np.uint8:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(image)
        if not encodings:
            return False, "No face detected in image"
        with self.lock:
            self.known_encodings.append(encodings[0])
            self.known_names.append(name)
            self.known_roles.append(role)
            if image_path_to_save:
                self.known_image_paths[name] = image_path_to_save
            else:
                save_path = os.path.join(self.known_faces_dir, f"{name}_{role}.jpg")
                bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                cv2.imwrite(save_path, bgr)
                self.known_image_paths[name] = save_path
            self.save_encodings()
        return True, f"Added face for {name}"

    def _get_age_group(self, age):
        if age is None: return 'Unknown'
        if age <= 12: return 'Child (0-12)'
        elif age <= 19: return 'Teen (13-19)'
        elif age <= 40: return 'Adult (20-40)'
        elif age <= 60: return 'Middle (41-60)'
        else: return 'Senior (60+)'

    def get_stats(self):
        return self.people_tracker.get_stats()

    def recognize(self, frame, scale=0.5):
        self.frame_count += 1

        small_frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_frame, model='hog')
        face_encodings_list = face_recognition.face_encodings(rgb_frame, face_locations)

        self.people_count = len(face_locations)
        results = []

        for i, ((top, right, bottom, left), face_encoding) in enumerate(
                zip(face_locations, face_encodings_list)):
            top    = int(top    / scale)
            right  = int(right  / scale)
            bottom = int(bottom / scale)
            left   = int(left   / scale)

            name = "Unknown"
            role = "intruder"
            confidence = 0.0
            face_key = f"{self.frame_count}_{i}"

            if self.known_encodings:
                distances = face_recognition.face_distance(self.known_encodings, face_encoding)
                best_idx = np.argmin(distances)
                if distances[best_idx] < self.tolerance:
                    name = self.known_names[best_idx]
                    role = self.known_roles[best_idx]
                    confidence = float(1 - distances[best_idx])
                    face_crop = frame[top:bottom, left:right]
                    self._submit_deepface_job(face_key, face_crop, candidate=name, action='verify')
                else:
                    face_crop = frame[top:bottom, left:right]
                    self._submit_deepface_job(face_key, face_crop, action='analyze')

            face_crop = frame[top:bottom, left:right]
            self._submit_deepface_job(f"analyze_{i}", face_crop, action='analyze')

            df_result = self._get_deepface_result(face_key)
            deepface_verified = df_result.get('verified') if df_result else None
            deepface_distance = df_result.get('distance') if df_result else None
            deepface_analysis = df_result.get('analysis') if df_result else None

            analyze_result = self._get_deepface_result(f"analyze_{i}")
            if analyze_result and analyze_result.get('analysis'):
                deepface_analysis = analyze_result['analysis']

            result = {
                'name': name,
                'role': role,
                'confidence': confidence,
                'bbox': (left, top, right - left, bottom - top),
                'is_known': name != "Unknown",
                'deepface_verified': deepface_verified,
                'deepface_distance': deepface_distance,
                'deepface_analysis': deepface_analysis,
                'age': deepface_analysis.get('age') if deepface_analysis else None,
                'gender': deepface_analysis.get('gender') if deepface_analysis else None,
            }
            results.append(result)

            if name == "Unknown" and self.on_unknown_face:
                self.on_unknown_face(frame, result)
            elif name != "Unknown" and self.on_known_face:
                self.on_known_face(frame, result)

        # Update people tracker — proper entry/exit
        self.people_tracker.update(results)

        return results

    def draw_faces(self, frame, faces):
        annotated = frame.copy()

        # People count overlay
        count = len(faces)
        cv2.rectangle(annotated, (8, 8), (230, 48), (0, 0, 0), -1)
        cv2.putText(annotated, f"PEOPLE: {count}", (12, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 212, 255), 2)

        for face in faces:
            x, y, w, h = face['bbox']
            if face['is_known']:
                color = (0, 165, 255) if face.get('deepface_verified') is False else (0, 255, 0)
            else:
                color = (0, 0, 255)

            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)

            label = f"{face['name']} ({face['confidence']:.1%})"
            lsz = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(annotated, (x, y - 30), (x + lsz[0] + 10, y), color, -1)
            cv2.putText(annotated, label, (x + 5, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            analysis = face.get('deepface_analysis')
            if analysis:
                parts = []
                if analysis.get('age'): parts.append(f"Age:{analysis['age']}")
                if analysis.get('gender'): parts.append(f"{analysis['gender']}")
                if analysis.get('emotion'): parts.append(f"{analysis['emotion']}")
                if parts:
                    cv2.putText(annotated, "  ".join(parts),
                                (x, y + h + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            dv = face.get('deepface_verified')
            if dv is True:
                cv2.putText(annotated, "DF:OK", (x + w - 55, y + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
            elif dv is False:
                cv2.putText(annotated, "DF:NO", (x + w - 55, y + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)

        return annotated