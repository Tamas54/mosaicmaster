import asyncio
import uuid
import os
import json
import logging
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from functools import partial

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from urllib.parse import quote

# Import configuration
from config import (
    TEMP_DIR,
    SYSTEM_DOWNLOADS,
    manager,
    logger,
    process_semaphore
)

router = APIRouter()

async def async_rmtree(path: Path):
    """Asynchronously remove a directory tree"""
    if not path.exists():
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(shutil.rmtree, path, ignore_errors=True))

async def run_ffmpeg_command(cmd: List[str], connection_id: str, progress_message: str) -> bool:
    """Run an FFmpeg command and update progress"""
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg command failed: {stderr.decode()}")
            await manager.send_progress(connection_id, 100, f"Error: {stderr.decode()[:100]}...")
            return False
        
        await manager.send_progress(connection_id, 100, progress_message)
        return True
    except Exception as e:
        logger.error(f"Error running FFmpeg command: {e}")
        await manager.send_progress(connection_id, 100, f"Error: {str(e)}")
        return False

async def run_mkvtoolnix_command(cmd: List[str], connection_id: str, progress_message: str) -> bool:
    """Run an MKVToolNix command and update progress"""
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"MKVToolNix command failed: {stderr.decode()}")
            await manager.send_progress(connection_id, 100, f"Error: {stderr.decode()[:100]}...")
            return False
        
        await manager.send_progress(connection_id, 100, progress_message)
        return True
    except Exception as e:
        logger.error(f"Error running MKVToolNix command: {e}")
        await manager.send_progress(connection_id, 100, f"Error: {str(e)}")
        return False

@router.post("/convert")
async def convert_video(
    file: UploadFile = File(...),
    target_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Convert video file to a different format (specifically for MKV to MP4 conversion)"""
    logger.info(f"Starting conversion. File: {file.filename}, Size: {file.size}, Type: {file.content_type}")
    
    if not connection_id:
        connection_id = str(uuid.uuid4())
    logger.info(f"Using connection ID: {connection_id}")
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    logger.info(f"Created work directory: {work_dir}")
    
    try:
        # Save uploaded file
        input_path = work_dir / file.filename
        logger.info(f"Saving uploaded file to: {input_path}")
        
        content = await file.read()
        logger.info(f"Read {len(content)} bytes from upload")
        
        async with aiofiles.open(input_path, "wb") as f:
            await f.write(content)
        logger.info(f"File saved successfully")
        
        if not input_path.exists():
            logger.error(f"File not saved correctly: {input_path}")
            raise HTTPException(status_code=500, detail="File save error")
        
        await manager.send_progress(connection_id, 20, "Videó formátum konvertálása...")
        
        # Determine file extension
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        # Prepare output filename (changing extension to target format)
        base_filename = os.path.splitext(file.filename)[0]
        output_filename = f"{base_filename}_converted.{target_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # We'll use more compatible encoding parameters for better browser support
        if file_ext == '.mkv' and target_format.lower() == 'mp4':
            # MKV to MP4 conversion using FFmpeg
            ffmpeg_cmd = [
                "ffmpeg",
                "-hwaccel", "auto",    # Enable hardware acceleration if available
                "-i", str(input_path),
                "-c:v", "libx264",     # Use H.264, most compatible codec
                "-profile:v", "high",  # Use high profile for better quality
                "-level", "4.0",       # Compatibility level
                "-preset", "veryfast", # Faster encoding (was medium)
                "-crf", "22",          # Higher quality (lower value)
                "-c:a", "aac",         # AAC audio
                "-b:a", "192k",        # Higher audio bitrate
                "-ar", "44100",        # Standard audio sample rate
                "-pix_fmt", "yuv420p", # Most compatible pixel format
                "-movflags", "+faststart",  # Optimize for web playback
                "-threads", "0",        # Use all available CPU threads
                str(output_path),
                "-y"
            ]
            
            # Run the FFmpeg command
            await manager.send_progress(connection_id, 30, "Videó konténer konvertálása...")
            success = await run_ffmpeg_command(
                ffmpeg_cmd,
                connection_id,
                "Videó konvertálás befejeződött"
            )
            
            if not success:
                raise HTTPException(status_code=500, detail="Videó konvertálás sikertelen")
            
            # Return result
            return JSONResponse({
                "download_url": f"/download/{output_filename}",
                "original_format": "mkv",
                "converted_format": "mp4",
                "message": "A videó sikeresen konvertálva MP4 formátumba"
            })
            
        else:
            # For other conversions or if not MKV to MP4
            raise HTTPException(status_code=400, detail=f"Nem támogatott konverzió: {file_ext} → {target_format}")
    
    except Exception as e:
        logger.error(f"Video conversion error: {e}")
        raise HTTPException(status_code=500, detail=f"Videó konvertálás sikertelen: {str(e)}")
    
    finally:
        # Clean up work directory
        if work_dir.exists():
            await async_rmtree(work_dir)

@router.post("/trim")
async def trim_video(
    file: Optional[UploadFile] = File(None),
    start_time: str = Form(...),  # Format: "00:00:00"
    end_time: str = Form(...),    # Format: "00:00:00"
    output_format: str = Form("mp4"),
    extract_audio: bool = Form(False),
    preserve_subtitles: bool = Form(False),
    connection_id: Optional[str] = Form(None),
    server_filename: Optional[str] = Form(None),
    is_server_file: bool = Form(False)
):
    """Trim a video file to the specified start and end times"""
    # Ellenőrizzük, hogy a kezdő idő korábbi-e a vég időnél
    def time_to_seconds(time_str):
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                h, m, s = map(float, parts)
                return h * 3600 + m * 60 + s
            elif len(parts) == 2:
                m, s = map(float, parts)
                return m * 60 + s
            else:
                return float(time_str)
        except Exception as e:
            logger.error(f"Error parsing time string '{time_str}': {e}")
            return 0
        
    start_seconds = time_to_seconds(start_time)
    end_seconds = time_to_seconds(end_time)
    
    logger.info(f"Parsed times: start={start_seconds}s, end={end_seconds}s")
    
    if end_seconds <= start_seconds:
        # Ha egyenlőek vagy helytelen a sorrend, automatikusan korrigálunk
        if end_seconds == 0 and start_seconds == 0:
            # Mindkettő 0, állítsuk be az end_time-ot 60 másodpercre
            end_seconds = 60
            end_time = "00:01:00"
            logger.info(f"Both times were 00:00:00, automatically adjusting end time to {end_time}")
        elif end_seconds <= start_seconds:
            # Ha a kezdőpont későbbi, mint a végpont, cseréljük meg őket
            temp = end_seconds
            end_seconds = start_seconds
            start_seconds = temp
            
            temp = end_time
            end_time = start_time
            start_time = temp
            logger.info(f"Swapped times because end < start. New values: {start_time} to {end_time}")
    
    logger.info(f"Trimming video with valid times: {start_time} to {end_time}")
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Handle either uploaded file or server file
        if is_server_file and server_filename:
            # For files that are already on the server (e.g. converted from MKV)
            input_path = SYSTEM_DOWNLOADS / server_filename
            
            # Make sure the file exists
            if not input_path.exists():
                raise HTTPException(status_code=404, detail=f"Server file not found: {server_filename}")
                
            # Log info about server file
            logger.info(f"Using server file: {input_path}")
            
            # Copy the file to work directory for consistent processing
            work_file_path = work_dir / server_filename
            shutil.copy(str(input_path), str(work_file_path))
            input_path = work_file_path
            
            # Use server_filename for output naming
            original_filename = server_filename
        elif file:
            # Save uploaded file
            input_path = work_dir / file.filename
            async with aiofiles.open(input_path, "wb") as f:
                await f.write(await file.read())
            original_filename = file.filename
        else:
            raise HTTPException(status_code=400, detail="Either file or server_filename must be provided")
        
        await manager.send_progress(connection_id, 10, "Processing video file...")
        
        # Prepare output filename
        output_filename = f"trimmed_{original_filename.split('.')[0]}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Build FFmpeg command for trimming
        ffmpeg_cmd = [
            "ffmpeg",
            "-hwaccel", "auto",
            "-i", str(input_path),
            "-ss", start_time,
            "-to", end_time
        ]
        
        # Log időpontok validálása
        logger.info(f"Trimming video from {start_time} to {end_time}")
        
        if output_format.lower() == "mp4":
            ffmpeg_cmd += ["-c:v", "libx264", "-c:a", "aac"]
        elif output_format.lower() == "webm":
            ffmpeg_cmd += ["-c:v", "libvpx-vp9", "-c:a", "libopus"]
        elif output_format.lower() == "mkv":
            ffmpeg_cmd += ["-c:v", "libx264", "-c:a", "copy"]
        elif output_format.lower() == "avi":
            ffmpeg_cmd += ["-c:v", "mpeg4", "-c:a", "mp2"]
        elif output_format.lower() == "mov":
            ffmpeg_cmd += ["-c:v", "prores", "-c:a", "pcm_s16le", "-profile:v", "2"]
        else:  # Default to MP4
            ffmpeg_cmd += ["-c:v", "libx264", "-c:a", "aac"]
        
        # Handle subtitles if requested
        if preserve_subtitles:
            ffmpeg_cmd += ["-c:s", "copy"]
        
        # Complete the command
        ffmpeg_cmd += [str(output_path), "-y"]
        
        # Run the FFmpeg command
        success = await run_ffmpeg_command(
            ffmpeg_cmd, 
            connection_id, 
            "Video trimming complete"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Video trimming failed")
        
        # Extract audio if requested
        audio_download_url = None
        if extract_audio:
            audio_filename = f"audio_{file.filename.split('.')[0]}.mp3"
            audio_path = SYSTEM_DOWNLOADS / audio_filename
            
            audio_cmd = [
                "ffmpeg",
                "-i", str(output_path),
                "-vn",
                "-acodec", "libmp3lame",
                "-q:a", "2",
                str(audio_path),
                "-y"
            ]
            
            audio_success = await run_ffmpeg_command(
                audio_cmd,
                connection_id,
                "Audio extraction complete"
            )
            
            if audio_success:
                audio_download_url = f"/download/{audio_filename}"
        
        # Return results
        return JSONResponse({
            "download_url": f"/download/{output_filename}",
            "audio_download_url": audio_download_url
        })
    
    except Exception as e:
        logger.error(f"Video trimming error: {e}")
        raise HTTPException(status_code=500, detail=f"Video trimming failed: {str(e)}")
    
    finally:
        # Clean up work directory
        if work_dir.exists():
            await async_rmtree(work_dir)

@router.post("/extract")
async def extract_tracks(
    file: UploadFile = File(...),
    extract_video: bool = Form(False),
    extract_audio: bool = Form(False),
    extract_subtitles: bool = Form(False),
    audio_format: str = Form("mp3"),
    subtitle_format: str = Form("srt"),
    audio_track: int = Form(0),
    subtitle_track: int = Form(0),
    connection_id: Optional[str] = Form(None)
):
    """Extract specific tracks from a video file"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded file
        input_path = work_dir / file.filename
        async with aiofiles.open(input_path, "wb") as f:
            await f.write(await file.read())
        
        await manager.send_progress(connection_id, 10, "Processing video file...")
        
        # Check if any extraction option is selected
        if not (extract_video or extract_audio or extract_subtitles):
            raise HTTPException(status_code=400, detail="At least one track type must be selected for extraction")
        
        download_urls = {}
        
        # Extract video track if requested
        if extract_video:
            video_filename = f"video_{file.filename.split('.')[0]}.mp4"
            video_path = SYSTEM_DOWNLOADS / video_filename
            
            video_cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-an",          # Remove audio
                "-sn",          # Remove subtitles
                "-c:v", "copy", # Copy video codec without re-encoding
                str(video_path),
                "-y"
            ]
            
            video_success = await run_ffmpeg_command(
                video_cmd,
                connection_id,
                "Video track extraction complete"
            )
            
            if video_success:
                download_urls["video"] = f"/download/{video_filename}"
        
        # Extract audio track if requested
        if extract_audio:
            audio_filename = f"audio_{file.filename.split('.')[0]}.{audio_format}"
            audio_path = SYSTEM_DOWNLOADS / audio_filename
            
            # Audio command based on format
            if audio_format == "mp3":
                audio_cmd = [
                    "ffmpeg",
                    "-i", str(input_path),
                    "-map", f"0:a:{audio_track}",  # Select specific audio track
                    "-vn",                         # Remove video
                    "-acodec", "libmp3lame",
                    "-q:a", "2",
                    str(audio_path),
                    "-y"
                ]
            elif audio_format == "aac":
                audio_cmd = [
                    "ffmpeg",
                    "-i", str(input_path),
                    "-map", f"0:a:{audio_track}",
                    "-vn",
                    "-acodec", "aac",
                    "-b:a", "192k",
                    str(audio_path),
                    "-y"
                ]
            elif audio_format == "flac":
                audio_cmd = [
                    "ffmpeg",
                    "-i", str(input_path),
                    "-map", f"0:a:{audio_track}",
                    "-vn",
                    "-acodec", "flac",
                    str(audio_path),
                    "-y"
                ]
            else:  # Default to WAV
                audio_format = "wav"
                audio_filename = f"audio_{file.filename.split('.')[0]}.wav"
                audio_path = SYSTEM_DOWNLOADS / audio_filename
                audio_cmd = [
                    "ffmpeg",
                    "-i", str(input_path),
                    "-map", f"0:a:{audio_track}",
                    "-vn",
                    "-acodec", "pcm_s16le",
                    str(audio_path),
                    "-y"
                ]
            
            audio_success = await run_ffmpeg_command(
                audio_cmd,
                connection_id,
                "Audio track extraction complete"
            )
            
            if audio_success:
                download_urls["audio"] = f"/download/{audio_filename}"
        
        # Extract subtitle track if requested
        if extract_subtitles:
            subtitle_filename = f"subtitle_{file.filename.split('.')[0]}.{subtitle_format}"
            subtitle_path = SYSTEM_DOWNLOADS / subtitle_filename
            
            subtitle_cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-map", f"0:s:{subtitle_track}",  # Select specific subtitle track
                str(subtitle_path),
                "-y"
            ]
            
            subtitle_success = await run_ffmpeg_command(
                subtitle_cmd,
                connection_id,
                "Subtitle track extraction complete"
            )
            
            if subtitle_success:
                download_urls["subtitle"] = f"/download/{subtitle_filename}"
        
        return JSONResponse({
            "download_urls": download_urls
        })
    
    except Exception as e:
        logger.error(f"Track extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Track extraction failed: {str(e)}")
    
    finally:
        await async_rmtree(work_dir)

@router.post("/merge")
async def merge_videos(
    files: List[UploadFile] = File(...),
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Merge multiple video files"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="At least two video files are required for merging")
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded files
        file_list_path = work_dir / "filelist.txt"
        input_paths = []
        
        for i, file in enumerate(files):
            input_path = work_dir / f"{i}_{file.filename}"
            async with aiofiles.open(input_path, "wb") as f:
                await f.write(await file.read())
            input_paths.append(input_path)
        
        # Create file list for concat demuxer
        async with aiofiles.open(file_list_path, "w") as f:
            for path in input_paths:
                await f.write(f"file '{str(path)}'\n")
        
        await manager.send_progress(connection_id, 20, "Processing video files...")
        
        # Prepare output filename
        output_filename = f"merged_video.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Build FFmpeg command for merging
        ffmpeg_cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", str(file_list_path),
            "-c", "copy",
            str(output_path),
            "-y"
        ]
        
        # Run the FFmpeg command
        success = await run_ffmpeg_command(
            ffmpeg_cmd,
            connection_id,
            "Video merging complete"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Video merging failed")
        
        # Return results
        return JSONResponse({
            "download_url": f"/download/{output_filename}"
        })
    
    except Exception as e:
        logger.error(f"Video merging error: {e}")
        raise HTTPException(status_code=500, detail=f"Video merging failed: {str(e)}")
    
    finally:
        await async_rmtree(work_dir)

@router.post("/mkvinfo")
async def get_mkv_info(
    file: UploadFile = File(...),
    connection_id: Optional[str] = Form(None)
):
    """Get detailed information about an MKV file"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Check if mkvinfo is available
        try:
            process = await asyncio.create_subprocess_exec(
                "mkvinfo", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise HTTPException(status_code=500, detail="MKVToolNix tools not found. Please install mkvtoolnix package.")
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="MKVToolNix tools not found. Please install mkvtoolnix package.")
        
        # Save uploaded file
        input_path = work_dir / file.filename
        async with aiofiles.open(input_path, "wb") as f:
            await f.write(await file.read())
        
        await manager.send_progress(connection_id, 30, "Analyzing MKV file...")
        
        # Run mkvinfo to get file information
        process = await asyncio.create_subprocess_exec(
            "mkvinfo", "--ui-language", "en", "--output-charset", "utf-8", str(input_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"mkvinfo failed: {stderr.decode()}")
            raise HTTPException(status_code=500, detail="Failed to analyze MKV file")
        
        info_text = stdout.decode()
        
        # Extract track information from the output
        tracks = []
        track_data = None
        track_type = None
        
        for line in info_text.split('\n'):
            line = line.strip()
            
            if '+ A track' in line:
                if track_data:
                    tracks.append(track_data)
                track_data = {'properties': {}}
                track_type = None
            
            if track_data:
                if '+ Track type:' in line:
                    track_type = line.split(':', 1)[1].strip()
                    track_data['type'] = track_type
                elif '+ Track number:' in line:
                    track_data['number'] = line.split(':', 1)[1].strip()
                elif '+ Name:' in line:
                    track_data['name'] = line.split(':', 1)[1].strip()
                elif '+ Language:' in line:
                    track_data['language'] = line.split(':', 1)[1].strip()
                elif '+ Codec ID:' in line:
                    track_data['codec'] = line.split(':', 1)[1].strip()
                elif '+' in line and ':' in line:
                    key = line.split(':', 1)[0].strip(' +')
                    value = line.split(':', 1)[1].strip()
                    track_data['properties'][key] = value
        
        # Add the last track
        if track_data:
            tracks.append(track_data)
        
        # Get general file information
        file_info = {
            'filename': file.filename,
            'size': os.path.getsize(input_path),
            'tracks': tracks
        }
        
        await manager.send_progress(connection_id, 100, "MKV analysis complete")
        
        return JSONResponse(file_info)
    
    except Exception as e:
        logger.error(f"MKV info error: {e}")
        raise HTTPException(status_code=500, detail=f"MKV analysis failed: {str(e)}")
    
    finally:
        await async_rmtree(work_dir)

@router.post("/mkvextract")
async def extract_mkv_tracks(
    file: UploadFile = File(...),
    tracks: str = Form(...),  # Format: "0:video,1:audio,2:subtitle"
    connection_id: Optional[str] = Form(None)
):
    """Extract specific tracks from an MKV file using mkvextract"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Check if mkvextract is available
        try:
            process = await asyncio.create_subprocess_exec(
                "mkvextract", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise HTTPException(status_code=500, detail="MKVToolNix tools not found. Please install mkvtoolnix package.")
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="MKVToolNix tools not found. Please install mkvtoolnix package.")
        
        # Save uploaded file
        input_path = work_dir / file.filename
        async with aiofiles.open(input_path, "wb") as f:
            await f.write(await file.read())
        
        await manager.send_progress(connection_id, 20, "Processing MKV file...")
        
        # Parse tracks to extract
        track_args = []
        download_urls = {}
        track_list = tracks.split(',')
        
        for track_info in track_list:
            if ':' not in track_info:
                continue
            
            track_id, track_type = track_info.split(':')
            track_id = track_id.strip()
            track_type = track_type.strip().lower()
            
            output_filename = f"track_{track_id}_{file.filename.split('.')[0]}"
            
            if track_type == "video":
                output_filename += ".h264"
                file_key = f"video_{track_id}"
            elif track_type == "audio":
                output_filename += ".aac"
                file_key = f"audio_{track_id}"
            elif track_type == "subtitle":
                output_filename += ".srt"
                file_key = f"subtitle_{track_id}"
            else:
                output_filename += ".bin"
                file_key = f"track_{track_id}"
            
            output_path = SYSTEM_DOWNLOADS / output_filename
            track_args.extend([track_id + ":" + str(output_path)])
            download_urls[file_key] = f"/download/{output_filename}"
        
        if not track_args:
            raise HTTPException(status_code=400, detail="No valid tracks specified")
        
        # Build mkvextract command
        cmd = ["mkvextract", "tracks", str(input_path)] + track_args
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"mkvextract failed: {stderr.decode()}")
            raise HTTPException(status_code=500, detail="Failed to extract MKV tracks")
        
        await manager.send_progress(connection_id, 100, "MKV tracks extraction complete")
        
        return JSONResponse({
            "download_urls": download_urls
        })
    
    except Exception as e:
        logger.error(f"MKV extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"MKV extraction failed: {str(e)}")
    
    finally:
        await async_rmtree(work_dir)

@router.post("/effects")
async def apply_video_effects(
    file: UploadFile = File(...),
    effect_type: str = Form("none"),  # none, grayscale, sepia, vignette, blur, sharpen
    rotate: int = Form(0),  # 0, 90, 180, 270
    flip_horizontal: bool = Form(False),
    flip_vertical: bool = Form(False),
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Apply video effects and transformations"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded file
        input_path = work_dir / file.filename
        async with aiofiles.open(input_path, "wb") as f:
            await f.write(await file.read())
        
        await manager.send_progress(connection_id, 10, "Processing video file...")
        
        # Prepare output filename
        output_filename = f"effect_{file.filename.split('.')[0]}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Build filter complex string
        filter_complex = []
        
        # Rotation
        if rotate == 90:
            filter_complex.append("transpose=1")
        elif rotate == 180:
            filter_complex.append("transpose=2,transpose=2")
        elif rotate == 270:
            filter_complex.append("transpose=2")
        
        # Flipping
        if flip_horizontal:
            filter_complex.append("hflip")
        if flip_vertical:
            filter_complex.append("vflip")
        
        # Visual effects
        if effect_type == "grayscale":
            filter_complex.append("colorchannelmixer=.3:.4:.3:0:.3:.4:.3:0:.3:.4:.3")
        elif effect_type == "sepia":
            filter_complex.append("colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131")
        elif effect_type == "vignette":
            filter_complex.append("vignette=PI/4")
        elif effect_type == "blur":
            filter_complex.append("boxblur=5:1")
        elif effect_type == "sharpen":
            filter_complex.append("unsharp=5:5:1.0:5:5:0.0")
        
        # Build FFmpeg command
        ffmpeg_cmd = ["ffmpeg", "-i", str(input_path)]
        
        # Add filter complex if any
        if filter_complex:
            ffmpeg_cmd += ["-vf", ",".join(filter_complex)]
        
        # Add codec settings based on output format
        if output_format.lower() == "mp4":
            ffmpeg_cmd += ["-c:v", "libx264", "-c:a", "aac"]
        elif output_format.lower() == "webm":
            ffmpeg_cmd += ["-c:v", "libvpx-vp9", "-c:a", "libopus"]
        elif output_format.lower() == "mkv":
            ffmpeg_cmd += ["-c:v", "libx264", "-c:a", "copy"]
        else:
            ffmpeg_cmd += ["-c:v", "libx264", "-c:a", "copy"]
        
        # Add output path
        ffmpeg_cmd += [str(output_path), "-y"]
        
        # Run the FFmpeg command
        success = await run_ffmpeg_command(
            ffmpeg_cmd,
            connection_id,
            "Video effects applied successfully"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Video effects application failed")
        
        # Return results
        return JSONResponse({
            "download_url": f"/download/{output_filename}"
        })
    
    except Exception as e:
        logger.error(f"Video effects error: {e}")
        raise HTTPException(status_code=500, detail=f"Video effects failed: {str(e)}")
    
    finally:
        await async_rmtree(work_dir)

# Subtitle handling endpoints
# ----------------------------------------

@router.post("/apply_subtitle")
async def apply_subtitle(
    video_file: UploadFile = File(...),
    subtitle_file: UploadFile = File(...),
    subtitle_language: str = Form("hun"),
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Apply subtitles to a video file (includes them as a separate stream)"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded files
        video_path = work_dir / video_file.filename
        subtitle_path = work_dir / subtitle_file.filename
        
        async with aiofiles.open(video_path, "wb") as f:
            await f.write(await video_file.read())
        
        async with aiofiles.open(subtitle_path, "wb") as f:
            await f.write(await subtitle_file.read())
        
        await manager.send_progress(connection_id, 20, "Felirat hozzáadása a videóhoz...")
        
        # Prepare output filename and path
        output_filename = f"subtitle_added_{video_file.filename.split('.')[0]}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Build FFmpeg command
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-i", str(subtitle_path),
            "-map", "0:v", 
            "-map", "0:a?", 
            "-map", "1",
            "-c:v", "copy",     # Copy video without re-encoding
            "-c:a", "copy",     # Copy audio without re-encoding
            "-c:s", "mov_text" if output_format.lower() == "mp4" else "srt",
            "-metadata:s:s:0", f"language={subtitle_language}",
            str(output_path),
            "-y"
        ]
        
        # Run FFmpeg command
        success = await run_ffmpeg_command(
            ffmpeg_cmd,
            connection_id,
            "Felirat sikeresen hozzáadva a videóhoz"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Felirat hozzáadása sikertelen")
        
        # Return result
        return JSONResponse({
            "download_url": f"/download/{output_filename}",
            "message": "Felirat sikeresen hozzáadva a videóhoz"
        })
        
    except Exception as e:
        logger.error(f"Error applying subtitle: {e}")
        raise HTTPException(status_code=500, detail=f"Felirat hozzáadása sikertelen: {str(e)}")
    
    finally:
        if work_dir.exists():
            await async_rmtree(work_dir)

@router.post("/burn_subtitle")
async def burn_subtitle(
    video_file: UploadFile = File(...),
    subtitle_file: UploadFile = File(...),
    subtitle_delay: float = Form(0.0),
    subtitle_font_size: int = Form(24),
    subtitle_color: str = Form("white"),
    subtitle_outline: bool = Form(True),
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Burn subtitles directly into the video stream (hardcoded subtitles)"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded files
        video_path = work_dir / video_file.filename
        subtitle_path = work_dir / subtitle_file.filename
        
        async with aiofiles.open(video_path, "wb") as f:
            await f.write(await video_file.read())
        
        async with aiofiles.open(subtitle_path, "wb") as f:
            await f.write(await subtitle_file.read())
        
        await manager.send_progress(connection_id, 20, "Felirat beégetése a videóba...")
        
        # Prepare output filename and path
        output_filename = f"hardsubbed_{video_file.filename.split('.')[0]}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Create subtitle filter with styling options
        subtitle_filter = f"subtitles='{subtitle_path}'"
        
        # Add styling parameters if needed
        filter_params = []
        
        # Font size
        if subtitle_font_size != 24:  # Default value
            filter_params.append(f"force_style='FontSize={subtitle_font_size}'")
        
        # Font color
        if subtitle_color != "white":
            filter_params.append(f"force_style='PrimaryColour=&H{subtitle_color}'")
        
        # Outline
        if subtitle_outline:
            filter_params.append(f"force_style='BorderStyle=1,Outline=1'")
        else:
            filter_params.append(f"force_style='BorderStyle=0,Outline=0'")
        
        # Add delay if needed
        if subtitle_delay != 0:
            filter_params.append(f"force_style='PlayResX=384,PlayResY=288'")
        
        # Combine filter parameters if any were added
        if filter_params:
            subtitle_filter += ":" + ":".join(filter_params)
        
        # Build FFmpeg command for burning subtitles
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", subtitle_filter,
            "-c:v", "libx264",
            "-crf", "23",        # Reasonable quality setting
            "-preset", "medium",  # Encoding speed/compression trade-off
            "-c:a", "copy",      # Copy audio without re-encoding
            str(output_path),
            "-y"
        ]
        
        # Run FFmpeg command
        success = await run_ffmpeg_command(
            ffmpeg_cmd,
            connection_id,
            "Felirat sikeresen beégetve a videóba"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Felirat beégetése sikertelen")
        
        # Return result
        return JSONResponse({
            "download_url": f"/download/{output_filename}",
            "message": "Felirat sikeresen beégetve a videóba"
        })
        
    except Exception as e:
        logger.error(f"Error burning subtitle: {e}")
        raise HTTPException(status_code=500, detail=f"Felirat beégetése sikertelen: {str(e)}")
    
    finally:
        if work_dir.exists():
            await async_rmtree(work_dir)

if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    
    app = FastAPI()
    app.include_router(router, prefix="/api/videocutter", tags=["videocutter"])
    
    uvicorn.run(app, host="127.0.0.1", port=8000)