import os
import asyncio
import logging
import shutil
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from functools import partial
from dotenv import load_dotenv
from fastapi import WebSocket, HTTPException
from openai import AsyncOpenAI
import tiktoken

# Betöltjük a .env fájlt
load_dotenv()

# API kulcsok
API_KEYS = {
    "openai": os.getenv("OPENAI_API_KEY", ""),
    "google": os.getenv("GOOGLE_API_KEY", ""),
    "deepl": os.getenv("DEEPL_API_KEY", ""),
}

# Feltöltési korlát (megabyte-ban)
UPLOAD_LIMIT_MB = int(os.getenv("UPLOAD_LIMIT_MB", "100"))

# Logging beállítása
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger(__name__)

# Könyvtárak létrehozása
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

# Fájlméret korlát (100MB alapértelmezetten)
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "104857600"))  # 100MB in bytes

# Tisztítási időközök
CLEANUP_INTERVAL_HOURS = float(os.getenv("CLEANUP_INTERVAL_HOURS", "1"))  # Óránként ellenőrizzük a régi fájlokat
MAX_TEMP_DIR_AGE_HOURS = float(os.getenv("MAX_TEMP_DIR_AGE_HOURS", "24"))  # 24 óránál régebbi ideiglenes könyvtárakat töröljük

# Különböző formátumok engedélyezése
ALLOWED_DOCUMENT_EXTENSIONS = {
    "pdf", "docx", "doc", "odt", "txt", "rtf", "ppt", "pptx", "epub", "srt", "mobi", "sub"
}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif"}
ALLOWED_AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "m4a"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "mkv", "avi", "mov", "flv", "3gp", "wmv"}

# Teljesítmény és erőforrás-korlátok
MAX_PARALLEL_PROCESSES = int(os.getenv("MAX_PARALLEL_PROCESSES", "3"))
DEFAULT_CHUNK_SIZE = int(os.getenv("DEFAULT_CHUNK_SIZE", "10"))  # Laponként ennyi oldalt dolgozunk fel
PROCESS_TIMEOUT_SECONDS = int(os.getenv("PROCESS_TIMEOUT_SECONDS", "600"))  # 10 perc időtúllépés alapértelmezetten

def get_system_downloads_dir() -> Path:
    """Rendszer letöltési könyvtárának meghatározása"""
    downloads = Path(os.getenv("DOWNLOADS_DIR", str(Path.home() / "Downloads")))
    downloads.mkdir(exist_ok=True)
    logger.info(f"Using system downloads directory: {downloads}")
    return downloads

SYSTEM_DOWNLOADS = get_system_downloads_dir()

# Párhuzamos kérések kezelése
MAX_PARALLEL_REQUESTS = int(os.getenv("MAX_PARALLEL_REQUESTS", "3"))
process_semaphore = asyncio.Semaphore(MAX_PARALLEL_REQUESTS)

# OpenAI kliens inicializálása
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Segédfüggvények
def sanitize_filename(filename: str) -> Path:
    """Fájlnév tisztítása nem megengedett karakterektől"""
    # Speciális karakterek helyettesítése
    sanitized = re.sub(r'[\\/*?:"<>|#]', "", filename)
    # Szóközök cseréje aláhúzásra
    sanitized = sanitized.replace(" ", "_")
    # Max 255 karakter (fájlrendszer korlátozás)
    if len(sanitized) > 255:
        base, ext = os.path.splitext(sanitized)
        sanitized = f"{base[:245]}{ext}"
    return Path(sanitized)

async def async_rmtree(path: Path):
    """Könyvtár aszinkron törlése"""
    if not path.exists():
        return
        
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(shutil.rmtree, path, ignore_errors=True))

def chunk_text_by_tokens(text: str, max_tokens: int = 1000, overlap: int = 100) -> List[str]:
    """Szöveg darabolása tokenek alapján"""
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    tokens = encoding.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(encoding.decode(chunk_tokens))
        start += max_tokens - overlap
    return chunks

def check_file_extension(filename: str, allowed_extensions: set) -> bool:
    """Fájlkiterjesztés ellenőrzése"""
    ext = Path(filename).suffix.lower()[1:]  # A pontot eltávolítjuk
    return ext in allowed_extensions

def get_mime_type(filename: str) -> str:
    """MIME típus meghatározása fájlnév alapján"""
    mapping = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "odt": "application/vnd.oasis.opendocument.text",
        "txt": "text/plain",
        "rtf": "application/rtf",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "epub": "application/epub+zip",
        "srt": "application/x-subrip",
        "mobi": "application/x-mobipocket-ebook",
        "sub": "text/plain",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "m4a": "audio/mp4",
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mkv": "video/x-matroska",
        "avi": "video/x-msvideo",
        "mov": "video/quicktime",
        "flv": "video/x-flv",
        "3gp": "video/3gpp",
        "wmv": "video/x-ms-wmv"
    }
    ext = Path(filename).suffix.lower()[1:]
    return mapping.get(ext, "application/octet-stream")

def check_calibre():
    """Kalibra telepítésének ellenőrzése"""
    if not shutil.which("ebook-convert"):
        logger.warning(
            "Calibre (ebook-convert) is not installed or not in your PATH. "
            "Some conversions may not work correctly."
        )
        return False
    return True

def check_libreoffice():
    """LibreOffice telepítésének ellenőrzése"""
    if not shutil.which("soffice"):
        logger.warning(
            "LibreOffice is not installed or not in your PATH. "
            "Some conversions may not work correctly."
        )
        return False
    return True

def check_ffmpeg():
    """FFmpeg telepítésének ellenőrzése"""
    if not shutil.which("ffmpeg"):
        logger.warning(
            "FFmpeg is not installed or not in your PATH. "
            "Media processing features may not work correctly."
        )
        return False
    return True

async def run_with_timeout(coroutine, timeout_seconds=PROCESS_TIMEOUT_SECONDS):
    """Coroutine futtatása időtúllépéssel"""
    try:
        return await asyncio.wait_for(coroutine, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail=f"Operation timed out after {timeout_seconds} seconds"
        )

def format_filesize(size_bytes: int) -> str:
    """Fájlméret olvasható formátumra alakítása"""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

# Teljesítménymonitorozás
class ProcessTracker:
    """Folyamatok teljesítményének monitorozása"""
    
    def __init__(self):
        self.processes: Dict[str, Dict[str, Any]] = {}
        
    def start_process(self, process_id: str, process_type: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Új folyamat indításának rögzítése"""
        self.processes[process_id] = {
            "start_time": time.time(),
            "end_time": None,
            "type": process_type,
            "status": "running",
            "metadata": metadata or {},
            "error": None
        }
        
    def end_process(self, process_id: str, success: bool = True, error: Optional[str] = None) -> None:
        """Folyamat befejezésének rögzítése"""
        if process_id in self.processes:
            self.processes[process_id]["end_time"] = time.time()
            self.processes[process_id]["status"] = "success" if success else "error"
            if error:
                self.processes[process_id]["error"] = error
                
            # Számítások
            start_time = self.processes[process_id]["start_time"]
            end_time = self.processes[process_id]["end_time"]
            self.processes[process_id]["duration"] = end_time - start_time
            
    def get_process_info(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Folyamat információinak lekérése"""
        return self.processes.get(process_id)
        
    def get_statistics(self) -> Dict[str, Any]:
        """Statisztikák lekérése a folyamatokról"""
        total = len(self.processes)
        if total == 0:
            return {
                "total": 0,
                "success_rate": 0,
                "avg_duration": 0,
                "processes_by_type": {}
            }
            
        success = sum(1 for p in self.processes.values() if p["status"] == "success")
        completed = sum(1 for p in self.processes.values() if p["end_time"] is not None)
        
        durations = [p["duration"] for p in self.processes.values() 
                    if "duration" in p and p["duration"] is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        # Folyamatok típusonként
        processes_by_type = {}
        for p in self.processes.values():
            p_type = p["type"]
            if p_type not in processes_by_type:
                processes_by_type[p_type] = {"total": 0, "success": 0}
            processes_by_type[p_type]["total"] += 1
            if p["status"] == "success":
                processes_by_type[p_type]["success"] += 1
                
        return {
            "total": total,
            "completed": completed,
            "success": success,
            "success_rate": (success / total) * 100 if total > 0 else 0,
            "avg_duration": avg_duration,
            "processes_by_type": processes_by_type
        }
        
    def cleanup_old_processes(self, max_age_hours: float = 24) -> None:
        """Régi folyamatok törlése a nyilvántartásból"""
        current_time = time.time()
        to_remove = []
        
        for process_id, process in self.processes.items():
            start_time = process["start_time"]
            age_hours = (current_time - start_time) / 3600
            
            if age_hours > max_age_hours:
                to_remove.append(process_id)
                
        for process_id in to_remove:
            del self.processes[process_id]

# WebSocket kapcsolatkezelő osztály
class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        logger.info(f"WebSocket connection established: {connection_id}")

    async def disconnect(self, connection_id: str):
        """Kapcsolat bontása"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            logger.info(f"WebSocket connection closed: {connection_id}")

    async def send_progress(self, connection_id: str, progress: float, message: str):
        """Folyamat állapotának küldése"""
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_json({
                    "progress": progress,
                    "status": message
                })
            except Exception as e:
                logger.error(f"Error sending progress update: {str(e)}")
                # Sikertelen küldés esetén zárjuk a kapcsolatot
                await self.disconnect(connection_id)

    async def broadcast(self, message: str):
        """Üzenet küldése minden kapcsolatnak"""
        disconnected = []
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {connection_id}: {str(e)}")
                disconnected.append(connection_id)
                
        # Sikertelen kapcsolatok törlése
        for connection_id in disconnected:
            await self.disconnect(connection_id)

# Globális connection manager példány
manager = ConnectionManager()

# Globális folyamat tracker példány
process_tracker = ProcessTracker()

# Aktív folyamatok és folyamat állapotok tárolása
active_processes = {}
process_progress = {}
