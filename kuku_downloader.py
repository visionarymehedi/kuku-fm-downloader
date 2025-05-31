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
from typing import Callable, Any 

class KuKu:
    def __init__(self, url: str,
                 cookies_file_path: str | None = None,
                 # export_metadata_flag removed
                 show_content_download_root_dir: Path = Path("Downloaded_Content_Default_Root") 
                ):
        self.showID = urlparse(url).path.split('/')[-1]
        self.session = requests.Session()
        self.current_show_url = url 
        
        self.cookies_file_path_config = cookies_file_path
        self.show_content_download_root_dir = Path(show_content_download_root_dir) 
        
        self.album_path: Path | None = None 
        self.metadata_filename_generated: str | None = None # Though export is removed, keep for internal structure if needed later

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Referer": "https://kukufm.com/",
            "Origin": "https://kukufm.com",
            "Authorization": "Bearer YOUR_BEARER_TOKEN_IF_ANY" 
        })

        self._load_cookies() 

        # --- Enhanced Cookie Logging ---
        print(f"SERVER LOG: Current session cookies after loading for show {self.showID}:")
        if self.session.cookies:
            for cookie in self.session.cookies:
                print(f"SERVER LOG: Cookie: Name='{cookie.name}', Value='{cookie.value[:30]}...', Domain='{cookie.domain}', Path='{cookie.path}'")
        else:
            print("SERVER LOG: No cookies in session after loading attempt.")
        
        cf_policy = self.session.cookies.get("CloudFront-Policy", domain=".kukufm.com") or self.session.cookies.get("CloudFront-Policy")
        cf_sig = self.session.cookies.get("CloudFront-Signature", domain=".kukufm.com") or self.session.cookies.get("CloudFront-Signature")
        cf_key = self.session.cookies.get("CloudFront-Key-Pair-Id", domain=".kukufm.com") or self.session.cookies.get("CloudFront-Key-Pair-Id")
        jwt_token = self.session.cookies.get("jwtToken", domain="kukufm.com") or self.session.cookies.get("jwtToken")
        print(f"SERVER LOG: Specific Check: jwtToken='{jwt_token[:30] if jwt_token else None}...', CF-Policy='{cf_policy[:30] if cf_policy else None}...', CF-Signature='{cf_sig[:30] if cf_sig else None}...', CF-Key-Pair-Id='{cf_key}'")
        # --- End Enhanced Cookie Logging ---


        print(f"SERVER LOG: Initializing KuKu for show ID: {self.showID} (URL: {url})")
        try:
            response = self.session.get(f"https://kukufm.com/api/v2.3/channels/{self.showID}/episodes/?page=1", timeout=20)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"SERVER LOG: ❌ Error fetching initial show data for {url}: {e}")
            raise 
        except json.JSONDecodeError as e:
            print(f"SERVER LOG: ❌ Error decoding JSON for initial show data from {url}: {e}")
            print(f"SERVER LOG: Response text: {response.text[:500]}") # Log more of the response
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
        cookies_loaded = False
        if self.cookies_file_path_config:
            print(f"SERVER LOG: ℹ️ Attempting to load cookies from configured file: '{self.cookies_file_path_config}'")
            if self._load_cookies_from_json(self.cookies_file_path_config):
                cookies_loaded = True
            else:
                print(f"SERVER LOG: ⚠️ Failed to load cookies from '{self.cookies_file_path_config}'.")
        
        if not cookies_loaded:
            try:
                import browser_cookie3
                print("SERVER LOG: ℹ️ Attempting to load cookies using browser_cookie3...")
                cj = browser_cookie3.load(domain_name='kukufm.com')
                if len(cj) > 0: 
                    self.session.cookies.update(cj)
                    print("SERVER LOG: ✅ Successfully loaded cookies using browser_cookie3.")
                    cookies_loaded = True
                    # self._check_essential_cookies("browser_cookie3") # This will be checked after all load attempts
                else:
                    print("SERVER LOG: ℹ️ browser_cookie3 did not find cookies for kukufm.com.")
            except ImportError:
                print("SERVER LOG: ℹ️ browser_cookie3 not installed. Skipping.")
            except Exception as e: 
                print(f"SERVER LOG: ⚠️ An error occurred while trying to load cookies with browser_cookie3: {e}")

        if not cookies_loaded:
            default_cookie_file = Path("cookies.json") 
            print(f"SERVER LOG: ℹ️ Attempting to load cookies from default '{default_cookie_file}'...")
            if self._load_cookies_from_json(str(default_cookie_file)): 
                cookies_loaded = True
        
        if not cookies_loaded:
            print("\nSERVER LOG: ‼️ IMPORTANT: No cookies were loaded by any method.")
        else:
            print("SERVER LOG: Cookie loading process completed.")
        self._check_essential_cookies("Final Check After All Load Attempts")


    def _check_essential_cookies(self, source_description: str):
        print(f"SERVER LOG: --- Cookie Check ({source_description}) ---")
        essential_cookies = ["jwtToken", "CloudFront-Policy", "CloudFront-Signature", "CloudFront-Key-Pair-Id"]
        found_all_essential = True
        for c_name in essential_cookies:
            # Try getting with specific domain first, then without (more general)
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


    def _load_cookies_from_json(self, cookie_filename_str="cookies.json") -> bool:
        cookie_file_path = Path(cookie_filename_str)
        if not cookie_file_path.is_absolute():
             script_dir_or_cwd = Path(__file__).parent if "__file__" in locals() else Path.cwd()
             cookie_file_path = script_dir_or_cwd / cookie_filename_str

        if not cookie_file_path.exists():
            if cookie_filename_str == "cookies.json": # Only log if it's the default local file attempt
                 print(f"SERVER LOG: ℹ️ Default cookie file '{cookie_filename_str}' not found at '{cookie_file_path.resolve()}'.")
            return False
        
        print(f"SERVER LOG: Attempting to load cookies from JSON file: {cookie_file_path.resolve()}")
        try:
            with open(cookie_file_path, 'r', encoding='utf-8') as f: cookies_data = json.load(f)
            if not isinstance(cookies_data, list):
                print(f"SERVER LOG: ⚠️ '{cookie_file_path}' content is not a list."); return False
            
            loaded_count = 0
            for c in cookies_data:
                if 'name' in c and 'value' in c:
                    domain_val = c.get('domain')
                    # Ensure domain starts with a dot if it's for all subdomains and not hostOnly
                    # and if it's a relevant domain.
                    if domain_val and "kukufm.com" in domain_val:
                        if not c.get('hostOnly', False) and not domain_val.startswith('.'):
                            domain_val = '.' + domain_val
                    elif domain_val and "kukufm.com" not in domain_val:
                        # Skip cookies not for kukufm.com to avoid polluting session for other domains
                        # print(f"SERVER LOG: Skipping cookie not for kukufm.com: {c.get('name')} for domain {domain_val}")
                        continue 
                    
                    self.session.cookies.set(
                        name=c['name'],value=c['value'],
                        domain=domain_val, # Pass None if not specified in JSON, requests handles it
                        path=c.get('path','/'),
                        secure=c.get('secure', False),
                        expires=c.get('expirationDate') 
                    )
                    loaded_count +=1
            print(f"SERVER LOG: ✅ Loaded {loaded_count} cookies from '{cookie_file_path}'.")
            # self._check_essential_cookies(str(cookie_file_path)); # Check is done after all load attempts
            return True
        except json.JSONDecodeError:
            print(f"SERVER LOG: ❌ Error decoding '{cookie_file_path}'. Ensure it's valid JSON.")
        except Exception as e: 
            print(f"SERVER LOG: ❌ Error loading cookies from '{cookie_file_path}': {e}")
        return False

    @staticmethod
    def clean(name: str) -> str:
        if not isinstance(name, str): name = str(name)
        name = name.strip(); name = re.sub(r'[:]', ' - ', name) 
        name = re.sub(r'[\\/*?"<>|$]', '', name); name = re.sub(r'\s+', ' ', name).strip() 
        return name if name else "Unknown"

    def _ffmpeg_headers(self) -> str:
        cookies = []
        for name in ["CloudFront-Policy", "CloudFront-Signature", "CloudFront-Key-Pair-Id"]:
            if val := self.session.cookies.get(name, domain='.kukufm.com') or self.session.cookies.get(name):
                cookies.append(f"{name}={val}")
        
        if not cookies:
            print("SERVER LOG: _ffmpeg_headers: ⚠️ No CloudFront cookies found in session for FFMPEG.")
            return ""
        header_string = f"Cookie: {'; '.join(cookies)}\r\n"
        print(f"SERVER LOG: _ffmpeg_headers: Generated FFMPEG Cookie header: {header_string[:100]}...") # Log part of it
        return header_string


    def download_episode(self, ep_data: dict, album_folder_path: Path, cover_file_path: Path | None):
        episode_title_cleaned = KuKu.clean(ep_data.get('title', 'Untitled Episode'))
        content_info = ep_data.get('content', {}); 
        hls_stream_url = content_info.get('hls_url') or content_info.get('premium_audio_url')
        
        print(f"SERVER LOG: Preparing to download episode '{episode_title_cleaned}'. HLS URL: {hls_stream_url}")

        if not hls_stream_url:
            print(f"SERVER LOG: ⛔ Ep '{episode_title_cleaned}': No stream URL found.")
            return episode_title_cleaned, False

        idx_str = str(ep_data.get('index',0)).zfill(len(str(self.metadata['nEpisodes'])))
        base_fn = f"{idx_str}. {episode_title_cleaned}"
        audio_p = album_folder_path/f"{base_fn}.m4a"; srt_p = album_folder_path/f"{base_fn}.srt"

        if audio_p.exists() and audio_p.stat().st_size > 1024: # Check if > 1KB
            print(f"SERVER LOG: ✅ Ep '{episode_title_cleaned}': Already exists and seems complete.")
            return episode_title_cleaned, True

        # print(f"SERVER LOG: ⬇️ Downloading: {episode_title_cleaned}") # Handled by tqdm in downAlbum
        ffmpeg_cmd_headers = self._ffmpeg_headers(); 
        cmd = ["ffmpeg","-y"]
        if ffmpeg_cmd_headers: # Only add headers if they are present and not empty
             cmd.extend(["-headers", ffmpeg_cmd_headers])
        
        cmd.extend(["-user_agent",self.session.headers['User-Agent'],"-rw_timeout","30000000","-timeout","30000000", # 30s timeouts
                    "-reconnect","1","-reconnect_streamed","1","-reconnect_delay_max","10",
                    "-i",hls_stream_url,"-c","copy","-bsf:a","aac_adtstoasc",
                    "-hide_banner","-loglevel","error",str(audio_p)])
        
        print(f"SERVER LOG: Executing FFMPEG for '{episode_title_cleaned}': {' '.join(cmd[:5])}... -i {hls_stream_url} ...") # Log partial command for brevity

        try: 
            # Using check=False to manually inspect output
            process_result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
            
            print(f"SERVER LOG: FFMPEG STDOUT for '{episode_title_cleaned}':\n{process_result.stdout.strip() if process_result.stdout else 'No STDOUT'}")
            print(f"SERVER LOG: FFMPEG STDERR for '{episode_title_cleaned}':\n{process_result.stderr.strip() if process_result.stderr else 'No STDERR'}")

            if process_result.returncode != 0:
                print(f"SERVER LOG: ❌ FFMPEG failed for '{episode_title_cleaned}' with exit code {process_result.returncode}")
                if audio_p.exists() and audio_p.stat().st_size == 0: audio_p.unlink(missing_ok=True)
                return episode_title_cleaned, False
        
        except FileNotFoundError: 
            print(f"SERVER LOG: ❌ FFMPEG not found for '{episode_title_cleaned}'. Ensure FFMPEG is installed and in PATH.")
            return episode_title_cleaned, False
        except Exception as e: 
            print(f"SERVER LOG: ❌ Unexpected FFMPEG error for '{episode_title_cleaned}': {e}")
            if audio_p.exists() and audio_p.stat().st_size == 0: audio_p.unlink(missing_ok=True)
            return episode_title_cleaned, False
        
        if not audio_p.exists() or audio_p.stat().st_size < 1024: # Check if file is too small or non-existent
            print(f"SERVER LOG: ❌ Downloaded file for '{episode_title_cleaned}' is missing or too small after FFMPEG. Size: {audio_p.stat().st_size if audio_p.exists() else 'N/A'}")
            return episode_title_cleaned, False

        if srt_url := content_info.get('subtitle_url'):
            try:
                print(f"SERVER LOG: 💬 Downloading subtitles for: {episode_title_cleaned}")
                with open(srt_p,'w',encoding='utf-8') as f: f.write(self.session.get(srt_url,timeout=10).text)
            except Exception as e: print(f"SERVER LOG: ⚠️ Subtitle download error for '{episode_title_cleaned}': {e}")

        try:
            print(f"SERVER LOG: 🏷️ Tagging: {episode_title_cleaned}")
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
            else: print(f"SERVER LOG: ⚠️ Cover not found/empty for tagging '{episode_title_cleaned}'.")
            tags.save()
        except Exception as e: 
            print(f"SERVER LOG: ❌ Tagging error for '{episode_title_cleaned}': {e}")
            return episode_title_cleaned, False
        
        print(f"SERVER LOG: 👍 Finished processing episode: {episode_title_cleaned}")
        return episode_title_cleaned, True

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

    # export_metadata_file method removed as per user request to remove metadata export feature

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
                                         disable=False) 

            for future in progress_bar_iterator: 
                ep_item = futures_map[future]
                ep_title_cleaned = KuKu.clean(ep_item.get('title', 'Unknown Episode'))
                processed_episodes_count += 1
                
                success_flag = False # Default to failure
                status_msg_for_callback = f"Starting processing for: {ep_title_cleaned}"
                try:
                    # The actual download and tagging happens here
                    _, success_flag = future.result() # title is already in ep_title_cleaned
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
                progress_bar_iterator.set_postfix_str(f"Last: {ep_title_cleaned[:20]}... ({'OK' if success_flag else 'FAIL'})")
        
        print(f"\nSERVER LOG: 🏁 Download summary for '{self.metadata['title']}': {ok_dl_count}/{total_episodes_to_process} successful.")
        if fail_titles_list: print(f"   SERVER LOG: ❌ Failed episodes: {', '.join(fail_titles_list)}")
        
        # Metadata export logic removed
        
        print(f"\nSERVER LOG: 🎉 Finished show (in KuKu class): {self.metadata['title']}")
