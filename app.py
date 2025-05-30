# app.py
from flask import Flask, render_template, request, jsonify, send_from_directory
from pathlib import Path
import threading
import os
import sys
import logging
import uuid 
import zipfile 
import shutil 
import time # For checking file ages
from flask_apscheduler import APScheduler 

try:
    from kuku_downloader import KuKu 
except ImportError as e:
    print(f"CRITICAL ERROR: Error importing KuKu class: {e}")
    print("Ensure kuku_downloader.py is in the same directory as app.py or correctly in PYTHONPATH.")
    sys.exit(1)

# --- Flask App Configuration ---
class Config:
    SCHEDULER_API_ENABLED = True
    # SCHEDULER_TIMEZONE = "Asia/Dhaka" 

app = Flask(__name__)
app.config.from_object(Config())
app.secret_key = os.urandom(24) 

# --- Path Configurations ---
APP_ROOT = Path(__file__).resolve().parent
DOWNLOAD_BASE_DIR = APP_ROOT / "Downloaded_Shows_Content" 
ZIP_STORAGE_DIR = APP_ROOT / "_zips_for_user_download"    
DEFAULT_COOKIES_FILE = APP_ROOT / "cookies.json"

DOWNLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)
ZIP_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)]) 

# --- Download Task Status ---
download_tasks_status = {} 

# --- APScheduler Setup ---
scheduler = APScheduler()

def cleanup_old_files_job():
    """Scheduled job to delete old files and folders."""
    with app.app_context(): 
        logging.info("SCHEDULER: Running cleanup job for old files...")
        now = time.time()
        
        max_age_seconds_zip = 5 * 60      # 1 minute for ZIPs
        max_age_seconds_content = 5 * 60  # 1 minute for raw content folders

        # Cleanup ZIPs
        deleted_zips_count = 0
        for item in ZIP_STORAGE_DIR.iterdir():
            try:
                if item.is_file() and item.suffix.lower() == '.zip':
                    file_mod_time = item.stat().st_mtime
                    if (now - file_mod_time) > max_age_seconds_zip:
                        item.unlink() 
                        logging.info(f"SCHEDULER: Deleted old ZIP: {item.name} (older than 1 minute)")
                        deleted_zips_count += 1
            except Exception as e:
                logging.error(f"SCHEDULER: Error deleting ZIP {item.name}: {e}")
        if deleted_zips_count > 0:
            logging.info(f"SCHEDULER: Deleted {deleted_zips_count} old ZIP file(s).")

        # Cleanup Raw Content Folders (Iterate deeper to target individual show folders)
        deleted_content_folders_count = 0
        for lang_dir in DOWNLOAD_BASE_DIR.iterdir():
            if lang_dir.is_dir():
                for type_dir in lang_dir.iterdir():
                    if type_dir.is_dir():
                        for show_dir in type_dir.iterdir(): # This is the actual show content folder
                            if show_dir.is_dir():
                                try:
                                    dir_mod_time = show_dir.stat().st_mtime 
                                    if (now - dir_mod_time) > max_age_seconds_content:
                                        shutil.rmtree(show_dir) 
                                        logging.info(f"SCHEDULER: Deleted old show content folder: {show_dir.name} (older than 1 minute)")
                                        deleted_content_folders_count +=1
                                except Exception as e_show:
                                    logging.error(f"SCHEDULER: Error deleting show content folder {show_dir.name}: {e_show}")
        
        if deleted_content_folders_count > 0:
            logging.info(f"SCHEDULER: Deleted {deleted_content_folders_count} old show content folder(s).")
        
        cleaned_tasks = 0
        tasks_to_delete = []
        # Clean up task statuses slightly after their corresponding ZIPs would have expired
        max_task_status_age_seconds = max_age_seconds_zip + (1 * 60) # e.g., 1 min after ZIP expiry

        for task_id, task_info in list(download_tasks_status.items()):
            task_timestamp = task_info.get("timestamp", 0) 
            if task_info.get("status") != "processing" and (now - task_timestamp) > max_task_status_age_seconds:
                tasks_to_delete.append(task_id)

        for task_id in tasks_to_delete:
            if task_id in download_tasks_status:
                del download_tasks_status[task_id]
                cleaned_tasks +=1
        if cleaned_tasks > 0:
            logging.info(f"SCHEDULER: Cleaned up {cleaned_tasks} old task status entries.")

        logging.info("SCHEDULER: Cleanup job finished.")

if not scheduler.running:
    scheduler.init_app(app)
    scheduler.start()
    logging.info("APScheduler initialized and started.")
    
    cleanup_job_interval_seconds = 20 # Run cleanup every 20 seconds for testing
    if not scheduler.get_job('cleanup_files_job_id'):
        scheduler.add_job(id='cleanup_files_job_id', func=cleanup_old_files_job, 
                          trigger='interval', seconds=cleanup_job_interval_seconds) 
        logging.info(f"SCHEDULER: Cleanup job scheduled to run every {cleanup_job_interval_seconds} seconds.")
    else:
        logging.info("SCHEDULER: Cleanup job already scheduled.")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def start_download_route():
    data = request.get_json();
    if not data: return jsonify({"status": "error", "message": "Invalid request."}), 400
    kuku_url = data.get('kuku_url')
    if not kuku_url: return jsonify({"status": "error", "message": "URL is required."}), 400

    task_id = str(uuid.uuid4())
    for t_info in download_tasks_status.values():
        if t_info.get("url")==kuku_url and t_info.get("status")=="processing":
            return jsonify({"status":"warning", "message":f"Download for {kuku_url} is already processing."}), 409

    download_path_for_kuku_instance = DOWNLOAD_BASE_DIR
    cookies_file_for_kuku = str(DEFAULT_COOKIES_FILE) if DEFAULT_COOKIES_FILE.exists() else None
    
    logging.info(f"Download request for URL: {kuku_url} -> Task ID: {task_id}")
        
    def download_task_wrapper(app_ctx, current_task_id, url, cookies_p, dl_path_kuku):
        threading.current_thread().name = f"Downloader-{current_task_id[:8]}"
        start_time = time.time() 
        download_tasks_status[current_task_id] = {
            "status": "processing", "message": "Initializing...", "show_title": "Fetching...", 
            "url": url, "zip_filename": None, "processed_count": 0, "total_episodes": 0,
            "current_episode_title": None, "episode_updates": [], "timestamp": start_time
        }
        
        downloader = None 
        try:
            with app_ctx: 
                logging.info(f"Thread: Initializing KuKu for {url} (Task: {current_task_id})")
                # export_metadata_flag is removed from KuKu constructor
                downloader = KuKu(url=url, cookies_file_path=cookies_p, 
                                  show_content_download_root_dir=dl_path_kuku)
                
                show_title = downloader.metadata.get('title', 'Unknown Show')
                total_eps = downloader.metadata.get('nEpisodes', 0)
                download_tasks_status[current_task_id].update({
                    "show_title": show_title, "total_episodes": total_eps,
                    "message": f"Preparing '{show_title}' ({total_eps} episodes)...",
                    "timestamp": time.time()
                })

                def episode_progress_cb(episode_title: str, success: bool, processed_count: int, total_episodes: int, status_message: str):
                    task_data = download_tasks_status.get(current_task_id)
                    if task_data:
                        task_data.update({
                            "processed_count": processed_count, 
                            "total_episodes": total_episodes,
                            "current_episode_title": episode_title,
                            "message": f"Ep {processed_count}/{total_episodes}: '{episode_title[:25]}...'",
                            "timestamp": time.time()
                        })
                        task_data["episode_updates"].append({
                            "title":episode_title,"status_message":status_message,"success":success,
                            "processed_count":processed_count,"total_episodes":total_episodes
                        })
                        if len(task_data["episode_updates"]) > 30: 
                            task_data["episode_updates"] = task_data["episode_updates"][-30:]
                
                downloader.downAlbum(episode_status_callback=episode_progress_cb) 
                
                album_out_path = downloader.album_path 
                if not album_out_path or not album_out_path.is_dir():
                    raise Exception("Album path missing post-download.")

                zip_fn = f"{KuKu.clean(show_title)}_{downloader.showID}.zip"
                zip_out_path = ZIP_STORAGE_DIR / zip_fn
                download_tasks_status[current_task_id]["message"] = f"Zipping '{show_title}'..."
                download_tasks_status[current_task_id]["timestamp"] = time.time()
                
                with zipfile.ZipFile(zip_out_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                    for item in album_out_path.rglob('*'): 
                        if item.is_file(): zf.write(item, item.relative_to(album_out_path))
                
                download_tasks_status[current_task_id].update({
                    "status": "complete", "message": "Download complete! ZIP ready.", 
                    "zip_filename": zip_fn,
                    "processed_count": total_eps, 
                    "timestamp": time.time()
                })
                logging.info(f"Thread: ZIP created: {zip_fn} (Task: {current_task_id})")

        except Exception as e:
            logging.error(f"❌ Thread Error (Task {current_task_id}): {e}", exc_info=True)
            title_err = downloader.metadata.get('title','Failed') if downloader else 'Failed (init)'
            download_tasks_status[current_task_id].update({"status": "error", "message": str(e), "show_title": title_err, "timestamp": time.time()})
        finally:
            final_stat = download_tasks_status.get(current_task_id,{}).get('status','unknown')
            logging.info(f"Thread: Task {current_task_id} for {url} ended: {final_stat}")

    try:
        thread = threading.Thread(target=download_task_wrapper, name=f"TaskMgr-{task_id[:8]}",
                                  args=(app.app_context(), task_id, kuku_url, cookies_file_for_kuku, 
                                        download_path_for_kuku_instance)) 
        thread.start()
        download_tasks_status[task_id] = {"status": "processing_queued", "message": "Download initiated...", "task_id": task_id, "url": kuku_url, "show_title": "Fetching...", "episode_updates": [], "timestamp": time.time()}
        return jsonify({"status": "processing_queued", "message": f"Download for {kuku_url} initiated.", "task_id": task_id})
    except Exception as e:
        logging.error(f"❌ Error initializing thread for {kuku_url}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Failed to start download: {str(e)}"}), 500

@app.route('/status/<task_id>', methods=['GET'])
def get_download_status(task_id):
    status_info = download_tasks_status.get(task_id)
    if not status_info: return jsonify({"status":"not_found", "message":"Task ID not found."}), 404
    return jsonify(status_info)

@app.route('/fetch_zip/<filename_to_serve>', methods=['GET'])
def fetch_zip_file(filename_to_serve):
    safe_filename = Path(filename_to_serve).name 
    if safe_filename != filename_to_serve: return jsonify({"status":"error","message":"Invalid filename."}),400
    logging.info(f"Serving ZIP: '{safe_filename}' from {ZIP_STORAGE_DIR}")
    try:
        return send_from_directory(ZIP_STORAGE_DIR, safe_filename, as_attachment=True, mimetype='application/zip')
    except FileNotFoundError: return jsonify({"status":"error","message":"ZIP file not found."}),404
    except Exception as e: logging.error(f"Error serving ZIP '{safe_filename}': {e}",exc_info=True); return jsonify({"status":"error","message":"Could not serve ZIP."}),500

@app.route('/static/<path:filename>')
def serve_static_files(filename):
    return send_from_directory(str(APP_ROOT / 'static'), filename)

if __name__ == '__main__':
    print("KuKu FM Web Downloader - Flask App Starting...")
    print(f"Flask app running on http://127.0.0.1:5000 or http://localhost:5000")
    print(f"Base directory for KUKU class downloads: {DOWNLOAD_BASE_DIR.resolve()}")
    print(f"Storage directory for user ZIPs: {ZIP_STORAGE_DIR.resolve()}")
    if DEFAULT_COOKIES_FILE.exists(): print(f"Default cookies.json found: {DEFAULT_COOKIES_FILE.resolve()}")
    else: print(f"Default cookies.json not found at {DEFAULT_COOKIES_FILE.resolve()}.")
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True, use_reloader=False) 
