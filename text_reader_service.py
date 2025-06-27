import os
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List
import logging
from dataclasses import dataclass
from datetime import datetime
import uuid

from fastapi import APIRouter, HTTPException, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import aiofiles
import aiohttp
from bs4 import BeautifulSoup

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

# Import document processor functions
try:
    from document_processor import convert_document_to_text, process_ocr
    DOCUMENT_PROCESSOR_AVAILABLE = True
except ImportError:
    DOCUMENT_PROCESSOR_AVAILABLE = False
    print("⚠️ Document processor not available")

# Konfigurációs elemek
logger = logging.getLogger(__name__)

@dataclass
class AudioChunk:
    id: str
    text: str
    filename: str
    file_path: Path
    created_at: datetime

@dataclass
class TextReaderJob:
    id: str
    text: str
    language: str
    chunks: List[AudioChunk]
    status: str  # "processing", "completed", "error"
    created_at: datetime
    error_message: Optional[str] = None
    total_chunks: int = 0
    processed_chunks: int = 0

class TextReaderService:
    def __init__(self, temp_dir: Path, downloads_dir: Path):
        self.temp_dir = Path(temp_dir)
        self.downloads_dir = Path(downloads_dir)
        self.active_jobs = {}
        self.max_chunk_length = 500
        
        # Ensure directories exist
        self.temp_dir.mkdir(exist_ok=True)
        self.downloads_dir.mkdir(exist_ok=True)
        
        if not GTTS_AVAILABLE:
            logger.error("gTTS not available! Please install: pip install gtts")
    
    def _split_text_into_chunks(self, text: str) -> List[str]:
        """Szöveg darabolása mondatok mentén"""
        import re
        
        # Mondatok vége jelölők
        sentence_endings = r'[.!?]\s+'
        sentences = re.split(sentence_endings, text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if not sentence.strip():
                continue
                
            # Ha a jelenlegi chunk + új mondat túl hosszú
            if len(current_chunk) + len(sentence) + 2 > self.max_chunk_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    # Ha maga a mondat túl hosszú, daraboljuk fel
                    while len(sentence) > self.max_chunk_length:
                        chunks.append(sentence[:self.max_chunk_length])
                        sentence = sentence[self.max_chunk_length:]
                    current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += ". " + sentence
                else:
                    current_chunk = sentence
        
        # Utolsó chunk hozzáadása
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _detect_language(self, text: str) -> str:
        """Fejlettebb nyelv felismerés a szöveg alapján"""
        if not text or len(text.strip()) < 10:
            return 'en'  # Alapértelmezett rövid szövegekhez
            
        text_lower = text.lower()
        text_words = text_lower.split()
        
        # Magyar karakterek és szavak
        hungarian_chars = ['á', 'é', 'í', 'ó', 'ö', 'ő', 'ú', 'ü', 'ű']
        hungarian_words = ['és', 'a', 'az', 'hogy', 'nem', 'van', 'egy', 'vagy', 'de', 'vagy', 'mint', 'csak', 'még', 'már', 'igen', 'igen', 'mit', 'aki', 'ami', 'amely']
        
        # Angol jellemző szavak
        english_words = ['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'will', 'would', 'can', 'could', 'should']
        
        # Számolások
        hungarian_char_count = sum(1 for char in text_lower if char in hungarian_chars)
        hungarian_word_matches = sum(1 for word in text_words if word in hungarian_words)
        english_word_matches = sum(1 for word in text_words if word in english_words)
        
        total_chars = len(text_lower)
        total_words = len(text_words)
        
        # Súlyozott pontszám számítás
        hungarian_score = 0
        english_score = 0
        
        # Magyar karakterek aránya
        if total_chars > 0:
            hungarian_char_ratio = hungarian_char_count / total_chars
            hungarian_score += hungarian_char_ratio * 100
        
        # Szó egyezések aránya
        if total_words > 0:
            hungarian_word_ratio = hungarian_word_matches / total_words
            english_word_ratio = english_word_matches / total_words
            
            hungarian_score += hungarian_word_ratio * 50
            english_score += english_word_ratio * 50
        
        # Döntés
        if hungarian_score > english_score and hungarian_score > 5:
            return 'hu'
        elif english_score > 10:
            return 'en'
        
        # Ha bizonytalan, próbáljunk nyelvi mintákat keresni
        if any(pattern in text_lower for pattern in ['tion', 'ing', 'ed', 'ly']):
            return 'en'
        elif any(pattern in text_lower for pattern in ['ság', 'ség', 'ban', 'ben', 'nak', 'nek']):
            return 'hu'
            
        # Alapértelmezett
        return 'en'
    
    async def _extract_text_from_document(self, file_path: Path) -> str:
        """Szöveg kinyerése dokumentumból a document processor használatával"""
        if not DOCUMENT_PROCESSOR_AVAILABLE:
            raise HTTPException(status_code=500, detail="Document processor not available")
        
        file_extension = file_path.suffix.lower()
        
        try:
            # Képek esetén OCR használata
            if file_extension in ['.jpg', '.jpeg', '.png', '.gif']:
                logger.info(f"Processing image file with OCR: {file_path}")
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                
                # OCR feldolgozás
                ocr_result = process_ocr(str(file_path), "hun+eng")
                
                if ocr_result and ocr_result.strip():
                    return ocr_result
                else:
                    raise Exception("OCR processing failed")
            
            # Dokumentumok esetén konvertálás
            else:
                logger.info(f"Processing document file: {file_path}")
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                
                # Dokumentum konvertálás szöveggé
                convert_result = convert_document_to_text(str(file_path), file_path.suffix.lower()[1:])
                
                if convert_result and convert_result.strip():
                    return convert_result
                else:
                    raise Exception("Document conversion failed")
                    
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to extract text from document: {str(e)}")
    
    async def _fetch_url_content(self, url: str) -> str:
        """URL-ből szöveg letöltése és kinyerése"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise HTTPException(
                            status_code=400, 
                            detail=f"Failed to fetch URL: HTTP {response.status}"
                        )
                    
                    content_type = response.headers.get('Content-Type', '').lower()
                    
                    if 'text/html' in content_type:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Remove scripts, styles, and other non-content elements
                        for element in soup(['script', 'style', 'header', 'footer', 'nav']):
                            element.decompose()
                        
                        # Extract text from main content areas
                        main_content = soup.find('main') or soup.find('article') or soup.find('body')
                        if main_content:
                            text = main_content.get_text(separator='\n', strip=True)
                        else:
                            text = soup.get_text(separator='\n', strip=True)
                        
                        # Clean up excessive whitespace
                        import re
                        text = re.sub(r'\n+', '\n', text)
                        text = re.sub(r'\s+', ' ', text)
                        
                        return text
                    elif 'application/pdf' in content_type:
                        # For PDFs, download and process with document processor
                        if not DOCUMENT_PROCESSOR_AVAILABLE:
                            raise HTTPException(status_code=500, detail="Document processor not available for PDF URLs")
                        
                        pdf_data = await response.read()
                        temp_pdf_path = self.temp_dir / f"url_pdf_{uuid.uuid4()}.pdf"
                        
                        async with aiofiles.open(temp_pdf_path, "wb") as f:
                            await f.write(pdf_data)
                        
                        try:
                            extracted_text = await self._extract_text_from_document(temp_pdf_path)
                            return extracted_text
                        finally:
                            # Clean up temporary PDF file
                            try:
                                temp_pdf_path.unlink()
                            except Exception as cleanup_error:
                                logger.warning(f"Failed to cleanup temp PDF: {cleanup_error}")
                    else:
                        # Just plain text
                        return await response.text()
        except aiohttp.ClientError as e:
            logger.error(f"URL fetch error: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error fetching URL {url}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to process URL content: {str(e)}")
    
    async def create_audio_job(self, text: str, language: Optional[str] = None) -> str:
        """Új audio generálási feladat létrehozása"""
        if not GTTS_AVAILABLE:
            raise HTTPException(status_code=500, detail="gTTS not available")
        
        job_id = str(uuid.uuid4())
        
        # Nyelv felismerés ha nincs megadva
        if not language:
            language = self._detect_language(text)
        
        # Feladat objektum létrehozása
        job = TextReaderJob(
            id=job_id,
            text=text,
            language=language,
            chunks=[],
            status="processing",
            created_at=datetime.now(),
            total_chunks=0,
            processed_chunks=0
        )
        
        self.active_jobs[job_id] = job
        
        return job_id
    
    async def process_text_to_audio(self, job_id: str) -> bool:
        """Szöveg feldolgozása audio fájllá/fájlokká"""
        if job_id not in self.active_jobs:
            return False
        
        job = self.active_jobs[job_id]
        
        try:
            # Szöveg darabolása
            text_chunks = self._split_text_into_chunks(job.text)
            job.total_chunks = len(text_chunks)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Minden chunk-hoz audio generálás
            for i, chunk_text in enumerate(text_chunks):
                # gTTS generálás
                tts = gTTS(text=chunk_text, lang=job.language, slow=False)
                
                # Fájlnév
                chunk_id = f"{job_id}_part{i+1:03d}"
                audio_filename = f"textreader_{timestamp}_{chunk_id}.mp3"
                audio_path = self.downloads_dir / audio_filename
                
                # Mentés
                tts.save(str(audio_path))
                
                # Chunk objektum létrehozása
                audio_chunk = AudioChunk(
                    id=chunk_id,
                    text=chunk_text,
                    filename=audio_filename,
                    file_path=audio_path,
                    created_at=datetime.now()
                )
                
                job.chunks.append(audio_chunk)
                job.processed_chunks = i + 1
                
                logger.info(f"Generated audio chunk {i+1}/{len(text_chunks)} for job {job_id}")
                
                # Kis szünet a Google szerver terhelésének csökkentéséhez
                if i < len(text_chunks) - 1:
                    await asyncio.sleep(1)
            
            job.status = "completed"
            logger.info(f"Text-to-audio job {job_id} completed successfully")
            return True
            
        except Exception as e:
            job.status = "error"
            job.error_message = str(e)
            logger.error(f"Error in text-to-audio job {job_id}: {e}")
            return False
    
    def get_job_status(self, job_id: str) -> Optional[TextReaderJob]:
        """Feladat állapotának lekérdezése"""
        return self.active_jobs.get(job_id)
    
    def get_audio_file(self, job_id: str, chunk_id: Optional[str] = None) -> Optional[Path]:
        """Audio fájl elérési útjának lekérdezése"""
        if job_id not in self.active_jobs:
            return None
        
        job = self.active_jobs[job_id]
        
        if not chunk_id and job.chunks:
            # Első chunk visszaadása ha nincs megadva
            return job.chunks[0].file_path
        
        # Specifikus chunk keresése
        for chunk in job.chunks:
            if chunk.id == chunk_id:
                return chunk.file_path
        
        return None
    
    async def cleanup_job(self, job_id: str):
        """Feladat fájljainak törlése"""
        if job_id not in self.active_jobs:
            return
        
        job = self.active_jobs[job_id]
        
        # Audio fájlok törlése
        for chunk in job.chunks:
            try:
                if chunk.file_path.exists():
                    chunk.file_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete audio file {chunk.file_path}: {e}")
        
        # Feladat törlése a memóriából
        del self.active_jobs[job_id]

# Router létrehozása
router = APIRouter()

# Service instance - ez majd a main-integrated.py-ban lesz inicializálva
text_reader_service: Optional[TextReaderService] = None

def init_text_reader_service(temp_dir: Path, downloads_dir: Path):
    """Text Reader Service inicializálása"""
    global text_reader_service
    text_reader_service = TextReaderService(temp_dir, downloads_dir)
    return text_reader_service

@router.post("/api/text-reader/generate")
async def generate_audio_from_text(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    language: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None)
):
    """Szöveg, fájl vagy URL alapján audio generálás"""
    if not text_reader_service:
        raise HTTPException(status_code=500, detail="Text Reader Service not initialized")
    
    extracted_text = text
    
    # Ha fájl van feltöltve, abból olvassuk ki a szöveget
    if file:
        # Támogatott fájlformátumok ellenőrzése
        supported_extensions = ['.txt', '.rtf', '.doc', '.docx', '.pdf', '.odt', '.jpg', '.jpeg', '.png', '.gif']
        file_extension = '.' + file.filename.lower().split('.')[-1] if '.' in file.filename else ''
        
        if file_extension not in supported_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file format. Supported: {', '.join(supported_extensions)}"
            )
        
        try:
            # Ideiglenes fájl mentése
            temp_file_path = text_reader_service.temp_dir / f"temp_{uuid.uuid4()}{file_extension}"
            
            # Fájl ellenőrzés
            if file.size and file.size > 50 * 1024 * 1024:  # 50MB limit
                raise HTTPException(status_code=400, detail="File size too large (max 50MB)")
            
            with open(temp_file_path, 'wb') as temp_file:
                content = await file.read()
                if not content:
                    raise HTTPException(status_code=400, detail="Empty file uploaded")
                temp_file.write(content)
            
            # Szöveg kinyerése a dokumentumból
            if file_extension in ['.txt', '.rtf']:
                # Egyszerű szöveges fájlok esetén
                encodings = ['utf-8', 'utf-8-sig', 'cp1252', 'iso-8859-1', 'cp1250', 'latin1']
                decoded_text = None
                last_error = None
                
                for encoding in encodings:
                    try:
                        with open(temp_file_path, 'r', encoding=encoding) as f:
                            decoded_text = f.read()
                        logger.info(f"Successfully decoded file with encoding: {encoding}")
                        break
                    except (UnicodeDecodeError, UnicodeError) as e:
                        last_error = e
                        continue
                
                if decoded_text is None:
                    logger.error(f"Failed to decode text file with all encodings. Last error: {last_error}")
                    raise HTTPException(status_code=400, detail=f"Could not decode text file. Try saving as UTF-8 encoded text.")
                
                if not decoded_text.strip():
                    raise HTTPException(status_code=400, detail="Text file appears to be empty")
                    
                extracted_text = decoded_text.strip()
            else:
                # Dokumentum feldolgozás vagy OCR
                try:
                    if not DOCUMENT_PROCESSOR_AVAILABLE:
                        raise HTTPException(status_code=500, 
                                          detail=f"Document processor not available for {file_extension} files. Please upload a .txt file instead.")
                    
                    extracted_text = await text_reader_service._extract_text_from_document(temp_file_path)
                    
                    if not extracted_text or not extracted_text.strip():
                        raise HTTPException(status_code=400, 
                                          detail=f"No text could be extracted from {file_extension} file. The document might be empty, corrupted, or contain only images.")
                        
                except Exception as e:
                    logger.error(f"Document processing failed for {file_extension}: {str(e)}")
                    raise HTTPException(status_code=400, 
                                      detail=f"Failed to process {file_extension} file: {str(e)}. Try converting to a plain text file.")
            
            # Ideiglenes fájl törlése
            try:
                temp_file_path.unlink()
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
                
        except HTTPException:
            # HTTP kivételek továbbadása
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing file {file.filename}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Unexpected error processing file: {str(e)}")
    
    # Ha URL van megadva, abból olvassuk ki a szöveget
    elif url:
        if not url.startswith('http://') and not url.startswith('https://'):
            raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
        
        try:
            logger.info(f"Fetching content from URL: {url}")
            extracted_text = await text_reader_service._fetch_url_content(url)
            
            if not extracted_text or not extracted_text.strip():
                raise HTTPException(status_code=400, detail="No text content found at the provided URL")
                
        except HTTPException:
            # HTTP kivételek továbbadása
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing URL {url}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch content from URL: {str(e)}")
    
    if not extracted_text or not extracted_text.strip():
        raise HTTPException(status_code=400, detail="No text content found")
    
    # Automatikus nyelvfelismerés ha nincs megadva
    if not language:
        try:
            detected_language = text_reader_service._detect_language(extracted_text)
            logger.info(f"Auto-detected language: {detected_language}")
            language = detected_language
        except Exception as e:
            logger.warning(f"Language detection failed: {e}, using default 'en'")
            language = 'en'
    
    # Feladat létrehozása
    job_id = await text_reader_service.create_audio_job(extracted_text, language)
    
    # Háttérben futtatjuk a feldolgozást
    background_tasks.add_task(text_reader_service.process_text_to_audio, job_id)
    
    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Audio generation started"
    }

@router.get("/api/text-reader/status/{job_id}")
async def get_audio_generation_status(job_id: str):
    """Audio generálás állapotának lekérdezése"""
    if not text_reader_service:
        raise HTTPException(status_code=500, detail="Text Reader Service not initialized")
    
    job = text_reader_service.get_job_status(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    result = {
        "job_id": job.id,
        "status": job.status,
        "language": job.language,
        "chunk_count": len(job.chunks),
        "total_chunks": job.total_chunks,
        "processed_chunks": job.processed_chunks,
        "created_at": job.created_at.isoformat()
    }
    
    if job.status == "error":
        result["error_message"] = job.error_message
    
    if job.status == "completed" and job.chunks:
        result["download_urls"] = []
        for chunk in job.chunks:
            result["download_urls"].append({
                "chunk_id": chunk.id,
                "filename": chunk.filename,
                "download_url": f"/api/text-reader/download/{job.id}/{chunk.id}"
            })
    
    return result

@router.get("/api/text-reader/download/{job_id}")
async def download_first_audio_chunk(job_id: str):
    """Első audio chunk letöltése"""
    return await download_audio_chunk(job_id, None)

@router.get("/api/text-reader/download/{job_id}/{chunk_id}")
async def download_audio_chunk(job_id: str, chunk_id: Optional[str] = None):
    """Specifikus audio chunk letöltése"""
    if not text_reader_service:
        raise HTTPException(status_code=500, detail="Text Reader Service not initialized")
    
    file_path = text_reader_service.get_audio_file(job_id, chunk_id)
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="audio/mpeg"
    )

@router.delete("/api/text-reader/cleanup/{job_id}")
async def cleanup_audio_job(job_id: str):
    """Audio feladat törlése"""
    if not text_reader_service:
        raise HTTPException(status_code=500, detail="Text Reader Service not initialized")
    
    await text_reader_service.cleanup_job(job_id)
    
    return {"message": "Job cleaned up successfully"}

@router.get("/api/text-reader/jobs")
async def list_active_jobs():
    """Aktív feladatok listázása"""
    if not text_reader_service:
        raise HTTPException(status_code=500, detail="Text Reader Service not initialized")
    
    jobs = []
    for job_id, job in text_reader_service.active_jobs.items():
        jobs.append({
            "job_id": job.id,
            "status": job.status,
            "language": job.language,
            "chunk_count": len(job.chunks),
            "created_at": job.created_at.isoformat()
        })
    
    return {"jobs": jobs}