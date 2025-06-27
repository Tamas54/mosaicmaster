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

# Try to import OpenShot, fall back to FFmpeg if not available
try:
    import openshot
    OPENSHOT_AVAILABLE = True
except ImportError:
    OPENSHOT_AVAILABLE = False

# Import configuration
from config import (
    TEMP_DIR,
    SYSTEM_DOWNLOADS,
    manager,
    logger,
    process_semaphore
)

# Module description
"""
VideoEditor - A modular video editing tool for web applications.

This module provides various video editing functionality including:
- Video trimming with precise timing control
- Track extraction (video, audio, subtitles)
- Video merging with transition effects
- Subtitle manipulation and burning
- Advanced visual effects and transformations
- Multi-track timeline support (via OpenShot integration)

Each function is implemented as a separate endpoint in the REST API.
The editor supports two processing engines:
1. OpenShot - For advanced editing with transitions and multi-track capabilities
2. FFmpeg - As a fallback for basic operations when OpenShot is not available
"""

router = APIRouter()

async def async_rmtree(path: Path):
    """Asynchronously remove a directory tree"""
    if not path.exists():
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(shutil.rmtree, path, ignore_errors=True))

# Utility functions for video processing
# ----------------------------------------

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

# Video Trimming Module
# ----------------------------------------

@router.post("/trim")
async def trim_video(
    file: UploadFile = File(...),
    start_time: str = Form(...),  # Format: "00:00:00"
    end_time: str = Form(...),    # Format: "00:00:00"
    output_format: str = Form("mp4"),
    extract_audio: bool = Form(False),
    preserve_subtitles: bool = Form(False),
    connection_id: Optional[str] = Form(None),
    use_openshot: bool = Form(True)  # Use OpenShot if available
):
    """Trim a video file to the specified start and end times"""
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
        output_filename = f"trimmed_{file.filename.split('.')[0]}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Check if we can use OpenShot
        if OPENSHOT_AVAILABLE and use_openshot:
            await manager.send_progress(connection_id, 20, "Using OpenShot for advanced video editing...")
            
            # Parse start and end time to seconds
            start_parts = start_time.split(':')
            end_parts = end_time.split(':')
            
            start_seconds = int(start_parts[0]) * 3600 + int(start_parts[1]) * 60 + int(start_parts[2])
            end_seconds = int(end_parts[0]) * 3600 + int(end_parts[1]) * 60 + int(end_parts[2])
            
            # Create OpenShot project
            project = openshot.Project()
            project.Open()
            
            # Create reader for input video
            reader = openshot.FFmpegReader(str(input_path))
            
            # Create clip from reader
            clip = openshot.Clip(reader)
            clip.Start(start_seconds)
            clip.End(end_seconds)
            
            # Add clip to track
            track = openshot.Track()
            track.AddClip(clip)
            project.AddTrack(track)
            
            # Set output parameters
            project.SetStabilizeVideo(False)
            project.SetPreviewScale(100)  # 100%
            project.SetVideoLength(end_seconds - start_seconds)
            
            # Export project
            export_format = f"video/{output_format}"
            project.Export(str(output_path), export_format)
            
            await manager.send_progress(connection_id, 90, "OpenShot processing complete")
            success = True
            
        else:
            # Fall back to FFmpeg
            await manager.send_progress(connection_id, 20, "Using FFmpeg for video trimming...")
            
            # Build FFmpeg command for trimming
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-ss", start_time,
                "-to", end_time
            ]
            
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
            "audio_download_url": audio_download_url,
            "engine_used": "OpenShot" if OPENSHOT_AVAILABLE and use_openshot else "FFmpeg"
        })
    
    except Exception as e:
        logger.error(f"Video trimming error: {e}")
        raise HTTPException(status_code=500, detail=f"Video trimming failed: {str(e)}")
    
    finally:
        # Clean up work directory
        if work_dir.exists():
            await async_rmtree(work_dir)

# Track Extraction Module
# ----------------------------------------

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

# Video Merging Module
# ----------------------------------------

@router.post("/merge")
async def merge_videos(
    files: List[UploadFile] = File(...),
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None),
    use_openshot: bool = Form(True),  # Use OpenShot if available
    add_transition: bool = Form(False),  # Add transitions between clips
    transition_type: str = Form("fade")  # Type of transition: fade, wipe, etc.
):
    """Merge multiple video files with optional transitions"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="At least two video files are required for merging")
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded files
        input_paths = []
        
        for i, file in enumerate(files):
            input_path = work_dir / f"{i}_{file.filename}"
            async with aiofiles.open(input_path, "wb") as f:
                await f.write(await file.read())
            input_paths.append(input_path)
        
        await manager.send_progress(connection_id, 20, "Processing video files...")
        
        # Prepare output filename
        output_filename = f"merged_video.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Check if we can use OpenShot
        if OPENSHOT_AVAILABLE and use_openshot:
            await manager.send_progress(connection_id, 30, "Using OpenShot for advanced video merging...")
            
            # Create OpenShot project
            project = openshot.Project()
            project.Open()
            
            # Track for all clips
            track = openshot.Track()
            project.AddTrack(track)
            
            # Calculate total duration for adjusting positions
            total_duration = 0
            clip_durations = []
            readers = []
            
            # First pass to calculate durations
            for input_path in input_paths:
                # Create reader for input video
                reader = openshot.FFmpegReader(str(input_path))
                readers.append(reader)
                
                # Get video duration in seconds
                duration = reader.info.duration
                clip_durations.append(duration)
                total_duration += duration
            
            # Add clips to timeline with proper positioning
            current_position = 0
            clips = []
            
            # Second pass to position clips
            for i, (input_path, duration, reader) in enumerate(zip(input_paths, clip_durations, readers)):
                # Create clip from reader
                clip = openshot.Clip(reader)
                clip.Position(current_position)
                clips.append(clip)
                
                # Add clip to track
                track.AddClip(clip)
                
                # Add transition if requested (except for the last clip)
                if add_transition and i < len(input_paths) - 1:
                    # Get transition end position (overlaps with next clip)
                    transition_duration = min(1.0, duration * 0.2)  # 20% of clip duration or 1 second
                    
                    # Add appropriate transition
                    if transition_type == "fade":
                        # Create fade transition
                        # For fade, we'll adjust opacity of the outgoing clip
                        fade = openshot.EffectInfo()
                        fade.Id = "Fade"
                        fade_options = {}
                        fade_options["start_opacity"] = 1.0
                        fade_options["end_opacity"] = 0.0
                        fade_options["start_time"] = current_position + duration - transition_duration
                        fade_options["end_time"] = current_position + duration
                        fade.Properties = fade_options
                        clip.AddEffect(fade)
                    
                    elif transition_type == "wipe":
                        # Create wipe transition
                        wipe = openshot.EffectInfo()
                        wipe.Id = "Wipe"
                        wipe_options = {}
                        wipe_options["direction"] = "right"
                        wipe_options["start_time"] = current_position + duration - transition_duration
                        wipe_options["end_time"] = current_position + duration
                        wipe.Properties = wipe_options
                        clip.AddEffect(wipe)
                
                # Update position for next clip
                current_position += duration - (transition_duration if add_transition and i < len(input_paths) - 1 else 0)
            
            # Set project parameters
            project.SetVideoLength(total_duration)
            
            # Export project
            export_format = f"video/{output_format}"
            project.Export(str(output_path), export_format)
            
            await manager.send_progress(connection_id, 90, "OpenShot merge complete")
            success = True
            
        else:
            # Fall back to FFmpeg for simple concatenation
            await manager.send_progress(connection_id, 30, "Using FFmpeg for video merging...")
            
            # Create file list for concat demuxer
            file_list_path = work_dir / "filelist.txt"
            async with aiofiles.open(file_list_path, "w") as f:
                for path in input_paths:
                    await f.write(f"file '{str(path)}'\n")
            
            # Build FFmpeg command for merging
            ffmpeg_cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", str(file_list_path),
                "-c", "copy"
            ]
            
            # If transitions are requested and we're using FFmpeg, warn about limitations
            if add_transition:
                await manager.send_progress(connection_id, 40, "Note: Advanced transitions require OpenShot. Using simple concatenation.")
            
            # Add output path
            ffmpeg_cmd += [str(output_path), "-y"]
            
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
            "download_url": f"/download/{output_filename}",
            "engine_used": "OpenShot" if OPENSHOT_AVAILABLE and use_openshot else "FFmpeg",
            "transitions_applied": add_transition and OPENSHOT_AVAILABLE and use_openshot
        })
    
    except Exception as e:
        logger.error(f"Video merging error: {e}")
        raise HTTPException(status_code=500, detail=f"Video merging failed: {str(e)}")
    
    finally:
        await async_rmtree(work_dir)

# MKV Analysis Module
# ----------------------------------------

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

# MKV Track Extraction Module
# ----------------------------------------

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

# Video Effects Module
# ----------------------------------------

@router.post("/effects")
async def apply_video_effects(
    file: UploadFile = File(...),
    effect_type: str = Form("none"),  # none, grayscale, sepia, vignette, blur, sharpen
    rotate: int = Form(0),  # 0, 90, 180, 270
    flip_horizontal: bool = Form(False),
    flip_vertical: bool = Form(False),
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None),
    use_openshot: bool = Form(True)  # Use OpenShot if available
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
        
        # Check if we can use OpenShot
        if OPENSHOT_AVAILABLE and use_openshot:
            await manager.send_progress(connection_id, 20, "Using OpenShot for advanced video effects...")
            
            # Create OpenShot project
            project = openshot.Project()
            project.Open()
            
            # Create reader for input video
            reader = openshot.FFmpegReader(str(input_path))
            
            # Create clip from reader
            clip = openshot.Clip(reader)
            
            # Apply effects based on user selection
            if effect_type == "grayscale":
                # Create grayscale effect
                grayscale = openshot.EffectInfo()
                grayscale.Id = "Grayscale"
                clip.AddEffect(grayscale)
            
            elif effect_type == "blur":
                # Create blur effect
                blur = openshot.EffectInfo()
                blur.Id = "Blur"
                # Set blur amount
                blur_options = {}
                blur_options["blur_amount"] = 0.5  # Range is typically 0-1
                blur.Properties = blur_options
                clip.AddEffect(blur)
            
            elif effect_type == "sepia":
                # Create sepia (color) effect
                color = openshot.EffectInfo()
                color.Id = "Color"
                # Set color properties to sepia tone
                color_options = {}
                color_options["color_r"] = 112  # Reddish
                color_options["color_g"] = 66   # Brownish
                color_options["color_b"] = 20   # Brownish
                color.Properties = color_options
                clip.AddEffect(color)
            
            # Apply rotation if needed
            if rotate != 0:
                # Create rotation effect
                rotation = openshot.EffectInfo()
                rotation.Id = "Rotation"
                # Set rotation amount (in degrees)
                rotation_options = {}
                rotation_options["rotation"] = float(rotate)
                rotation.Properties = rotation_options
                clip.AddEffect(rotation)
            
            # Apply flipping if needed
            if flip_horizontal or flip_vertical:
                # Create transform effect for flipping
                transform = openshot.EffectInfo()
                transform.Id = "Transform"
                # Set transform properties
                transform_options = {}
                transform_options["scale_x"] = -1.0 if flip_horizontal else 1.0
                transform_options["scale_y"] = -1.0 if flip_vertical else 1.0
                transform.Properties = transform_options
                clip.AddEffect(transform)
            
            # Add clip to track
            track = openshot.Track()
            track.AddClip(clip)
            project.AddTrack(track)
            
            # Export project
            export_format = f"video/{output_format}"
            project.Export(str(output_path), export_format)
            
            await manager.send_progress(connection_id, 90, "OpenShot processing complete")
            success = True
            
        else:
            # Fall back to FFmpeg for effects
            await manager.send_progress(connection_id, 20, "Using FFmpeg for video effects...")
            
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
            "download_url": f"/download/{output_filename}",
            "engine_used": "OpenShot" if OPENSHOT_AVAILABLE and use_openshot else "FFmpeg"
        })
    
    except Exception as e:
        logger.error(f"Video effects error: {e}")
        raise HTTPException(status_code=500, detail=f"Video effects failed: {str(e)}")
    
    finally:
        await async_rmtree(work_dir)

# Burn Subtitles Module
# ----------------------------------------

@router.post("/burn_subtitles")
async def burn_subtitles(
    video_file: UploadFile = File(...),
    subtitle_file: UploadFile = File(...),
    subtitle_delay: float = Form(0.0),
    subtitle_language: str = Form("eng"),
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Burn subtitles directly into a video file"""
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
        
        await manager.send_progress(connection_id, 20, "Processing files...")
        
        # Prepare output filename and path
        output_filename = f"video_with_subtitles_{video_file.filename.split('.')[0]}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Apply subtitle delay if needed
        subtitle_options = []
        if subtitle_delay != 0:
            delay_ms = int(subtitle_delay * 1000)
            subtitle_options = [
                "-c:s", "mov_text" if output_format == "mp4" else "srt",
                "-metadata:s:s:0", f"language={subtitle_language}",
                "-ss", f"{abs(delay_ms)}ms" if delay_ms < 0 else "0",
                "-itsoffset", f"{delay_ms}ms" if delay_ms > 0 else "0"
            ]
        
        # Build FFmpeg command for burning subtitles
        ffmpeg_cmd = [
            "ffmpeg", 
            "-i", str(video_path),
            "-i", str(subtitle_path),
            "-map", "0:v", 
            "-map", "0:a?", 
            "-map", "1",
            "-c:v", "libx264",
            "-c:a", "copy",
            "-c:s", "mov_text" if output_format == "mp4" else "copy",
            "-metadata:s:s:0", f"language={subtitle_language}",
            "-vf", f"subtitles='{subtitle_path}'",
            str(output_path),
            "-y"
        ]
        
        # Run FFmpeg command
        success = await run_ffmpeg_command(
            ffmpeg_cmd,
            connection_id,
            "Subtitles burned into video successfully"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to burn subtitles")
        
        # Return result
        return JSONResponse({
            "download_url": f"/download/{output_filename}"
        })
    
    except Exception as e:
        logger.error(f"Error burning subtitles: {e}")
        raise HTTPException(status_code=500, detail=f"Error burning subtitles: {str(e)}")
    
    finally:
        if work_dir.exists():
            await async_rmtree(work_dir)

# Check OpenShot Availability
# ----------------------------------------

@router.get("/check_openshot")
async def check_openshot():
    """Check if OpenShot is available on the server"""
    return JSONResponse({
        "available": OPENSHOT_AVAILABLE,
        "engine": "OpenShot" if OPENSHOT_AVAILABLE else "FFmpeg"
    })

# Advanced Timeline Editing (OpenShot only)
# ----------------------------------------

@router.post("/timeline_edit")
async def timeline_edit(
    files: List[UploadFile] = File(...),
    timeline_data: str = Form(...),  # JSON string with timeline configuration
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Advanced timeline editing with multiple tracks (OpenShot only)"""
    if not OPENSHOT_AVAILABLE:
        raise HTTPException(status_code=400, detail="OpenShot library is not available on the server")
    
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Parse timeline data
        timeline_config = json.loads(timeline_data)
        
        # Save uploaded files
        input_paths = {}
        
        for i, file in enumerate(files):
            input_path = work_dir / f"{i}_{file.filename}"
            async with aiofiles.open(input_path, "wb") as f:
                await f.write(await file.read())
            input_paths[file.filename] = input_path
        
        await manager.send_progress(connection_id, 20, "Processing timeline data...")
        
        # Prepare output filename
        output_filename = f"timeline_project.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Create OpenShot project
        project = openshot.Project()
        project.Open()
        
        # Create tracks according to timeline data
        tracks = []
        for track_data in timeline_config.get("tracks", []):
            track = openshot.Track()
            project.AddTrack(track)
            tracks.append(track)
        
        # Add clips to tracks
        for clip_data in timeline_config.get("clips", []):
            file_name = clip_data.get("file")
            track_index = clip_data.get("track", 0)
            start_time = clip_data.get("start", 0)
            end_time = clip_data.get("end")
            position = clip_data.get("position", 0)
            
            if file_name not in input_paths:
                continue
            
            # Create reader
            reader = openshot.FFmpegReader(str(input_paths[file_name]))
            
            # Create clip from reader
            clip = openshot.Clip(reader)
            
            # Set clip properties
            if end_time:
                clip.End(float(end_time))
            clip.Position(float(position))
            
            # Add effects if specified
            for effect_data in clip_data.get("effects", []):
                effect_type = effect_data.get("type")
                effect_properties = effect_data.get("properties", {})
                
                effect = openshot.EffectInfo()
                effect.Id = effect_type
                
                # Set effect properties
                properties = {}
                for key, value in effect_properties.items():
                    properties[key] = value
                effect.Properties = properties
                
                clip.AddEffect(effect)
            
            # Add clip to correct track
            if 0 <= track_index < len(tracks):
                tracks[track_index].AddClip(clip)
        
        # Calculate total duration
        total_duration = timeline_config.get("duration", 60)  # Default to 60 seconds
        
        # Set project parameters
        project.SetVideoLength(total_duration)
        
        # Export project
        export_format = f"video/{output_format}"
        project.Export(str(output_path), export_format)
        
        await manager.send_progress(connection_id, 90, "Timeline project exported successfully")
        
        # Return results
        return JSONResponse({
            "download_url": f"/download/{output_filename}",
            "engine_used": "OpenShot",
            "timeline_processed": True
        })
    
    except Exception as e:
        logger.error(f"Timeline editing error: {e}")
        raise HTTPException(status_code=500, detail=f"Timeline editing failed: {str(e)}")
    
    finally:
        await async_rmtree(work_dir)

# Main entry point for standalone usage
# ----------------------------------------

if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    
    app = FastAPI(
        title="VideoEditor API",
        description="A REST API for video editing operations including trimming, merging, effects and subtitle handling",
        version="1.0.0"
    )
    app.include_router(router, prefix="/api/videoeditor", tags=["videoeditor"])
    
    print("Starting VideoEditor API server...")
    print("Access the API at: http://127.0.0.1:8000/api/videoeditor")
    print(f"OpenShot library available: {OPENSHOT_AVAILABLE}")
    uvicorn.run(app, host="127.0.0.1", port=8000)