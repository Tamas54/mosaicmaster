# -*- coding: utf-8 -*-
import re
import subprocess
import asyncio
import logging
import os
import sys
import signal
import platform
from pathlib import Path
from typing import Dict, Optional, List, Any, Union, Tuple
from pydantic import BaseModel
from fastapi import HTTPException, BackgroundTasks
import uuid
import time
import json
import aiofiles

# Transzkripciós modul importálása 
from transcriber import _transcribe_audio

# Konfigurációs beállítások importálása
from config import manager, logger, TEMP_DIR, SYSTEM_DOWNLOADS

# Logger konfigurálása
logger = logging.getLogger(__name__)

# Stream-modellek
class StreamSource(BaseModel):
    url: str
    type: str  # youtube, facebook, twitch, other
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    is_live: bool = True
    embed_url: Optional[str] = None
    stream_id: Optional[str] = None

class StreamInfo(BaseModel):
    id: str
    source: StreamSource
    status: str  # active, recording, error, fixing_recording, pending_validation
    recording_path: Optional[str] = None
    proxy_url: Optional[str] = None
    recording_fixed: bool = False  # Jelzi, hogy a felvétel már javítva lett-e
    transcription_id: Optional[str] = None  # A folyamatban lévő átiratolás azonosítója

# Stream-kezelő osztály
class LiveStreamHandler:
    def __init__(self):
        self.active_streams: Dict[str, StreamInfo] = {}
        self.recording_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.proxy_processes: Dict[str, asyncio.subprocess.Process] = {}

        # Könyvtárak létrehozása
        Path("recordings").mkdir(exist_ok=True)
        Path("hls").mkdir(exist_ok=True)
        
        # Transzkripciós folyamatok
        self.transcription_tasks = {}
        
        # SIGTERM kezelése a tiszta leállítás érdekében
        self._register_signal_handlers()

    def _register_signal_handlers(self):
        """Regisztrál handler függvényeket a rendszer jelzésekhez a tiszta leállításhoz"""
        loop = asyncio.get_event_loop()
        try:
            # Windows nem támogatja ezeket
            if platform.system() != "Windows":
                loop.add_signal_handler(signal.SIGTERM, self._handle_termination, signal.SIGTERM, None)
                loop.add_signal_handler(signal.SIGINT, self._handle_termination, signal.SIGINT, None)
            # Megjegyzés: Az add_signal_handler async környezetben preferáltabb, mint a signal.signal
        except NotImplementedError:
            logger.warning("Signal handlers via add_signal_handler are not supported on this platform (likely Windows).")
            # Fallback for simpler environments or tests, less reliable for async cleanup
            try:
                 signal.signal(signal.SIGTERM, self._handle_termination_sync)
                 signal.signal(signal.SIGINT, self._handle_termination_sync)
                 logger.info("Using signal.signal for termination handling.")
            except ValueError as e:
                 # Happens if not called from main thread or other restrictions
                 logger.warning(f"Could not set synchronous signal handlers using signal.signal: {e}")
            except AttributeError:
                 # signal.signal might not be available everywhere (e.g. certain embedded scenarios)
                  logger.warning("signal.signal is not available on this platform.")


    def _handle_termination_sync(self, signum, frame):
        """Synchronous fallback termination handler (less safe for async state)."""
        logger.warning(f"Received signal {signum}. Initiating synchronous termination (may be less clean).")
        # This is risky as it doesn't integrate with the event loop gracefully
        # Try to terminate processes directly using os.kill
        all_pids = []
        # Make copies of PIDs to avoid dictionary size change errors during iteration
        recording_pids = [proc.pid for proc in self.recording_processes.values() if proc and proc.pid]
        proxy_pids = [proc.pid for proc in self.proxy_processes.values() if proc and proc.pid]
        all_pids = recording_pids + proxy_pids

        logger.info(f"Synchronously sending SIGTERM to PIDs: {all_pids}")
        for pid in all_pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                logger.warning(f"(Sync Term) Process with PID {pid} already exited.")
            except Exception as e:
                logger.error(f"(Sync Term) Error sending SIGTERM to PID {pid}: {e}")

        # Give a very short time, then exit forcefully if needed.
        # This part is still problematic in a truly async app.
        time.sleep(0.5) # Blocking sleep, but we are shutting down anyway. Shorter wait.
        logger.info("Exiting after synchronous termination attempt.")
        sys.exit(0)


    def _handle_termination(self, signum, frame):
        """Asynchronous-friendly termination handler triggered by signals."""
        logger.info(f"Received signal {signum}. Initiating graceful shutdown sequence.")
        # We should trigger an async shutdown task rather than doing it here directly.
        # For simplicity now, we still use os.kill but avoid blocking sleeps.
        # A more robust solution would involve setting a flag and having the main loop handle it.

        # Create lists of PIDs to avoid issues if dicts change during iteration
        recording_pids = [proc.pid for proc in self.recording_processes.values() if proc and proc.pid]
        proxy_pids = [proc.pid for proc in self.proxy_processes.values() if proc and proc.pid]

        all_pids = recording_pids + proxy_pids

        logger.info(f"Sending SIGTERM to {len(all_pids)} processes: {all_pids}")
        term_count = 0
        for pid in all_pids:
            try:
                os.kill(pid, signal.SIGTERM)
                term_count += 1
            except ProcessLookupError:
                logger.warning(f"(Async Term) Process {pid} not found during termination signal.")
            except Exception as e:
                logger.error(f"(Async Term) Error sending SIGTERM to PID {pid}: {e}")

        logger.info(f"Sent SIGTERM to {term_count} processes. Scheduling application exit.")
        # Note: FFmpeg might not finish writing files perfectly here.
        # Manual stop via API before shutdown is the safest.

        # Schedule exit very soon to allow loop to process signal sending confirmation etc.
        asyncio.get_event_loop().call_later(0.2, sys.exit, 0)


    # --- ASYNC TERMINATION HELPER ---
    async def _terminate_process(self, process: asyncio.subprocess.Process, timeout: float = 5.0):
        """Asynchronously terminate a process with a grace period."""
        if process is None:
             logger.debug("Terminate called on None process.")
             return
        if process.returncode is not None:
            logger.debug(f"Process {process.pid} already terminated with code {process.returncode}.")
            return

        pid = process.pid
        logger.info(f"Attempting to terminate process {pid} (SIGTERM)...")
        try:
            process.terminate() # Sends SIGTERM
        except ProcessLookupError:
            logger.warning(f"Process {pid} not found during terminate attempt (already exited?).")
            return
        except Exception as e:
            logger.error(f"Error sending SIGTERM to process {pid}: {e}")
            # Attempt SIGKILL immediately if SIGTERM fails
            try:
                logger.warning(f"SIGTERM failed for {pid}, attempting SIGKILL immediately.")
                process.kill() # Sends SIGKILL
                await process.wait() # Wait for kill to complete
            except ProcessLookupError:
                 logger.warning(f"Process {pid} not found during immediate kill attempt.")
            except Exception as kill_e:
                logger.error(f"Error sending SIGKILL to process {pid} after SIGTERM error: {kill_e}")
            return

        try:
            logger.debug(f"Waiting up to {timeout}s for process {pid} to exit gracefully...")
            await asyncio.wait_for(process.wait(), timeout=timeout)
            logger.info(f"Process {pid} terminated gracefully with code {process.returncode}.")
        except asyncio.TimeoutError:
            logger.warning(f"Process {pid} did not terminate within {timeout}s after SIGTERM. Sending SIGKILL.")
            try:
                process.kill() # Sends SIGKILL
                await process.wait() # Wait for kill to complete
                logger.info(f"Process {pid} killed with code {process.returncode}.")
            except ProcessLookupError:
                 logger.warning(f"Process {pid} not found during kill attempt (exited concurrently?).")
            except Exception as e:
                logger.error(f"Error sending SIGKILL or waiting after kill for process {pid}: {e}")
        except Exception as e:
            # Catch other potential errors during wait() like CancelledError
            logger.error(f"Error waiting for process {pid} termination: {e}")
            # Ensure process is likely dead if wait failed unexpectedly
            if process.returncode is None:
                 try:
                     process.kill()
                 except Exception: pass # Ignore errors here, best effort kill


    # --- Stream Detection and Validation ---
    def detect_stream_type(self, url: str) -> StreamSource:
        """Stream típus felismerése URL alapján"""
        youtube_patterns = [
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([^&?\/]+)',
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/live\/([^?\/]+)',
            r'(?:https?:\/\/)?youtu\.be\/([^?\/]+)'
        ]
        facebook_patterns = [
            r'(?:https?:\/\/)?(?:www\.)?facebook\.com\/(?:[^\/]+)\/videos\/(\d+)', # More specific for video ID
            r'(?:https?:\/\/)?(?:www\.)?facebook\.com\/watch\/?(?:\?v=(\d+)|live\/?\?v=(\d+))' # Watch page with video ID
        ]
        twitch_patterns = [
            r'(?:https?:\/\/)?(?:www\.)?twitch\.tv\/([a-zA-Z0-9_]+)$' # Match channel name at the end
        ]
        # YouTube
        for pattern in youtube_patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                logger.debug(f"Detected YouTube stream with ID: {video_id}")
                return StreamSource(url=url, type="youtube", stream_id=video_id, embed_url=f"https://www.youtube.com/embed/{video_id}?autoplay=1")
        # Facebook
        for pattern in facebook_patterns:
            match = re.search(pattern, url)
            if match:
                 # Find the first non-None group which should be the video ID
                 video_id = next((g for g in match.groups() if g is not None), None)
                 logger.debug(f"Detected Facebook stream with ID: {video_id}" if video_id else "Detected Facebook stream (no ID captured)")
                 return StreamSource(url=url, type="facebook", stream_id=video_id, embed_url=url) # Embed URL might need FB JS SDK
        # Twitch
        for pattern in twitch_patterns:
            match = re.search(pattern, url)
            if match:
                channel = match.group(1)
                logger.debug(f"Detected Twitch stream with channel: {channel}")
                # Parent should be the domain serving the player, adjust if needed
                parent_domain = os.getenv("PLAYER_PARENT_DOMAIN", "localhost")
                return StreamSource(url=url, type="twitch", stream_id=channel, embed_url=f"https://player.twitch.tv/?channel={channel}&parent={parent_domain}")
        # Other
        logger.debug(f"Detected stream type as 'other' for URL: {url}")
        return StreamSource(url=url, type="other")


    async def validate_stream(self, stream_source: StreamSource) -> bool:
        """Ellenőrzi, hogy a stream aktív-e"""
        try:
            logger.info(f"Validating stream: {stream_source.url} (Type: {stream_source.type})")
            if stream_source.type == "youtube":
                logger.info(f"Using yt-dlp to check YouTube stream status")
                cmd = ["yt-dlp", "--skip-download", "--no-warnings", "--print", "is_live", stream_source.url]
                process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await process.communicate()
                if process.returncode != 0:
                     logger.warning(f"yt-dlp is_live check failed (Code {process.returncode}): {stderr.decode(errors='ignore')}")
                     return False # Consider if failure means not live or just yt-dlp error
                is_live_str = stdout.decode().strip() if stdout else "False"
                is_live = is_live_str == "True"
                logger.info(f"YouTube stream is_live check result: '{is_live_str}' -> {is_live}")
                if not is_live:
                     logger.warning(f"A YouTube stream nem élő: {stream_source.url}")
                     return False # Explicitly return False if not live
                # Get title if live
                cmd_title = ["yt-dlp", "--skip-download", "--no-warnings", "--print", "title", stream_source.url]
                proc_title = await asyncio.create_subprocess_exec(*cmd_title, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout_title, _ = await proc_title.communicate()
                if proc_title.returncode == 0 and stdout_title:
                    stream_source.title = stdout_title.decode().strip()
                    logger.info(f"Extracted title: {stream_source.title}")
                else:
                     logger.warning("Could not extract title for YouTube stream.")
                return True # Was live

            elif stream_source.type == "twitch":
                logger.info(f"Checking Twitch stream status using yt-dlp to get HLS URL")
                cmd_geturl = ["yt-dlp", "-g", "--no-warnings", stream_source.url]
                proc_geturl = await asyncio.create_subprocess_exec(*cmd_geturl, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout_url, stderr_url = await proc_geturl.communicate()
                if proc_geturl.returncode == 0 and stdout_url:
                    twitch_hls_url = stdout_url.decode().strip()
                    logger.info(f"Got Twitch HLS URL via yt-dlp: {twitch_hls_url[:100]}...")
                    # Optional: Quick ffprobe check on HLS URL (can be slow/unreliable)
                    # cmd_probe = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", twitch_hls_url]
                    # ... run ffprobe ...
                    # For now, assume if yt-dlp gives a URL, it's likely live enough to try
                    stream_source.title = f"Twitch Stream: {stream_source.stream_id}" # Placeholder
                    logger.info(f"Twitch stream assumed active (got HLS URL).")
                    return True
                else:
                    # If yt-dlp fails, it's likely offline or restricted
                    logger.warning(f"Failed to get Twitch HLS URL via yt-dlp (Code {proc_geturl.returncode}): {stderr_url.decode(errors='ignore')}")
                    return False

            elif stream_source.type == "facebook":
                 # FB Live validation is tricky due to potential logins and API changes
                 # A simple ffprobe might work if the URL is direct, but often isn't
                 logger.warning("Facebook stream validation is currently unreliable. Assuming active if URL provided.")
                 # Placeholder title
                 stream_source.title = f"Facebook Stream ({stream_source.stream_id or 'Unknown ID'})"
                 return True # Assume active for now

            else: # 'other' type
                logger.info(f"Stream type 'other'. Attempting ffprobe check.")
                cmd_probe = ["ffprobe", "-v", "error", "-select_streams", "v:0", # Check for video stream
                             "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
                             stream_source.url]
                process = await asyncio.create_subprocess_exec(*cmd_probe, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await process.communicate()
                if process.returncode == 0 and stdout:
                    codec = stdout.decode().strip()
                    logger.info(f"'Other' stream check successful (found video stream, codec: {codec}). Assuming active.")
                    stream_source.title = f"Livestream ({stream_source.type})" # Generic title
                    return True
                else:
                    logger.warning(f"'Other' stream check failed (ffprobe code {process.returncode}): {stderr.decode(errors='ignore')}. Assuming inactive.")
                    return False

        except Exception as e:
            logger.error(f"Error validating stream {stream_source.url}: {e}", exc_info=True)
            return False


    # --- Proxy Stream Handling ---
    async def start_proxy_stream(self, stream_id: str, stream_source: StreamSource) -> str:
        """Proxy stream indítása FFmpeg-gel"""
        try:
            logger.info(f"Starting proxy stream for {stream_id}, type: {stream_source.type}")
            proxy_id = str(uuid.uuid4())
            hls_dir = Path("hls") / f"live_{proxy_id}"
            hls_dir.mkdir(exist_ok=True, parents=True)
            playlist_path = hls_dir / "playlist.m3u8"
            input_args = []
            direct_url = None # Initialize direct_url

            logger.info(f"Extracting stream URL using yt-dlp: {stream_source.url}")
            process_geturl = await asyncio.create_subprocess_exec(
                "yt-dlp", "-g", "--no-warnings", stream_source.url, # Use -g to get URL, let yt-dlp choose format
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process_geturl.communicate()
            if process_geturl.returncode != 0:
                err_msg = stderr.decode(errors='ignore').strip() if stderr else "No error output"
                logger.error(f"Stream URL extraction error via yt-dlp (Code {process_geturl.returncode}): {err_msg}")
                # Fallback for 'other' types if yt-dlp fails but URL might be direct
                if stream_source.type == 'other':
                     logger.warning("yt-dlp failed for 'other' stream, attempting to use original URL directly.")
                     direct_url = stream_source.url
                else:
                    raise Exception(f"Failed to extract stream URL: {err_msg}")
            else:
                direct_url = stdout.decode().strip()

            if not direct_url:
                 raise Exception("Failed to obtain a stream URL.")

            logger.info(f"Using direct URL (first 100 chars): {direct_url[:100]}...")
            input_args = ["-i", direct_url]

            # *** JAVÍTÁS: H.264 Level növelve és jobb audio beállítások ***
            output_args = [
                # Video encoding
                "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
                "-profile:v", "main", # Baseline/Main profile often safer for wide compatibility
                "-level", "4.1",     # Level 4.1 for up to 1080p
                "-crf", "23",        # Constant Rate Factor for quality/size balance
                # Audio encoding - javított beállítások
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-strict", "experimental",
                # HLS settings
                "-hls_time", "4", "-hls_list_size", "10", "-hls_flags", "delete_segments+program_date_time",
                "-start_number", "0",
                 # GOP size: Match keyframe interval to segment duration for better seeking?
                 # Assuming ~30fps, 4s segment -> GOP size 120? Let's use 96 (3s) for safety.
                "-g", "96", "-keyint_min", "96",
                "-sc_threshold", "0", "-f", "hls",
                str(playlist_path)
            ]
            # Use input flags before -i
            ffmpeg_input_flags = ["-hide_banner", "-loglevel", "warning", "-fflags", "+genpts"] # Add genpts for input
            cmd = ["ffmpeg", *ffmpeg_input_flags, *input_args, *output_args]

            logger.info(f"Starting FFmpeg for proxy stream: {' '.join(cmd)}")
            process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

            # Check if process started successfully immediately (optional, basic check)
            await asyncio.sleep(0.5) # Give a brief moment for potential instant crash
            if process.returncode is not None:
                 stdout, stderr = await process.communicate() # Get error message
                 stderr_text = stderr.decode(errors='ignore').strip() if stderr else "No output"
                 logger.error(f"FFmpeg proxy process failed immediately (Code {process.returncode}): {stderr_text}")
                 raise Exception(f"FFmpeg proxy failed on startup: {stderr_text}")

            self.proxy_processes[stream_id] = process
            # Pass PID for logging in monitor task
            asyncio.create_task(self._monitor_process(stream_id, process, "Proxy"))
            proxy_url = f"/hls/live_{proxy_id}/playlist.m3u8"
            logger.info(f"Proxy stream started for {stream_id} (PID: {process.pid}): {proxy_url}")
            return proxy_url
        except Exception as e:
            logger.error(f"Error starting proxy stream for {stream_id}: {e}", exc_info=True)
            # Clean up process if it started but failed later
            if stream_id in self.proxy_processes:
                 proc = self.proxy_processes.pop(stream_id) # Use pop
                 await self._terminate_process(proc)
            raise HTTPException(status_code=500, detail=f"Failed to start proxy stream: {str(e)}")


    # --- Recording Handling ---
    async def start_recording(self, stream_id: str) -> str:
        """Stream felvétel indítása"""
        if stream_id not in self.active_streams:
            logger.error(f"Cannot start recording: Stream {stream_id} not found")
            raise HTTPException(status_code=404, detail="Stream not found")

        if stream_id in self.recording_processes:
            logger.warning(f"Recording already in progress for stream {stream_id}")
            raise HTTPException(status_code=400, detail="Recording already in progress")

        stream_info = self.active_streams[stream_id]
        stream_source = stream_info.source

        try:
            logger.info(f"Starting recording for stream {stream_id}, type: {stream_source.type}")
            recordings_dir = Path("recordings")
            recordings_dir.mkdir(exist_ok=True)
            timestamp = int(time.time())
            stream_type = stream_source.type
            identifier = stream_source.stream_id or "stream"
            # Ensure title exists and is safe for filename
            title_text = stream_source.title or "untitled"
            title_safe = ''.join(c if c.isalnum() or c in ['_','-'] else '_' for c in title_text)
            title_safe = title_safe.strip('_').strip('-') # Remove leading/trailing separators
            if not title_safe: title_safe = "untitled" # Ensure not empty
            title_safe = title_safe[:50] # Limit length
            output_file = recordings_dir / f"{stream_type}_{identifier}_{title_safe}_{timestamp}.mp4"

            input_args = []
            direct_url = None # Initialize direct_url

            logger.info(f"Extracting stream URL for recording using yt-dlp: {stream_source.url}")
            process_geturl = await asyncio.create_subprocess_exec(
                "yt-dlp", "-g", "--no-warnings", stream_source.url, # Use -g to get URL, let yt-dlp choose format
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process_geturl.communicate()

            if process_geturl.returncode != 0:
                err_msg = stderr.decode(errors='ignore').strip() if stderr else "No error output"
                logger.error(f"Failed to extract stream URL for recording via yt-dlp (Code {process_geturl.returncode}): {err_msg}")
                # Fallback for 'other' types if yt-dlp fails but URL might be direct
                if stream_source.type == 'other':
                     logger.warning("yt-dlp failed for 'other' stream recording, attempting to use original URL directly.")
                     direct_url = stream_source.url
                else:
                     raise Exception(f"Failed to extract stream URL for recording: {err_msg}")
            else:
                 direct_url = stdout.decode().strip()

            if not direct_url:
                 raise Exception("Failed to obtain a stream URL for recording.")

            logger.info(f"Using extracted URL for recording (first 100 chars): {direct_url[:100]}...")
            input_args = ["-i", direct_url]

            # *** JAVÍTÁS: Explicit audio újrakódolás hozzáadva ***
            output_args = [
                "-c:v", "copy",              # Copy video stream
                "-c:a", "aac",               # Explicit AAC újrakódolás a hang kompatibilitás érdekében
                "-b:a", "192k",              # Jó minőségű hang biztosítása
                "-ar", "48000",              # Standard mintavételi frekvencia
                "-strict", "experimental",   # Bizonyos codec-ek miatt esetleg szükséges
                "-movflags", "+faststart+frag_keyframe+empty_moov", # Resilient MP4 flags
                "-avoid_negative_ts", "make_zero", # Correct negative timestamps
                "-map", "0",                 # Map all streams from input 0
                "-f", "mp4",
                str(output_file)
            ]

            # Input flags should generally go before -i
            # genpts might cause issues with -c copy if timestamps are already okay. Test removal if problems persist.
            ffmpeg_input_flags = ["-hide_banner", "-loglevel", "warning", "-fflags", "+genpts"]
            cmd = ["ffmpeg", *ffmpeg_input_flags, *input_args, *output_args]

            logger.info(f"Starting recording: {' '.join(cmd)}")
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            # Check if process started successfully immediately
            await asyncio.sleep(0.5) # Brief wait
            if process.returncode is not None:
                 stdout, stderr = await process.communicate()
                 stderr_text = stderr.decode(errors='ignore').strip() if stderr else "No output"
                 logger.error(f"FFmpeg recording process failed immediately (Code {process.returncode}): {stderr_text}")
                 raise Exception(f"FFmpeg recording failed on startup: {stderr_text}")

            self.recording_processes[stream_id] = process
            stream_info.status = "recording"
            stream_info.recording_path = str(output_file)
            stream_info.recording_fixed = False # Reset fixed status on new recording

            # Pass PID for logging in monitor task
            asyncio.create_task(self._monitor_process(stream_id, process, "Recording"))

            logger.info(f"Recording started for stream {stream_id} (PID: {process.pid}) to {output_file}")
            return str(output_file)

        except Exception as e:
            logger.error(f"Error starting recording for {stream_id}: {e}", exc_info=True)
            # Clean up stream status if needed
            if stream_id in self.active_streams:
                 self.active_streams[stream_id].status = "error"
                 self.active_streams[stream_id].recording_path = None
            # Ensure no lingering process entry
            if stream_id in self.recording_processes:
                 # Try to kill if process object exists but might not be running
                 proc = self.recording_processes.pop(stream_id)
                 await self._terminate_process(proc)
            raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")


    # --- Unified Process Monitor ---
    async def _monitor_process(self, stream_id: str, process: asyncio.subprocess.Process, process_type: str):
        """Monitors a subprocess (Recording or Proxy) and handles completion/errors."""
        if process is None:
             logger.warning(f"Monitor called with None process for stream {stream_id}, type {process_type}. Cannot monitor.")
             return

        pid = process.pid
        logger.info(f"Monitoring {process_type} process for stream {stream_id} (PID: {pid})")
        stderr_text = f"{process_type} process {pid} monitoring did not capture stderr." # Default
        try:
            # Capture stderr continuously in background? More complex.
            # For now, rely on communicate() to get it at the end.
            stdout, stderr = await process.communicate() # Wait for process to exit
            return_code = process.returncode
            stderr_text = stderr.decode(errors='ignore').strip() if stderr else "No error output"
        except Exception as e:
            logger.error(f"Error communicating with {process_type} process {pid}: {e}", exc_info=True)
            # Process might be dead or unresponsive, try to get return code if possible
            return_code = process.returncode if hasattr(process, 'returncode') and process.returncode is not None else -999 # Assign arbitrary error code
            stderr_text += f" Communication error: {e}"

        stream_info = self.active_streams.get(stream_id)
        log_prefix = f"{process_type} process (PID: {pid}, Stream: {stream_id})"

        # Log outcome
        if return_code == 0:
            logger.info(f"{log_prefix} completed successfully.")
        elif return_code is not None and return_code < 0: # Termination by signal
             try:
                 signal_name = signal.Signals(abs(return_code)).name
             except ValueError:
                 signal_name = f"Signal {abs(return_code)}"
             logger.warning(f"{log_prefix} terminated by {signal_name} (code {return_code}).")
        elif return_code is None: # Should not happen after communicate(), but handle defensively
            logger.error(f"{log_prefix} monitoring finished but return code is None. Process state unclear.")
        else: # Error exit code
            logger.error(f"{log_prefix} exited with error code {return_code}: {stderr_text}")

        # --- Cleanup based on process type ---
        try:
            if process_type == "Recording":
                # Remove from recording processes dict if it still matches the monitored process
                current_proc = self.recording_processes.get(stream_id)
                if current_proc and current_proc.pid == pid:
                    del self.recording_processes[stream_id]
                    logger.debug(f"Removed recording process {pid} from active list.")
                elif current_proc:
                     logger.warning(f"Monitored recording process {pid} finished, but a different process ({current_proc.pid}) is now listed for stream {stream_id}.")
                # else: Process already removed or never added correctly

                recording_path = stream_info.recording_path if stream_info else None
                file_exists = recording_path and os.path.exists(recording_path)
                file_has_size = file_exists and os.path.getsize(recording_path) > 0

                # Attempt to fix recording unless it was a clean exit (0)
                # Also fix on SIGTERM (-15) as it might not be perfectly closed.
                # Don't try to fix if killed (-9) or other negative signals, likely corrupted.
                # Also don't fix if file doesn't exist or is empty.
                should_fix = (return_code != 0 and (return_code is None or return_code > 0 or return_code == -15) and
                              file_has_size)

                if should_fix:
                    logger.info(f"{log_prefix}: Recording process did not exit cleanly (code {return_code}). Attempting to fix file: {recording_path}")
                    try:
                        fixed = await self._fix_broken_recording(recording_path)
                        if stream_info: stream_info.recording_fixed = fixed
                    except Exception as fix_e:
                         logger.error(f"Error during attempt to fix recording {recording_path}: {fix_e}", exc_info=True)
                         if stream_info: stream_info.recording_fixed = False
                elif return_code == 0 and file_has_size:
                     logger.info(f"{log_prefix}: Recording finished cleanly. File: {recording_path}")
                     if stream_info: stream_info.recording_fixed = True # Mark as likely okay
                elif not file_exists and recording_path: # Check path existed
                     logger.warning(f"{log_prefix}: Recording file not found after process exit: {recording_path}")
                elif file_exists and not file_has_size: # Check exists but empty
                     logger.warning(f"{log_prefix}: Recording file is empty after process exit: {recording_path}")
                     # Optionally delete empty file
                     try: os.remove(recording_path)
                     except Exception as e: logger.warning(f"Could not remove empty file {recording_path}: {e}")

                # Update stream status only if the stream still exists and status was 'recording'
                if stream_info and stream_info.status == "recording":
                     is_error_state = return_code != 0 and return_code != -15 # Not clean exit or sigterm
                     stream_info.status = "error" if is_error_state else "active"
                     logger.info(f"{log_prefix}: Stream status updated to '{stream_info.status}'")
                     # Maybe clear path if error and not fixed? Let's keep it for inspection for now.

            elif process_type == "Proxy":
                # Remove from proxy processes dict if it matches
                current_proc = self.proxy_processes.get(stream_id)
                if current_proc and current_proc.pid == pid:
                    del self.proxy_processes[stream_id]
                    logger.debug(f"Removed proxy process {pid} from active list.")
                elif current_proc:
                     logger.warning(f"Monitored proxy process {pid} finished, but a different process ({current_proc.pid}) is now listed for stream {stream_id}.")
                # else: Process already removed or never added correctly

                # Update stream status if proxy failed (ignore clean exit 0 or SIGTERM -15)
                if return_code != 0 and return_code != -15 and stream_info:
                     if stream_info.status == "active": # Only set error if it wasn't already recording etc.
                          stream_info.status = "error"
                          logger.error(f"{log_prefix}: Proxy process failed. Stream status set to error.")
                # Clean up HLS files? Could be complex. Manual cleanup might be better.

        except Exception as monitor_cleanup_e:
             logger.error(f"Error during {process_type} monitor cleanup for {stream_id} (PID {pid}): {monitor_cleanup_e}", exc_info=True)

        logger.info(f"Finished monitoring {process_type} process for stream {stream_id} (PID: {pid})")


    async def _fix_broken_recording(self, file_path: str) -> bool:
        """Hibás felvételi fájl javítása (indexek újraépítése, konténer javítása)"""
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.error(f"Cannot fix recording, file not found: {file_path}")
                return False
            if file_path_obj.stat().st_size == 0:
                logger.warning(f"Cannot fix recording, file is empty: {file_path}")
                # Optionally delete the empty file here?
                try: file_path_obj.unlink()
                except OSError as e: logger.warning(f"Could not remove empty file {file_path}: {e}")
                return False # Cannot fix empty file

            logger.info(f"Attempting to fix potentially broken recording: {file_path}")
            # Use Path objects for consistency
            temp_path_obj = file_path_obj.with_suffix(".fixed.mp4")
            temp_path = str(temp_path_obj)

            # Ensure temp file does not exist from previous failed attempt
            if temp_path_obj.exists():
                 try:
                    logger.warning(f"Removing existing temporary file: {temp_path}")
                    temp_path_obj.unlink()
                 except OSError as e:
                    logger.error(f"Could not remove existing temp file {temp_path}: {e}. Cannot proceed with fix.")
                    return False

            # Command for fixing - használjuk az explicit audio újrakódolást itt is!
            # Az audio stream problémák miatt jobb, ha nem csak másolunk, hanem explicit AAC-re kódolunk.
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "warning",
                "-i", file_path,
                "-c:v", "copy",               # Copy video
                "-c:a", "aac",                # Explicit AAC újrakódolás a hang kompatibilitás érdekében
                "-b:a", "192k",               # Jó minőségű hang biztosítása
                "-ar", "48000",               # Standard mintavételi frekvencia
                "-strict", "experimental",    # Bizonyos codec-ek miatt esetleg szükséges
                "-movflags", "+faststart+frag_keyframe+empty_moov", # Rebuild indexes
                "-avoid_negative_ts", "make_zero", # Fix timestamps
                "-map", "0", # Ensure all streams are mapped
                "-f", "mp4",
                temp_path
            ]

            logger.info(f"Running fix command: {' '.join(cmd)}")
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            stderr_text = stderr.decode(errors='ignore').strip() if stderr else "No error output"

            # Check if fix process succeeded AND the temp file exists and has size
            fix_succeeded = process.returncode == 0
            temp_file_valid = temp_path_obj.exists() and temp_path_obj.stat().st_size > 0

            if fix_succeeded and temp_file_valid:
                logger.info(f"FFmpeg fix process completed successfully for {file_path}.")
                try:
                    logger.info(f"Replacing original file '{file_path}' with fixed version '{temp_path}'.")
                    # Use os.replace for potential atomicity
                    os.replace(temp_path, file_path)
                    logger.info(f"Successfully fixed and replaced recording file: {file_path}")
                    return True
                except Exception as e:
                    logger.error(f"Error replacing original file '{file_path}' after fix: {e}", exc_info=True)
                    # Try to clean up temp file if replacement failed
                    try: temp_path_obj.unlink()
                    except OSError: pass
                    return False
            else:
                # Fixing failed
                logger.error(f"Failed to fix recording '{file_path}'. FFmpeg exit code {process.returncode}. Temp file valid: {temp_file_valid}. Stderr: {stderr_text}")
                # Clean up failed or empty temp file
                if temp_path_obj.exists():
                    try:
                        logger.debug(f"Removing failed temporary fix file: {temp_path}")
                        temp_path_obj.unlink()
                    except OSError as e:
                         logger.warning(f"Could not remove failed temp file {temp_path}: {e}")
                # Original file might still be useful, don't delete it automatically.
                return False

        except Exception as e:
            logger.error(f"Exception during recording fix attempt for {file_path}: {e}", exc_info=True)
            return False

    async def stop_recording(self, stream_id: str) -> dict:
        """Stream felvétel leállítása (aszinkron módon)"""
        if stream_id not in self.active_streams:
            logger.error(f"Cannot stop recording: Stream {stream_id} not found in active_streams.")
            raise HTTPException(status_code=404, detail="Stream not found")

        stream_info = self.active_streams.get(stream_id) # Use get for safety
        if not stream_info:
             logger.error(f"Stream info inconsistency for {stream_id} during stop request.")
             raise HTTPException(status_code=404, detail="Stream info inconsistency")

        # Check if a process actually exists for this stream ID
        process = self.recording_processes.pop(stream_id, None) # Remove from dict immediately if present
        if not process:
             logger.warning(f"Stop recording requested for {stream_id}, but no active recording process found.")
             # Check status consistency
             if stream_info.status == "recording":
                 logger.warning(f"Stream {stream_id} status is 'recording' but no process was found. Resetting status to 'active'.")
                 stream_info.status = "active"
                 stream_info.recording_path = None
                 stream_info.recording_fixed = False
             # Even if status wasn't 'recording', report no active process
             raise HTTPException(status_code=404, detail="No active recording process found for this stream")

        # If we got here, a process was found and removed from the dict
        recording_path = stream_info.recording_path # Get path before clearing or changing status

        try:
            logger.info(f"Stopping recording for stream {stream_id} (PID: {process.pid})...")
            # Use the async terminate helper
            await self._terminate_process(process, timeout=10.0) # Give 10s grace period

            # Process termination attempted (gracefully or forcefully)
            logger.info(f"Recording process termination attempt finished for stream {stream_id} (PID: {process.pid}).")

            # Update stream status *after* termination attempt completes
            stream_info.status = "active" # Revert to active after stopping
            stream_info.recording_path = None # Clear current recording path in info object
            stream_info.recording_fixed = False # Reset fixed status

            result = {
                "status": "success",
                "stream_id": stream_id,
                "recording_stopped": True,
                "recording_path": None, # Initialize path
                "fix_attempted": False,
                "fix_successful": None,
                "video_added": False, # Default to false
            }

            # Attempt to fix the file after stopping
            file_exists = recording_path and os.path.exists(recording_path)
            file_has_size = file_exists and os.path.getsize(recording_path) > 0

            if file_has_size:
                logger.info(f"Attempting to finalize/fix recording file after manual stop: {recording_path}")
                result["fix_attempted"] = True
                try:
                    fix_success = await self._fix_broken_recording(recording_path)
                    result["fix_successful"] = fix_success
                    # Check again if file exists and has size *after* fix attempt
                    if fix_success and os.path.exists(recording_path) and os.path.getsize(recording_path) > 0:
                        result["recording_path"] = recording_path
                        result["video_added"] = True # Indicate to caller this video is ready
                        stream_info.recording_fixed = True # Update status in stream_info too
                    elif not fix_success:
                         logger.warning(f"Fixing failed for {recording_path} after manual stop.")
                         result["recording_path"] = recording_path # Still return path, but fix failed
                         # video_added remains false
                    else: # Fix reported success but file missing/empty? Should not happen with os.replace
                         logger.error(f"Fix reported success but file {recording_path} is invalid post-fix.")
                         result["recording_path"] = None # Don't return invalid path
                         # video_added remains false

                except Exception as e:
                    logger.error(f"Error during post-stop fix for {recording_path}: {e}", exc_info=True)
                    result["fix_successful"] = False
                    result["recording_path"] = recording_path # Return path even if fix crashed
                    # video_added remains false
            elif file_exists and not file_has_size:
                 logger.warning(f"Recording file {recording_path} is empty after stopping. Discarding.")
                 try: os.remove(recording_path)
                 except OSError as e: logger.warning(f"Could not remove empty file {recording_path}: {e}")
            elif recording_path: # Path existed but file doesn't
                 logger.warning(f"Recording file {recording_path} not found after stopping.")

            return result

        except Exception as e:
            logger.error(f"Error stopping recording for stream {stream_id}: {e}", exc_info=True)
            # Ensure stream status is updated even on error
            if stream_id in self.active_streams:
                 stream_info = self.active_streams[stream_id]
                 stream_info.status = "error" # Set to error on failure
                 stream_info.recording_path = None
                 stream_info.recording_fixed = False
            # Process was already popped, no need to check recording_processes dict again
            raise HTTPException(status_code=500, detail=f"Failed to stop recording: {str(e)}")

    async def cleanup_stream(self, stream_id: str):
        """Stream erőforrások felszabadítása (aszinkron)"""
        logger.info(f"Cleaning up resources for stream {stream_id}")
        stream_info = self.active_streams.pop(stream_id, None) # Remove stream info first

        # Stop recording process if active
        process_rec = self.recording_processes.pop(stream_id, None) # Use pop with default None
        if process_rec:
            logger.info(f"Stopping recording process during cleanup for stream {stream_id} (PID: {process_rec.pid})...")
            await self._terminate_process(process_rec, timeout=5.0) # Shorter timeout for general cleanup
            # Don't attempt fix during generic cleanup. Check for empty file.
            recording_path = stream_info.recording_path if stream_info else None
            if recording_path:
                try:
                    if os.path.exists(recording_path) and os.path.getsize(recording_path) == 0:
                        logger.warning(f"Removing empty recording file during cleanup: {recording_path}")
                        os.remove(recording_path)
                except OSError as e:
                    logger.warning(f"Error checking/removing recording file {recording_path} during cleanup: {e}")

        # Stop proxy process if active
        process_proxy = self.proxy_processes.pop(stream_id, None) # Use pop with default None
        if process_proxy:
            logger.info(f"Stopping proxy process during cleanup for stream {stream_id} (PID: {process_proxy.pid})...")
            await self._terminate_process(process_proxy, timeout=2.0) # Even shorter timeout for proxy

        if stream_info:
             logger.info(f"Removed stream info for {stream_id}")
        else:
             logger.debug(f"Cleanup called for stream {stream_id}, but it was not found in active_streams (might have been removed already).")


# Élő stream transzkripció funkció
async def live_transcribe_stream(stream_id: str, recording_path: str, background_tasks: BackgroundTasks):
    """
    Elindítja az élő stream átiratolását a háttérben
    
    Args:
        stream_id: Az élő stream azonosítója
        recording_path: A felvétel elérési útja
        background_tasks: BackgroundTasks objektum a háttérben futó feladatokhoz
    """
    handler = live_stream_handler
    
    if stream_id not in handler.active_streams:
        logger.error(f"Stream not found for live transcription: {stream_id}")
        return
    
    stream_info = handler.active_streams[stream_id]
    
    if not os.path.exists(recording_path):
        logger.error(f"Recording file not found: {recording_path}")
        return
    
    # Munkkönyvtár létrehozása
    work_dir = TEMP_DIR / f"live_transcription_{stream_id}"
    work_dir.mkdir(exist_ok=True, parents=True)
    
    # Átiratolás azonosító
    transcription_id = str(uuid.uuid4())
    stream_info.transcription_id = transcription_id
    
    async def _transcribe_background():
        try:
            # Haladás jelzése
            await manager.send_progress(stream_id, 10, "Élő átiratolás kezdeményezése...")
            
            # Átiratolás elindítása gyors módban
            # Megváltozott: fast_mode=True, gyorsabb feldolgozáshoz
            text, format_info = await _transcribe_audio(
                Path(recording_path),
                identify_speakers=True,
                fast_mode=True  # Gyorsabb feldolgozás
            )
            
            # Ellenőrzés, hogy a formátum információ megfelelő-e
            segments = []
            if format_info and isinstance(format_info, dict):
                format_segments = format_info.get("segments")
                if format_segments and isinstance(format_segments, list):
                    segments = format_segments
            
            # Átiratolás eredményének mentése
            timestamp = int(time.time())
            output_filename = f"live_transcript_{stream_id}_{timestamp}.txt"
            output_path = SYSTEM_DOWNLOADS / output_filename
            
            # Szegmensek formázása és mentése
            if segments:
                try:
                    # TXT jegyzőkönyv formázása szegmensekkel
                    from transcriber import generate_transcript_txt
                    await generate_transcript_txt(segments, output_path, with_timestamps=True)
                except Exception as format_error:
                    logger.error(f"Error formatting transcript: {format_error}")
                    # Fallback: egyszerű szöveg mentése
                    async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                        await f.write(text)
            else:
                # Ha nincsenek szegmensek, egyszerűen mentsük el a szöveget
                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write(text)
            
            # Haladás jelzése
            await manager.send_progress(stream_id, 100, "Élő átiratolás elkészült")
            
            # Eredmény készítése
            result = {
                "status": "completed",
                "transcript_id": transcription_id,
                "download_url": f"/download/{output_filename}",
                "text": text
            }
            
            # Frissítsük a stream információit
            if stream_id in handler.active_streams:
                current_stream = handler.active_streams[stream_id]
                if current_stream.transcription_id == transcription_id:
                    current_stream.transcription_id = None
            
            # Task törlése
            if transcription_id in handler.transcription_tasks:
                del handler.transcription_tasks[transcription_id]
            
        except Exception as e:
            logger.error(f"Live transcription error: {e}")
            
            # Egyszerű hibaüzenet mentése fájlba
            try:
                timestamp = int(time.time())
                error_filename = f"failed_transcript_{stream_id}_{timestamp}.txt"
                error_path = SYSTEM_DOWNLOADS / error_filename
                
                async with aiofiles.open(error_path, "w", encoding="utf-8") as f:
                    await f.write(f"Hiba történt a leiratolás során: {str(e)}\n\nIdőbélyeg: {timestamp}")
            except Exception as file_error:
                logger.error(f"Error saving error transcript: {file_error}")
                
            # Stream információk frissítése
            if stream_id in handler.active_streams:
                current_stream = handler.active_streams[stream_id]
                if current_stream.transcription_id == transcription_id:
                    current_stream.transcription_id = None
            
            # Task törlése hiba esetén is
            if transcription_id in handler.transcription_tasks:
                del handler.transcription_tasks[transcription_id]
    
    # Ellenőrizzük, hogy már van-e folyamatban lévő transzkripció
    if stream_info.transcription_id and stream_info.transcription_id in handler.transcription_tasks:
        # Leállítjuk a korábbi feladatot
        old_task = handler.transcription_tasks[stream_info.transcription_id]
        if not old_task.done():
            old_task.cancel()
            try:
                # Várjunk egy rövid ideig a feladat leállására
                await asyncio.wait_for(asyncio.shield(old_task), timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass  # Ignoráljuk a megszakítási kivételt
            except Exception as e:
                logger.error(f"Error cancelling previous transcription task: {e}")
        
        # Töröljük a régi feladatot
        if stream_info.transcription_id in handler.transcription_tasks:
            del handler.transcription_tasks[stream_info.transcription_id]
    
    # Aszinkron feladat indítása
    task = asyncio.create_task(_transcribe_background())
    handler.transcription_tasks[transcription_id] = task
    
    # Naplózzuk a feladat elindítását
    logger.info(f"Started transcription task {transcription_id} for stream {stream_id}")
    
    return {
        "status": "started", 
        "transcription_id": transcription_id
    }

# Globális példány
live_stream_handler = LiveStreamHandler()

# Example usage (for testing, requires an event loop)
# Commented out by default, uncomment to run standalone test
# async def main_test():
#     # --- TESTING CODE ---
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     handler = live_stream_handler # Use the global instance
#
#     # Example: Add a stream (replace with a valid live URL for testing)
#     test_url = "https://www.youtube.com/watch?v=jfKfPfyJRdk" # Example Lo-fi Girl
#
#     source = handler.detect_stream_type(test_url)
#     stream_id = str(uuid.uuid4())
#
#     logger.info(f"--- Starting Test for Stream ID: {stream_id} ---")
#
#     # 1. Add stream info (validation happens next)
#     stream_info = StreamInfo(id=stream_id, source=source, status="pending_validation")
#     handler.active_streams[stream_id] = stream_info
#     logger.info(f"Added stream info: {stream_info.model_dump_json(indent=2)}")
#
#     # 2. Validate stream
#     is_valid = await handler.validate_stream(source)
#     if not is_valid:
#         logger.error("Stream validation failed. Exiting test.")
#         if stream_id in handler.active_streams: del handler.active_streams[stream_id] # Clean up info
#         return
#
#     stream_info.status = "active" # Mark as active after validation
#     logger.info(f"Stream validated. Title: {source.title}")
#
#     # 3. Start Recording
#     try:
#         recording_path = await handler.start_recording(stream_id)
#         logger.info(f"Recording started, path: {recording_path}")
#         logger.info("Waiting 30 seconds before stopping recording...")
#         await asyncio.sleep(30)
#
#         # 4. Stop Recording
#         logger.info("--- Stopping Recording ---")
#         stop_result = await handler.stop_recording(stream_id)
#         logger.info(f"Stop recording result: {json.dumps(stop_result, indent=2)}")
#
#         # Check file
#         final_path = stop_result.get("recording_path")
#         if final_path:
#             logger.info(f"Final recording path: {final_path}")
#             try:
#                 if os.path.exists(final_path):
#                     file_size = os.path.getsize(final_path)
#                     logger.info(f"File size: {file_size / 1024 / 1024:.2f} MB")
#                     if file_size == 0:
#                          logger.error("Recording resulted in an empty file!")
#                 else:
#                      logger.error("Final recording file does not exist after stop/fix!")
#             except OSError as e:
#                  logger.error(f"Error accessing final file {final_path}: {e}")
#         else:
#              logger.warning("No final recording path returned after stop.")
#
#     except HTTPException as http_exc:
#          logger.error(f"HTTP Exception during test: Status={http_exc.status_code}, Detail={http_exc.detail}")
#     except Exception as e:
#         logger.error(f"An unexpected error occurred during recording test: {e}", exc_info=True)
#
#     # 5. Cleanup
#     finally:
#         logger.info(f"--- Cleaning up Stream ID: {stream_id} ---")
#         await handler.cleanup_stream(stream_id) # Use the instance method
#         logger.info("Test cleanup complete.")
#         # Verify cleanup
#         logger.info(f"Stream active? {stream_id in handler.active_streams}")
#         logger.info(f"Recording process active? {stream_id in handler.recording_processes}")
#         logger.info(f"Proxy process active? {stream_id in handler.proxy_processes}")
#
# if __name__ == "__main__":
#     try:
#         asyncio.run(main_test())
#     except KeyboardInterrupt:
#         logger.info("Test interrupted by user.")
#     finally:
#         # Standard asyncio cleanup pattern
#         try:
#             loop = asyncio.get_running_loop()
#             tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]
#             if tasks:
#                  [task.cancel() for task in tasks]
#                  loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
#             loop.run_until_complete(loop.shutdown_asyncgens())
#             # loop.close() # asyncio.run() handles loop closing
#             logger.info("Async tasks cancelled and shutdown complete.")
#         except RuntimeError as e:
#              # Ignore "cannot schedule new futures after shutdown" if loop is already closing
#              if "shutdown" not in str(e):
#                  logger.warning(f"Error during final cleanup: {e}")
#         except Exception as e:
#              logger.error(f"Unexpected error during final cleanup: {e}")

# --- END OF FILE ---