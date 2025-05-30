# app.py
from flask import Flask, render_template, request, jsonify, send_from_directory
from pathlib import Path
import threading
import os
import sys
import logging
import uuid 
import zipfile 
import shutil # For optional cleanup

try:
    from kuku_downloader import KuKu 
except ImportError as e:
    print(f"CRITICAL ERROR: Error importing KuKu class: {e}")
    print("Ensure kuku_downloader.py is in the same directory as app.py or correctly in PYTHONPATH.")
    sys.exit(1)

app = Flask(__name__)
app.secret_key = os.urandom(24) 

# --- Configuration ---
APP_ROOT = Path(__file__).resolve().parent
# Base directory where KuKu class will download show content (organized by lang/type/show title)
DOWNLOAD_BASE_DIR = APP_ROOT / "Downloaded_Shows_Content" 
# Directory where final ZIP files for user download will be stored
ZIP_STORAGE_DIR = APP_ROOT / "_zips_for_user_download"    
DEFAULT_COOKIES_FILE = APP_ROOT / "cookies.json" # Default location for cookies.json

DOWNLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)
ZIP_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)]) # Ensure logs go to stdout

# Store download task statuses and results
# task_id: {"status": "processing/complete/error", "message": "...", "zip_filename": "...", "show_title": "...", "url": "..."}
download_tasks_status = {} 

@app.route('/')
def index():
    """Renders the main page."""
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def start_download_route():
    """Handles the download request from the web form and starts a background task."""
    data = request.get_json()
    if not data: 
        logging.warning("Invalid request: No JSON data received.")
        return jsonify({"status": "error", "message": "Invalid request: No JSON data."}), 400
        
    kuku_url = data.get('kuku_url')
    user_subfolder_name_raw = data.get('download_path', '').strip() # Optional subfolder within DOWNLOAD_BASE_DIR

    if not kuku_url:
        logging.warning("Download request failed: KuKu FM URL is required.")
        return jsonify({"status": "error", "message": "KuKu FM URL is required."}), 400

    task_id = str(uuid.uuid4()) # Generate a unique task ID

    # Basic check for already processing URL (can be improved for robustness)
    for existing_task_id, t_info in download_tasks_status.items():
        if t_info.get("url") == kuku_url and t_info.get("status") == "processing":
            logging.warning(f"Download for {kuku_url} is already processing under task ID {existing_task_id}.")
            return jsonify({"status": "warning", 
                            "message": f"Download for {kuku_url} is already in progress (Task ID: {existing_task_id}). Please wait for it to complete."}), 409

    # Sanitize user-provided subfolder name to prevent path traversal
    safe_subfolder_name = "".join(c for c in user_subfolder_name_raw if c.isalnum() or c in (' ', '_', '-')).strip()
    
    # The KuKu class will create its own lang/type/show_title structure within this path
    # This is the base directory passed to the KuKu class instance for *this specific download run*.
    download_path_for_kuku_instance = DOWNLOAD_BASE_DIR / safe_subfolder_name if safe_subfolder_name else DOWNLOAD_BASE_DIR
    
    download_path_for_kuku_instance.mkdir(parents=True, exist_ok=True) # Ensure this base for KuKu class exists
    
    cookies_file_for_kuku = str(DEFAULT_COOKIES_FILE) if DEFAULT_COOKIES_FILE.exists() else None
    convert_format_option = data.get('convert_format') 
    export_metadata_option = data.get('export_metadata', False) 

    logging.info(f"Download request for URL: {kuku_url} -> Assigned Task ID: {task_id}")
    logging.info(f"  Base download path for KuKu class instance: {download_path_for_kuku_instance.resolve()}")
    logging.info(f"  Cookies file for KuKu class: {cookies_file_for_kuku}")
    logging.info(f"  Convert format: {convert_format_option}, Export metadata: {export_metadata_option}")
        
    def download_task_wrapper(app_context, current_task_id, url, cookies_path, convert_fmt, export_meta, dl_path_for_kuku):
        threading.current_thread().name = f"Downloader-{current_task_id[:8]}"
        # Initial status
        download_tasks_status[current_task_id] = {
            "status": "processing", 
            "message": "Initializing download...", 
            "show_title": "Fetching info...", # Placeholder until KuKu class fetches it
            "url": url # Store URL for reference
        }
        
        downloader_instance_obj = None 
        try:
            with app_context: # Ensures Flask context is available in thread if needed by extensions
                logging.info(f"Thread: Initializing KuKu for {url} (Task: {current_task_id})")
                downloader_instance_obj = KuKu(
                    url=url, 
                    cookies_file_path=cookies_path, 
                    convert_format=convert_fmt,
                    export_metadata_flag=export_meta, 
                    download_base_dir=dl_path_for_kuku # Pass the specific base for this show's content
                )
                
                # Update show title in status now that metadata is fetched
                current_show_title_from_meta = downloader_instance_obj.metadata.get('title', 'Unknown Show')
                download_tasks_status[current_task_id]["show_title"] = current_show_title_from_meta
                download_tasks_status[current_task_id]["message"] = f"Processing '{current_show_title_from_meta}'..."

                logging.info(f"Thread: Starting downAlbum for {url} (Task: {current_task_id})")
                downloader_instance_obj.downAlbum() # This method sets downloader_instance_obj.album_path
                
                # album_output_path_on_server is where KuKu class saved the show's content (e.g., .../Hindi/Audio Book/Show Title (Year) [Lang])
                album_output_path_on_server = downloader_instance_obj.album_path 
                if not album_output_path_on_server or not album_output_path_on_server.is_dir(): # Check if it's a directory
                    logging.error(f"Thread: Album content path '{album_output_path_on_server}' not found or not a directory after download (Task: {current_task_id}).")
                    raise Exception("Album content path not found or is not a directory after download.")

                # Create a ZIP file of the downloaded content
                show_title_cleaned_for_zip = KuKu.clean(current_show_title_from_meta)
                # Sanitize showID from URL just in case, though it should be safe from urlparse
                show_id_cleaned_for_zip = KuKu.clean(downloader_instance_obj.showID) 
                
                zip_filename_base = f"{show_title_cleaned_for_zip}_{show_id_cleaned_for_zip}.zip"
                zip_output_path_on_server = ZIP_STORAGE_DIR / zip_filename_base
                
                logging.info(f"Thread: Creating ZIP file: {zip_output_path_on_server} from content at: {album_output_path_on_server} (Task: {current_task_id})")
                with zipfile.ZipFile(zip_output_path_on_server, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                    for item_path in album_output_path_on_server.rglob('*'): 
                        if item_path.is_file():
                            # Arcname is the path inside the ZIP file
                            arcname = item_path.relative_to(album_output_path_on_server)
                            zf.write(item_path, arcname)
                
                download_tasks_status[current_task_id].update({
                    "status": "complete", 
                    "message": "Download and zipping complete! Your file is ready.", 
                    "zip_filename": zip_filename_base, # Just the filename for client
                })
                logging.info(f"Thread: ZIP created successfully: {zip_filename_base} (Task: {current_task_id})")

        except Exception as e:
            logging.error(f"❌ Thread: Error in download task for {url} (Task ID: {current_task_id}): {e}", exc_info=True)
            show_title_for_error_status = downloader_instance_obj.metadata.get('title', 'Failed Show') if downloader_instance_obj else 'Failed Show (init error)'
            download_tasks_status[current_task_id].update({"status": "error", "message": f"Error: {str(e)}", "show_title": show_title_for_error_status})
        finally:
            # Optional: Clean up the original downloaded show folder after zipping
            # Enable with caution, ensure ZIP is valid and accessible first.
            # if downloader_instance_obj and downloader_instance_obj.album_path and downloader_instance_obj.album_path.exists() and \
            #    download_tasks_status.get(current_task_id, {}).get("status") == "complete":
            #     try:
            #         shutil.rmtree(downloader_instance_obj.album_path)
            #         logging.info(f"Thread: Cleaned up source folder {downloader_instance_obj.album_path} (Task: {current_task_id})")
            #     except Exception as e_clean:
            #         logging.error(f"Thread: Error cleaning source folder {downloader_instance_obj.album_path}: {e_clean} (Task: {current_task_id})")
            
            final_status = download_tasks_status.get(current_task_id, {}).get('status', 'unknown_end_state')
            logging.info(f"Thread: Download task for {url} (Task ID: {current_task_id}) ended with status: {final_status}")

    try:
        # Start the download process in a new thread
        thread = threading.Thread(target=download_task_wrapper, 
                                  name=f"TaskMgr-{task_id[:8]}", # Give thread a name for logging
                                  args=(app.app_context(), task_id, kuku_url, cookies_file_for_kuku, 
                                        convert_format_option, export_metadata_option, download_path_for_kuku_instance))
        thread.start()
        
        # Initial status update for the client to start polling
        download_tasks_status[task_id] = {"status": "processing_queued", "message": "Download process initiated. Polling for status...", "task_id": task_id, "url": kuku_url, "show_title": "Fetching info..."}
        
        return jsonify({
            "status": "processing_queued", 
            "message": f"Download process initiated for {kuku_url}. Please wait for completion.",
            "task_id": task_id
        })

    except Exception as e:
        logging.error(f"❌ Error initializing download thread for {kuku_url}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Failed to start download thread: {str(e)}"}), 500


@app.route('/status/<task_id>', methods=['GET'])
def get_download_status(task_id):
    """Client polls this endpoint to check download status."""
    status_info = download_tasks_status.get(task_id)
    if not status_info:
        return jsonify({"status": "not_found", "message": "Task ID not found or task has expired/been cleaned up."}), 404
    return jsonify(status_info)


@app.route('/fetch_zip/<zip_filename_from_route>', methods=['GET'])
def fetch_zip_file(zip_filename_from_route):
    """Serves the generated ZIP file to the user for download."""
    # Basic sanitization: ensure filename doesn't contain path traversal characters like '..' or '/'
    # Path().name extracts the final component, which is safer.
    safe_filename = Path(zip_filename_from_route).name 
    if safe_filename != zip_filename_from_route: 
        logging.warning(f"Potentially unsafe zip filename requested: '{zip_filename_from_route}', sanitized to '{safe_filename}'")
        return jsonify({"status": "error", "message": "Invalid filename character(s)."}), 400

    logging.info(f"Request to serve ZIP: '{safe_filename}' from directory: {ZIP_STORAGE_DIR}")
    try:
        # send_from_directory is generally safe against directory traversal outside its root directory.
        return send_from_directory(
            ZIP_STORAGE_DIR, 
            safe_filename, 
            as_attachment=True, # This prompts the user to download the file
            mimetype='application/zip' # Explicitly set mimetype for ZIP
        )
    except FileNotFoundError:
        logging.error(f"ZIP file not found for serving: '{safe_filename}' in {ZIP_STORAGE_DIR}")
        return jsonify({"status": "error", "message": "ZIP file not found. It might have been deleted, the download may have failed, or the task ID was incorrect."}), 404
    except Exception as e:
        logging.error(f"Error serving ZIP file '{safe_filename}': {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Could not serve the ZIP file due to a server error."}), 500


# To serve static files (CSS, JS, images)
@app.route('/static/<path:filename>')
def serve_static_files(filename):
    return send_from_directory(str(APP_ROOT / 'static'), filename)

if __name__ == '__main__':
    print(f"KuKu FM Web Downloader - Flask App")
    print(f"Flask app running on http://127.0.0.1:5000 or http://localhost:5000")
    print(f"Base directory for KUKU class downloads (content source for zipping): {DOWNLOAD_BASE_DIR.resolve()}")
    print(f"Storage directory for user-downloadable ZIPs: {ZIP_STORAGE_DIR.resolve()}")
    if DEFAULT_COOKIES_FILE.exists():
        print(f"Default cookies file found at: {DEFAULT_COOKIES_FILE.resolve()}")
    else:
        print(f"Default cookies.json not found. Relying on browser_cookie3 or no cookies (if applicable).")
    
    # threaded=True is okay for development with Flask's built-in server to handle multiple requests.
    # For production, use a proper WSGI server like Gunicorn or uWSGI.
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
