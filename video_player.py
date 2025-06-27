import os
import json
import logging
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel
import subprocess
import shutil

# MediaStreamInfo osztály a stream információk kezeléséhez
class MediaStreamInfo(BaseModel):
    video_streams: List[Dict[str, Any]] = []
    audio_streams: List[Dict[str, Any]] = []
    subtitle_streams: List[Dict[str, Any]] = []
    chapters: List[Dict[str, Any]] = []
    format_info: Dict[str, Any] = {}

class VideoPlayerService:
    """Videólejátszással és -feldolgozással kapcsolatos szolgáltatások - LEOPARD FINAL EDITION"""
    
    def __init__(self, upload_dir: Path, converted_dir: Path, hls_dir: Path, 
                 gpu_accelerator, videos_db: Dict[str, Any], logger):
        self.UPLOAD_DIR = upload_dir
        self.CONVERTED_DIR = converted_dir
        self.HLS_DIR = hls_dir
        self.gpu_accelerator = gpu_accelerator
        self.videos_db = videos_db
        self.logger = logger
        
        # Inicializáljuk a LEOPARD beállításokat
        self._init_leopard_mode()
        
        self.logger.info(f"VideoPlayerService inicializálva LEOPARD FINAL EDITION módban")
    
    def _init_leopard_mode(self):
        """LEOPARD II A7+ mód inicializálása - GPU optimalizációk"""
        self.logger.info("🔥🔥🔥 LEOPARD II FINAL EDITION AKTIVÁLVA! 🔥🔥🔥")
        
        # CPU információk
        self.cpu_cores = os.cpu_count() or 4
        
        # GPU detektálása és optimális beállítások
        gpu_type = self.gpu_accelerator.gpu_type["type"]
        gpu_name = self.gpu_accelerator.gpu_type["name"]
        
        # NVIDIA GPU specifikus optimalizáció
        if gpu_type == "nvidia":
            self.logger.info(f"💥 NVIDIA {gpu_name} LEOPARD TURBO ÜZEMMÓDBA KAPCSOLVA!")
            
            # NVIDIA-specifikus encoder beállítások - JAVÍTOTT PARAMÉTEREK
            self.leopard_settings = {
                "encoder": "-c:v h264_nvenc -preset p1 -tune ll -rc constqp -qp 28 -bf 0 -b_adapt 0 -spatial_aq 0 -temporal_aq 0 -sc_threshold 0 -zerolatency 1 -surfaces 32 -threads 8",
                "hwaccel": "-hwaccel cuda -hwaccel_output_format cuda"
            }
            
        # Intel QSV optimalizáció
        elif gpu_type == "intel":
            self.logger.info(f"💥 INTEL {gpu_name} LEOPARD ÜZEMMÓDBA KAPCSOLVA!")
            
            # Intel-specifikus beállítások
            self.leopard_settings = {
                "encoder": "-c:v h264_qsv -preset veryfast -look_ahead 0 -global_quality 28 -async_depth 6",
                "hwaccel": "-hwaccel qsv -hwaccel_output_format qsv"
            }
        
        # AMD GPU optimalizáció
        elif gpu_type == "amd":
            self.logger.info(f"💥 AMD {gpu_name} LEOPARD ÜZEMMÓDBA KAPCSOLVA!")
            
            # AMD-specifikus beállítások
            self.leopard_settings = {
                "encoder": "-c:v h264_amf -quality speed -usage transcoding -rc constqp -qp 28 -header_insertion_mode none",
                "hwaccel": "-hwaccel amf -hwaccel_output_format amf"
            }
        
        # CPU fallback, de még így is optimalizálva a sebességre
        else:
            self.logger.info("⚡ CPU-ALAPÚ LEOPARD ÜZEMMÓD AKTIVÁLVA!")
            
            # CPU-specifikus beállítások - maximálisan kihasználjuk a processzormagokat
            self.leopard_settings = {
                "encoder": f"-c:v libx264 -preset ultrafast -tune fastdecode,zerolatency -crf 28 -threads {self.cpu_cores} -flags +low_delay -sc_threshold 0 -profile:v baseline",
                "hwaccel": ""
            }
    
    def get_video_duration(self, file_path):
        """Get video duration using ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path)
            ]
            output = subprocess.check_output(cmd).decode("utf-8").strip()
            return float(output)
        except Exception as e:
            self.logger.error(f"Error getting duration: {e}")
            return None

    def generate_thumbnail(self, video_path, output_path, time_offset="00:00:05"):
        """Generate thumbnail for video using ffmpeg."""
        try:
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-i", str(video_path),
                "-ss", time_offset,
                "-vframes", "1",
                "-vf", "scale='min(640,iw):-1'",  # Méretezés, de max 640px széles
                "-y",
                str(output_path)
            ]
            subprocess.run(cmd, check=True)
            return True
        except Exception as e:
            self.logger.error(f"Error generating thumbnail: {e}")
            return False

    def is_web_compatible(self, file_extension):
        """Check if the file format is already web compatible."""
        return file_extension.lower() in ['mp4', 'webm']
    
    async def get_media_streams(self, file_path: str) -> MediaStreamInfo:
        """Detektálja a videó, audio és felirat stream-eket egy médiafájlban"""
        try:
            # FFprobe parancs a médiafolyamok lekérdezéséhez JSON formátumban
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                "-show_chapters",
                str(file_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"FFprobe error: {stderr.decode() if stderr else 'Unknown error'}")
                return MediaStreamInfo()
            
            # JSON eredmény feldolgozása
            media_info = json.loads(stdout.decode())
            
            result = MediaStreamInfo(
                format_info=media_info.get("format", {})
            )
            
            # Streamek szétválogatása típus szerint
            for stream in media_info.get("streams", []):
                codec_type = stream.get("codec_type", "")
                
                # Alapvető metadatok hozzáadása
                stream_info = {
                    "index": stream.get("index"),
                    "codec_name": stream.get("codec_name"),
                    "codec_long_name": stream.get("codec_long_name"),
                    "language": stream.get("tags", {}).get("language", "und"),
                    "title": stream.get("tags", {}).get("title", f"Stream {stream.get('index')}")
                }
                
                # Stream típusonkénti feldolgozás
                if codec_type == "video":
                    stream_info.update({
                        "width": stream.get("width"),
                        "height": stream.get("height"),
                        "fps": eval(stream.get("r_frame_rate", "0/1")) if stream.get("r_frame_rate") else 0,
                        "bit_rate": stream.get("bit_rate")
                    })
                    result.video_streams.append(stream_info)
                    
                elif codec_type == "audio":
                    stream_info.update({
                        "channels": stream.get("channels", 0),
                        "sample_rate": stream.get("sample_rate"),
                        "bit_rate": stream.get("bit_rate")
                    })
                    result.audio_streams.append(stream_info)
                    
                elif codec_type == "subtitle":
                    result.subtitle_streams.append(stream_info)
            
            # Fejezetek feldolgozása
            result.chapters = media_info.get("chapters", [])
            
            return result
                
        except Exception as e:
            self.logger.error(f"Error detecting media streams: {e}")
            return MediaStreamInfo()
    
    async def extract_subtitle_to_vtt(self, file_path, stream_index, output_path):
        """Felirat kinyerése és konvertálása WebVTT formátumba"""
        try:
            cmd = [
                "ffmpeg",
                "-i", str(file_path),
                "-map", f"0:s:{stream_index}",
                "-c:s", "webvtt",
                str(output_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            return process.returncode == 0
        except Exception as e:
            self.logger.error(f"Error converting subtitle: {e}")
            return False
    
    async def add_subtitles_to_master_playlist(self, master_playlist_path, subtitle_streams):
        """Feliratok hozzáadása a master playlisthez"""
        try:
            # Eredeti playlist beolvasása
            with open(master_playlist_path, "r") as f:
                content = f.read()
            
            # Felirat bejegyzések generálása
            subtitle_entries = []
            for stream in subtitle_streams:
                subtitle_entries.append(f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="{stream.get("title", "Unknown")}",LANGUAGE="{stream.get("language", "und")}",URI="subtitle_{stream["index"]}/subtitles.vtt"')
            
            # Bejegyzések hozzáadása a playlist végéhez
            content += "\n" + "\n".join(subtitle_entries)
            
            # Módosított playlist visszaírása
            with open(master_playlist_path, "w") as f:
                f.write(content)
                
            return True
        except Exception as e:
            self.logger.error(f"Error modifying master playlist: {e}")
            return False
    
    async def create_direct_copy_hls(self, video_id: str, file_path: str, video_info: MediaStreamInfo) -> str:
        """Ultra gyors HLS létrehozás Stream Copy módszerrel kompatibilis formátumokhoz"""
        try:
            start_time = time.time()
            self.logger.info(f"🚄 STREAM COPY MÓD INDÍTÁSA: {video_id}")
            
            # HLS könyvtár létrehozása
            video_hls_dir = self.HLS_DIR / video_id
            video_hls_dir.mkdir(exist_ok=True)
            
            # Alapértelmezett képméret
            width = 1920
            height = 1080
            
            # Ha van videó stream, kivesszük a felbontást
            if video_info.video_streams:
                first_video = video_info.video_streams[0]
                width = first_video.get("width", 1920)
                height = first_video.get("height", 1080)
            
            # Közvetlen stream copy parancs
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "warning",
                "-i", str(file_path),
                "-c:v", "copy",       # Videó stream másolása
                "-c:a", "copy",       # Audio stream másolása
                "-hls_time", "4",
                "-hls_list_size", "0",
                "-hls_playlist_type", "vod",
                "-hls_segment_type", "mpegts",
                "-hls_flags", "independent_segments+split_by_time",
                "-hls_segment_filename", f"{video_hls_dir}/segment_%03d.ts",
                "-f", "hls",
                f"{video_hls_dir}/playlist.m3u8",
                "-y"
            ]
            
            self.logger.info(f"STREAM COPY PARANCS: {' '.join(map(str, cmd))}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Log only on error
            if process.returncode != 0:
                self.logger.error(f"Stream copy hiba: {stderr.decode()}")
                return None
            
            # Master playlist létrehozása
            master_playlist_path = video_hls_dir / "master.m3u8"
            with open(master_playlist_path, "w") as f:
                f.write(f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION={width}x{height}
playlist.m3u8
""")
            
            # Feliratok hozzáadása a master playlisthez
            if video_info.subtitle_streams:
                # Feliratok mappáinak létrehozása és konvertálás
                for stream in video_info.subtitle_streams:
                    subtitle_dir = video_hls_dir / f"subtitle_{stream['index']}"
                    subtitle_dir.mkdir(exist_ok=True)
                    
                    # Felirat konvertálása WebVTT formátumba
                    await self.extract_subtitle_to_vtt(file_path, stream['index'], subtitle_dir / "subtitles.vtt")
                
                await self.add_subtitles_to_master_playlist(master_playlist_path, video_info.subtitle_streams)
            
            # Sikeres feldolgozás időmérése
            end_time = time.time()
            processing_time = end_time - start_time
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)  # MB-ban
            speed_mbps = file_size_mb / processing_time if processing_time > 0 else 0
            
            self.logger.info(f"🔥 STREAM COPY BEFEJEZVE: {video_id}")
            self.logger.info(f"⏱️ STREAM COPY IDŐ: {processing_time:.2f} másodperc")
            self.logger.info(f"🚀 STREAM COPY SEBESSÉG: {speed_mbps:.2f} MB/s")
            
            return f"/hls/{video_id}/master.m3u8"
            
        except Exception as e:
            self.logger.error(f"Stream copy hiba: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    async def create_turbo_hls(self, video_id: str, file_path: str, video_info: MediaStreamInfo) -> str:
        """TURBO ÜZEMMÓD: Gyorsított HLS készítés GPU-val (vagy optimalizált CPU parancsokkal)"""
        try:
            start_time = time.time()
            self.logger.info(f"🔥 TURBO MÓD INDÍTÁSA: {video_id}")
            
            # HLS könyvtár létrehozása
            video_hls_dir = self.HLS_DIR / video_id
            video_hls_dir.mkdir(exist_ok=True)
            
            # Alapértelmezett képméret
            width = 1920
            height = 1080
            
            # Ha van videó stream, kivesszük a felbontást
            if video_info.video_streams:
                first_video = video_info.video_streams[0]
                width = first_video.get("width", 1920)
                height = first_video.get("height", 1080)
            
            # Optimalizált ffmpeg parancs összeállítása GPU gyorsítással
            cmd_parts = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]
            
            # GPU gyorsítás hozzáadása, ha van
            if self.leopard_settings["hwaccel"]:
                cmd_parts.extend(self.leopard_settings["hwaccel"].split())
            
            # Input fájl
            cmd_parts.extend(["-i", str(file_path)])
            
            # Mappeljük az első videó- és az összes audiostreamt
            cmd_parts.extend(["-map", "0:v:0"])  # Első videó stream
            
            for i in range(len(video_info.audio_streams)):
                cmd_parts.extend(["-map", f"0:a:{i}"])  # Audio streamek
            
            # Encoder beállítások hozzáadása
            cmd_parts.extend(self.leopard_settings["encoder"].split())
            
            # Audio beállítások
            cmd_parts.extend(["-c:a", "aac", "-b:a", "192k"])
            
            # Seeking javításához
            cmd_parts.extend([
                "-force_key_frames", "expr:gte(t,n_forced*2)",  # 2 másodpercenként kulcsképkocka
                "-g", "48",                # GOP méret
                "-keyint_min", "48",       # Minimális kulcskép távolság
            ])
            
            # HLS beállítások
            cmd_parts.extend([
                "-hls_time", "4",
                "-hls_list_size", "0",
                "-hls_playlist_type", "vod",
                "-hls_segment_type", "mpegts",
                "-hls_flags", "independent_segments+split_by_time",
                "-hls_segment_filename", f"{video_hls_dir}/segment_%03d.ts",
                "-f", "hls",
                f"{video_hls_dir}/playlist.m3u8",
                "-y"
            ])
            
            self.logger.info(f"TURBO MÓD PARANCS: {' '.join(map(str, cmd_parts))}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd_parts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Log only on error
            if process.returncode != 0:
                self.logger.error(f"TURBO mód hiba: {stderr.decode()}")
                return None
            
            # Master playlist létrehozása
            master_playlist_path = video_hls_dir / "master.m3u8"
            with open(master_playlist_path, "w") as f:
                f.write(f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION={width}x{height}
playlist.m3u8
""")
            
            # Feliratok hozzáadása a master playlisthez
            if video_info.subtitle_streams:
                # Feliratok mappáinak létrehozása és konvertálás
                for stream in video_info.subtitle_streams:
                    subtitle_dir = video_hls_dir / f"subtitle_{stream['index']}"
                    subtitle_dir.mkdir(exist_ok=True)
                    
                    # Felirat konvertálása WebVTT formátumba
                    await self.extract_subtitle_to_vtt(file_path, stream['index'], subtitle_dir / "subtitles.vtt")
                
                await self.add_subtitles_to_master_playlist(master_playlist_path, video_info.subtitle_streams)
            
            # Sikeres feldolgozás időmérése
            end_time = time.time()
            processing_time = end_time - start_time
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)  # MB-ban
            speed_mbps = file_size_mb / processing_time if processing_time > 0 else 0
            
            self.logger.info(f"🔥 TURBO MÓD BEFEJEZVE: {video_id}")
            self.logger.info(f"⏱️ TURBO MÓD IDŐ: {processing_time:.2f} másodperc")
            self.logger.info(f"🚀 TURBO MÓD SEBESSÉG: {speed_mbps:.2f} MB/s")
            
            return f"/hls/{video_id}/master.m3u8"
            
        except Exception as e:
            self.logger.error(f"TURBO mód hiba: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    async def create_preview_hls(self, video_id: str, file_path: str, original_format: str) -> Optional[str]:
        """3 perces előnézeti HLS létrehozása azonnali lejátszáshoz"""
        try:
            self.logger.info(f"⚡ ELŐNÉZETI HLS LÉTREHOZÁSA: {video_id}")
            
            # HLS könyvtár létrehozása
            preview_dir = self.HLS_DIR / f"{video_id}_preview"
            preview_dir.mkdir(exist_ok=True)
            
            # A leggyorsabb ultrafast preset használata
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "warning",
                "-i", str(file_path),
                "-t", "180",  # 3 perc
                "-map", "0:v:0",   # Első videó stream
                "-map", "0:a:0?",  # Első audio stream (opcionális)
                "-c:v", "libx264", # CPU-alapú kodek a sebességért
                "-preset", "ultrafast", # Leggyorsabb preset
                "-crf", "26",      # Kicsit alacsonyabb minőség a sebességért
                "-c:a", "aac",
                "-b:a", "96k",     # Alacsonyabb audio bitráta
                "-hls_time", "4",
                "-hls_list_size", "0",
                "-hls_playlist_type", "vod",
                "-hls_segment_filename", f"{preview_dir}/segment_%03d.ts",
                "-f", "hls",
                f"{preview_dir}/playlist.m3u8",
                "-y"
            ]
            
            self.logger.info(f"ELŐNÉZET PARANCS: {' '.join(map(str, cmd))}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"Előnézet FFmpeg hiba: {stderr.decode()}")
                return None
            
            playlist_path = preview_dir / "playlist.m3u8"
            if process.returncode == 0 and playlist_path.exists():
                # Master playlist létrehozása
                master_playlist_path = preview_dir / "master.m3u8"
                with open(master_playlist_path, "w") as f:
                    f.write("""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=854x480
playlist.m3u8
""")
                
                self.logger.info(f"Előnézeti HLS sikeresen létrehozva: {video_id}")
                return f"/hls/{video_id}_preview/master.m3u8"
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Előnézet létrehozási hiba: {e}")
            return None

    async def convert_video(self, video_id: str, file_path: str, original_format: str):
        """Ultra-optimalizált videó feldolgozás - LEOPARD FINAL EDITION"""
        try:
            self.logger.info(f"⚡⚡⚡ LEOPARD FINAL FELDOLGOZÁS INDUL: {video_id}, formátum: {original_format} ⚡⚡⚡")
            
            # Állítsuk be az útvonalakat
            thumbnail_path = self.CONVERTED_DIR / f"{video_id}_thumb.jpg"
            
            # Kezdeti státusz: feldolgozás alatt
            self.videos_db[video_id]["status"] = "processing"
            
            # Azonnali párhuzamos indítás:
            # 1. Thumbnail generálás külön háttérben
            thumbnail_future = asyncio.create_task(asyncio.to_thread(
                self.generate_thumbnail, file_path, thumbnail_path
            ))
            
            # 2. Media streams információk lekérése a feldolgozáshoz
            media_info = await self.get_media_streams(file_path)
            
            # 3. Előnézeti HLS indítása azonnal
            preview_future = asyncio.create_task(
                self.create_preview_hls(video_id, file_path, original_format)
            )
            
            # 4. Teljes verzió feldolgozása közvetlenül stream copy vagy egyszerű GPU paranccsal
            if self.is_web_compatible(original_format):
                # MP4/WebM esetén gyors stream copy - azonnali másolt verzió
                main_future = asyncio.create_task(
                    self.create_direct_copy_hls(video_id, file_path, media_info)
                )
            else:
                # MKV/AVI esetén turbo feldolgozás - egyszerű GPU kódolás
                main_future = asyncio.create_task(
                    self.create_turbo_hls(video_id, file_path, media_info)
                )
            
            # Előnézeti verzió kész, frissítsük azonnal a státuszt
            preview_hls_url = await preview_future
            if preview_hls_url:
                self.videos_db[video_id]["status"] = "preview_ready"
                self.videos_db[video_id]["preview_hls_url"] = preview_hls_url
                self.videos_db[video_id]["thumbnail"] = f"/api/thumbnails/{video_id}" if os.path.exists(thumbnail_path) else None
                self.videos_db[video_id]["duration"] = self.get_video_duration(file_path)
                self.logger.info(f"✅ ELŐNÉZET KÉSZ: {video_id}")
            
            # Thumbnail kész, ha még nincs beállítva
            await thumbnail_future
            if os.path.exists(thumbnail_path) and not self.videos_db[video_id].get("thumbnail"):
                self.videos_db[video_id]["thumbnail"] = f"/api/thumbnails/{video_id}"
            
            # Teljes videó feldolgozás eredménye
            hls_url = await main_future
            
            # Stream információk eltárolása
            self.videos_db[video_id]["stream_info"] = {
                "audio_streams": len(media_info.audio_streams),
                "subtitle_streams": len(media_info.subtitle_streams),
                "video_streams": len(media_info.video_streams)
            }
            
            # Adatbázis frissítése az eredményekkel
            if hls_url:
                self.videos_db[video_id]["status"] = "ready"
                self.videos_db[video_id]["web_compatible"] = True
                self.videos_db[video_id]["hls_url"] = hls_url
                self.videos_db[video_id]["duration"] = self.get_video_duration(file_path)
                self.logger.info(f"✅ TELJES VIDEÓ FELDOLGOZÁS SIKERES: {video_id}, HLS URL: {hls_url}")
            else:
                # Még HLS hiba esetén is ready állapotba állítjuk, ha van előnézet
                if self.videos_db[video_id]["status"] != "ready":
                    self.videos_db[video_id]["status"] = "ready" if preview_hls_url else "error"
                self.logger.warning(f"⚠️ HLS HIBA: {video_id}, de előnézet vagy direkt streamelés elérhető")
                    
        except Exception as e:
            self.videos_db[video_id]["status"] = "error"
            self.logger.error(f"Feldolgozási hiba: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
