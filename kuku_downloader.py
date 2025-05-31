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
import sys 
from typing import Callable, Any, List, Dict # Added List and Dict for type hinting

class KuKu:
    def __init__(self, url: str,
                 # cookies_file_path is for the server-side default cookies.json
                 cookies_file_path: str | None = None, 
                 # user_cookies_list is for cookies provided by the user via the web UI
                 user_cookies_list: List[Dict[str, Any]] | None = None, 
                 show_content_download_root_dir: Path = Path("Downloaded_Content_Default_Root") 
                ):
        """
        Initializes the KuKu downloader with the show URL and configurations.
        User-provided cookies take precedence.
        """
        self.showID = urlparse(url).path.split('/')[-1]
        self.session = requests.Session()
        self.current_show_url = url 
        
        self.cookies_file_path_config = cookies_file_path # For server-side default cookies.json
        self.user_provided_cookies_config = user_cookies_list # For user-inputted cookies
        
        self.show_content_download_root_dir = Path(show_content_download_root_dir) 
        
        self.album_path: Path | None = None 
        self.metadata_filename_generated: str | None = None # Though export is removed, keep for potential future internal use

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Referer": "https://kukufm.com/",
            "Origin": "https://kukufm.com",
            "Authorization": "Bearer YOUR_BEARER_TOKEN_IF_ANY" # This might be overridden or unnecessary if jwtToken cookie is primary
        })

        self._load_cookies() # This method will now prioritize user_provided_cookies_config

        print(f"SERVER LOG: Initializing KuKu for show ID: {self.showID} (URL: {url})")
        try:
            response = self.session.get(f"https://kukufm.com/api/v2.3/channels/{self.showID}/episodes/?page=1", timeout=20)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"SERVER LOG: ❌ Error fetching initial show data for {url}: {e}")
            print(f"SERVER LOG: Headers sent: {self.session.headers}")
            print(f"SERVER LOG: Cookies sent: {self.session.cookies.get_dict()}")
            raise 
        except json.JSONDecodeError as e:
            print(f"SERVER LOG: ❌ Error decoding JSON for initial show data from {url}: {e}")
            print(f"SERVER LOG: Response text: {response.text[:500]}") 
            raise

        show = data.get('show', {})
        if not show:
            raise ValueError(f"❌ 'show' data not found in API response for {url}.")

        self.metadata = {
            'show_id': self.showID, 'show_url': url,
            'title': KuKu.clean(show.get('title', 'Untitled Show')),
            'image': show.get('original_image', ''),
            'date': show.get('published_on', '')[:10],
            'author': KuKu.clean(show.get('author', {}).get('name', 'Unknown Author')),
            'lang': show.get('lang', {}).get('title_secondary', 'Unknown').capitalize(),
            'nEpisodes': show.get('n_episodes', 0),
            'type': show.get('content_type', {}).get('slug', 'unknown').replace('-', ' ').title(),
            'fictional': show.get('is_fictional', False),
            'ageRating': show.get('meta_data', {}).get('age_rating', 'Unrated'),
            'description': KuKu.clean(show.get('description_title', '')), 
            'credits': {} 
        }

        if 'credits' in show and isinstance(show['credits'], dict):
            for role, members in show['credits'].items():
                if isinstance(members, list):
                    cleaned_members = [KuKu.clean(p.get('full_name', '')) for p in members if p.get('full_name')]
                    if cleaned_members: 
                        self.metadata['credits'][role.replace('_', ' ').title()] = ', '.join(cleaned_members)
        
        print("SERVER LOG: 📝 Show Metadata Initialized:")
        print(f"SERVER LOG: Title: {self.metadata['title']}, Episodes: {self.metadata['nEpisodes']}")

    def _load_cookies(self):
        """
        Loads cookies with priority:
        1. User-provided cookies (passed to __init__).
        2. browser_cookie3 (if available and user cookies not provided).
        3. Server-side default cookies.json (if available and others not provided).
        """
        cookies_loaded_source = None

        # 1. Try user-provided cookies first
        if self.user_provided_cookies_config and isinstance(self.user_provided_cookies_config, list):
            print(f"SERVER LOG: ℹ️ Attempting to load user-provided cookies ({len(self.user_provided_cookies_config)} items)...")
            loaded_count = 0
            for cookie_dict in self.user_provided_cookies_config:
                if 'name' in cookie_dict and 'value' in cookie_dict:
                    # Ensure domain is correctly formatted for requests.Session
                    domain_val = cookie_dict.get('domain')
                    if domain_val and not domain_val.startswith('.'): # requests prefers leading dot for domain-wide cookies
                        if "kukufm.com" in domain_val: # Only adjust for relevant domains
                             # Check if it's a subdomain or the main domain to avoid double dots like "..kukufm.com"
                            if domain_val == "kukufm.com" or not domain_val.count('.') > 1 : # e.g. kukufm.com or .kukufm.com
                                pass # Keep as is or ensure leading dot if appropriate
                            elif not cookie_dict.get('hostOnly', False): # For subdomains, ensure leading dot if not hostOnly
                                domain_val = '.' + domain_val
                    
                    self.session.cookies.set(
                        name=cookie_dict['name'],
                        value=cookie_dict['value'],
                        domain=domain_val,
                        path=cookie_dict.get('path', '/'),
                        secure=cookie_dict.get('secure', False),
                        expires=cookie_dict.get('expirationDate') # requests handles Unix timestamp
                    )
                    loaded_count += 1
            if loaded_count > 0:
                print(f"SERVER LOG: ✅ Successfully loaded {loaded_count} user-provided cookies.")
                cookies_loaded_source = "User Input"
            else:
                print("SERVER LOG: ⚠️ No valid user-provided cookies were loaded from the input list.")
        
        # 2. Try browser_cookie3 if user cookies were not provided or failed
        if not cookies_loaded_source:
            try:
                import browser_cookie3
                print("SERVER LOG: ℹ️ No user cookies provided, attempting browser_cookie3...")
                cj = browser_cookie3.load(domain_name='kukufm.com')
                if len(cj) > 0: 
                    self.session.cookies.update(cj)
                    print("SERVER LOG: ✅ Successfully loaded cookies using browser_cookie3.")
                    cookies_loaded_source = "browser_cookie3"
                else:
                    print("SERVER LOG: ℹ️ browser_cookie3 did not find cookies for kukufm.com.")
            except ImportError:
                print("SERVER LOG: ℹ️ browser_cookie3 not installed. Skipping.")
            except Exception as e: 
                print(f"SERVER LOG: ⚠️ An error occurred with browser_cookie3: {e}")

        # 3. Try server-side default cookies.json if still no cookies
        if not cookies_loaded_source and self.cookies_file_path_config:
            print(f"SERVER LOG: ℹ️ No user/browser_cookie3 cookies, attempting server default: '{self.cookies_file_path_config}'")
            if self._load_cookies_from_json_file(self.cookies_file_path_config): # Renamed for clarity
                cookies_loaded_source = f"Server File ({self.cookies_file_path_config})"
            else:
                print(f"SERVER LOG: ⚠️ Failed to load cookies from server default '{self.cookies_file_path_config}'.")
        
        if not cookies_loaded_source:
            print("\nSERVER LOG: ‼️ IMPORTANT: No cookies were loaded by any method for this session.")
        else:
            print(f"SERVER LOG: Cookies successfully loaded into session from: {cookies_loaded_source}.")
        
        self._check_essential_cookies(f"Final Check (Source: {cookies_loaded_source or 'None'})")


    def _check_essential_cookies(self, source_description: str):
        # ... (this method remains the same as in the Canvas ID: kuku_downloader_web_py_full) ...
        print(f"SERVER LOG: --- Cookie Check ({source_description}) ---")
        essential_cookies = ["jwtToken", "CloudFront-Policy", "CloudFront-Signature", "CloudFront-Key-Pair-Id"]
        found_all_essential = True
        for c_name in essential_cookies:
            cookie_val = self.session.cookies.get(c_name, domain="kukufm.com") or \
                         self.session.cookies.get(c_name, domain=".kukufm.com") or \
                         self.session.cookies.get(c_name)
            if cookie_val:
                print(f"SERVER LOG: ✅ Found '{c_name}'.")
            else:
                print(f"SERVER LOG: ⚠️ MISSING essential cookie: '{c_name}'.")
                found_all_essential = False
        if not found_all_essential:
             print(f"SERVER LOG: ‼️ At least one essential cookie is missing after {source_description}. Downloads likely to fail for protected content.")
        print(f"SERVER LOG: --- End Cookie Check ---")


    def _load_cookies_from_json_file(self, cookie_filename_str: str) -> bool: # Renamed from _load_cookies_from_json
        """Loads cookies from a specified JSON file into the session."""
        cookie_file_path = Path(cookie_filename_str)
        if not cookie_file_path.is_absolute():
             # If it's a relative path for the server-side default, assume it's next to this script
             script_dir = Path(__file__).parent if "__file__" in locals() else Path.cwd()
             cookie_file_path = script_dir / cookie_filename_str

        if not cookie_file_path.exists():
            print(f"SERVER LOG: ℹ️ Server cookie file '{cookie_filename_str}' not found at '{cookie_file_path.resolve()}'.")
            return False
        
        print(f"SERVER LOG: Attempting to load cookies from server JSON file: {cookie_file_path.resolve()}")
        try:
            with open(cookie_file_path, 'r', encoding='utf-8') as f: cookies_data = json.load(f)
            if not isinstance(cookies_data, list):
                print(f"SERVER LOG: ⚠️ '{cookie_file_path}' content is not a list."); return False
            
            loaded_count = 0
            for c_dict in cookies_data:
                if 'name' in c_dict and 'value' in c_dict:
                    domain_val = c_dict.get('domain')
                    if domain_val and "kukufm.com" in domain_val:
                        if not c_dict.get('hostOnly', False) and not domain_val.startswith('.'):
                            domain_val = '.' + domain_val
                    elif domain_val and "kukufm.com" not in domain_val:
                        continue 
                    
                    self.session.cookies.set(
                        name=c_dict['name'],value=c_dict['value'],
                        domain=domain_val, path=c_dict.get('path','/'),
                        secure=c_dict.get('secure', False), expires=c_dict.get('expirationDate')
                    )
                    loaded_count +=1
            print(f"SERVER LOG: ✅ Loaded {loaded_count} cookies from server file '{cookie_file_path}'.")
            return True # _check_essential_cookies will be called once after all loading attempts
        except json.JSONDecodeError:
            print(f"SERVER LOG: ❌ Error decoding '{cookie_file_path}'. Ensure it's valid JSON.")
        except Exception as e: 
            print(f"SERVER LOG: ❌ Error loading cookies from '{cookie_file_path}': {e}")
        return False

    # --- Static method clean remains the same ---
    @staticmethod
    def clean(name: str) -> str:
        if not isinstance(name, str): name = str(name)
        name = name.strip(); name = re.sub(r'[:]', ' - ', name) 
        name = re.sub(r'[\\/*?"<>|$]', '', name); name = re.sub(r'\s+', ' ', name).strip() 
        return name if name else "Unknown"

    # --- Method _ffmpeg_headers remains the same ---
    def _ffmpeg_headers(self) -> str:
        cookies = []
        for name in ["CloudFront-Policy", "CloudFront-Signature", "CloudFront-Key-Pair-Id"]:
            if val := self.session.cookies.get(name, domain='.kukufm.com') or self.session.cookies.get(name):
                cookies.append(f"{name}={val}")
        if not cookies: print("SERVER LOG: _ffmpeg_headers: ⚠️ No CloudFront cookies found in session for FFMPEG.")
        header_string = f"Cookie: {'; '.join(cookies)}\r\n" if cookies else ""
        if header_string: print(f"SERVER LOG: _ffmpeg_headers: Generated FFMPEG Cookie header: {header_string[:100]}...")
        return header_string

    # --- Method download_episode remains largely the same (no conversion logic) ---
    def download_episode(self, ep_data: dict, album_folder_path: Path, cover_file_path: Path | None):
        episode_title_cleaned = KuKu.clean(ep_data.get('title', 'Untitled Episode'))
        content_info = ep_data.get('content', {}); 
        hls_stream_url = content_info.get('hls_url') or content_info.get('premium_audio_url')
        
        # print(f"SERVER LOG: Preparing to download episode '{episode_title_cleaned}'. HLS URL: {hls_stream_url}") # Logged by callback

        if not hls_stream_url:
            # print(f"SERVER LOG: ⛔ Ep '{episode_title_cleaned}': No stream URL found.") # Logged by callback
            return episode_title_cleaned, False

        idx_str = str(ep_data.get('index',0)).zfill(len(str(self.metadata['nEpisodes'])))
        base_fn = f"{idx_str}. {episode_title_cleaned}"
        audio_p = album_folder_path/f"{base_fn}.m4a"; srt_p = album_folder_path/f"{base_fn}.srt"

        if audio_p.exists() and audio_p.stat().st_size > 1024: 
            # print(f"SERVER LOG: ✅ Ep '{episode_title_cleaned}': Already exists.") # Logged by callback
            return episode_title_cleaned, True

        ffmpeg_cmd_headers = self._ffmpeg_headers(); 
        cmd = ["ffmpeg","-y"]
        if ffmpeg_cmd_headers: cmd.extend(["-headers", ffmpeg_cmd_headers])
        cmd.extend(["-user_agent",self.session.headers['User-Agent'],"-rw_timeout","30000000","-timeout","30000000",
                    "-reconnect","1","-reconnect_streamed","1","-reconnect_delay_max","10",
                    "-i",hls_stream_url,"-c","copy","-bsf:a","aac_adtstoasc",
                    "-hide_banner","-loglevel","error",str(audio_p)])
        
        # print(f"SERVER LOG: Executing FFMPEG for '{episode_title_cleaned}'...") # Logged by callback

        try: 
            process_result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
            if process_result.returncode != 0:
                # print(f"SERVER LOG: ❌ FFMPEG failed for '{episode_title_cleaned}' with exit code {process_result.returncode}") # Logged by callback
                # print(f"FFMPEG STDERR:\n{process_result.stderr.strip() if process_result.stderr else 'No STDERR'}") # Logged by callback
                if audio_p.exists() and audio_p.stat().st_size == 0: audio_p.unlink(missing_ok=True)
                return episode_title_cleaned, False
        except FileNotFoundError: 
            # print(f"SERVER LOG: ❌ FFMPEG not found for '{episode_title_cleaned}'.") # Logged by callback
            return episode_title_cleaned, False
        except Exception as e: 
            # print(f"SERVER LOG: ❌ Unexpected FFMPEG error for '{episode_title_cleaned}': {e}") # Logged by callback
            if audio_p.exists() and audio_p.stat().st_size == 0: audio_p.unlink(missing_ok=True)
            return episode_title_cleaned, False
        
        if not audio_p.exists() or audio_p.stat().st_size < 1024: 
            # print(f"SERVER LOG: ❌ Downloaded file for '{episode_title_cleaned}' is missing or too small.") # Logged by callback
            return episode_title_cleaned, False

        if srt_url := content_info.get('subtitle_url'):
            try:
                # print(f"SERVER LOG: 💬 Downloading subtitles for: {episode_title_cleaned}") # Logged by callback
                with open(srt_p,'w',encoding='utf-8') as f: f.write(self.session.get(srt_url,timeout=10).text)
            except Exception as e: print(f"SERVER LOG: ⚠️ Subtitle download error for '{episode_title_cleaned}': {e}")

        try:
            # print(f"SERVER LOG: 🏷️ Tagging: {episode_title_cleaned}") # Logged by callback
            tags=MP4(str(audio_p)); tags['\xa9nam']=[episode_title_cleaned]; tags['\xa9ART']=[self.metadata['author']]
            tags['aART']=[self.metadata['author']]; tags['\xa9alb']=[self.metadata['title']]
            tags['trkn']=[(ep_data.get('index',1),self.metadata['nEpisodes'])]
            if pd:=ep_data.get('published_on',''): tags['\xa9day']=[pd[:10]]
            tags['stik']=[2]; tags.pop("©too",None)
            itunes_tags={'Fictional':str(self.metadata['fictional']),'Author':self.metadata['author'],
                           'Language':self.metadata['lang'],'Type':self.metadata['type'],
                           'Season':str(ep_data.get('season_no',1))}
            if self.metadata['ageRating'] not in ['Unrated',None,'']:
                itunes_tags['Age rating']=str(self.metadata['ageRating'])
            for r,n in self.metadata['credits'].items(): itunes_tags[r]=n
            for k,v in itunes_tags.items():tags[f'----:com.apple.iTunes:{k}']=v.encode('utf-8')
            if cover_file_path and cover_file_path.exists() and cover_file_path.stat().st_size > 0:
                with open(cover_file_path,'rb') as img_f: tags['covr']=[MP4Cover(img_f.read())]
            tags.save()
        except Exception as e: 
            # print(f"SERVER LOG: ❌ Tagging error for '{episode_title_cleaned}': {e}") # Logged by callback
            return episode_title_cleaned, False
        
        # print(f"SERVER LOG: 👍 Finished processing episode: {episode_title_cleaned}") # Logged by callback
        return episode_title_cleaned, True

    # --- Method download_cover remains the same ---
    def download_cover(self, image_url: str, save_to_path: Path) -> bool:
        if not image_url: print("SERVER LOG: ⚠️ No cover URL."); return False
        if save_to_path.exists() and save_to_path.stat().st_size > 100: return True
        try:
            print(f"SERVER LOG: 🖼️ Downloading cover: {image_url}")
            h={"User-Agent":self.session.headers.get("User-Agent"),"Referer":self.session.headers.get("Referer"),"Accept":"image/*"}
            cf_c={k:v for k,v in {n:self.session.cookies.get(n) for n in ["CloudFront-Policy","CloudFront-Signature","CloudFront-Key-Pair-Id"]}.items() if v}
            r=requests.get(image_url,stream=True,headers=h,cookies=cf_c or None,timeout=30); r.raise_for_status()
            ct,cl=r.headers.get("Content-Type","").lower(),int(r.headers.get("Content-Length",0))
            if not ct.startswith("image/") or cl<100: raise ValueError(f"Invalid cover(type:{ct},size:{cl})")
            with open(save_to_path,'wb') as f: 
                for chunk in r.iter_content(8192): f.write(chunk)
            print(f"SERVER LOG: ✅ Cover saved: {save_to_path.name}"); return True
        except Exception as e: print(f"SERVER LOG: ⚠️ Cover download error: {e}")
        if save_to_path.exists(): save_to_path.unlink(missing_ok=True)
        return False
    
    # --- export_metadata_file method removed as per user request ---

    # --- Method downAlbum (with episode_status_callback) remains largely the same ---
    def downAlbum(self, episode_status_callback: Callable[[str, bool, int, int, str], None] | None = None):
        album_folder_name_cleaned = f"{self.metadata['title']} ({self.metadata['date'][:4] if self.metadata['date'] else 'ND'}) [{self.metadata['lang']}]"
        self.album_path = self.show_content_download_root_dir / self.clean(self.metadata['lang']) / self.clean(self.metadata['type']) / self.clean(album_folder_name_cleaned)
        self.album_path.mkdir(parents=True, exist_ok=True)
        print(f"SERVER LOG: 📂 Album content will be saved to: {self.album_path.resolve()}")

        cover_ext = ".png"; img_url_l = self.metadata['image'].lower()
        if ".jpg" in img_url_l or ".jpeg" in img_url_l: cover_ext = ".jpg"
        cover_p = self.album_path / f"cover{cover_ext}"
        actual_cover_p = cover_p if self.download_cover(self.metadata['image'], cover_p) else None

        all_eps_api, page = [], 1
        print("SERVER LOG: 🔄 Fetching all episode details from API...")
        while True:
            try:
                r = self.session.get(f"https://kukufm.com/api/v2.3/channels/{self.showID}/episodes/?page={page}",timeout=15)
                r.raise_for_status(); data = r.json()
            except Exception as e: print(f"SERVER LOG: ❌ API error page {page}: {e}"); break
            eps_pg = data.get('episodes',[])
            if not eps_pg: print(f"SERVER LOG: No more eps on page {page}."); break
            all_eps_api.extend(eps_pg)
            if not data.get('has_more',False): print("SERVER LOG: Last page of episodes reached."); break
            page += 1
        
        if not all_eps_api: 
            print("SERVER LOG: ❌ No episodes found for this show after API fetch.")
            if episode_status_callback:
                 episode_status_callback(episode_title="Show Setup", success=False, processed_count=0, total_episodes=0, status_message="No episodes found for this show.")
            return

        total_episodes_to_process = len(all_eps_api)
        print(f"SERVER LOG: 🎬 Total episodes to process: {total_episodes_to_process}")
        if self.metadata['nEpisodes']!=total_episodes_to_process: self.metadata['nEpisodes']=total_episodes_to_process
        
        ok_dl_count, fail_titles_list = 0,[]
        processed_episodes_count = 0
        workers = min(os.cpu_count() or 1, 2) 
        print(f"SERVER LOG: Starting ThreadPoolExecutor with {workers} workers.")
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures_map = {executor.submit(self.download_episode, ep, self.album_path, actual_cover_p): ep for ep in all_eps_api}
            
            progress_bar_iterator = tqdm(as_completed(futures_map), 
                                         total=total_episodes_to_process, 
                                         desc=f"Processing '{self.metadata['title']}'", 
                                         unit="ep", file=sys.stdout, 
                                         bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]',
                                         disable=True) # Disable tqdm for web app server logs by default

            for future in progress_bar_iterator: 
                ep_item = futures_map[future]
                ep_title_cleaned = KuKu.clean(ep_item.get('title', 'Unknown Episode'))
                processed_episodes_count += 1
                
                success_flag = False 
                status_msg_for_callback = f"Starting processing for: {ep_title_cleaned}"
                try:
                    _, success_flag = future.result() 
                    if success_flag:
                        ok_dl_count+=1
                        status_msg_for_callback = f"Successfully processed: {ep_title_cleaned}"
                    else: 
                        fail_titles_list.append(ep_title_cleaned)
                        status_msg_for_callback = f"Failed to process: {ep_title_cleaned}"
                except Exception as e: 
                    fail_titles_list.append(ep_title_cleaned)
                    status_msg_for_callback = f"Error during processing of '{ep_title_cleaned}': {e}"
                    print(f"SERVER LOG: ‼️ Thread error for '{ep_title_cleaned}': {e}")
                
                if episode_status_callback:
                    episode_status_callback(
                        episode_title=ep_title_cleaned, 
                        success=success_flag, 
                        processed_count=processed_episodes_count, 
                        total_episodes=total_episodes_to_process,
                        status_message=status_msg_for_callback
                    )
                # tqdm postfix update is less critical if callback handles UI update
                # progress_bar_iterator.set_postfix_str(f"Last: {ep_title_cleaned[:20]}... ({'OK' if success_flag else 'FAIL'})")
        
        print(f"\nSERVER LOG: 🏁 Download summary for '{self.metadata['title']}': {ok_dl_count}/{total_episodes_to_process} successful.")
        if fail_titles_list: print(f"   SERVER LOG: ❌ Failed episodes: {', '.join(fail_titles_list)}")
        
        # Metadata export logic removed
        
        print(f"\nSERVER LOG: 🎉 Finished show (in KuKu class): {self.metadata['title']}")

