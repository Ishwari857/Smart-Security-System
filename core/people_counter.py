"""
core/people_counter.py — Face-based Entry/Exit Tracker
Same person tab tak inside rahega jab tak face na dikhe
"""

import threading
from datetime import datetime
from collections import defaultdict


class PeopleCounter:
    def __init__(self, line_position=0.5, direction='horizontal',
                 min_track_frames=3, max_disappeared=60,
                 exit_timeout=30):

        self._lock        = threading.Lock()
        self.exit_timeout = exit_timeout  # seconds

        # {name: {entry_time, exit_time, gender, age, last_seen, date}}
        self._active   = {}
        self.log_entries  = []
        self._session_log = {}

        self.entry_count = 0
        self.exit_count  = 0

        self.on_entry = None
        self.on_exit  = None

        # Background thread for auto-exit
        self._running = True
        t = threading.Thread(target=self._auto_exit_checker, daemon=True)
        t.start()

    def _auto_exit_checker(self):
        """Har 5 second mein check karo koi face timeout hua kya"""
        import time
        while self._running:
            time.sleep(5)
            now = datetime.now()
            with self._lock:
                for name in list(self._active.keys()):
                    last = self._active[name].get('last_seen')
                    if last and (now - last).total_seconds() > self.exit_timeout:
                        self._do_exit_locked(name)

    def update(self, frame, face_results):
        if not face_results:
            return frame

        now = datetime.now()

        with self._lock:
            seen_names = set()

            for r in face_results:
                name   = r.get('name', 'Unknown')
                gender = r.get('gender', '') or ''
                age    = r.get('age', '')    or ''

                # deepface analysis se gender/age
                analysis = r.get('deepface_analysis') or {}
                if not gender and analysis.get('gender'):
                    gender = analysis['gender']
                if not age and analysis.get('age'):
                    age = str(analysis['age'])

                # Normalize gender
                if gender in ('Man', 'man', 'male', 'Male'):
                    gender = 'Male'
                elif gender in ('Woman', 'woman', 'female', 'Female'):
                    gender = 'Female'

                seen_names.add(name)

                if name not in self._active:
                    # New entry
                    self._active[name] = {
                        'entry_time': now.strftime('%H:%M:%S'),
                        'date'      : now.strftime('%d %b %Y'),
                        'exit_time' : None,
                        'gender'    : gender,
                        'age'       : age,
                        'last_seen' : now,
                        'name'      : name
                    }
                    self.entry_count += 1
                    key = f"{name}_{now.strftime('%H%M%S')}"
                    self._active[name]['_key'] = key
                    self._session_log[key] = self._active[name]
                    self.log_entries.append(self._active[name])
                    if len(self.log_entries) > 100:
                        self.log_entries = self.log_entries[-100:]

                    if self.on_entry:
                        threading.Thread(
                            target=self.on_entry, args=(name,), daemon=True
                        ).start()
                else:
                    # Already inside — update last_seen
                    self._active[name]['last_seen'] = now
                    if gender and not self._active[name].get('gender'):
                        self._active[name]['gender'] = gender
                    if age and not self._active[name].get('age'):
                        self._active[name]['age'] = age

        return frame

    def _do_exit_locked(self, name):
        """Call this only when _lock is already held"""
        if name not in self._active:
            return
        now_str = datetime.now().strftime('%H:%M:%S')
        self.exit_count += 1
        entry = self._active[name]
        entry['exit_time'] = now_str
        del self._active[name]

        if self.on_exit:
            threading.Thread(
                target=self.on_exit, args=(name,), daemon=True
            ).start()

    def get_stats(self):
        with self._lock:
            active_people = [
                {
                    'name'      : v['name'],
                    'entry_time': v['entry_time'],
                    'gender'    : v.get('gender', ''),
                    'age'       : v.get('age', '')
                }
                for v in self._active.values()
            ]

            gender_breakdown = {'Male': 0, 'Female': 0}
            for entry in self.log_entries:
                g = entry.get('gender', '')
                if g == 'Male':
                    gender_breakdown['Male'] += 1
                elif g == 'Female':
                    gender_breakdown['Female'] += 1

            log_table = list(reversed(self.log_entries[-50:]))

            return {
                'total_entries'   : self.entry_count,
                'total_exits'     : self.exit_count,
                'current'         : len(active_people),
                'active_people'   : active_people,
                'gender_breakdown': gender_breakdown,
                'log'             : log_table
            }

    def reset(self):
        with self._lock:
            self.entry_count  = 0
            self.exit_count   = 0
            self._active      = {}
            self.log_entries  = []
            self._session_log = {}

    def stop(self):
        self._running = False