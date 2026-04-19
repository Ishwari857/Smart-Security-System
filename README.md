# 🛡️ Smart Security System

A real-time intelligent surveillance system built using **Flask, OpenCV, and Face Recognition**.
This system provides live monitoring, motion detection, face recognition, alert management, and people counting with a modern web dashboard.

---

## 🚀 Features

* 🎥 **Live Camera Streaming**
* 🧠 **Face Recognition (Authorized / Unknown Detection)**
* 🚨 **Motion Detection & Auto Recording**
* 📩 **Real-time Alerts (Web + Telegram)**
* 👥 **People Counter (Entry / Exit Tracking)**
* 💾 **Video Recording & Snapshots**
* 📊 **Dashboard with Analytics**
* 🔐 **Login Authentication System**
* ⚙️ **Settings & Face Management Panel**

---

## 🏗️ Project Structure

```
smart-security-system/
│
├── core/                      # 🔧 Main backend logic
│   ├── __init__.py
│   ├── alert_system.py
│   ├── camera.py
│   ├── database.py
│   ├── face_recognizer.py
│   ├── motion_detector.py
│   └── people_counter.py
│
├── data/                      # 📂 Stored data
│   ├── captures/              # Captured images
│   ├── known_faces/           # Known persons dataset
│   └── database.db            # SQLite database
│
├── logs/                      # 📜 Logs
│   └── security.log
│
├── models/                    # 🤖 ML Models
│   ├── deploy.prototxt
│   └── res10_300x300_ssd_iter_140000.caffemodel
│
├── web/                       # 🌐 Frontend + Web app
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── alert.mp3
│   │
│   ├── templates/
│   │   ├── index.html
│   │   ├── login.html
│   │   ├── live.html
│   │   ├── alerts.html
│   │   ├── people.html
│   │   └── settings.html
│   │
│   ├── recorder.py
│   ├── app.py
│   └── __init__.py
│
├── config/                    # ⚙️ Configuration files
│   └── config.py
│
├── .env                       # 🔐 Environment variables
├── .gitignore
├── main.py                    # 🚀 Entry point
├── requirements.txt           # 📦 Dependencies
│
├── venv/                      # 🐍 Virtual environment
└── smart_security_system_venv/
```

---

## 📦 Requirements

Install dependencies using:

```
pip install -r requirements.txt
```

### Dependencies Used:

* OpenCV
* Face Recognition
* Flask
* Flask-SocketIO
* NumPy
* Pillow
* python-dotenv
* eventlet / gevent
* requests

---

## ⚙️ Setup & Installation

### 1️⃣ Clone Repository

```
git clone https://github.com/your-username/smart-security-system.git
cd smart-security-system
```

### 2️⃣ Create Virtual Environment

```
python -m venv venv
venv\Scripts\activate   # Windows
```

### 3️⃣ Install Requirements

```
pip install -r requirements.txt
```

### 4️⃣ Set Environment Variables (.env)

```
ADMIN_USER=admin
ADMIN_PASS=Admin@1234
SECRET_KEY=your_secret_key
```

---

## ▶️ Run the Project

```
python main.py
```

Then open in browser:

```
http://127.0.0.1:5000
```

---

## 🔑 Default Login

```
Username: admin
Password: Admin@1234
```

---

## 📡 API Endpoints

### 🎥 Video & Recording

* `/api/video_feed` → Live stream
* `/api/snapshot` → Capture image
* `/api/recording/start` → Start recording
* `/api/recording/stop` → Stop recording

### 🚨 Alerts

* `/api/alerts` → Get alerts
* `/api/alerts/<id>/acknowledge`
* `/api/alerts/delete_all`

### 👥 People Counter

* `/api/people_stats`
* `/api/people_counter/reset`

### 👤 Face Management

* `/api/faces` → Add / Get faces
* `/api/faces/<id>` → Delete face

### ⚙️ System

* `/api/system/status`
* `/api/change_password`

---

## 🧠 How It Works

1. Camera captures live frames
2. Motion detection triggers activity
3. Face recognition identifies known/unknown persons
4. Alerts are generated and stored in database
5. Recording starts automatically on motion
6. Dashboard shows live updates via WebSockets

---

## 📸 Screens

* Dashboard (Analytics)
* Live Camera Feed
* Alerts Page
* People Counter
* Settings Panel

---

## 🔔 Telegram Integration

You can send alerts to Telegram using:

```
/api/send_telegram
```

Required:

* Bot Token
* Chat ID

---

## 🛠️ Future Improvements

* 🔍 Advanced AI detection (weapons, fire)
* ☁️ Cloud storage integration
* 📱 Mobile app support
* 🧾 Report generation

---

## 👩‍💻 Author

**Ishwari Thombare**

---

## 📜 License

This project is for educational and personal use.
