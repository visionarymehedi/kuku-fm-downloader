# KuKu FM Web Downloader

A Flask web application to download shows from KuKu FM, zip them, and make them available for download.

## Features

* Web interface to input KuKu FM show URLs.
* Downloads show content (audio, subtitles, cover) to the server.
* Zips the downloaded show content.
* Provides a download link for the generated ZIP file.
* Optional metadata export.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git](https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git)
    cd YOUR_REPOSITORY_NAME
    ```
2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install Flask requests mutagen tqdm pathlib browser-cookie3 # Add any other specific dependencies
    ```
    (You should create a `requirements.txt` file for this - see below)
4.  **Cookies:**
    * This application can attempt to load cookies using `browser_cookie3` if you are logged into KuKu FM in a supported browser.
    * Alternatively, you can export your cookies from your browser (e.g., using an extension like "EditThisCookie") into a file named `cookies.json` in the project's root directory.
    * **Important:** Ensure your `cookies.json` is listed in your `.gitignore` file if it contains sensitive session information and you don't want to commit it.
5.  **FFMPEG:**
    * Ensure FFMPEG is installed and accessible in your system's PATH. It's required for processing audio streams.

## Running the Application

1.  Navigate to the project directory.
2.  Run the Flask application:
    ```bash
    python app.py
    ```
3.  Open your web browser and go to `http://127.0.0.1:5000`.

## Project Structure