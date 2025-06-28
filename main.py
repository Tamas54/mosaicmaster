from datetime import datetime
import json
import asyncio
import logging
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.websockets import WebSocket, WebSocketDisconnect
from urllib.parse import quote

# MosaicMaster components
from config import (
    TEMP_DIR, 
    SYSTEM_DOWNLOADS, 
    manager,
    logger,
    check_calibre,
    API_KEYS,
    UPLOAD_LIMIT_MB,
    client
)

# Function to send progress updates to the client
async def send_progress(connection_id: str, progress: int, status: str):
    await manager.send_progress(connection_id, progress, status)

from video_processor import router as video_router
from translator import router as translator_router
from document_processor import router as document_router
from document_processor import router as ocr_router
from transcriber import router as transcriber_router
from videoeditor import router as videoeditor_router
from videocutter import router as videocutter_router
from branding import router as branding_router
from subtitle_module import router as subtitle_router

# Königstiger components
from gpu_acceleration import GPUAccelerator
from live_stream_handler import live_stream_handler, StreamSource, StreamInfo, live_transcribe_stream
from video_player import VideoPlayerService, MediaStreamInfo
from videodownloader import VideoDownloader

# Initialize the FastAPI app
app = FastAPI(title="MosaicMaster & Königstiger Integrated Platform")

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create necessary directories
uploads_dir = Path("uploads")
results_dir = Path("results")
temp_dir = Path("temp")
static_dir = Path("static")
hls_dir = Path("hls")
converted_dir = Path("converted")

# Ensure directories exist
uploads_dir.mkdir(exist_ok=True)
results_dir.mkdir(exist_ok=True)
temp_dir.mkdir(exist_ok=True)
static_dir.mkdir(exist_ok=True)
hls_dir.mkdir(exist_ok=True)
converted_dir.mkdir(exist_ok=True)
Path("recordings").mkdir(exist_ok=True)

# MIME types
MIME_TYPES = {
    ".txt": "text/plain; charset=utf-8",
    ".srt": "text/srt; charset=utf-8",
    ".vtt": "text/vtt; charset=utf-8",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".rtf": "application/rtf",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".epub": "application/epub+zip",
    ".mobi": "application/x-mobipocket-ebook",
}

# Initialize Königstiger components
gpu_accelerator = GPUAccelerator()
logger.info(f"Video acceleration using: {gpu_accelerator.gpu_type['name']} with encoder: {gpu_accelerator.gpu_type['encoder']}")

# In-memory database for videos
videos_db = {}

# Initialize VideoPlayerService
video_player_service = VideoPlayerService(
    upload_dir=uploads_dir,
    converted_dir=converted_dir,
    hls_dir=hls_dir,
    gpu_accelerator=gpu_accelerator,
    videos_db=videos_db,
    logger=logger
)

# Model definitions for Königstiger
class VideoInfo(BaseModel):
    id: str
    filename: str
    original_format: str
    status: str
    duration: Optional[float] = None
    thumbnail: Optional[str] = None
    web_compatible: bool = False
    hls_url: Optional[str] = None
    preview_hls_url: Optional[str] = None
    full_hls_url: Optional[str] = None
    stream_info: Optional[Dict[str, Any]] = None
    download_url: Optional[str] = None  # Új: közvetlenül letölthető URL

class VideoList(BaseModel):
    videos: List[VideoInfo]

# Stream API models
class AddStreamRequest(BaseModel):
    url: str
    proxy_mode: bool = False

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

class ProgressUpdate(BaseModel):
    progress: int
    status: str

# Include MosaicMaster routers
app.include_router(video_router, prefix="/api/video", tags=["video"])
app.include_router(video_router, prefix="/api/videoprocessor", tags=["videoprocessor"])
app.include_router(translator_router, prefix="/api/translate", tags=["translate"])
app.include_router(document_router, prefix="/api/convert", tags=["convert"])
app.include_router(ocr_router, prefix="/api/ocr", tags=["ocr"])
app.include_router(transcriber_router, prefix="/api/transcribe", tags=["transcribe"])
app.include_router(videoeditor_router, prefix="/api/videoeditor", tags=["videoeditor"])
app.include_router(videocutter_router, prefix="/api/videocutter", tags=["videocutter"])
app.include_router(branding_router, prefix="/api/branding", tags=["branding"])
app.include_router(subtitle_router, prefix="/api/subtitles", tags=["subtitles"])

# WebSocket endpoint for progress updates
@app.websocket("/ws/{connection_id}")
async def websocket_endpoint(websocket: WebSocket, connection_id: str):
    await manager.connect(websocket, connection_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(connection_id)

@app.get("/api/progress/{connection_id}")
async def get_progress(connection_id: str):
    """Folyamat állapotának lekérése"""
    if connection_id not in manager.active_connections:
        return {"progress": 0, "status": "Waiting..."}
    return {"progress": 100, "status": "Complete"}

# Helper function to check file size
async def check_file_size(file: UploadFile) -> float:
    file.file.seek(0, 2)  # Seek to the end of the file
    file_size = file.file.tell()  # Get current position = file size
    file.file.seek(0)  # Reset file position
    
    file_size_mb = file_size / (1024 * 1024)
    
    if file_size_mb > UPLOAD_LIMIT_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File size ({file_size_mb:.2f} MB) exceeds the limit of {UPLOAD_LIMIT_MB} MB"
        )
    
    return file_size_mb

# Helper function to save uploaded file
async def save_upload(file: UploadFile, directory: Path) -> Path:
    # Generate a unique filename
    original_filename = file.filename
    extension = original_filename.split(".")[-1] if "." in original_filename else ""
    unique_filename = f"{uuid.uuid4()}.{extension}"
    file_path = directory / unique_filename
    
    # Save the file
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    return file_path

# File download endpoint
@app.get("/download/{filename}")
async def download_file(filename: str):
    """Fájl letöltése"""
    file_path = SYSTEM_DOWNLOADS / filename
    if not file_path.exists():
        return JSONResponse(
            status_code=404,
            content={"detail": "File not found"}
        )

    # MIME típus meghatározása
    media_type = MIME_TYPES.get(
        file_path.suffix.lower(),
        "application/octet-stream"
    )

    try:
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
            }
        )
    except Exception as e:
        logger.error(f"Error serving download: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Error processing download"}
        )

# ====================== KÖNIGSTIGER API ENDPOINTS ======================

# Video upload API
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
    file_path = uploads_dir / f"{video_id}.{file_extension}"
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()
    
    logger.info(f"File saved to {file_path}, size: {os.path.getsize(file_path)} bytes")
    
    # Generate thumbnail
    thumbnail_path = converted_dir / f"{video_id}_thumb.jpg"
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
        "preview_hls_url": None,
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
    
    # A downloads_url mező hozzáadása, ha ez egy letöltött videó
    video_info = videos_db[video_id]
    if "download_url" not in video_info and video_info["original_format"] == "mp4":
        # Ellenőrizzük, hogy létezik-e a fájl a SYSTEM_DOWNLOADS mappában
        from config import SYSTEM_DOWNLOADS
        if "filename" in video_info:
            potential_download_path = SYSTEM_DOWNLOADS / video_info["filename"]
            if potential_download_path.exists():
                video_info["download_url"] = f"/download/{video_info['filename']}"
    
    return video_info

@app.get("/api/videos/{video_id}/streams")
async def get_video_streams(video_id: str):
    """Visszaadja a videó streamjeit és egyéb médiainfo adatokat"""
    if video_id not in videos_db:
        raise HTTPException(status_code=404, detail="Videó nem található")
    
    video_info = videos_db[video_id]
    
    if video_info["status"] != "ready" and video_info["status"] != "preview_ready":
        raise HTTPException(status_code=400, detail="A videó még nem elérhető")
    
    file_path = uploads_dir / f"{video_id}.{video_info['original_format']}"
    
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
    original_file_path = uploads_dir / f"{video_id}.{video_info['original_format']}"
    
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
    
    # Letöltési URL ellenőrzése
    download_url = video_info.get("download_url")
    
    # Ha nincs letöltési URL, ellenőrizzük, hogy a fájl létezik-e a SYSTEM_DOWNLOADS mappában
    if not download_url and original_format in ['mp4', 'webm', 'mkv', 'avi']:
        from config import SYSTEM_DOWNLOADS
        potential_download_path = SYSTEM_DOWNLOADS / f"{video_id}.{original_format}"
        if potential_download_path.exists():
            download_url = f"/download/{video_id}.{original_format}"
            video_info["download_url"] = download_url
    
    # Return all streaming options to the client
    return {
        "direct_url": f"/api/direct-stream/{video_id}",
        "media_type": f"video/{original_format}" if original_format in ['mp4', 'webm'] else "video/webm",
        "hls_url": hls_url,
        "preview_hls_url": preview_hls_url,
        "full_hls_url": full_hls_url,
        "original_format": original_format,
        "stream_info": stream_info,
        "status": video_info["status"],
        "download_url": download_url  # Új: letöltési URL
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
    file_path = uploads_dir / f"{video_id}.{video_info['original_format']}"
    
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
    
    thumbnail_path = converted_dir / f"{video_id}_thumb.jpg"
    
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
    original_path = uploads_dir / f"{video_id}.{original_format}"
    converted_path = converted_dir / f"{video_id}.mp4"
    thumbnail_path = converted_dir / f"{video_id}_thumb.jpg"
    hls_dir_path = hls_dir / video_id
    
    # Remove files if they exist
    for path in [original_path, converted_path, thumbnail_path]:
        if os.path.exists(path):
            os.remove(path)
    
    # Remove HLS directory and contents if it exists
    if os.path.exists(hls_dir_path):
        shutil.rmtree(hls_dir_path)
    
    # Remove from database
    del videos_db[video_id]
    
    return {"message": "Video deleted successfully"}

@app.get("/api/transcription-status/{transcript_id}")
async def get_transcription_status(transcript_id: str):
    """Átiratolási állapot lekérdezése"""
    # Itt ellenőrizzük, hogy a leirat elkészült-e már
    # Egyszerűsítve: csak megnézzük, létezik-e a megfelelő fájl
    transcript_path = SYSTEM_DOWNLOADS / f"transcript_{transcript_id}.txt"
    
    if os.path.exists(transcript_path):
        return {
            "id": transcript_id,
            "status": "completed",
            "download_url": f"/download/transcript_{transcript_id}.txt",
            "message": "Leirat elkészült"
        }
    
    # Ha nem találjuk, valószínűleg még feldolgozás alatt van
    return {
        "id": transcript_id,
        "status": "processing",
        "message": "Leirat készítése folyamatban"
    }

async def process_downloaded_media_transcription(transcript_id: str, media_path: Path, filename: str, 
                                              timecoded: bool = True, identify_speakers: bool = False, fast_mode: bool = False):
    """Közös media átiratolási folyamat - videó és URL alapú leiratkészítéshez"""
    try:
        logger.info(f"Processing media transcription for {filename} (fast_mode: {fast_mode})")
        
        # Ideiglenes munkakönyvtár
        work_dir = TEMP_DIR / transcript_id
        work_dir.mkdir(exist_ok=True, parents=True)
        
        # Audió kinyerése a videóból
        audio_path = work_dir / f"{transcript_id}.mp3"
        
        # FFmpeg használata az audió kinyeréséhez - robusztusabb beállításokkal
        cmd = [
            "ffmpeg", 
            "-i", str(media_path), 
            "-vn",                # Csak hang, videó nélkül
            "-c:a", "libmp3lame", # Explicit MP3 codec
            "-q:a", "0",          # Legjobb minőség
            "-ar", "44100",       # Standard mintavételezés
            "-ac", "2",           # Sztereó hang
            str(audio_path)
        ]
        
        # FFmpeg futtatása
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.wait()
        
        if not audio_path.exists():
            logger.error(f"Failed to extract audio from {media_path}")
            return
        
        # Transzkripciós modul hívása
        from transcriber import _transcribe_audio, generate_transcript_txt
        
        # Audió transzkripciója - fast_mode paraméter átadása
        transcript_text, transcript_data = await _transcribe_audio(
            audio_path, 
            identify_speakers=identify_speakers,
            fast_mode=fast_mode
        )
        
        # Leirat mentése TXT fájlba
        transcript_file = SYSTEM_DOWNLOADS / f"transcript_{transcript_id}.txt"
        await generate_transcript_txt(
            transcript_data["segments"], 
            transcript_file,
            with_timestamps=timecoded
        )
        
        # Takarítás
        try:
            shutil.rmtree(work_dir)
        except:
            pass
        
        logger.info(f"Transcription completed for {filename}")
        
    except Exception as e:
        logger.error(f"Error in transcription process: {e}")
        # Takarítás hiba esetén is
        try:
            shutil.rmtree(work_dir)
        except:
            pass

async def process_video_transcription(transcript_id: str, video_path: Path, filename: str, 
                                     timecoded: bool = True, identify_speakers: bool = False, fast_mode: bool = False):
    """Videó átiratolási háttérfolyamat"""
    try:
        logger.info(f"Starting transcription process for {filename} (fast_mode: {fast_mode})")
        
        await process_downloaded_media_transcription(transcript_id, video_path, filename, 
                                                  timecoded, identify_speakers, fast_mode)
    except Exception as e:
        logger.error(f"Error in video transcription process: {e}")

@app.post("/api/transcribe-video/{video_id}")
async def transcribe_video(video_id: str, background_tasks: BackgroundTasks, request: Request):
    """Videó leiratolása a videólejátszóból"""
    try:
        # Ellenőrizzük, hogy a videó létezik-e
        if video_id not in videos_db:
            raise HTTPException(status_code=404, detail="Videó nem található")
        
        video_info = videos_db[video_id]
        
        # Ellenőrizzük, hogy a videó lejátszható-e
        if video_info["status"] not in ["ready", "preview_ready"]:
            raise HTTPException(status_code=400, detail="A videó még nem elérhető leiratolásra")
        
        # Request body kiolvasása
        request_data = await request.json()
        
        # Paraméterek kinyerése
        timecoded = request_data.get("timecoded", False)
        identify_speakers = request_data.get("identify_speakers", False)
        fast_mode = request_data.get("fast_mode", True)
        
        # File path meghatározása
        file_extension = video_info["original_format"]
        file_path = uploads_dir / f"{video_id}.{file_extension}"
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Videó fájl nem található")
        
        # Egyedi azonosító a leirat számára
        transcript_id = str(uuid.uuid4())
        
        # Háttérfolyamat indítása a leirat elkészítésére
        background_tasks.add_task(
            process_video_transcription,
            transcript_id,
            file_path,
            video_info["filename"],
            timecoded,
            identify_speakers,
            fast_mode
        )
        
        return {
            "id": transcript_id,
            "status": "processing",
            "message": "Leirat készítése folyamatban"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in video transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Stream APIs
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
            thumbnail_path = converted_dir / f"{video_id}_thumb.jpg"
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
            asyncio.create_task(video_player_service.create_turbo_hls(video_id, recording_path, media_info))
            
            # Frissítsük a választ a videó azonosítóval
            result["video_id"] = video_id
            result["video_added"] = True
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
        
        logger.info(f"Stream {stream_id} removed successfully")
        return {"status": "success", "message": "Stream removed"}
    except Exception as e:
        logger.error(f"Error removing stream {stream_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ====================== ROUTES FOR HTML PAGES ======================

# Serve the main page
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Főoldal betöltése"""
    return FileResponse("static/index.html")

# Serve video player page
@app.get("/video-player.html", response_class=HTMLResponse)
async def get_video_player():
    try:
        with open("video-player.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        logger.error(f"Error serving video player page: {e}")
        return HTMLResponse(content="<h1>Error loading the video player page</h1>")

# Serve live streams page
@app.get("/live-streams.html", response_class=HTMLResponse)
async def get_live_streams():
    try:
        with open("live-streams.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        logger.error(f"Error serving live streams page: {e}")
        return HTMLResponse(content="<h1>Error loading the live streams page</h1>")


# ====================== ROUTE MOUNTS ======================

# Mount static dirs
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/hls", StaticFiles(directory="hls"), name="hls")


# Run the server when executed directly
if __name__ == "__main__":
    import uvicorn
    
    # Check calibre
    check_calibre()
    
    # Log branding information
    logger.info("=" * 50)
    logger.info("MosaicMaster & Königstiger Integrated Platform")
    logger.info("Version: 1.0.0")
    logger.info("=" * 50)
    
    # Start the server
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")