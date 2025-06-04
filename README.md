# KuKu FM Downloader Pro 🎧

A user-friendly Flask web application to download your favorite shows from KuKu FM. Users securely provide their own KuKu FM cookies to access and download show content, which is conveniently zipped for easy retrieval. Features live progress updates and a clean, responsive interface with dark/light theme support.

---

## 🌟 Demo & Screenshots

**(Tip: Add an animated GIF here showing the app in action)**

### Application Screenshots

1. **Main Interface / Downloader Section**  
![Main Downloader UI](https://github.com/visionarymehedi/kuku-fm-downloader/raw/main/static/images/Screenshot_27.png)

2. **Cookie Management Section**  
![Cookie Management UI](https://github.com/visionarymehedi/kuku-fm-downloader/raw/main/static/images/Screenshot_28.png)

3. **Live Download Log in Action**  
![Live Download Log](https://github.com/visionarymehedi/kuku-fm-downloader/raw/main/static/images/Screenshot_29.png)

4. **Completed Download with Links**  
![Download Complete with Links](https://github.com/visionarymehedi/kuku-fm-downloader/raw/main/static/images/Screenshot_30.png)

5. **Responsive Design / Mobile View**  
![Mobile View Example](https://github.com/visionarymehedi/kuku-fm-downloader/raw/main/static/images/Screenshot_31.png)

---

## ✨ Features

- Web-based, responsive UI (desktop & mobile)
- User-specific cookie login (secure session storage)
- Download complete shows:
  - Audio episodes
  - Cover art
  - Subtitles (if available)
- Automatic ZIP packaging
- Live progress updates with status log
- Automatic file cleanup (configurable)
- Dark/light theme toggle

---

## 🚀 Prerequisites

- Python 3.8+
- pip
- FFMPEG (must be in system PATH)
- Modern web browser

---

## 🛠️ Setup & Installation

```bash
# Clone the repo
git clone https://github.com/visionarymehedi/kuku-fm-downloader.git
cd kuku-fm-downloader

# Create virtual environment
python -m venv venv
# For Windows:
venv\Scripts\activate
# For macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run The script in your local machine
python app.py
