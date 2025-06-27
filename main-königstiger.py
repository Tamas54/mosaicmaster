import os
import json
import shutil
import tempfile
import subprocess
from typing import List, Dict, Any, Optional, Union
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging
from pathlib import Path
import uuid
import asyncio
import time
from datetime import datetime

# GPU Gyorsító importálása
from gpu_acceleration import GPUAccelerator

# Élő stream kezelő importálása
from live_stream_handler import live_stream_handler, StreamSource, StreamInfo

# Videó lejátszó szolgáltatás importálása
from video_player import VideoPlayerService

# Videó letöltő importálása
from videodownloader import VideoDownloader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("konigstiger.log")
    ]
)

# Globális logszint beállítása a jobb debug-olhatóságért
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Königstiger Video Streaming API")

# Configure CORS to allow frontend to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Globális GPU gyorsító példány létrehozása
gpu_accelerator = GPUAccelerator()
logger.info(f"Video acceleration using: {gpu_accelerator.gpu_type['name']} with encoder: {gpu_accelerator.gpu_type['encoder']}")

# Create storage directories
UPLOAD_DIR = Path("uploads")
CONVERTED_DIR = Path("converted")
HLS_DIR = Path("hls")
STATIC_DIR = Path("static")
UPLOAD_DIR.mkdir(exist_ok=True)
CONVERTED_DIR.mkdir(exist_ok=True)
HLS_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
Path("recordings").mkdir(exist_ok=True)

# VideoPlayerService inicializálása
video_player_service = VideoPlayerService(
    upload_dir=UPLOAD_DIR,
    converted_dir=CONVERTED_DIR,
    hls_dir=HLS_DIR,
    gpu_accelerator=gpu_accelerator,
    videos_db={},  # Üres kezdeti érték, a valós értéket később adjuk át
    logger=logger
)

# Másold a frontend fájlokat a static könyvtárba
try:
    # Fő index oldal
    with open(STATIC_DIR / "index.html", "w", encoding="utf-8") as f:
        with open("index.html", "r", encoding="utf-8") as source:
            f.write(source.read())
    
    # Videólejátszó oldal létrehozása
    with open(STATIC_DIR / "video-player.html", "w", encoding="utf-8") as f:
        with open("video-player.html", "r", encoding="utf-8") as source:
            f.write(source.read())
    
    # Élő közvetítések oldal létrehozása
    with open(STATIC_DIR / "live-streams.html", "w", encoding="utf-8") as f:
        with open("live-streams.html", "r", encoding="utf-8") as source:
            f.write(source.read())
except Exception as e:
    logger.error(f"Hiba a frontend másolása közben: {e}")

# Models for API - FRISSÍTVE a preview_hls_url és source_url mezőkkel
class VideoInfo(BaseModel):
    id: str
    filename: str
    original_format: str
    status: str
    duration: Optional[float] = None
    thumbnail: Optional[str] = None
    web_compatible: bool = False
    hls_url: Optional[str] = None
    preview_hls_url: Optional[str] = None  # Előnézeti verzió URL
    full_hls_url: Optional[str] = None
    stream_info: Optional[Dict[str, Any]] = None
    source_url: Optional[str] = None  # Forrás URL letöltött videóknál
    error_message: Optional[str] = None  # Hibaüzenet hiba esetén

class VideoList(BaseModel):
    videos: List[VideoInfo]

# Stream API modellek
class AddStreamRequest(BaseModel):
    url: str
    proxy_mode: bool = False  # True = FFmpeg-proxy, False = natív embed

class StreamResponse(BaseModel):
    id: str
    url: str
    type: str
    title: Optional[str] = None
    status: str
    is_live: bool
    embed_url: Optional[str] = None
    proxy_url: Optional[str] = None
    is_recording: bool = False
    
# Videó letöltés API model
class VideoDownloadRequest(BaseModel):
    url: str
    platform: Optional[str] = "auto"  # auto, youtube, twitter, facebook, instagram, tiktok, videa, stb.

# Media streams model
class MediaStreamInfo(BaseModel):
    video_streams: List[Dict[str, Any]] = []
    audio_streams: List[Dict[str, Any]] = []
    subtitle_streams: List[Dict[str, Any]] = []
    chapters: List[Dict[str, Any]] = []
    format_info: Dict[str, Any] = {}

# In-memory database (replace with a real DB in production)
videos_db = {}

# Videó adatbázis átadása a service-nek
video_player_service.videos_db = videos_db

# HTML fájlok kiszolgálása
@app.get("/")
async def read_root():
    """Serve the main HTML page."""
    try:
        with open(STATIC_DIR / "index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Frissítsük a STATIC_DIR és a HTML fájl tartalmát is
        try:
            with open("index.html", "r", encoding="utf-8") as source:
                updated_content = source.read()
                
            # Első betöltésnél frissítsük a HTML-t
            with open(STATIC_DIR / "index.html", "w", encoding="utf-8") as f:
                f.write(updated_content)
            
            return HTMLResponse(content=updated_content)
        except:
            # Ha nincs forrásfájl, használjuk a már meglévőt
            return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"Hiba a főoldal kiszolgálása közben: {e}")
        return {"message": "Hiba a főoldal betöltése közben"}

@app.get("/video-player.html")
async def read_video_player():
    """Serve the video player HTML page."""
    try:
        with open(STATIC_DIR / "video-player.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Frissítsük a STATIC_DIR és a HTML fájl tartalmát is
        try:
            with open("video-player.html", "r", encoding="utf-8") as source:
                updated_content = source.read()
                
            # Első betöltésnél frissítsük a HTML-t
            with open(STATIC_DIR / "video-player.html", "w", encoding="utf-8") as f:
                f.write(updated_content)
            
            return HTMLResponse(content=updated_content)
        except:
            # Ha nincs forrásfájl, használjuk a már meglévőt
            return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"Hiba a videólejátszó oldal kiszolgálása közben: {e}")
        return {"message": "Hiba a videólejátszó oldal betöltése közben"}

@app.get("/live-streams.html")
async def read_live_streams():
    """Serve the live streams HTML page."""
    try:
        with open(STATIC_DIR / "live-streams.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Frissítsük a STATIC_DIR és a HTML fájl tartalmát is
        try:
            with open("live-streams.html", "r", encoding="utf-8") as source:
                updated_content = source.read()
                
            # Első betöltésnél frissítsük a HTML-t
            with open(STATIC_DIR / "live-streams.html", "w", encoding="utf-8") as f:
                f.write(updated_content)
            
            return HTMLResponse(content=updated_content)
        except:
            # Ha nincs forrásfájl, használjuk a már meglévőt
            return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"Hiba az élő közvetítések oldal kiszolgálása közben: {e}")
        return {"message": "Hiba az élő közvetítések oldal betöltése közben"}

# Videó API végpontok
@app.post("/api/upload", response_model=VideoInfo)
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload a video file."""
    # Validate file extension
    filename = file.filename
    file_extension = filename.split(".")[-1].lower()
    
    if file_extension not in ["avi", "mkv", "mp4", "webm"]:
        raise HTTPException(
            status_code=400, 
            detail="Unsupported file format. Only AVI, MKV, MP4, and WebM are supported."
        )
    
    logger.info(f"Uploading file: {filename} with extension {file_extension}")
    
    # Save uploaded file
    video_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{video_id}.{file_extension}"
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()
    
    logger.info(f"File saved to {file_path}, size: {os.path.getsize(file_path)} bytes")
    
    # Generate thumbnail
    thumbnail_path = CONVERTED_DIR / f"{video_id}_thumb.jpg"
    video_player_service.generate_thumbnail(file_path, thumbnail_path)

    # Check if the format is directly web compatible
    web_compatible = video_player_service.is_web_compatible(file_extension)
    
    # Create video info - initially processing unless MP4/WebM
    video_info = {
        "id": video_id,
        "filename": filename,
        "original_format": file_extension,
        "status": "processing",
        "web_compatible": web_compatible,
        "thumbnail": f"/api/thumbnails/{video_id}" if os.path.exists(thumbnail_path) else None,
        "duration": video_player_service.get_video_duration(file_path),
        "hls_url": None,
        "preview_hls_url": None,  # Előnézeti URL, később kerül kitöltésre
        "full_hls_url": None,
        "stream_info": None
    }
    
    videos_db[video_id] = video_info
    
    # Start processing in background with GPU acceleration
    background_tasks.add_task(video_player_service.convert_video, video_id, file_path, file_extension)
    
    return video_info

@app.get("/api/videos", response_model=VideoList)
async def list_videos():
    """List all uploaded videos."""
    return {"videos": list(videos_db.values())}

@app.get("/api/videos/{video_id}", response_model=VideoInfo)
async def get_video_info(video_id: str):
    """Get information about a specific video."""
    if video_id not in videos_db:
        raise HTTPException(status_code=404, detail="Video not found")
    return videos_db[video_id]
    
@app.get("/api/download-status/{video_id}")
async def get_download_status(video_id: str):
    """Videó letöltési státusz ellenőrzése"""
    if video_id not in videos_db:
        raise HTTPException(status_code=404, detail="Video not found")
    
    video_info = videos_db[video_id]
    status = video_info.get("status", "unknown")
    
    # Ha hibastátusz van, adjuk vissza a hibaüzenetet is
    if status == "error" and "error_message" in video_info:
        return {
            "id": video_id,
            "status": status,
            "error_message": video_info["error_message"]
        }
    
    # Különböző státuszok kezelése
    if status in ["downloading", "processing"]:
        return {
            "id": video_id,
            "status": status,
            "message": "A videó feldolgozás alatt áll..."
        }
    elif status in ["ready", "preview_ready"]:
        return {
            "id": video_id,
            "status": "ready",
            "hls_url": video_info.get("hls_url"),
            "preview_hls_url": video_info.get("preview_hls_url"),
            "thumbnail": video_info.get("thumbnail")
        }
    
    return {
        "id": video_id,
        "status": status
    }

@app.get("/api/videos/{video_id}/streams")
async def get_video_streams(video_id: str):
    """Visszaadja a videó streamjeit és egyéb médiainfo adatokat"""
    if video_id not in videos_db:
        raise HTTPException(status_code=404, detail="Videó nem található")
    
    video_info = videos_db[video_id]
    
    if video_info["status"] != "ready" and video_info["status"] != "preview_ready":
        raise HTTPException(status_code=400, detail="A videó még nem elérhető")
    
    file_path = UPLOAD_DIR / f"{video_id}.{video_info['original_format']}"
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Videó fájl nem található")
    
    # Media streamek lekérdezése
    media_info = await video_player_service.get_media_streams(file_path)
    
    return {
        "id": video_id,
        "streams": {
            "video": media_info.video_streams,
            "audio": media_info.audio_streams,
            "subtitle": media_info.subtitle_streams
        },
        "chapters": media_info.chapters,
        "format": media_info.format_info
    }

@app.get("/api/stream/{video_id}")
async def stream_video(video_id: str):
    """Get streaming information for a video."""
    if video_id not in videos_db:
        raise HTTPException(status_code=404, detail="Video not found")
    
    video_info = videos_db[video_id]
    
    logger.info(f"Stream request for video {video_id}. Status: {video_info['status']}")
    
    # Check video status
    if video_info["status"] != "ready" and video_info["status"] != "preview_ready":
        raise HTTPException(status_code=400, detail=f"Video is not ready for streaming. Current status: {video_info['status']}")
    
    # Check if file exists
    original_file_path = UPLOAD_DIR / f"{video_id}.{video_info['original_format']}"
    
    if not original_file_path.exists():
        video_info["status"] = "error"
        raise HTTPException(status_code=404, detail="Video file not found. Please try uploading again.")
    
    # Determine media type and sources
    original_format = video_info["original_format"]
    
    # Check for HLS availability
    hls_url = video_info.get("hls_url")
    preview_hls_url = video_info.get("preview_hls_url")
    full_hls_url = video_info.get("full_hls_url")
    
    # Stream info visszaadása
    stream_info = video_info.get("stream_info", {})
    
    # Return all streaming options to the client
    return {
        "direct_url": f"/api/direct-stream/{video_id}",
        "media_type": f"video/{original_format}" if original_format in ['mp4', 'webm'] else "video/webm",
        "hls_url": hls_url,
        "preview_hls_url": preview_hls_url,  # Előnézeti URL is
        "full_hls_url": full_hls_url,
        "original_format": original_format,
        "stream_info": stream_info,
        "status": video_info["status"]
    }

@app.get("/api/direct-stream/{video_id}")
async def direct_stream_video(request: Request, video_id: str):
    """Egyszerűsített valós idejű videó streamelés - CPU-alapú"""
    if video_id not in videos_db:
        raise HTTPException(status_code=404, detail="Video not found")
    
    video_info = videos_db[video_id]
    
    if video_info["status"] not in ["ready", "preview_ready"]:
        raise HTTPException(status_code=400, detail="Video is not ready for streaming")
    
    # Az eredeti videófájlt használjuk
    file_path = UPLOAD_DIR / f"{video_id}.{video_info['original_format']}"
    
    if not os.path.exists(file_path):
        video_info["status"] = "error"
        logger.error(f"Video file not found at {file_path} for video {video_id}")
        raise HTTPException(status_code=404, detail="Video file not found")
    
    # Check file size
    file_size = os.path.getsize(file_path)
    
    # Ellenőrizzük a range header-t
    range_header = request.headers.get("Range", None)
    
    # Határozzuk meg, milyen kimeneti formátumot használjunk
    original_format = video_info["original_format"].lower()
    
    # MP4/WebM formátumok közvetlenül streamelhetők
    if original_format in ['mp4', 'webm']:
        output_format = original_format
        media_type = f"video/{output_format}"
        
        headers = {"Accept-Ranges": "bytes"}
        
        if range_header:
            # Részleges tartalom kezelése
            start, end = 0, file_size - 1
            range_value = range_header.replace("bytes=", "").split("-")
            
            if range_value[0]:
                start = int(range_value[0])
            if len(range_value) > 1 and range_value[1]:
                end = int(range_value[1])
                
            # Limit range to file size
            end = min(end, file_size - 1)
            
            # Open file at specific position
            file = open(file_path, "rb")
            file.seek(start)
            
            # Create streaming response with proper headers
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(end - start + 1)
            
            async def file_stream():
                buffer_size = 1024 * 1024  # 1MB buffer
                bytes_to_read = end - start + 1
                
                while bytes_to_read > 0:
                    chunk_size = min(buffer_size, bytes_to_read)
                    chunk = file.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
                    bytes_to_read -= len(chunk)
                
                file.close()
            
            return StreamingResponse(
                file_stream(),
                status_code=206,  # Partial Content
                headers=headers,
                media_type=media_type
            )
        else:
            # Return full file
            return FileResponse(
                path=file_path,
                headers=headers,
                media_type=media_type
            )
    
    # AVI/MKV esetén valós idejű konverzió webm formátumba - TISZTÁN CPU ALAPÚ, BIZTOS MEGOLDÁS
    else:
        # A jól bevált CPU-alapú parancs összeállítása (az eredetiből)
        output_format = "webm"
        output_mime = "video/webm"
        
        start = 0
        if range_header:
            range_value = range_header.replace("bytes=", "").split("-")
            if range_value[0]:
                # Pontosabb időkonverzió a seekinghez - megbecsüljük a tényleges időpozíciót
                if file_size > 0 and video_info.get("duration", 0) > 0:
                    # Tényleges időarányos pozícionálás
                    start_byte_percent = int(range_value[0]) / file_size
                    start = start_byte_percent * video_info["duration"]
                else:
                    # Fallback az eredeti becsült értékre
                    start_mb = int(range_value[0]) / (1024 * 1024)
                    start = start_mb * 10  # Becsült idő másodpercben
                
                logger.info(f"Seeking to position {start} seconds for video {video_id}")
            
            command = [
                "ffmpeg",
                "-ss", str(start),
                "-i", str(file_path),
                "-f", output_format,
                "-c:v", "libvpx-vp9",
                "-b:v", "1M",
                "-deadline", "realtime",
                "-cpu-used", "8",
                "-threads", "8",
                "-tile-columns", "6",
                "-frame-parallel", "1",
                # Seeking javítása
                "-g", "24",                    # Kisebb GOP méret a jobb seekinghez
                "-keyint_min", "24",           # Kisebb minimális kulcskép távolság
                "-force_key_frames", "expr:gte(t,n_forced*1)",  # 1 másodpercenként kulcsképkocka
                "-movflags", "frag_keyframe+empty_moov+faststart",
                "-"
            ]
        else:
            command = [
                "ffmpeg",
                "-i", str(file_path),
                "-f", output_format,
                "-c:v", "libvpx-vp9",
                "-b:v", "1M",
                "-deadline", "realtime",
                "-cpu-used", "8",
                "-threads", "8",
                "-tile-columns", "6",
                "-frame-parallel", "1",
                # Seeking javítása
                "-g", "24",                    # Kisebb GOP méret a jobb seekinghez
                "-keyint_min", "24",           # Kisebb minimális kulcskép távolság
                "-force_key_frames", "expr:gte(t,n_forced*1)",  # 1 másodpercenként kulcsképkocka
                "-movflags", "frag_keyframe+empty_moov+faststart",
                "-"
            ]
        
        # CPU process indítása
        logger.info(f"Starting CPU FFmpeg for direct streaming: {' '.join(map(str, command))}")
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Itt folytatódik a közös kód
        headers = {"Content-Type": output_mime}
        status_code = 206 if range_header else 200
        
        # Hibakövetés
        errors = []
        
        # Stderr olvasása háttérben
        async def read_stderr():
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                error_line = line.decode('utf-8', errors='ignore').strip()
                logger.debug(f"FFmpeg: {error_line}")
                if "error" in error_line.lower():
                    errors.append(error_line)
        
        asyncio.create_task(read_stderr())
        
        # Stream generátor
        async def stream_generator():
            buffer_size = 1024 * 1024  # 1MB buffer
            
            try:
                while True:
                    chunk = await process.stdout.read(buffer_size)
                    if not chunk:
                        break
                    yield chunk
                    
                    # Break on errors
                    if errors:
                        logger.error(f"Streaming error: {errors}")
                        break
                        
            except Exception as e:
                logger.error(f"Stream error: {e}")
                if process.returncode is None:
                    process.kill()
            finally:
                if process.returncode is None:
                    process.kill()
        
        return StreamingResponse(
            stream_generator(),
            status_code=status_code,
            headers=headers
        )

@app.get("/api/thumbnails/{video_id}")
async def get_thumbnail(video_id: str):
    """Get video thumbnail."""
    if video_id not in videos_db:
        raise HTTPException(status_code=404, detail="Video not found")
    
    thumbnail_path = CONVERTED_DIR / f"{video_id}_thumb.jpg"
    
    if not os.path.exists(thumbnail_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    
    return FileResponse(path=thumbnail_path, media_type="image/jpeg")

@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    """Delete a video."""
    if video_id not in videos_db:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Delete files
    original_format = videos_db[video_id]["original_format"]
    original_path = UPLOAD_DIR / f"{video_id}.{original_format}"
    converted_path = CONVERTED_DIR / f"{video_id}.mp4"
    thumbnail_path = CONVERTED_DIR / f"{video_id}_thumb.jpg"
    hls_dir = HLS_DIR / video_id
    
    # Remove files if they exist
    for path in [original_path, converted_path, thumbnail_path]:
        if os.path.exists(path):
            os.remove(path)
    
    # Remove HLS directory and contents if it exists
    if os.path.exists(hls_dir):
        shutil.rmtree(hls_dir)
    
    # Remove from database
    del videos_db[video_id]
    
    return {"message": "Video deleted successfully"}

# Stream API végpontok
@app.post("/api/streams", response_model=StreamResponse)
async def add_stream(request: AddStreamRequest):
    """Új élő stream hozzáadása"""
    try:
        logger.info(f"Adding new stream: {request.url}, proxy_mode: {request.proxy_mode}")
        
        # Stream típus felismerése
        stream_source = live_stream_handler.detect_stream_type(request.url)
        
        # Stream validálása
        is_valid = await live_stream_handler.validate_stream(stream_source)
        if not is_valid:
            logger.warning(f"Stream validation failed: {request.url}")
            raise HTTPException(status_code=400, detail="Invalid or offline stream")
        
        # Stream ID generálása
        stream_id = str(uuid.uuid4())
        
        # Proxy mód aktiválása ha szükséges
        proxy_url = None
        if request.proxy_mode:
            logger.info(f"Starting proxy mode for stream {stream_id}")
            proxy_url = await live_stream_handler.start_proxy_stream(stream_id, stream_source)
        
        # Stream információk tárolása
        stream_info = StreamInfo(
            id=stream_id,
            source=stream_source,
            status="active",
            proxy_url=proxy_url
        )
        
        live_stream_handler.active_streams[stream_id] = stream_info
        
        # Válasz formázása
        response = StreamResponse(
            id=stream_id,
            url=stream_source.url,
            type=stream_source.type,
            title=stream_source.title,
            status="active",
            is_live=True,
            embed_url=stream_source.embed_url,
            proxy_url=proxy_url,
            is_recording=False
        )
        
        logger.info(f"Stream added successfully: {stream_id}, type: {stream_source.type}")
        return response
        
    except HTTPException:
        # Már formázott HTTP kivétel továbbadása
        raise
    except Exception as e:
        logger.error(f"Error adding stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/streams", response_model=List[StreamResponse])
async def list_streams():
    """Összes aktív stream listázása"""
    try:
        logger.info("Listing all active streams")
        streams = []
        
        for stream_id, info in live_stream_handler.active_streams.items():
            is_recording = stream_id in live_stream_handler.recording_processes
            
            streams.append(StreamResponse(
                id=stream_id,
                url=info.source.url,
                type=info.source.type,
                title=info.source.title,
                status=info.status,
                is_live=info.source.is_live,
                embed_url=info.source.embed_url,
                proxy_url=info.proxy_url,
                is_recording=is_recording
            ))
        
        logger.info(f"Found {len(streams)} active streams")
        return streams
        
    except Exception as e:
        logger.error(f"Error listing streams: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/streams/{stream_id}", response_model=StreamResponse)
async def get_stream(stream_id: str):
    """Információk lekérése egy adott streamről"""
    if stream_id not in live_stream_handler.active_streams:
        logger.error(f"Stream not found: {stream_id}")
        raise HTTPException(status_code=404, detail="Stream not found")
    
    try:
        info = live_stream_handler.active_streams[stream_id]
        is_recording = stream_id in live_stream_handler.recording_processes
        
        logger.info(f"Returning info for stream {stream_id}")
        return StreamResponse(
            id=stream_id,
            url=info.source.url,
            type=info.source.type,
            title=info.source.title,
            status=info.status,
            is_live=info.source.is_live,
            embed_url=info.source.embed_url,
            proxy_url=info.proxy_url,
            is_recording=is_recording
        )
    except Exception as e:
        logger.error(f"Error getting stream {stream_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/streams/{stream_id}/record/start")
async def start_stream_recording(stream_id: str):
    """Stream felvétel indítása"""
    try:
        # Ellenőrizzük, hogy a stream létezik-e
        if stream_id not in live_stream_handler.active_streams:
            logger.error(f"Cannot start recording: Stream {stream_id} not found")
            raise HTTPException(status_code=404, detail="Stream not found")
        
        # Ellenőrizzük, hogy nincs-e már felvétel folyamatban
        if stream_id in live_stream_handler.recording_processes:
            logger.warning(f"Recording already in progress for stream {stream_id}")
            raise HTTPException(status_code=400, detail="Recording already in progress")
        
        logger.info(f"Starting recording for stream {stream_id}")
        recording_path = await live_stream_handler.start_recording(stream_id)
        
        logger.info(f"Recording started successfully for stream {stream_id}: {recording_path}")
        return {
            "status": "recording",
            "stream_id": stream_id,
            "recording_path": recording_path
        }
        
    except HTTPException:
        # Már formázott HTTP kivétel továbbadása
        raise
    except Exception as e:
        logger.error(f"Error starting recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/streams/{stream_id}/record/stop")
async def stop_stream_recording(stream_id: str):
    """Stream felvétel leállítása"""
    try:
        # Ellenőrizzük, hogy a stream létezik-e
        if stream_id not in live_stream_handler.active_streams:
            logger.error(f"Cannot stop recording: Stream {stream_id} not found")
            raise HTTPException(status_code=404, detail="Stream not found")
        
        # Ellenőrizzük, hogy van-e aktív felvétel
        if stream_id not in live_stream_handler.recording_processes:
            logger.error(f"Cannot stop recording: No active recording for stream {stream_id}")
            raise HTTPException(status_code=404, detail="No active recording")
        
        logger.info(f"Stopping recording for stream {stream_id}")
        result = await live_stream_handler.stop_recording(stream_id)
        
        # Ha van érvényes felvételi fájl, akkor hozzáadjuk a videókönyvtárhoz
        if result.get("recording_path") and os.path.exists(result["recording_path"]):
            recording_path = result["recording_path"]
            logger.info(f"Adding recorded video to library: {recording_path}")
            
            # Videó ID generálása
            video_id = str(uuid.uuid4())
            
            # Alap metaadatok kinyerése
            filename = os.path.basename(recording_path)
            file_extension = filename.split(".")[-1].lower()
            
            # Thumbnail generálása
            thumbnail_path = CONVERTED_DIR / f"{video_id}_thumb.jpg"
            video_player_service.generate_thumbnail(recording_path, thumbnail_path)
            
            # Időtartam lekérése
            duration = video_player_service.get_video_duration(recording_path)
            
            # Médiafolyamatok lekérése
            media_info = await video_player_service.get_media_streams(recording_path)
            
            # Beillesztés az adatbázisba
            videos_db[video_id] = {
                "id": video_id,
                "filename": filename,
                "original_format": file_extension,
                "status": "ready",
                "web_compatible": True,
                "thumbnail": f"/api/thumbnails/{video_id}" if os.path.exists(thumbnail_path) else None,
                "duration": duration,
                "hls_url": None,
                "preview_hls_url": None,
                "full_hls_url": None,
                "stream_info": {
                    "audio_streams": len(media_info.audio_streams),
                    "subtitle_streams": len(media_info.subtitle_streams),
                    "video_streams": len(media_info.video_streams)
                },
                "source": "recording",
                "recorded_from": stream_id,
                "recording_time": datetime.now().isoformat()
            }
            
            # HLS playlist generálása a háttérben
            asyncio.create_task(video_player_service.create_hls_playlist_with_gpu(video_id, recording_path, file_extension))
            
            # Frissítsük a választ a videó azonosítóval
            result["video_id"] = video_id
            logger.info(f"Recorded video added to library: {video_id}")
        else:
            logger.warning(f"No valid recording file found for stream {stream_id}")
        
        logger.info(f"Recording stopped successfully for stream {stream_id}")
        return result
        
    except HTTPException:
        # Már formázott HTTP kivétel továbbadása
        raise
    except Exception as e:
        logger.error(f"Error stopping recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/streams/{stream_id}")
async def remove_stream(stream_id: str):
    """Stream eltávolítása"""
    if stream_id not in live_stream_handler.active_streams:
        logger.error(f"Cannot remove stream: Stream {stream_id} not found")
        raise HTTPException(status_code=404, detail="Stream not found")
    
    try:
        logger.info(f"Removing stream {stream_id}")
        
        # Erőforrások felszabadítása
        await live_stream_handler.cleanup_stream(stream_id)
        
        # Stream eltávolítása
        del live_stream_handler.active_streams[stream_id]
        
        logger.info(f"Stream {stream_id} removed successfully")
        return {"status": "success", "message": "Stream removed"}
    except Exception as e:
        logger.error(f"Error removing stream {stream_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Videó letöltő API végpontok
@app.post("/api/download-video", response_model=VideoInfo)
async def download_video(request: VideoDownloadRequest, background_tasks: BackgroundTasks):
    """Videó letöltése URL-ről és hozzáadása a lejátszási könyvtárhoz"""
    try:
        logger.info(f"Video download request: {request.url}, platform: {request.platform}")
        
        # Egyedi azonosítók létrehozása
        video_id = str(uuid.uuid4())
        connection_id = str(uuid.uuid4())
        
        # Ideiglenes letöltési könyvtár
        work_dir = Path('temp') / connection_id
        work_dir.mkdir(exist_ok=True, parents=True)
        
        # VideoDownloader példány inicializálása
        downloader = VideoDownloader(connection_id, work_dir)
        
        # Kezdeti videó infó létrehozása
        video_info = {
            "id": video_id,
            "filename": f"downloaded_video_{video_id}",
            "original_format": "mp4",  # Alapértelmezett formátum, később frissítjük
            "status": "downloading",
            "source_url": request.url,
            "web_compatible": False,
            "thumbnail": None,
            "duration": None,
            "hls_url": None,
            "preview_hls_url": None,
            "full_hls_url": None,
            "stream_info": None
        }
        
        # Hozzáadás az adatbázishoz
        videos_db[video_id] = video_info
        
        # Háttérfolyamat indítása a letöltéshez
        background_tasks.add_task(
            process_video_download, 
            video_id, 
            request.url, 
            request.platform, 
            downloader, 
            connection_id
        )
        
        return video_info
        
    except Exception as e:
        logger.error(f"Error starting video download: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_video_download(video_id: str, url: str, platform: str, 
                                 downloader: VideoDownloader, connection_id: str):
    """Videó letöltési és feldolgozási folyamat"""
    try:
        logger.info(f"Starting video download process for {url}")
        
        # Videó letöltése
        video_path = await downloader.download_video(url, platform)
        
        if not video_path or not video_path.exists():
            logger.error(f"Download failed for {url}")
            videos_db[video_id]["status"] = "error"
            videos_db[video_id]["error_message"] = "Nem sikerült letölteni a videót"
            return
        
        # Sikeres letöltés, adatok frissítése
        file_extension = video_path.suffix[1:]  # A pont nélküli kiterjesztés
        filename = video_path.name
        
        # Áthelyezés a feltöltési könyvtárba
        target_path = UPLOAD_DIR / f"{video_id}.{file_extension}"
        shutil.copy(video_path, target_path)
        
        # Adatbázis frissítése
        videos_db[video_id].update({
            "filename": filename,
            "original_format": file_extension,
            "status": "processing",
        })
        
        # Thumbnai generálása
        thumbnail_path = CONVERTED_DIR / f"{video_id}_thumb.jpg"
        video_player_service.generate_thumbnail(target_path, thumbnail_path)
        
        if os.path.exists(thumbnail_path):
            videos_db[video_id]["thumbnail"] = f"/api/thumbnails/{video_id}"
        
        # Videó feldolgozása
        await video_player_service.convert_video(video_id, target_path, file_extension)
        
        # Sikeres feldolgozás, ideiglenes könyvtár törlése
        await downloader.cleanup()
        
        logger.info(f"Video download and processing complete for {video_id}")
        
    except Exception as e:
        logger.error(f"Error in video download process: {e}")
        videos_db[video_id]["status"] = "error"
        videos_db[video_id]["error_message"] = str(e)
        # Kísérlet a cleanup-ra hiba esetén is
        try:
            await downloader.cleanup()
        except:
            pass

# Mount static files directories - AFTER endpoint definitions
app.mount("/hls", StaticFiles(directory="hls"), name="hls")
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
