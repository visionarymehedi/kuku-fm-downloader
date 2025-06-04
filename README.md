# KuKu FM Downloader Pro 🎧

A user-friendly Flask web application designed to download your favorite shows from KuKu FM. This tool allows users to securely use their own KuKu FM cookies to access and download show content, which is then conveniently zipped for easy retrieval. Features live progress updates and a clean, responsive interface with dark/light theme support.

## ✨ Features

* **Web-Based Interface:** Easy-to-use UI accessible via a web browser.
* **User-Specific Cookie Login:** Securely use your own KuKu FM cookies via the "My Cookies" section to download content associated with your account. Cookies are stored in your browser's Flask session and not permanently on the server.
* **Show Downloading:** Downloads complete shows including:
    * Audio episodes (typically M4A)
    * Cover art
    * Subtitles (SRT files, if available)
* **ZIP Archiving:** Automatically zips the entire downloaded show content for a single, convenient download.
* **Live Status Updates:**
    * Real-time progress bar for the overall download process.
    * Episode-by-episode status logging directly in the UI.
* **Dynamic UI:**
    * Responsive design for desktop, tablet, and mobile.
    * Collapsible sidebar for desktop, slide-in overlay for mobile.
    * Dark/Light theme toggle with preference saved in `localStorage`.
* **Server-Side File Management:**
    * Automatic cleanup of generated ZIP files and raw downloaded content from the server after a configurable period (default: ZIPs after 1 hour, raw content after 2 hours).
* **SEO Friendly:** Includes `robots.txt` and dynamic `sitemap.xml` for better discoverability (if deployed publicly).

## 🚀 Prerequisites

Before you begin, ensure you have the following installed:

* **Python 3.8+**
* **pip** (Python package installer)
* **FFMPEG:** This is crucial for processing audio streams. Download FFMPEG from [ffmpeg.org](https://ffmpeg.org/download.html) and ensure it's installed and added to your system's PATH environment variable. You can verify by typing `ffmpeg -version` in your terminal.
* A modern web browser (e.g., Chrome, Firefox, Edge).

## 🛠️ Setup & Installation

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/visionarymehedi/kuku-fm-web-downloader.git](https://github.com/visionarymehedi/kuku-fm-web-downloader.git)
    cd kuku-fm-web-downloader
    ```

2.  **Create and Activate a Virtual Environment (Recommended):**
    ```bash
    # For Windows
    python -m venv venv
    venv\Scripts\activate

    # For macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    Create a `requirements.txt` file in the project root with the following content:
    ```txt
    Flask
    requests
    mutagen
    tqdm
    pathlib
    APScheduler
    Flask-APScheduler
    # Add browser-cookie3 if you plan to use its fallback for server-side default cookies
    # browser-cookie3 
    ```
    Then install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Cookie Setup (Important for Users):**
    This application requires KuKu FM cookies to access and download content, especially premium shows.
    * **Primary Method (User-Provided Cookies):**
        1.  Navigate to the "My Cookies" section in the web application.
        2.  Open KuKu FM in your browser and log in.
        3.  Use a browser extension like "EditThisCookie" or "Cookie-Editor".
        4.  Export your cookies for the `kukufm.com` domain as a **JSON array**.
        5.  Paste the entire JSON array string into the textarea in the "My Cookies" section and click "Save Cookies for Session".
        *Your cookies are stored in the server-side Flask session and are tied to your browser session. They are not saved permanently on the server's disk after your session ends.*
    * **Server-Side Fallback (Optional, for Admin/Dev):**
        If no user cookies are provided in the session, the `kuku_downloader.py` script can attempt to load cookies from a `cookies.json` file placed in the root directory of the application (where `app.py` is). This is primarily for development or if the server itself has a default account to use.
        **Important:** If you create a `cookies.json` file for this fallback, **DO NOT commit it to Git** if it contains sensitive session information. Ensure it's listed in your `.gitignore` file.

5.  **Bearer Token (Optional):**
    If KuKu FM uses a Bearer token in addition to cookies for some API calls, you might need to update the placeholder in `kuku_downloader.py`:
    ```python
    # In kuku_downloader.py, inside KuKu class __init__
    self.session.headers.update({
        # ... other headers ...
        "Authorization": "Bearer YOUR_BEARER_TOKEN_IF_ANY" # <-- REPLACE THIS
    })
    ```
    Often, the `jwtToken` cookie is sufficient.

6.  **Google Site Verification (Optional):**
    If you intend to verify your site with Google Search Console using an HTML file:
    1.  Download your verification HTML file from Google (e.g., `google1234567890abcdef.html`).
    2.  Place this file in the **root directory** of the project (alongside `app.py`).
    3.  In `app.py`, find the `@app.route('/google<your_code>.html')` decorator and the `google_file_name` variable inside the `google_verification()` function. **Update both** to match your exact Google verification filename.

## ▶️ Running the Application

1.  Ensure your virtual environment is activated.
2.  Navigate to the project's root directory in your terminal.
3.  Run the Flask application:
    ```bash
    python app.py
    ```
4.  Open your web browser and go to: `http://127.0.0.1:5000` (or `http://localhost:5000`).

## 📖 How to Use

1.  **Set Your Cookies:**
    * Navigate to the "My Cookies" section using the sidebar.
    * Paste your exported KuKu FM cookie JSON data into the textarea.
    * Click "Save Cookies for Session". You should see a success message.
2.  **Download a Show:**
    * Navigate to the "Downloader" section. The download form should now be active.
    * Paste the full URL of the KuKu FM show you want to download (e.g., `https://kukufm.com/show/your-show-title`).
    * Click "Initiate Download".
3.  **Monitor Progress:**
    * The "Live Download Log" area will appear below the form.
    * You'll see status updates, including episode-by-episode progress.
    * A progress bar will show the overall status.
4.  **Download Your File:**
    * Once the server has finished downloading all episodes and zipping them, a download link for the `.zip` file will appear at the top of the status log.
    * **Important:** A warning will also appear indicating that the download link will expire (default is 1 hour, but configurable in `app.py`). Download your file promptly.

## 📁 Project Structure



kuku-fm-web-downloader/
├── app.py                   # Main Flask web application, routes, and logic
├── kuku_downloader.py       # Core class for KuKu FM interaction and downloading
├── cookies.json             # Optional: Server-side default cookies (ignored by Git by default)
├── requirements.txt         # Python dependencies
├── .gitignore               # Specifies intentionally untracked files by Git
├── README.md                # This file
├── templates/
│   └── index.html           # Main HTML page for the UI
└── static/
├── css/
│   └── style.css        # Stylesheet for the application
└── js/
└── script.js        # Client-side JavaScript for interactivity

(The application will also create `Downloaded_Shows_Content/` and `_zips_for_user_download/` directories at runtime, which are ignored by Git).

## ⚠️ Important Notes

* **Cookies & Authentication:** This tool relies on valid KuKu FM cookies for accessing content. Ensure your cookies are fresh and correctly formatted. Downloads will likely fail for premium content if cookies are invalid or missing.
* **File Expiry & Server Storage:**
    * Generated ZIP files are stored temporarily on the server. The default cleanup schedule removes ZIPs older than **1 hour** and raw downloaded content older than **2 hours**.
    * These timings and the cleanup job frequency are configurable in `app.py` (look for `max_age_seconds_zip`, `max_age_seconds_content`, and `cleanup_job_interval_minutes` within the `cleanup_old_files_job` and scheduler setup).
    * This is especially important if deploying on platforms with limited or ephemeral disk space.
* **FFMPEG Requirement:** FFMPEG must be installed on the system running this application and be accessible via the system's PATH.
* **Disclaimer:** This tool is intended for personal, private use only, such as creating backups of content you have legitimate access to. Please respect KuKu FM's Terms of Service and all applicable copyright laws. The developers of this tool are not responsible for its misuse.

## ☁️ Deployment (e.g., on Render.com)

* When deploying to a platform like Render, ensure you set up a **Persistent Disk** and configure the application (via the `RENDER_DISK_MOUNT_PATH` environment variable, which `app.py` checks for) to use this disk for `Downloaded_Shows_Content/` and `_zips_for_user_download/`. This prevents downloaded files from being lost on service restarts or re-deploys.
* Set a strong `FLASK_SECRET_KEY` as an environment variable for session security.
* Use a production-grade WSGI server (e.g., Gunicorn) instead of Flask's built-in development server.

## 💡 Potential Future Enhancements

* More robust error handling and user feedback.
* Option for users to specify download quality (if available via API).
* Queueing system for handling multiple concurrent download requests.
* Admin panel for server monitoring.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Please feel free to fork the repository, make changes, and submit a pull request.

## 📄 License

Consider adding a license file (e.g., MIT License) to define how others can use your code.
