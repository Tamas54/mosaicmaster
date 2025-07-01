# videodownloader.py - Javított verzió a thread hiba kiküszöbölésére
import asyncio
import random
import re
import logging
import time
import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
import threading

# Függőségek
import aiohttp
import aiofiles
import yt_dlp

# Konfig importálása a letöltési mappához
from config import SYSTEM_DOWNLOADS

# Alap logging beállítás
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# User Agent lista
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

class VideoDownloader:
    """Fejlett videó letöltő osztály a rendszerbe integráláshoz"""
    
    def __init__(self, connection_id: str, work_dir: Path = None, manager=None):
        self.connection_id = connection_id
        
        # Munkakönyvtár beállítása
        if work_dir is None:
            work_dir = Path('temp') / connection_id
        
        self.work_dir = work_dir
        self.work_dir.mkdir(exist_ok=True, parents=True)
        
        # Manager beállítása
        self.manager = manager
        
        # Cookies könyvtár létrehozása
        self.cookies_dir = self.work_dir / "cookies"
        self.cookies_dir.mkdir(exist_ok=True)
        self.create_cookies()
        
        # Alapértelmezett eseményhurok, amit a szálak között megosztunk
        self.main_loop = asyncio.get_running_loop()
        
        # Utolsó progress üzenet nyomon követése
        self._last_progress = 0
        self._progress_lock = threading.Lock()
        
    async def download_audio(self, url: str, platform: str = None) -> Optional[Path]:
        """
        Hang letöltése a videóból
        
        Args:
            url: Videó URL
            platform: Platform azonosító (opcionális)
            
        Returns:
            Path: A letöltött hang fájl elérési útja
        """
        try:
            await self.send_progress(10, "Hang letöltésének előkészítése...")
            
            # Platform azonosítása, ha nincs megadva
            if not platform or platform == "auto":
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.lower()
                
                if "youtube.com" in domain or "youtu.be" in domain:
                    platform = "youtube"
                elif "twitter.com" in domain or "x.com" in domain:
                    platform = "twitter"
                elif "facebook.com" in domain or "fb.watch" in domain:
                    platform = "facebook"
                elif "instagram.com" in domain:
                    platform = "instagram"
                elif "tiktok.com" in domain:
                    platform = "tiktok"
                elif "videa.hu" in domain:
                    platform = "videa"
                else:
                    platform = "other"
            
            # Videó ID kinyerése
            video_id = await self.extract_video_id(url, platform)
            
            # Ideiglenes kimenet a munkakönyvtárba
            temp_output_path = self.work_dir / f"audio_{platform}_{video_id}.mp3"
            
            # Végső kimenet a system downloads könyvtárba
            system_output_path = SYSTEM_DOWNLOADS / f"audio_{platform}_{video_id}.mp3"
            
            # yt-dlp használata
            await self.send_progress(20, "Hang letöltése yt-dlp segítségével...")
            
            # yt-dlp opciók a hangletöltéshez
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(temp_output_path),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'noplaylist': True,
                'quiet': False,
                'no_warnings': True,
                'user_agent': random.choice(USER_AGENTS),
                'referer': 'https://www.google.com/',
                'cookiefile': str(self.cookies_dir / "cookies.txt"),
                'nocheckcertificate': True,
                'ignoreerrors': True,
                'geo_bypass': True,
                'geo_bypass_country': 'US',
            }
            
            # Progress hook hozzáadása
            def progress_hook(d):
                if d['status'] == 'downloading':
                    if 'downloaded_bytes' in d and ('total_bytes' in d or 'total_bytes_estimate' in d):
                        total = d.get('total_bytes', d.get('total_bytes_estimate', 0))
                        if total > 0:
                            percent = min(90, 20 + (d['downloaded_bytes'] / total * 60))
                            self.update_progress(percent, f"Hang letöltése: {d.get('_percent_str', '')} ({d.get('_speed_str', '')})")
            
            ydl_opts['progress_hooks'] = [progress_hook]
            
            # yt-dlp futtatása külön szálban
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                def run_yt_dlp():
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([url])
                        return True
                    except Exception as e:
                        logger.error(f"yt-dlp hiba hangletöltésnél: {e}")
                        return False
                        
                success = await loop.run_in_executor(executor, run_yt_dlp)
            
            # Ellenőrizzük, hogy sikerült-e a letöltés
            if success and temp_output_path.exists() and temp_output_path.stat().st_size > 0:
                # Másoljuk át a fájlt a rendszer letöltési mappájába
                try:
                    shutil.copy2(temp_output_path, system_output_path)
                    await self.send_progress(100, "Hang letöltése sikeres!")
                    logger.info(f"[{self.connection_id}] Sikeres hangletöltés: {system_output_path}")
                    return temp_output_path
                except Exception as e:
                    logger.error(f"Hiba a hangfájl másolása közben: {e}")
                    return temp_output_path
            
            logger.error(f"[{self.connection_id}] Nem sikerült letölteni a hangot: {url}")
            return None
        
        except Exception as e:
            logger.error(f"[{self.connection_id}] Hiba a hang letöltése közben: {e}")
            await self.send_progress(100, f"Hiba a hang letöltése közben: {str(e)}")
            return None
    
    async def download_to_system(self, url: str, platform: str = None) -> Optional[Path]:
        """
        Videó letöltése közvetlenül a rendszer letöltési mappájába
        
        Args:
            url: Videó URL
            platform: Platform azonosító (opcionális)
            
        Returns:
            Path: A letöltött videó fájl elérési útja
        """
        try:
            await self.send_progress(10, "Videó letöltésének előkészítése...")
            
            # Platform azonosítása, ha nincs megadva
            if not platform or platform == "auto":
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.lower()
                
                if "youtube.com" in domain or "youtu.be" in domain:
                    platform = "youtube"
                elif "twitter.com" in domain or "x.com" in domain:
                    platform = "twitter"
                elif "facebook.com" in domain or "fb.watch" in domain:
                    platform = "facebook"
                elif "instagram.com" in domain:
                    platform = "instagram"
                elif "tiktok.com" in domain:
                    platform = "tiktok"
                elif "videa.hu" in domain:
                    platform = "videa"
                else:
                    platform = "other"
            
            # Videó ID kinyerése
            video_id = await self.extract_video_id(url, platform)
            
            # Közvetlenül a rendszer downloads mappájába töltünk le
            system_output_path = SYSTEM_DOWNLOADS / f"{platform}_{video_id}.mp4"
            
            # yt-dlp használata
            await self.send_progress(20, "Letöltés yt-dlp segítségével...")
            
            # yt-dlp opciók
            ydl_opts = {
                'format': 'best/bestvideo+bestaudio',
                'outtmpl': str(system_output_path),  # Közvetlenül a rendszer mappába
                'merge_output_format': 'mp4',
                'noplaylist': True,
                'quiet': False,
                'no_warnings': True,
                'user_agent': random.choice(USER_AGENTS),
                'referer': 'https://www.google.com/',
                'cookiefile': str(self.cookies_dir / "cookies.txt"),
                'nocheckcertificate': True,
                'ignoreerrors': True,
                'geo_bypass': True,
                'geo_bypass_country': 'US',
            }
            
            # Progress hook hozzáadása
            def progress_hook(d):
                if d['status'] == 'downloading':
                    if 'downloaded_bytes' in d and ('total_bytes' in d or 'total_bytes_estimate' in d):
                        total = d.get('total_bytes', d.get('total_bytes_estimate', 0))
                        if total > 0:
                            percent = min(95, 20 + (d['downloaded_bytes'] / total * 75))
                            self.update_progress(percent, f"Rendszermappába letöltés: {d.get('_percent_str', '')} ({d.get('_speed_str', '')})")
            
            ydl_opts['progress_hooks'] = [progress_hook]
            
            # yt-dlp futtatása külön szálban
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                def run_yt_dlp():
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([url])
                        return True
                    except Exception as e:
                        logger.error(f"yt-dlp hiba rendszermappába letöltésnél: {e}")
                        return False
                        
                success = await loop.run_in_executor(executor, run_yt_dlp)
            
            # Ellenőrizzük, hogy sikerült-e a letöltés
            if success and system_output_path.exists() and system_output_path.stat().st_size > 0:
                await self.send_progress(100, "Rendszermappába letöltés sikeres!")
                logger.info(f"[{self.connection_id}] Sikeres rendszermappába letöltés: {system_output_path}")
                return system_output_path
            
            logger.error(f"[{self.connection_id}] Nem sikerült a rendszermappába letölteni: {url}")
            return None
        
        except Exception as e:
            logger.error(f"[{self.connection_id}] Hiba a rendszermappába letöltés közben: {e}")
            await self.send_progress(100, f"Hiba a rendszermappába letöltés közben: {str(e)}")
            return None

    async def send_progress(self, progress: float, message: str):
        """Haladás jelzése a manager-en keresztül"""
        if self.manager:
            try:
                await self.manager.send_progress(self.connection_id, progress, message)
            except Exception as e:
                logger.error(f"Error sending progress: {e}")
        else:
            logger.info(f"[{self.connection_id}] Progress {progress:.1f}%: {message}")

    # Ez egy szinkron metódus a thread-ek számára
    def update_progress(self, progress: float, message: str):
        """Szinkron progress frissítés a thread-ekből"""
        with self._progress_lock:
            # Csak akkor küldjünk, ha érdemi változás van
            if progress > self._last_progress + 1 or progress == 100:
                self._last_progress = progress
                # Biztonságos ütemezés az eseményhurokba
                if self.main_loop and self.main_loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.send_progress(progress, message),
                        self.main_loop
                    )

    def create_cookies(self):
        """Speciális cookie-k létrehozása a bot-védelmek megkerüléséhez"""
        cookies_path = self.cookies_dir / "cookies.txt"
        # Cookie-k regenerálása minden alkalommal a frissesség érdekében
        try:
            with open(cookies_path, "w") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write(f"# Generated by VideoDownloader on {time.ctime()}\n")
                
                # YouTube fejlettebb cookie-k bot-detektálás ellen
                current_time = int(time.time())
                expire_time = current_time + 86400
                
                # Alapvető YouTube cookie-k
                f.write(f".youtube.com\tTRUE\t/\tFALSE\t{expire_time}\tPREF\tid=f1=50000000&f6=8&hl=en&gl=US\n")
                f.write(f".youtube.com\tTRUE\t/\tFALSE\t{expire_time}\tCONSENT\tYES+cb.{time.strftime('%Y%m%d', time.gmtime())}-11-p0.en+FX+{str(random.randint(100, 999))}\n")
                
                # Dinamikus session cookie-k
                ysc_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=11))
                visitor_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_', k=26))
                session_token = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_', k=43))
                
                f.write(f".youtube.com\tTRUE\t/\tFALSE\t{expire_time}\tYSC\t{ysc_id}\n")
                f.write(f".youtube.com\tTRUE\t/\tFALSE\t{expire_time}\tVISITOR_INFO1_LIVE\t{visitor_id}\n")
                f.write(f".youtube.com\tTRUE\t/\tFALSE\t{expire_time}\tSIDCC\tAJ{session_token}\n")
                f.write(f".youtube.com\tTRUE\t/\tFALSE\t{expire_time}\t__Secure-1PSID\tg.{session_token}\n")
                f.write(f".youtube.com\tTRUE\t/\tFALSE\t{expire_time}\t__Secure-3PSID\tg.{session_token}\n")
                
                # Időzóna és nyelvi beállítások
                f.write(f".youtube.com\tTRUE\t/\tFALSE\t{expire_time}\tGPS\t1\n")
                f.write(f".youtube.com\tTRUE\t/\tFALSE\t{expire_time}\tNID\t511={(''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_', k=52)))}\n")
                
                # További platformok cookie-jai
                f.write(f".twitter.com\tTRUE\t/\tFALSE\t{expire_time}\tct0\t{(''.join(random.choices('0123456789abcdef', k=32)))}\n")
                f.write(f".facebook.com\tTRUE\t/\tFALSE\t{expire_time}\tdatr\t{(''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_', k=24)))}\n")
                
            logger.info(f"[{self.connection_id}] Cookie fájl létrehozva")
        except Exception as e:
            logger.warning(f"[{self.connection_id}] Hiba a cookie fájl létrehozásakor: {e}")

    async def extract_video_id(self, url: str, platform: str) -> str:
        """Platform-specifikus videó ID kinyerése"""
        try:
            # YouTube videók
            if platform == "youtube":
                patterns = [
                    r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
                    r'(?:shorts\/)([0-9A-Za-z_-]{11}).*',
                    r'(?:youtu\.be\/)([0-9A-Za-z_-]{11}).*'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, url)
                    if match:
                        return match.group(1)
                
                # URL paraméterek ellenőrzése
                parsed = urlparse(url)
                video_id = parse_qs(parsed.query).get("v", [None])[0]
                if video_id:
                    return video_id
            
            # Egyéb platformok
            elif platform == "twitter":
                pattern = r'(?:status|statuses)\/(\d+)'
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
                
            elif platform == "tiktok":
                pattern = r'(?:\/video\/|vm\.tiktok\.com\/)(\d+)'
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
                    
            elif platform == "facebook":
                patterns = [
                    r'(?:\/videos\/|watch\/\?v=)(\d+)',
                    r'(?:videos\/)(\d+)'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, url)
                    if match:
                        return match.group(1)
            
            # Fallback: egyedi azonosító generálása
            return f"{platform}_{int(time.time())}"
        except Exception as e:
            logger.error(f"Hiba a videó ID kinyerésekor: {e}")
            return f"unknown_{int(time.time())}"

    async def download_video(self, url: str, platform: str = None) -> Optional[Path]:
        """
        Fő metódus videó letöltésére
        
        Args:
            url: Videó URL
            platform: Platform azonosító (opcionális)
            
        Returns:
            Path: A letöltött videó fájl elérési útja
        """
        try:
            await self.send_progress(10, "Videó letöltésének előkészítése...")
            
            # Platform azonosítása, ha nincs megadva
            if not platform or platform == "auto":
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.lower()
                
                if "youtube.com" in domain or "youtu.be" in domain:
                    platform = "youtube"
                elif "twitter.com" in domain or "x.com" in domain:
                    platform = "twitter"
                elif "facebook.com" in domain or "fb.watch" in domain:
                    platform = "facebook"
                elif "instagram.com" in domain:
                    platform = "instagram"
                elif "tiktok.com" in domain:
                    platform = "tiktok"
                elif "videa.hu" in domain:
                    platform = "videa"
                else:
                    platform = "other"
            
            # Videó ID kinyerése
            video_id = await self.extract_video_id(url, platform)
            
            # Ideiglenes kimenet a munkakönyvtárba
            temp_output_path = self.work_dir / f"{platform}_{video_id}.mp4"
            
            # Végső kimenet a system downloads könyvtárba
            system_output_path = SYSTEM_DOWNLOADS / f"{platform}_{video_id}.mp4"
            
            # yt-dlp használata (legrobusztusabb megoldás)
            await self.send_progress(20, "Letöltés yt-dlp segítségével...")
            
            # YouTube specifikus yt-dlp beállítások a botelhárítás kivédésére
            if platform == "youtube":
                extra_options = {
                    'cookiefile': str(self.cookies_dir / "cookies.txt"),
                    'nocheckcertificate': True,
                    'ignoreerrors': True,
                    'geo_bypass': True,
                    'geo_bypass_country': 'US',
                    'sleep_interval': 2,
                    'max_sleep_interval': 10,
                    'sleep_interval_subtitles': 1,
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android', 'web', 'tv_embedded', 'mweb'],
                            'player_skip': ['webpage', 'js'],
                            'innertube_host': 'youtubei.googleapis.com',
                            'skip': ['hls', 'dash'],
                        }
                    },
                    'http_headers': {
                        'User-Agent': random.choice(USER_AGENTS),
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                    }
                }
            else:
                extra_options = {}
            
            # yt-dlp opciók
            ydl_opts = {
                'format': 'best/bestvideo+bestaudio',
                'outtmpl': str(temp_output_path),  # Ideiglenes fájlhelyre mentünk először
                'merge_output_format': 'mp4',
                'noplaylist': True,
                'quiet': False,
                'no_warnings': True,
                'user_agent': random.choice(USER_AGENTS),
                'referer': 'https://www.google.com/',
                **extra_options
            }
            
            # Progress hook hozzáadása - JAVÍTOTT VERZIÓ
            def progress_hook(d):
                if d['status'] == 'downloading':
                    if 'downloaded_bytes' in d and ('total_bytes' in d or 'total_bytes_estimate' in d):
                        total = d.get('total_bytes', d.get('total_bytes_estimate', 0))
                        if total > 0:
                            percent = min(90, 20 + (d['downloaded_bytes'] / total * 60))
                            # Ez a thread-biztos verzió
                            self.update_progress(percent, f"Letöltés: {d.get('_percent_str', '')} ({d.get('_speed_str', '')})")
            
            ydl_opts['progress_hooks'] = [progress_hook]
            
            # yt-dlp futtatása külön szálban exponenciális visszalépéssel
            loop = asyncio.get_event_loop()
            max_retries = 3
            base_delay = 5
            
            success = False
            for attempt in range(max_retries):
                with ThreadPoolExecutor() as executor:
                    def run_yt_dlp():
                        try:
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                ydl.download([url])
                            return True
                        except Exception as e:
                            error_msg = str(e).lower()
                            # Specifikus bot detection hibák kezelése
                            if any(keyword in error_msg for keyword in ['sign in', 'bot', 'captcha', 'verification']):
                                logger.warning(f"Bot detection attempt {attempt + 1}: {e}")
                                # Regeneráljuk a cookie-kat
                                self.create_cookies()
                            else:
                                logger.error(f"yt-dlp hiba attempt {attempt + 1}: {e}")
                            return False
                            
                    success = await loop.run_in_executor(executor, run_yt_dlp)
                
                if success:
                    break
                elif attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(1, 3)
                    await self.send_progress(25 + attempt * 5, f"Újrapróbálkozás {delay:.1f} másodperc múlva...")
                    await asyncio.sleep(delay)
            
            # Ellenőrizzük, hogy sikerült-e a letöltés
            if success and temp_output_path.exists() and temp_output_path.stat().st_size > 0:
                # Másoljuk át a fájlt a rendszer letöltési mappájába
                try:
                    shutil.copy2(temp_output_path, system_output_path)
                    await self.send_progress(100, "Letöltés sikeres!")
                    logger.info(f"[{self.connection_id}] Sikeres letöltés: {system_output_path}")
                    # Return temp_output_path instead of system_output_path to match expectations in video_processor.py
                    return temp_output_path
                except Exception as e:
                    logger.error(f"Hiba a fájl másolása közben: {e}")
                    # Ha nem sikerül a másolás, visszaadjuk az eredeti fájlt
                    return temp_output_path
            
            # Ha nem sikerült a retry-okkal, próbáljunk Railway-specifikus egyszerű konfigurációval
            if not success:
                await self.send_progress(50, "Railway-specifikus letöltési kísérlet...")
                
                # Minimális konfiguráció Railway szerverre
                simple_ydl_opts = {
                    'format': 'worst/best',  # Kisebb fájl Railway-re
                    'outtmpl': str(temp_output_path),
                    'noplaylist': True,
                    'quiet': True,
                    'no_warnings': True,
                    'ignoreerrors': True,
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android'],  # Csak Android client
                        }
                    }
                }
                
                with ThreadPoolExecutor() as executor:
                    def run_simple_yt_dlp():
                        try:
                            with yt_dlp.YoutubeDL(simple_ydl_opts) as ydl:
                                ydl.download([url])
                            return True
                        except Exception as e:
                            logger.warning(f"Simple yt-dlp failed: {e}")
                            return False
                            
                    success = await loop.run_in_executor(executor, run_simple_yt_dlp)
                
                if success and temp_output_path.exists() and temp_output_path.stat().st_size > 0:
                    try:
                        shutil.copy2(temp_output_path, system_output_path)
                        await self.send_progress(100, "Letöltés sikeres (egyszerű mód)!")
                        logger.info(f"[{self.connection_id}] Sikeres egyszerű letöltés: {system_output_path}")
                        return temp_output_path
                    except Exception as e:
                        logger.error(f"Hiba a fájl másolása közben: {e}")
                        return temp_output_path
            
            # Ha még mindig nem sikerült, próbáljuk meg parancssorból futtatni yt-dlp
            await self.send_progress(60, "Letöltés alternatív módon...")
            
            # Alapvető parancs összeállítása
            cmd = [
                "yt-dlp",
                "-f", "best/bestvideo+bestaudio",
                "-o", str(temp_output_path),
                "--no-playlist",
                "--cookies", str(self.cookies_dir / "cookies.txt"),
                "--user-agent", random.choice(USER_AGENTS),
                "--referer", "https://www.google.com/",
                "--no-check-certificate",
                "--geo-bypass",
                "--force-ipv4"
            ]
            
            # YouTube-specifikus paraméterek
            if platform == "youtube":
                cmd.extend([
                    "--extractor-args", "youtube:player_client=android,web",
                    "--extractor-args", "youtube:player_skip=webpage,js"
                ])
            
            # URL hozzáadása (utolsó paraméter)
            cmd.append(url)
            
            # Parancs futtatása
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Ellenőrizzük ismét a kimeneti fájlt
            if temp_output_path.exists() and temp_output_path.stat().st_size > 0:
                # Másoljuk át a fájlt a rendszer letöltési mappájába
                try:
                    shutil.copy2(temp_output_path, system_output_path)
                    await self.send_progress(100, "Letöltés sikeres!")
                    logger.info(f"[{self.connection_id}] Sikeres letöltés parancssorból: {system_output_path}")
                    # Return temp_output_path instead of system_output_path to match expectations in video_processor.py
                    return temp_output_path
                except Exception as e:
                    logger.error(f"Hiba a fájl másolása közben: {e}")
                    # Ha nem sikerül a másolás, visszaadjuk az eredeti fájlt
                    return temp_output_path
            
            # Ha még mindig nem sikerült, megpróbálunk közvetlenül letölteni egy alternatív megoldással
            await self.send_progress(80, "Végső letöltési kísérlet...")
            
            # Itt egy egyszerűbb megoldással próbálkozunk
            try:
                final_cmd = [
                    "yt-dlp",  # Modern eszköz Railway szerveren
                    "-f", "best",
                    "-o", str(temp_output_path),
                    "--no-check-certificate",
                    "--extractor-args", "youtube:player_client=android",
                    "--user-agent", random.choice(USER_AGENTS),
                    "--cookies", str(self.cookies_dir / "cookies.txt"),
                    url
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *final_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if temp_output_path.exists() and temp_output_path.stat().st_size > 0:
                    # Másoljuk át a fájlt a rendszer letöltési mappájába
                    try:
                        shutil.copy2(temp_output_path, system_output_path)
                        await self.send_progress(100, "Letöltés sikeres!")
                        logger.info(f"[{self.connection_id}] Sikeres letöltés alternatív módszerrel: {system_output_path}")
                        # Return temp_output_path instead of system_output_path to match expectations in video_processor.py
                        return temp_output_path
                    except Exception as e:
                        logger.error(f"Hiba a fájl másolása közben: {e}")
                        # Ha nem sikerül a másolás, visszaadjuk az eredeti fájlt
                        return temp_output_path
            except Exception as e:
                logger.error(f"Végső letöltési hiba: {e}")
            
            # Ha nem sikerült semmilyen módszerrel
            logger.error(f"[{self.connection_id}] Sikertelen letöltés: {url}")
            await self.send_progress(100, "Sikertelen letöltés")
            return None
            
        except Exception as e:
            logger.error(f"[{self.connection_id}] Videó letöltési hiba: {e}")
            await self.send_progress(100, f"Hiba: {str(e)}")
            return None
    
    async def cleanup(self):
        """Ideiglenes fájlok törlése"""
        try:
            if self.work_dir.exists():
                logger.info(f"[{self.connection_id}] Ideiglenes fájlok törlése: {self.work_dir}")
                shutil.rmtree(str(self.work_dir), ignore_errors=True)
        except Exception as e:
            logger.warning(f"[{self.connection_id}] Cleanup hiba: {e}")
