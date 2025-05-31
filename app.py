# app.py
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, session
from pathlib import Path
import threading
import os
import sys
import logging
import uuid 
import zipfile 
import shutil 
import time 
import json # <<< IMPORT ADDED HERE
from flask_apscheduler import APScheduler 

try:
    from kuku_downloader import KuKu 
except ImportError as e:
    print(f"CRITICAL ERROR: Error importing KuKu class: {e}")
    print("Ensure kuku_downloader.py is in the same directory as app.py or correctly in PYTHONPATH.")
    sys.exit(1)

class Config:
    SCHEDULER_API_ENABLED = True
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', os.urandom(32))


app = Flask(__name__)
app.config.from_object(Config())

APP_ROOT = Path(__file__).resolve().parent

RENDER_DISK_MOUNT_PATH_STR = os.environ.get('RENDER_DISK_MOUNT_PATH')
if RENDER_DISK_MOUNT_PATH_STR:
    PERSISTENT_STORAGE_ROOT = Path(RENDER_DISK_MOUNT_PATH_STR)
    logging.info(f"RENDER_DISK_MOUNT_PATH found: Using {PERSISTENT_STORAGE_ROOT} for persistent storage.")
else:
    PERSISTENT_STORAGE_ROOT = APP_ROOT 
    logging.info(f"RENDER_DISK_MOUNT_PATH not found. Using local app root {APP_ROOT} for storage.")

DOWNLOAD_BASE_DIR = PERSISTENT_STORAGE_ROOT / "Downloaded_Shows_Content" 
ZIP_STORAGE_DIR = PERSISTENT_STORAGE_ROOT / "_zips_for_user_download"    
DEFAULT_COOKIES_FILE = APP_ROOT / "cookies.json" 

DOWNLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)
ZIP_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)]) 

download_tasks_status = {} 
scheduler = APScheduler()

def cleanup_old_files_job():
    with app.app_context(): 
        logging.info("SCHEDULER: Running cleanup job for old files...")
        now = time.time()
        
        max_age_seconds_zip = 1 * 60 * 60      
        max_age_seconds_content = 2 * 60 * 60  
        
        deleted_zips_count = 0
        for item in ZIP_STORAGE_DIR.iterdir():
            try:
                if item.is_file() and item.suffix.lower() == '.zip':
                    file_mod_time = item.stat().st_mtime
                    if (now - file_mod_time) > max_age_seconds_zip:
                        item.unlink() 
                        logging.info(f"SCHEDULER: Deleted old ZIP: {item.name} (older than {max_age_seconds_zip/60:.0f} minutes)")
                        deleted_zips_count += 1
            except Exception as e:
                logging.error(f"SCHEDULER: Error deleting ZIP {item.name}: {e}")
        if deleted_zips_count > 0: logging.info(f"SCHEDULER: Deleted {deleted_zips_count} old ZIP file(s).")

        deleted_content_folders_count = 0
        for lang_dir in DOWNLOAD_BASE_DIR.iterdir():
            if lang_dir.is_dir():
                for type_dir in lang_dir.iterdir():
                    if type_dir.is_dir():
                        for show_dir in type_dir.iterdir(): 
                            if show_dir.is_dir():
                                try:
                                    dir_mod_time = show_dir.stat().st_mtime 
                                    if (now - dir_mod_time) > max_age_seconds_content:
                                        shutil.rmtree(show_dir) 
                                        logging.info(f"SCHEDULER: Deleted old show content folder: {show_dir.resolve()} (older than {max_age_seconds_content/60:.0f} minutes)")
                                        deleted_content_folders_count +=1
                                except Exception as e_show:
                                    logging.error(f"SCHEDULER: Error deleting show content folder {show_dir.name}: {e_show}")
        if deleted_content_folders_count > 0: logging.info(f"SCHEDULER: Deleted {deleted_content_folders_count} old show content folder(s).")
        
        cleaned_tasks = 0; tasks_to_delete = []
        max_task_status_age_seconds = max_age_seconds_zip + (15 * 60) 
        for task_id, task_info in list(download_tasks_status.items()):
            task_timestamp = task_info.get("timestamp", 0) 
            if task_info.get("status") != "processing" and (now - task_timestamp) > max_task_status_age_seconds:
                tasks_to_delete.append(task_id)
        for task_id in tasks_to_delete:
            if task_id in download_tasks_status: del download_tasks_status[task_id]; cleaned_tasks +=1
        if cleaned_tasks > 0: logging.info(f"SCHEDULER: Cleaned up {cleaned_tasks} old task status entries.")
        logging.info("SCHEDULER: Cleanup job finished.")

if not scheduler.running:
    scheduler.init_app(app)
    scheduler.start()
    logging.info("APScheduler initialized and started.")
    cleanup_job_interval_minutes = 30 
    trigger_args = {'minutes': cleanup_job_interval_minutes}
    if not scheduler.get_job('cleanup_files_job_id'):
        scheduler.add_job(id='cleanup_files_job_id', func=cleanup_old_files_job, trigger='interval', **trigger_args) 
        logging.info(f"SCHEDULER: Cleanup job scheduled with interval: {trigger_args}")
    else: logging.info("SCHEDULER: Cleanup job already scheduled.")

@app.route('/')
def index(): return render_template('index.html')

@app.route('/favicon.ico')
def favicon(): return Response(status=204)

@app.route('/api/set_user_cookies', methods=['POST'])
def set_user_cookies():
    data = request.get_json()
    if not data or 'cookies_json_string' not in data:
        return jsonify({"status": "error", "message": "No cookie data provided."}), 400

    cookies_json_string = data['cookies_json_string']
    try:
        parsed_cookies = json.loads(cookies_json_string) # Now json is defined
        if not isinstance(parsed_cookies, list):
            raise ValueError("Cookie data must be a JSON array of cookie objects.")
        
        for cookie_obj in parsed_cookies:
            if not all(k in cookie_obj for k in ('name', 'value')):
                raise ValueError("Each cookie object must have 'name' and 'value' keys.")
        
        session['user_kuku_cookies'] = parsed_cookies 
        logging.info(f"User cookies set in session. Count: {len(parsed_cookies)}")
        return jsonify({"status": "success", "message": "Cookies saved successfully for this session."})
    except json.JSONDecodeError: # Now json is defined
        logging.warning("Failed to parse user cookie JSON string.")
        return jsonify({"status": "error", "message": "Invalid JSON format for cookies."}), 400
    except ValueError as ve:
        logging.warning(f"Invalid cookie data structure: {ve}")
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as e:
        logging.error(f"Error setting user cookies: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "An unexpected error occurred while saving cookies."}), 500

@app.route('/api/clear_user_cookies', methods=['POST'])
def clear_user_cookies():
    if 'user_kuku_cookies' in session:
        del session['user_kuku_cookies']
        logging.info("User cookies cleared from session.")
        return jsonify({"status": "success", "message": "Your custom cookies have been cleared."})
    return jsonify({"status": "info", "message": "No custom cookies were set to clear."})

@app.route('/api/check_user_cookies', methods=['GET'])
def check_user_cookies():
    if 'user_kuku_cookies' in session and session['user_kuku_cookies']:
        return jsonify({"status": "success", "cookies_set": True, "message": "User cookies are currently set."})
    return jsonify({"status": "info", "cookies_set": False, "message": "No user cookies are currently set."})


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
    
    user_specific_cookies_list = session.get('user_kuku_cookies') 
    server_default_cookies_file = None
    if not user_specific_cookies_list: 
        server_default_cookies_file = str(DEFAULT_COOKIES_FILE) if DEFAULT_COOKIES_FILE.exists() else None
        logging.info(f"Task {task_id}: No user-specific cookies in session, using server default: {server_default_cookies_file}")
    else:
        logging.info(f"Task {task_id}: Using user-specific cookies from session ({len(user_specific_cookies_list)} cookies).")
    
    logging.info(f"Download request for URL: {kuku_url} -> Task ID: {task_id}")
        
    def download_task_wrapper(app_ctx, current_task_id, url, srv_cookies_p, user_cookies_l, dl_path_kuku):
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
                downloader = KuKu(
                    url=url, 
                    cookies_file_path=srv_cookies_p, 
                    user_cookies_list=user_cookies_l, 
                    show_content_download_root_dir=dl_path_kuku
                )
                
                show_title = downloader.metadata.get('title', 'Unknown Show')
                total_eps = downloader.metadata.get('nEpisodes', 0)
                download_tasks_status[current_task_id].update({"show_title":show_title,"total_episodes":total_eps,"message":f"Preparing '{show_title}'...","timestamp":time.time()})

                def episode_progress_cb(episode_title: str, success: bool, processed_count: int, total_episodes: int, status_message: str):
                    task_data = download_tasks_status.get(current_task_id)
                    if task_data:
                        task_data.update({"processed_count":processed_count,"total_episodes":total_episodes,"current_episode_title":episode_title,"message":f"Ep {processed_count}/{total_episodes}: '{episode_title[:25]}...'","timestamp":time.time()})
                        task_data["episode_updates"].append({"title":episode_title,"status_message":status_message,"success":success,"processed_count":processed_count,"total_episodes":total_episodes})
                        if len(task_data["episode_updates"]) > 30: task_data["episode_updates"] = task_data["episode_updates"][-30:]
                
                downloader.downAlbum(episode_status_callback=episode_progress_cb) 
                album_out_path = downloader.album_path 
                if not album_out_path or not album_out_path.is_dir(): raise Exception("Album path missing.")

                zip_fn = f"{KuKu.clean(show_title)}_{downloader.showID}.zip"
                zip_out_path = ZIP_STORAGE_DIR / zip_fn
                download_tasks_status[current_task_id].update({"message":f"Zipping '{show_title}'...","timestamp":time.time()})
                with zipfile.ZipFile(zip_out_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                    for item in album_out_path.rglob('*'): 
                        if item.is_file(): zf.write(item, item.relative_to(album_out_path))
                download_tasks_status[current_task_id].update({"status":"complete","message":"Download complete! ZIP ready.","zip_filename":zip_fn,"processed_count":total_eps,"timestamp":time.time()})
                logging.info(f"Thread: ZIP created: {zip_fn} (Task: {current_task_id})")
        except Exception as e:
            logging.error(f"❌ Thread Error (Task {current_task_id}): {e}", exc_info=True)
            title_err = downloader.metadata.get('title','Failed') if downloader else 'Failed (init)'
            download_tasks_status[current_task_id].update({"status":"error","message":str(e),"show_title":title_err,"timestamp":time.time()})
        finally:
            final_stat = download_tasks_status.get(current_task_id,{}).get('status','unknown')
            logging.info(f"Thread: Task {current_task_id} for {url} ended: {final_stat}")

    try:
        thread = threading.Thread(target=download_task_wrapper, name=f"TaskMgr-{task_id[:8]}",
                                  args=(app.app_context(), task_id, kuku_url, 
                                        server_default_cookies_file, 
                                        user_specific_cookies_list,  
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
    
    target_file_path = ZIP_STORAGE_DIR / safe_filename
    logging.info(f"Attempting to serve ZIP: '{safe_filename}' from resolved directory: {ZIP_STORAGE_DIR.resolve()}. Full target path: {target_file_path.resolve()}")
    
    if not target_file_path.exists():
        logging.error(f"ZIP file NOT FOUND for serving: '{safe_filename}' at resolved path {target_file_path.resolve()}")
        try:
            dir_contents = [str(p.name) for p in ZIP_STORAGE_DIR.iterdir() if p.is_file()] 
            logging.info(f"Contents of ZIP_STORAGE_DIR ({ZIP_STORAGE_DIR.resolve()}): {dir_contents if dir_contents else 'is empty or unreadable.'}")
        except Exception as e_dir:
            logging.error(f"Could not list contents of ZIP_STORAGE_DIR: {e_dir}")
        return jsonify({"status":"error","message":"ZIP file not found. It may have been cleaned up or the download failed."}),404
    try:
        return send_from_directory(ZIP_STORAGE_DIR, safe_filename, as_attachment=True, mimetype='application/zip')
    except Exception as e: 
        logging.error(f"Error serving ZIP '{safe_filename}': {e}",exc_info=True)
        return jsonify({"status":"error","message":"Could not serve ZIP."}),500

@app.route('/api/data', methods=['GET']) 
def api_data():
    logging.info("Placeholder /api/data endpoint was reached.")
    return jsonify({"message": "This is the /api/data endpoint.","status": "ok"})

@app.route('/static/<path:filename>')
def serve_static_files(filename):
    return send_from_directory(str(APP_ROOT / 'static'), filename)

if __name__ == '__main__':
    print("KuKu FM Web Downloader - Flask App Starting...")
    print(f"Flask app running on http://127.0.0.1:5000 or http://localhost:5000")
    print(f"Persistent storage root (for downloads & zips): {PERSISTENT_STORAGE_ROOT.resolve()}")
    print(f"  -> Raw content will be in: {DOWNLOAD_BASE_DIR.resolve()}")
    print(f"  -> User ZIPs will be in: {ZIP_STORAGE_DIR.resolve()}")
    if DEFAULT_COOKIES_FILE.exists(): print(f"Default cookies.json found: {DEFAULT_COOKIES_FILE.resolve()}")
    else: print(f"Default cookies.json not found at {DEFAULT_COOKIES_FILE.resolve()}.")
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True, use_reloader=False) 
