import uuid
import os
import json
import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from config import (
    TEMP_DIR,
    SYSTEM_DOWNLOADS,
    manager,
    logger,
    async_rmtree,
    process_semaphore
)

router = APIRouter()

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

@router.post("/overlay_logo")
async def overlay_logo(
    video_file: UploadFile = File(...),
    logo_file: UploadFile = File(...),
    position: str = Form("top-right"),  # top-left, top-right, bottom-left, bottom-right, center
    scale: float = Form(0.1),  # Logo scale as percentage of video width
    opacity: float = Form(0.8),  # 0.0-1.0
    margin: int = Form(20),  # Margin in pixels
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Add a logo/watermark overlay to a video"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded files
        video_path = work_dir / video_file.filename
        logo_path = work_dir / logo_file.filename
        
        async with aiofiles.open(video_path, "wb") as f:
            await f.write(await video_file.read())
        
        async with aiofiles.open(logo_path, "wb") as f:
            await f.write(await logo_file.read())
        
        await manager.send_progress(connection_id, 20, "Processing files...")
        
        # Determine position coordinates
        position_str = ""
        if position == "top-left":
            position_str = f"{margin}:{margin}"
        elif position == "top-right":
            position_str = f"main_w-overlay_w-{margin}:{margin}"
        elif position == "bottom-left":
            position_str = f"{margin}:main_h-overlay_h-{margin}"
        elif position == "bottom-right":
            position_str = f"main_w-overlay_w-{margin}:main_h-overlay_h-{margin}"
        elif position == "center":
            position_str = "(main_w-overlay_w)/2:(main_h-overlay_h)/2"
        
        # Prepare output filename and path
        output_filename = f"logo_overlay_{video_file.filename.split('.')[0]}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Build FFmpeg command for logo overlay
        # We use the scale filter to size the logo relative to video width
        # and the overlay filter to position it with opacity
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-i", str(logo_path),
            "-filter_complex", 
            f"[1:v]scale=iw*{scale}:-1[overlay];[0:v][overlay]overlay={position_str}:format=auto:alpha={opacity}[out]",
            "-map", "[out]",
            "-map", "0:a?",  # Copy audio if available
            "-c:a", "copy",
            str(output_path),
            "-y"
        ]
        
        # Run FFmpeg command
        success = await run_ffmpeg_command(
            ffmpeg_cmd,
            connection_id,
            "Logo overlay added successfully"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add logo overlay")
        
        # Return result
        return JSONResponse({
            "download_url": f"/download/{output_filename}"
        })
    
    except Exception as e:
        logger.error(f"Error adding logo overlay: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding logo overlay: {str(e)}")
    
    finally:
        if work_dir.exists():
            await async_rmtree(work_dir)

@router.post("/add_text_overlay")
async def add_text_overlay(
    video_file: UploadFile = File(...),
    text: str = Form(...),
    font: str = Form("Arial"),
    font_size: int = Form(24),
    font_color: str = Form("white"),
    position: str = Form("bottom"),  # top, bottom, middle
    background_opacity: float = Form(0.5),  # 0.0-1.0
    border: bool = Form(False),
    start_time: Optional[str] = Form(None),  # Format: "00:00:00"
    end_time: Optional[str] = Form(None),    # Format: "00:00:00"
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Add text overlay to a video (title, caption, etc.)"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded file
        video_path = work_dir / video_file.filename
        async with aiofiles.open(video_path, "wb") as f:
            await f.write(await video_file.read())
        
        await manager.send_progress(connection_id, 20, "Processing video file...")
        
        # Prepare output filename and path
        output_filename = f"text_overlay_{video_file.filename.split('.')[0]}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Configure text position
        y_position = ""
        if position == "top":
            y_position = "10"
        elif position == "middle":
            y_position = "(h-text_h)/2"
        else:  # bottom
            y_position = "h-text_h-10"
        
        # Prepare font settings
        border_setting = ":borderw=2" if border else ""
        
        # Prepare time settings
        time_setting = ""
        if start_time and end_time:
            time_setting = f":enable='between(t,{start_time},{end_time})'"
        
        # Build FFmpeg command for text overlay
        drawtext_filter = (
            f"drawtext=text='{text}':fontfile={font}:fontsize={font_size}:"
            f"fontcolor={font_color}:x=(w-text_w)/2:y={y_position}:"
            f"box=1:boxcolor=black@{background_opacity}:boxborderw=5{border_setting}{time_setting}"
        )
        
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", drawtext_filter,
            "-c:a", "copy",  # Copy audio
            str(output_path),
            "-y"
        ]
        
        # Run FFmpeg command
        success = await run_ffmpeg_command(
            ffmpeg_cmd,
            connection_id,
            "Text overlay added successfully"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add text overlay")
        
        # Return result
        return JSONResponse({
            "download_url": f"/download/{output_filename}"
        })
    
    except Exception as e:
        logger.error(f"Error adding text overlay: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding text overlay: {str(e)}")
    
    finally:
        if work_dir.exists():
            await async_rmtree(work_dir)

@router.post("/add_intro_outro")
async def add_intro_outro(
    video_file: UploadFile = File(...),
    intro_file: Optional[UploadFile] = File(None),
    outro_file: Optional[UploadFile] = File(None),
    fade_duration: float = Form(1.0),  # Transition duration in seconds
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Add intro and/or outro sequences to a video with a smooth transition"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    if not intro_file and not outro_file:
        raise HTTPException(status_code=400, detail="Either intro or outro file must be provided")
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded main video file
        video_path = work_dir / video_file.filename
        async with aiofiles.open(video_path, "wb") as f:
            await f.write(await video_file.read())
        
        await manager.send_progress(connection_id, 10, "Processing video files...")
        
        # Save uploaded intro/outro files
        intro_path = None
        outro_path = None
        
        if intro_file:
            intro_path = work_dir / intro_file.filename
            async with aiofiles.open(intro_path, "wb") as f:
                await f.write(await intro_file.read())
        
        if outro_file:
            outro_path = work_dir / outro_file.filename
            async with aiofiles.open(outro_path, "wb") as f:
                await f.write(await outro_file.read())
        
        # Prepare output filename and path
        output_filename = f"complete_{video_file.filename.split('.')[0]}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Prepare temporary file list for concat
        file_list_path = work_dir / "filelist.txt"
        
        # We'll use different approaches based on whether we have intro, outro, or both
        if intro_path and outro_path:
            # Create crossfade transition between intro and main video
            intro_main_path = work_dir / "intro_main.mp4"
            
            intro_main_cmd = [
                "ffmpeg",
                "-i", str(intro_path),
                "-i", str(video_path),
                "-filter_complex", f"[0:v]format=yuva444p,fade=t=out:st={fade_duration}:d={fade_duration}:alpha=1[outv];[1:v]format=yuva444p,fade=t=in:st=0:d={fade_duration}:alpha=1[inv];[outv][inv]overlay[v]",
                "-map", "[v]",
                "-map", "1:a",  # Use main video audio
                str(intro_main_path),
                "-y"
            ]
            
            success = await run_ffmpeg_command(
                intro_main_cmd,
                connection_id,
                "Combined intro and main video"
            )
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to combine intro and main video")
            
            # Now combine with outro
            async with aiofiles.open(file_list_path, "w") as f:
                await f.write(f"file '{str(intro_main_path)}'\n")
                await f.write(f"file '{str(outro_path)}'\n")
            
            concat_cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", str(file_list_path),
                "-c", "copy",
                str(output_path),
                "-y"
            ]
            
            success = await run_ffmpeg_command(
                concat_cmd,
                connection_id,
                "Combined with outro video"
            )
            
        elif intro_path:
            # Only have intro, combine with main video
            async with aiofiles.open(file_list_path, "w") as f:
                await f.write(f"file '{str(intro_path)}'\n")
                await f.write(f"file '{str(video_path)}'\n")
            
            concat_cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", str(file_list_path),
                "-c", "copy",
                str(output_path),
                "-y"
            ]
            
            success = await run_ffmpeg_command(
                concat_cmd,
                connection_id,
                "Combined with intro video"
            )
            
        elif outro_path:
            # Only have outro, combine with main video
            async with aiofiles.open(file_list_path, "w") as f:
                await f.write(f"file '{str(video_path)}'\n")
                await f.write(f"file '{str(outro_path)}'\n")
            
            concat_cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", str(file_list_path),
                "-c", "copy",
                str(output_path),
                "-y"
            ]
            
            success = await run_ffmpeg_command(
                concat_cmd,
                connection_id,
                "Combined with outro video"
            )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add intro/outro")
        
        # Return result
        return JSONResponse({
            "download_url": f"/download/{output_filename}"
        })
    
    except Exception as e:
        logger.error(f"Error adding intro/outro: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding intro/outro: {str(e)}")
    
    finally:
        if work_dir.exists():
            await async_rmtree(work_dir)