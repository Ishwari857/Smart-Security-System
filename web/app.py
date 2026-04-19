from flask import Flask, render_template, Response, jsonify, request, send_from_directory, redirect, url_for, session
from flask_socketio import SocketIO, emit
import cv2
import os
import time
import threading
import requests
from datetime import datetime
from functools import wraps


class VideoRecorder:
    def __init__(self, captures_dir):
        self.captures_dir = str(captures_dir)
        self.recording = False
        self.writer = None
        self.current_file = None
        self.lock = threading.Lock()
        self.fps = 15
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


def create_app(config, camera, motion_detector, face_recognizer,
               alert_system, database, people_counter=None):

    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config['SECRET_KEY'] = getattr(config, 'SECRET_KEY', 'secureguard-secret')

    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
    video_recorder = VideoRecorder(config.CAPTURES_DIR)
    _auto_stop_timer = [None]

    def _schedule_auto_stop():
        if _auto_stop_timer[0] is not None:
            _auto_stop_timer[0].cancel()
        def do_stop():
            fname = video_recorder.stop_recording()
            if fname:
                socketio.emit('recording_stopped', {'filename': fname})
        t = threading.Timer(10.0, do_stop)
        t.daemon = True
        t.start()
        _auto_stop_timer[0] = t

    admin_credentials = {
        'username': os.environ.get("ADMIN_USER", "admin"),
        'password': os.environ.get("ADMIN_PASS", "Admin@1234")
    }

    def login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('logged_in'):
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated

    @app.after_request
    def add_no_cache(response):
        if not session.get('logged_in'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    def broadcast_alert(alert_data):
        socketio.emit('new_alert', alert_data)

    if alert_system:
        alert_system.on_alert = broadcast_alert

    @app.template_filter('basename')
    def basename_filter(path):
        return os.path.basename(path) if path else ''

    # ── AUTH ──
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        if request.method == 'POST':
            if (request.form.get('username') == admin_credentials['username'] and
                    request.form.get('password') == admin_credentials['password']):
                session['logged_in'] = True
                return redirect(url_for('index'))
            error = 'Invalid credentials'
        return render_template('login.html', error=error)

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    # ── PAGES ──
    @app.route('/')
    @login_required
    def index():
        stats = database.get_alert_stats()
        return render_template('index.html', stats=stats)

    @app.route('/live')
    @login_required
    def live():
        return render_template('live.html')

    @app.route('/alerts')
    @login_required
    def alerts():
        page = request.args.get('page', 1, type=int)
        per_page = 20
        alerts_list = database.get_alerts(limit=per_page, offset=(page - 1) * per_page)
        return render_template('alerts.html', alerts=alerts_list, page=page)

    @app.route('/settings')
    @login_required
    def settings():
        faces = database.get_known_faces()
        return render_template('settings.html', faces=faces)

    @app.route('/people')
    @login_required
    def people():
        return render_template('people.html')

    # ── VIDEO FEED ──
    @app.route('/api/video_feed')
    def video_feed():
        def generate():
            frame_num  = 0
           
            while True:
                if camera is None:
                    time.sleep(0.1)
                    continue
                frame = camera.get_frame()
                if frame is None:
                    time.sleep(0.05)
                    continue
                try:
                    frame_num += 1
                    annotated  = frame.copy()

                    if motion_detector:
                        motion_detected, regions, _ = motion_detector.detect(frame)
                        annotated = motion_detector.draw_motion(frame, regions)
                        if motion_detected:
                            if not video_recorder.is_recording():
                                fname = video_recorder.start_recording(
                                    (frame.shape[1], frame.shape[0]))
                                socketio.emit('recording_started', {'filename': fname})
                            _schedule_auto_stop()

                    faces = []

                    if face_recognizer:
                        faces = face_recognizer.recognize(annotated)
                        annotated = face_recognizer.draw_faces(annotated, faces)

                    # ── People Counter ──
                    if people_counter and faces is not None:
                        annotated = people_counter.update(annotated, faces)

                        # Emit people stats every 15 frames
                        if frame_num % 15 == 0:
                            socketio.emit('people_stats', people_counter.get_stats())            
                                    
                    video_recorder.write_frame(annotated)

                    _, buffer = cv2.imencode('.jpg', annotated,
                                            [cv2.IMWRITE_JPEG_QUALITY, 75])
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' +
                           buffer.tobytes() + b'\r\n')

                except Exception as e:
                    print(f"Frame error: {e}")
                    time.sleep(0.1)

        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

    # ── SNAPSHOT ──
    @app.route('/api/snapshot', methods=['POST'])
    def snapshot():
        if camera is None:
            return jsonify({'error': 'Camera not available'}), 400
        frame = camera.get_frame()
        if frame is None:
            return jsonify({'error': 'No frame available'}), 400
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename  = f"snapshot_{timestamp}.jpg"
        filepath  = os.path.join(str(config.CAPTURES_DIR), filename)
        cv2.imwrite(filepath, frame)
        return jsonify({'success': True, 'filename': filename})

    # ── RECORDING ──
    @app.route('/api/recording/start', methods=['POST'])
    @login_required
    def start_recording():
        if video_recorder.is_recording():
            return jsonify({'error': 'Already recording', 'filename': video_recorder.current_file})
        frame = camera.get_frame() if camera else None
        size  = (frame.shape[1], frame.shape[0]) if frame is not None else None
        fname = video_recorder.start_recording(size)
        socketio.emit('recording_started', {'filename': fname})
        return jsonify({'success': True, 'filename': fname})

    @app.route('/api/recording/stop', methods=['POST'])
    @login_required
    def stop_recording():
        if _auto_stop_timer[0] is not None:
            _auto_stop_timer[0].cancel()
            _auto_stop_timer[0] = None
        fname = video_recorder.stop_recording()
        if fname:
            socketio.emit('recording_stopped', {'filename': fname})
            return jsonify({'success': True, 'filename': fname})
        return jsonify({'error': 'Not currently recording'})

    @app.route('/api/recording/status')
    def recording_status():
        return jsonify({'recording': video_recorder.is_recording(),
                        'filename': video_recorder.current_file})

    @app.route('/api/recordings')
    @login_required
    def list_recordings():
        files = []
        captures_dir = str(config.CAPTURES_DIR)
        for f in os.listdir(captures_dir):
            if f.startswith('recording_') and f.endswith('.avi'):
                fpath = os.path.join(captures_dir, f)
                files.append({
                    'filename': f,
                    'size_mb' : round(os.path.getsize(fpath) / 1024 / 1024, 2),
                    'created' : datetime.fromtimestamp(
                        os.path.getctime(fpath)).strftime('%Y-%m-%d %H:%M:%S')
                })
        files.sort(key=lambda x: x['created'], reverse=True)
        return jsonify(files)

    @app.route('/api/recordings/<path:filename>', methods=['DELETE'])
    @login_required
    def delete_recording(filename):
        try:
            fpath = os.path.join(str(config.CAPTURES_DIR), filename)
            if os.path.exists(fpath):
                os.remove(fpath)
                return jsonify({'success': True})
            return jsonify({'error': 'File not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # ── PEOPLE COUNTER API ──
    @app.route('/api/people_stats')
    def people_stats():
        if people_counter:
            return jsonify(people_counter.get_stats())
        if face_recognizer:
            try:
                return jsonify(face_recognizer.get_stats())
            except Exception:
                pass
        return jsonify({
            'entry': 0, 'exit': 0, 'current': 0,
            'total_visited': 0, 'log': []
        })

    @app.route('/api/people_counter/reset', methods=['POST'])
    @login_required
    def reset_people_counter():
        if people_counter:
            people_counter.reset()
        return jsonify({'success': True})

   
    # ── PASSWORD CHANGE ──
    @app.route('/api/change_password', methods=['POST'])
    @login_required
    def change_password():
        data     = request.json
        current  = data.get('current_password', '')
        new_pass = data.get('new_password', '')
        if current != admin_credentials['password']:
            return jsonify({'error': 'Current password is incorrect'}), 400
        if len(new_pass) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        admin_credentials['password'] = new_pass
        return jsonify({'success': True})

    # ── ALERTS API ──
    @app.route('/api/alerts')
    def api_alerts():
        limit = request.args.get('limit', 50, type=int)
        return jsonify(database.get_alerts(limit=limit))

    @app.route('/api/alerts/<int:alert_id>/acknowledge', methods=['POST'])
    def acknowledge_alert(alert_id):
        database.acknowledge_alert(alert_id)
        return jsonify({'success': True})

    @app.route('/api/alerts/acknowledge_all', methods=['POST'])
    def acknowledge_all():
        for alert in database.get_alerts(limit=1000):
            if not alert.get('is_acknowledged'):
                database.acknowledge_alert(alert['id'])
        return jsonify({'success': True})

    @app.route('/api/alerts/<int:alert_id>/delete', methods=['DELETE'])
    def delete_alert(alert_id):
        try:
            database.delete_alert(alert_id)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/alerts/delete_all', methods=['DELETE'])
    def delete_all_alerts():
        try:
            database.delete_all_alerts()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/stats')
    def api_stats():
        return jsonify(database.get_alert_stats())

    # ── FACES API ──
    @app.route('/api/faces', methods=['GET', 'POST'])
    def api_faces():
        if request.method == 'GET':
            return jsonify(database.get_known_faces())
        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400
        file     = request.files['image']
        name     = request.form.get('name', 'Unknown')
        role     = request.form.get('role', 'employee')
        filename = f"{name}_{role}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        filepath = os.path.join(str(config.KNOWN_FACES_DIR), filename)
        file.save(filepath)
        success, message = face_recognizer.add_face(filepath, name, role)
        if success:
            database.add_known_face(name, role, filepath, None)
            return jsonify({'success': True, 'message': message})
        os.remove(filepath)
        return jsonify({'error': message}), 400

    @app.route('/api/faces/<int:face_id>', methods=['DELETE'])
    def delete_face(face_id):
        try:
            with database.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name, image_path FROM known_faces WHERE id = ?", (face_id,))
                row = cursor.fetchone()
                if row:
                    name, image_path = row['name'], row['image_path']
                    if face_recognizer and name in face_recognizer.known_names:
                        idxs = [i for i, n in enumerate(face_recognizer.known_names) if n == name]
                        for idx in sorted(idxs, reverse=True):
                            face_recognizer.known_encodings.pop(idx)
                            face_recognizer.known_names.pop(idx)
                            face_recognizer.known_roles.pop(idx)
                        face_recognizer.known_image_paths.pop(name, None)
                        face_recognizer.save_encodings()
                    if image_path and os.path.exists(image_path):
                        try: os.remove(image_path)
                        except: pass
                cursor.execute("UPDATE known_faces SET is_active = 0 WHERE id = ?", (face_id,))
                conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # ── TELEGRAM ──
    @app.route('/api/send_telegram', methods=['POST'])
    def send_telegram():
        try:
            data    = request.json
            token   = data.get('token', '')
            chat_id = data.get('chat_id', '')
            message = data.get('message', 'Security Alert!')
            url     = f"https://api.telegram.org/bot{token}/sendMessage"
            res     = requests.post(url, json={'chat_id': chat_id, 'text': message})
            if res.ok:
                return jsonify({'success': True})
            return jsonify({'error': 'Telegram API failed'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # ── SYSTEM STATUS ──
    @app.route('/api/system/status')
    def system_status():
        return jsonify({
            'camera_running'    : camera.is_running if camera else False,
            'motion_detection'  : motion_detector.motion_detected if motion_detector else False,
            'known_faces_count' : len(face_recognizer.known_names) if face_recognizer else 0,
            'recording'         : video_recorder.is_recording(),
            'people_counter_on' : people_counter is not None,
            'uptime'            : datetime.now().isoformat()
        })

    @app.route('/captures/<path:filename>')
    def serve_capture(filename):
        return send_from_directory(str(config.CAPTURES_DIR), filename)

    # ── WEBSOCKET ──
    @socketio.on('connect')
    def handle_connect():
        emit('connected', {'status': 'Connected to security system'})

    @socketio.on('request_status')
    def handle_status_request():
        emit('status_update', database.get_alert_stats())

    return app, socketio