# kuku_downloader.py
import json
import os
import re
import requests
import subprocess
from urllib.parse import urlparse
from mutagen.mp4 import MP4, MP4Cover
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tqdm import tqdm
# tqdm can be used for server-side logging of progress if desired, but not for direct UI feedback here.
# from tqdm import tqdm

class KuKu:
    def __init__(self, url: str,
                 cookies_file_path: str | None = None,
                 convert_format: str | None = None,
                 export_metadata_flag: bool = False,
                 download_base_dir: Path = Path("Downloaded_Shows_Web")  # Default for web app
                ):
        """
        Initializes the KuKu downloader with the show URL and configurations.
        """
        self.showID = urlparse(url).path.split('/')[-1]
        self.session = requests.Session()
        self.current_show_url = url 
        
        # Store configurations passed from the web app
        self.cookies_file_path_config = cookies_file_path
        self.convert_format_config = convert_format
        self.export_metadata_config = export_metadata_flag
        self.download_base_dir_config = Path(download_base_dir) # Ensure it's a Path object
        
        self.album_path: Path | None = None # Will be set in downAlbum after path calculation

        # --- START: Authentication Headers ---
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Referer": "https://kukufm.com/",
            "Origin": "https://kukufm.com",
            # IMPORTANT: Replace with your actual token or ensure cookie-based auth is sufficient.
            # For a web service, managing this token securely is critical if used.
            "Authorization": "Bearer YOUR_BEARER_TOKEN_IF_ANY" 
        })
        # --- END: Authentication Headers ---

        # --- START: Cookie Loading ---
        self._load_cookies() 
        # --- END: Cookie Loading ---

        print(f"SERVER LOG: Initializing KuKu for show ID: {self.showID} (URL: {url})")
        try:
            # Fetch the first page of episodes to get show metadata
            response = self.session.get(f"https://kukufm.com/api/v2.3/channels/{self.showID}/episodes/?page=1", timeout=20)
            response.raise_for_status() # Raises an HTTPError for bad responses
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"SERVER LOG: ❌ Error fetching initial show data for {url}: {e}")
            raise # Propagate error to be handled by Flask app
        except json.JSONDecodeError as e:
            print(f"SERVER LOG: ❌ Error decoding JSON for initial show data from {url}: {e}")
            print(f"SERVER LOG: Response text: {response.text[:200]}")
            raise

        show = data.get('show', {})
        if not show:
            raise ValueError(f"❌ 'show' data not found in API response for {url}. Check URL or authentication.")

        # Populate metadata dictionary
        self.metadata = {
            'show_id': self.showID, # For internal reference and metadata export
            'show_url': url,       # For internal reference and metadata export
            'title': KuKu.clean(show.get('title', 'Untitled Show')),
            'image': show.get('original_image', ''),
            'date': show.get('published_on', '')[:10], # YYYY-MM-DD
            'author': KuKu.clean(show.get('author', {}).get('name', 'Unknown Author')),
            'lang': show.get('lang', {}).get('title_secondary', 'Unknown').capitalize(),
            'nEpisodes': show.get('n_episodes', 0),
            'type': show.get('content_type', {}).get('slug', 'unknown').replace('-', ' ').title(),
            'fictional': show.get('is_fictional', False),
            'ageRating': show.get('meta_data', {}).get('age_rating', 'Unrated'),
            'description': KuKu.clean(show.get('description_title', '')), # Added description
            'credits': {} # To store narrator, writer, etc.
        }
        
        if 'credits' in show and isinstance(show['credits'], dict):
            for role, members in show['credits'].items():
                if isinstance(members, list):
                    cleaned_members = [KuKu.clean(p.get('full_name', '')) for p in members if p.get('full_name')]
                    if cleaned_members: # Only add if there are actual names
                        self.metadata['credits'][role.replace('_', ' ').title()] = ', '.join(cleaned_members)
        
        print("SERVER LOG: 📝 Show Metadata Initialized:")
        # Log a subset or confirmation rather than full metadata to keep logs cleaner
        print(f"SERVER LOG: Title: {self.metadata['title']}, Episodes: {self.metadata['nEpisodes']}")


    def _load_cookies(self):
        """Loads cookies using priority: configured file path, browser_cookie3, local 'cookies.json'."""
        cookies_loaded = False
        
        # 1. Try loading from configured cookies_file_path (passed from Flask app)
        if self.cookies_file_path_config:
            print(f"SERVER LOG: ℹ️ Attempting to load cookies from configured file: '{self.cookies_file_path_config}'")
            if self._load_cookies_from_json(self.cookies_file_path_config):
                cookies_loaded = True
            else:
                print(f"SERVER LOG: ⚠️ Failed to load cookies from '{self.cookies_file_path_config}'.")
        
        # 2. Try browser_cookie3 if not already loaded
        if not cookies_loaded:
            try:
                import browser_cookie3
                print("SERVER LOG: ℹ️ Attempting to load cookies using browser_cookie3...")
                # This might depend on the server environment having access to browser cookie stores
                cj = browser_cookie3.load(domain_name='kukufm.com')
                if len(cj) > 0: # Check if any cookies were loaded
                    self.session.cookies.update(cj)
                    print("SERVER LOG: ✅ Successfully loaded cookies using browser_cookie3.")
                    cookies_loaded = True
                    self._check_essential_cookies("browser_cookie3")
                else:
                    print("SERVER LOG: ℹ️ browser_cookie3 did not find cookies for kukufm.com.")
            except ImportError:
                print("SERVER LOG: ℹ️ browser_cookie3 not installed. Skipping automatic browser cookie loading.")
            except Exception as e: # Catch any error from browser_cookie3 (e.g., permission issues)
                print(f"SERVER LOG: ⚠️ An error occurred while trying to load cookies with browser_cookie3: {e}")

        # 3. Try local 'cookies.json' (relative to where app.py is run) if not already loaded
        if not cookies_loaded:
            # Path is relative to the current working directory of app.py
            default_cookie_file = Path("cookies.json") 
            print(f"SERVER LOG: ℹ️ Attempting to load cookies from default '{default_cookie_file}'...")
            if self._load_cookies_from_json(str(default_cookie_file)): # Pass as string
                cookies_loaded = True
        
        if not cookies_loaded:
            print("\nSERVER LOG: ‼️ IMPORTANT: No cookies were loaded by any method.")
            print("   Downloads for authenticated content will likely fail.")
        else:
            print("SERVER LOG: Cookies loaded into session.")


    def _check_essential_cookies(self, source_description: str):
        """Checks for essential cookies after loading them and logs warnings if not found."""
        if not self.session.cookies.get("jwtToken"):
            print(f"SERVER LOG: ⚠️ jwtToken not found after loading from {source_description}. Authentication might fail.")
        if not (self.session.cookies.get("CloudFront-Policy") and \
                self.session.cookies.get("CloudFront-Signature") and \
                self.session.cookies.get("CloudFront-Key-Pair-Id")):
            print(f"SERVER LOG: ⚠️ Essential CloudFront cookies not found after loading from {source_description}. Downloads might fail.")


    def _load_cookies_from_json(self, cookie_filename_str="cookies.json") -> bool:
        """Loads cookies from a JSON file into the session."""
        cookie_file_path = Path(cookie_filename_str)
        # If the path is not absolute, it's relative to where app.py is run (current working directory)
        if not cookie_file_path.is_absolute():
             # This assumes kuku_downloader.py is in the same dir as app.py, or CWD is set correctly.
             # For web apps, absolute paths or paths relative to APP_ROOT (from Flask app) are safer.
             # However, if cookies_file_path_config is passed, it might already be an absolute path.
             pass # Keep it as is, will be resolved based on CWD if relative

        if not cookie_file_path.exists():
            if cookie_filename_str == "cookies.json": # Only log for the default local file attempt
                 print(f"SERVER LOG: ℹ️ Default cookie file '{cookie_filename_str}' not found at '{cookie_file_path.resolve()}'.")
            return False
        
        try:
            with open(cookie_file_path, 'r', encoding='utf-8') as f:
                cookies_data = json.load(f)
            
            if not isinstance(cookies_data, list):
                print(f"SERVER LOG: ⚠️ '{cookie_file_path}' content is not a list. Expected JSON array of cookie objects.")
                return False

            for cookie_dict in cookies_data:
                if 'name' in cookie_dict and 'value' in cookie_dict:
                    domain = cookie_dict.get('domain')
                    # Ensure domain starts with a dot if it's for all subdomains and not hostOnly
                    if domain and not cookie_dict.get('hostOnly', False) and not domain.startswith('.'):
                        domain = '.' + domain
                    
                    self.session.cookies.set(
                        name=cookie_dict['name'],
                        value=cookie_dict['value'],
                        domain=domain, # Let requests handle None domain
                        path=cookie_dict.get('path', '/') # Default path to '/'
                    )
            print(f"SERVER LOG: ✅ Successfully loaded cookies from '{cookie_file_path}'.")
            self._check_essential_cookies(str(cookie_file_path))
            return True
        except json.JSONDecodeError:
            print(f"SERVER LOG: ❌ Error decoding '{cookie_file_path}'. Ensure it's valid JSON.")
        except Exception as e:
            print(f"SERVER LOG: ❌ An unexpected error occurred while loading cookies from '{cookie_file_path}': {e}")
        return False

    @staticmethod
    def clean(name: str) -> str:
        """Sanitises a string for use as a filename component."""
        if not isinstance(name, str): 
            name = str(name) # Ensure it's a string
        name = name.strip()
        name = re.sub(r'[:]', ' - ', name) # Replace colons
        name = re.sub(r'[\\/*?"<>|$]', '', name) # Remove illegal characters
        name = re.sub(r'\s+', ' ', name).strip() # Normalize whitespace and strip again
        return name if name else "Unknown" # Return "Unknown" if name becomes empty after cleaning

    def _ffmpeg_headers(self) -> str:
        """Constructs the Cookie header string for FFMPEG using CloudFront cookies."""
        cookies = []
        # Try to get cookies with and without domain specification for robustness
        # as different cookie export tools might format domain differently.
        for name in ["CloudFront-Policy", "CloudFront-Signature", "CloudFront-Key-Pair-Id"]:
            if val := self.session.cookies.get(name, domain='.kukufm.com') or self.session.cookies.get(name):
                cookies.append(f"{name}={val}")
        
        if not cookies:
            print("SERVER LOG: ⚠️ Warning: No CloudFront cookies found in session for FFMPEG. Downloads might fail for CDN content.")
            return ""
        return f"Cookie: {'; '.join(cookies)}\r\n"

    def _convert_audio(self, input_path: Path, output_format: str):
        """Converts the audio file to the specified format using FFMPEG."""
        output_path = input_path.with_suffix(f".{output_format.lower()}")
        if output_path.exists() and output_path.stat().st_size > 0: # Check if already converted and not empty
            print(f"SERVER LOG: ✅ Converted file already exists: {output_path.name}")
            return

        print(f"SERVER LOG: 🔄 Converting {input_path.name} to {output_format.upper()}...")
        ffmpeg_convert_command = [
            "ffmpeg", "-y", # Overwrite output without asking
            "-i", str(input_path),
            "-vn", # No video
            # Add specific codec/bitrate options if desired, e.g., for MP3:
            # "-codec:a", "libmp3lame", "-q:a", "2", # VBR quality 2 (good)
            "-hide_banner", "-loglevel", "error",
            str(output_path)
        ]
        try:
            subprocess.run(ffmpeg_convert_command, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            print(f"SERVER LOG: ✅ Successfully converted to {output_path.name}")
        except subprocess.CalledProcessError as e:
            print(f"SERVER LOG: ❌ ffmpeg conversion failed for: {input_path.name} to {output_format}")
            print(f"Command: {' '.join(e.cmd)}")
            print(f"Stderr: {e.stderr.strip() if e.stderr else 'No stderr'}")
        except FileNotFoundError:
            print("SERVER LOG: ❌ FFMPEG not found for conversion. Please ensure it's installed and in your PATH.")


    def download_episode(self, ep_data: dict, album_folder_path: Path, cover_file_path: Path | None):
        """Downloads, tags, and optionally converts a single episode. Returns (title, success_boolean)."""
        episode_title_cleaned = KuKu.clean(ep_data.get('title', 'Untitled Episode'))
        content_info = ep_data.get('content', {})
        
        hls_stream_url = content_info.get('hls_url') or content_info.get('premium_audio_url')
        if not hls_stream_url:
            print(f"SERVER LOG: ⛔ Episode '{episode_title_cleaned}': No stream URL found.")
            return episode_title_cleaned, False

        episode_index_str = str(ep_data.get('index', 0)).zfill(len(str(self.metadata['nEpisodes'])))
        base_filename = f"{episode_index_str}. {episode_title_cleaned}"
        
        audio_output_path = album_folder_path / f"{base_filename}.m4a"
        subtitle_output_path = album_folder_path / f"{base_filename}.srt"

        if audio_output_path.exists() and audio_output_path.stat().st_size > 1024: # Check if > 1KB
            print(f"SERVER LOG: ✅ Episode '{episode_title_cleaned}': Already exists and seems complete.")
            if self.convert_format_config: # Convert if needed even if m4a exists
                self._convert_audio(audio_output_path, self.convert_format_config)
            return episode_title_cleaned, True

        print(f"SERVER LOG: ⬇️ Downloading: {episode_title_cleaned}")
        ffmpeg_cmd_headers = self._ffmpeg_headers()
        ffmpeg_command = ["ffmpeg", "-y"]
        if ffmpeg_cmd_headers: 
             ffmpeg_command.extend(["-headers", ffmpeg_cmd_headers])
        
        ffmpeg_command.extend([
            "-user_agent", self.session.headers['User-Agent'],
            "-rw_timeout", "25000000", # 25 seconds read/write timeout
            "-timeout", "25000000",    # 25 seconds connection timeout
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10", # Increased max reconnect delay
            "-i", hls_stream_url,
            "-c", "copy", # Copy audio stream without re-encoding
            "-bsf:a", "aac_adtstoasc", # Essential for some HLS AAC streams to be valid MP4
            "-hide_banner", "-loglevel", "error", # Show only errors
            str(audio_output_path)
        ])

        try:
            process_result = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            # print(f"SERVER LOG: Downloaded successfully: {episode_title_cleaned}") # Logged at end of func
        except subprocess.CalledProcessError as e:
            print(f"SERVER LOG: ❌ ffmpeg failed for: {episode_title_cleaned}")
            print(f"Command: {' '.join(e.cmd)}")
            print(f"Stderr: {e.stderr.strip() if e.stderr else 'No stderr'}")
            if audio_output_path.exists() and audio_output_path.stat().st_size == 0: # Remove empty file
                audio_output_path.unlink() 
            return episode_title_cleaned, False
        except FileNotFoundError:
            print("SERVER LOG: ❌ FFMPEG not found. Please ensure it's installed and in your PATH.")
            return episode_title_cleaned, False
        except Exception as e:
            print(f"SERVER LOG: ❌ Unexpected error during FFMPEG execution for {episode_title_cleaned}: {e}")
            return episode_title_cleaned, False


        # Download Subtitles
        subtitle_url = content_info.get('subtitle_url')
        if subtitle_url:
            try:
                print(f"SERVER LOG: 💬 Downloading subtitles for: {episode_title_cleaned}")
                srt_content = self.session.get(subtitle_url, timeout=10).text
                with open(subtitle_output_path, 'w', encoding='utf-8') as f:
                    f.write(srt_content)
                # print(f"SERVER LOG: Subtitles saved: {subtitle_output_path.name}")
            except Exception as e:
                print(f"SERVER LOG: ⚠️ Subtitle download error for {episode_title_cleaned}: {e}")

        # Tagging
        if not audio_output_path.exists() or audio_output_path.stat().st_size == 0:
            print(f"SERVER LOG: Audio file {audio_output_path.name} missing or empty after download attempt, skipping tagging.")
            return episode_title_cleaned, False # If file is gone after supposed download, it's a failure
            
        try:
            print(f"SERVER LOG: 🏷️ Tagging: {episode_title_cleaned}")
            audio_tags = MP4(str(audio_output_path))
            audio_tags['\xa9nam'] = [episode_title_cleaned] # Track Title
            audio_tags['\xa9ART'] = [self.metadata['author']] # Artist
            audio_tags['aART'] = [self.metadata['author']]    # Album Artist
            audio_tags['\xa9alb'] = [self.metadata['title']]  # Album Title
            audio_tags['trkn'] = [(ep_data.get('index', 1), self.metadata['nEpisodes'])] # Track num / Total tracks
            
            episode_publish_date = ep_data.get('published_on', '')[:10]
            if episode_publish_date:
                 audio_tags['\xa9day'] = [episode_publish_date] # Release Date

            audio_tags['stik'] = [2] # Media Kind: Audiobook

            # Custom iTunes tags
            audio_tags['----:com.apple.iTunes:Fictional'] = str(self.metadata['fictional']).encode('utf-8')
            audio_tags['----:com.apple.iTunes:Author'] = self.metadata['author'].encode('utf-8')
            audio_tags['----:com.apple.iTunes:Language'] = self.metadata['lang'].encode('utf-8')
            audio_tags['----:com.apple.iTunes:Type'] = self.metadata['type'].encode('utf-8')
            audio_tags['----:com.apple.iTunes:Season'] = str(ep_data.get('season_no', 1)).encode('utf-8')

            if self.metadata['ageRating'] and self.metadata['ageRating'] != 'Unrated':
                audio_tags['----:com.apple.iTunes:Age rating'] = str(self.metadata['ageRating']).encode('utf-8')

            for role, people_names in self.metadata['credits'].items():
                audio_tags[f'----:com.apple.iTunes:{role}'] = people_names.encode('utf-8')
            
            audio_tags.pop("©too", None) # Remove encoding tool tag

            if cover_file_path and cover_file_path.exists() and cover_file_path.stat().st_size > 0:
                with open(cover_file_path, 'rb') as img_file:
                    img_bytes = img_file.read()
                    audio_tags['covr'] = [MP4Cover(img_bytes)] # Mutagen auto-detects format
            else:
                print(f"SERVER LOG: ⚠️ Cover image not found at '{cover_file_path}' or is empty. Skipping cover embedding for {episode_title_cleaned}.")

            audio_tags.save()
            # print(f"SERVER LOG: 👍 Tagged successfully: {episode_title_cleaned}") # Logged at end
        except Exception as e:
            print(f"SERVER LOG: ❌ Tagging failed for {episode_title_cleaned}: {e}")
            # import traceback; traceback.print_exc() # Uncomment for detailed tagging errors
            return episode_title_cleaned, False # Tagging failure means overall failure for this ep

        # Audio Conversion (if specified and download+tagging were successful)
        if self.convert_format_config:
            self._convert_audio(audio_output_path, self.convert_format_config)
            
        print(f"SERVER LOG: 👍 Finished processing episode: {episode_title_cleaned}")
        return episode_title_cleaned, True # Indicate success


    def download_cover(self, image_url: str, save_to_path: Path) -> bool:
        """Downloads the cover image, attempting to use specific CloudFront cookies."""
        if not image_url:
            print("SERVER LOG: ⚠️ No cover image URL provided in metadata.")
            return False
        if save_to_path.exists() and save_to_path.stat().st_size > 100: # Assume if >100 bytes, it's fine
            print(f"SERVER LOG: ✅ Cover image already exists: {save_to_path.name}")
            return True
            
        try:
            print(f"SERVER LOG: 🖼️ Attempting cover download from: {image_url}")
            
            image_request_headers = {
                "User-Agent": self.session.headers.get("User-Agent", "Mozilla/5.0"),
                "Referer": self.session.headers.get("Referer", "https://kukufm.com/"),
                "Accept": "image/avif,image/webp,image/apng,image/png,image/svg+xml,image/*,*/*;q=0.8",
            }
            
            cloudfront_cookies_for_request = {}
            if policy := self.session.cookies.get("CloudFront-Policy"): cloudfront_cookies_for_request["CloudFront-Policy"] = policy
            if signature := self.session.cookies.get("CloudFront-Signature"): cloudfront_cookies_for_request["CloudFront-Signature"] = signature
            if key_id := self.session.cookies.get("CloudFront-Key-Pair-Id"): cloudfront_cookies_for_request["CloudFront-Key-Pair-Id"] = key_id

            response = requests.get(
                image_url, 
                stream=True, 
                headers=image_request_headers, 
                cookies=cloudfront_cookies_for_request if cloudfront_cookies_for_request else None,
                timeout=30 # Increased timeout for image
            )
            response.raise_for_status() 

            content_type = response.headers.get("Content-Type", "").lower()
            content_length = int(response.headers.get("Content-Length", 0))

            print(f"SERVER LOG: 🔎 Cover Content-Type: {content_type}, Size: {content_length} bytes")
            if not content_type.startswith("image/") or content_length < 100: 
                raise ValueError(f"Cover does not appear to be a valid image (type: {content_type}, size: {content_length}).")

            with open(save_to_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"SERVER LOG: ✅ Cover downloaded successfully to: {save_to_path.name}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"SERVER LOG: ⚠️ Cover download HTTP error: {e}")
        except ValueError as e: 
            print(f"SERVER LOG: ⚠️ Cover validation error: {e}")
        except Exception as e:
            print(f"SERVER LOG: ⚠️ Unexpected error during cover download: {e}")
        
        if save_to_path.exists(): # Clean up if download failed partially
             save_to_path.unlink(missing_ok=True)
        return False

    def export_metadata_file(self, all_episodes_metadata_list: list, album_path_not_used_here: Path):
        """Exports show and episode metadata to a JSON file in the download_base_dir_config."""
        if not self.export_metadata_config:
            return
        
        # Save metadata in the root of download_base_dir_config, not inside the show's specific folder.
        export_directory = self.download_base_dir_config 
        export_directory.mkdir(parents=True, exist_ok=True) # Ensure the base export directory exists
        
        export_filename = export_directory / f"metadata_{self.metadata['show_id']}_{KuKu.clean(self.metadata['title'])}.json"
        
        metadata_to_export_content = {
            "show_info": self.metadata, # Contains show_id, show_url, title, image, etc.
            "episodes_list": all_episodes_metadata_list # List of dicts for each processed episode
        }
        try:
            with open(export_filename, 'w', encoding='utf-8') as f:
                json.dump(metadata_to_export_content, f, indent=2, ensure_ascii=False)
            print(f"SERVER LOG: 📄 Metadata exported successfully to: {export_filename}")
        except Exception as e:
            print(f"SERVER LOG: ❌ Error exporting metadata: {e}")


    def downAlbum(self):
        """Manages the download of the entire show. Sets self.album_path."""
        album_folder_name_cleaned = f"{self.metadata['title']} ({self.metadata['date'][:4] if self.metadata['date'] else 'ND'}) [{self.metadata['lang']}]"
        
        # self.album_path is where the specific show's files (m4a, srt, cover) will be stored.
        self.album_path = self.download_base_dir_config / self.clean(self.metadata['lang']) / self.clean(self.metadata['type']) / self.clean(album_folder_name_cleaned)
        self.album_path.mkdir(parents=True, exist_ok=True)
        print(f"SERVER LOG: 📂 Album content will be saved to: {self.album_path}")

        cover_ext = ".png" # Default
        if self.metadata['image']:
            img_url_lower = self.metadata['image'].lower()
            if ".jpg" in img_url_lower or ".jpeg" in img_url_lower:
                cover_ext = ".jpg"
        
        cover_file_path_on_server = self.album_path / f"cover{cover_ext}"
        
        cover_downloaded_successfully = self.download_cover(self.metadata['image'], cover_file_path_on_server)
        actual_cover_path_for_tagging = cover_file_path_on_server if cover_downloaded_successfully and cover_file_path_on_server.exists() else None

        all_episodes_data_from_api = []
        current_page = 1
        print("SERVER LOG: 🔄 Fetching all episode details from API...")
        
        # No tqdm here for server log, as it's not interactive. Client UI handles progress perception.
        while True:
            try:
                api_url = f"https://kukufm.com/api/v2.3/channels/{self.showID}/episodes/?page={current_page}"
                response = self.session.get(api_url, timeout=15)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                print(f"SERVER LOG: ❌ Failed to fetch episode page {current_page}: {e}")
                break 
            except json.JSONDecodeError as e:
                print(f"SERVER LOG: ❌ Failed to decode JSON for episode page {current_page}: {e}. Response: {response.text[:200]}")
                break

            episodes_on_page = data.get('episodes', [])
            if not episodes_on_page:
                print(f"SERVER LOG: No more episodes found on page {current_page} or page is empty.")
                break
            
            all_episodes_data_from_api.extend(episodes_on_page)
            print(f"SERVER LOG: Fetched page {current_page}, total episodes so far: {len(all_episodes_data_from_api)}")
            
            if not data.get('has_more', False):
                print("SERVER LOG: Reached the last page of episodes.")
                break
            current_page += 1
        
        if not all_episodes_data_from_api:
            print("SERVER LOG: ❌ No episodes found for this show after checking all pages. Exiting download process for this show.")
            # self.album_path might still exist as an empty folder, which is fine.
            return # Critical: stop if no episodes

        print(f"SERVER LOG: 🎬 Total episodes to process: {len(all_episodes_data_from_api)}")
        if self.metadata['nEpisodes'] != len(all_episodes_data_from_api):
             print(f"SERVER LOG: ℹ️ Note: Initial episode count was {self.metadata['nEpisodes']}, actual fetched is {len(all_episodes_data_from_api)}. Using actual count.")
             self.metadata['nEpisodes'] = len(all_episodes_data_from_api) # Update if different

        processed_episode_metadata_for_export = []
        successful_downloads_count = 0
        failed_episode_titles_list = []

        # For web app, limit workers to avoid overloading server. Could be configurable.
        num_workers = min(os.cpu_count() or 1, 4) # Max 4 workers for web context
        print(f"SERVER LOG: Starting ThreadPoolExecutor with {num_workers} workers for episode processing.")
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Map future to episode_data to retrieve original item if needed
            futures_map = {executor.submit(self.download_episode, ep_data, self.album_path, actual_cover_path_for_tagging): ep_data 
                           for ep_data in all_episodes_data_from_api}
            
            # Using tqdm for server log to see progress, disable=True for cleaner logs in production
            for future in tqdm(as_completed(futures_map), total=len(all_episodes_data_from_api), desc="Server Processing Episodes", unit="ep", disable=False):
                ep_data_item = futures_map[future] # Get original episode data
                try:
                    episode_title, success_flag = future.result()
                    if success_flag:
                        successful_downloads_count += 1
                        # Store metadata for export only on success
                        ep_export_meta = {
                            'index': ep_data_item.get('index'), 
                            'title': self.clean(ep_data_item.get('title')),
                            'published_on': ep_data_item.get('published_on', '')[:10],
                            'season_no': ep_data_item.get('season_no', 1),
                            # Optionally add HLS/subtitle URLs if needed in export
                            # 'hls_url': ep_data_item.get('content', {}).get('hls_url'),
                            # 'subtitle_url': ep_data_item.get('content', {}).get('subtitle_url')
                        }
                        processed_episode_metadata_for_export.append(ep_export_meta)
                    else:
                        failed_episode_titles_list.append(episode_title)
                except Exception as e:
                    # This catches errors from the future.result() call itself (e.g., if the thread task raised an unhandled exception)
                    failed_title = self.clean(ep_data_item.get('title', 'Unknown Episode (thread error)'))
                    print(f"SERVER LOG: ‼️ Exception in episode download thread for '{failed_title}': {e}")
                    failed_episode_titles_list.append(failed_title)
        
        print(f"\nSERVER LOG: 🏁 Download summary for '{self.metadata['title']}':")
        print(f"   SERVER LOG: 👍 Successful episodes: {successful_downloads_count}/{len(all_episodes_data_from_api)}")
        if failed_episode_titles_list:
            print(f"   SERVER LOG: ❌ Failed episodes ({len(failed_episode_titles_list)}):")
            for f_title in failed_episode_titles_list: 
                print(f"      SERVER LOG: - {f_title}")
        
        if self.export_metadata_config and processed_episode_metadata_for_export:
            self.export_metadata_file(processed_episode_metadata_for_export, self.album_path)
        
        # Ensure self.album_path is set if downloads occurred, even if some episodes failed.
        # It's set at the beginning of downAlbum. If no episodes were found, it might be an empty dir.
        if successful_downloads_count == 0 and len(all_episodes_data_from_api) > 0:
            print(f"SERVER LOG: ⚠️ No episodes were successfully downloaded for '{self.metadata['title']}'. The show folder might be empty or incomplete.")
        
        print(f"\nSERVER LOG: 🎉 Finished processing show (in KuKu class method): {self.metadata['title']}")
