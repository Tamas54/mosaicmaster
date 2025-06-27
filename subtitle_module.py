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

# Import from existing modules
from transcriber import _transcribe_audio, create_srt_content, generate_vtt, convert_txt_to_srt

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

async def extract_audio_from_video(video_path: Path, output_path: Path) -> bool:
    """Extract audio track from a video file"""
    try:
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",  # No video
            "-acodec", "libmp3lame",  # MP3 format
            "-q:a", "2",  # Quality setting
            str(output_path),
            "-y"  # Overwrite if exists
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Failed to extract audio: {stderr.decode()}")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error extracting audio from video: {e}")
        return False

@router.post("/auto_generate")
async def auto_generate_subtitles(
    file: UploadFile = File(...),
    subtitle_format: str = Form("srt"),
    identify_speakers: bool = Form(True),
    burn_into_video: bool = Form(False),
    font_size: int = Form(24),
    font_color: str = Form("white"),
    background_opacity: float = Form(0.5),
    connection_id: Optional[str] = Form(None)
):
    """Automatically generate subtitles for a video with optional speaker identification and burning"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded video file
        video_path = work_dir / file.filename
        async with aiofiles.open(video_path, "wb") as f:
            await f.write(await file.read())
        
        await manager.send_progress(connection_id, 10, "Processing video file...")
        
        # Extract audio from video
        audio_path = work_dir / f"{video_path.stem}_audio.mp3"
        extraction_success = await extract_audio_from_video(video_path, audio_path)
        
        if not extraction_success:
            raise HTTPException(status_code=500, detail="Failed to extract audio from video")
        
        await manager.send_progress(connection_id, 30, "Transcribing audio and generating subtitles...")
        
        # Transcribe audio
        transcript_text, transcript_data = await _transcribe_audio(
            audio_path, 
            identify_speakers=identify_speakers
        )
        
        segments = transcript_data.get("segments", [])
        
        # Generate subtitle file
        subtitle_path = work_dir / f"{video_path.stem}.{subtitle_format}"
        if subtitle_format.lower() == "srt":
            content = create_srt_content(segments)
            async with aiofiles.open(subtitle_path, 'w', encoding='utf-8') as f:
                await f.write(content)
        elif subtitle_format.lower() == "vtt":
            content = await generate_vtt(segments)
            async with aiofiles.open(subtitle_path, 'w', encoding='utf-8') as f:
                await f.write(content)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported subtitle format: {subtitle_format}")
        
        # Copy subtitle file to downloads directory
        download_subtitle_path = SYSTEM_DOWNLOADS / f"{video_path.stem}.{subtitle_format}"
        async with aiofiles.open(subtitle_path, "rb") as src:
            async with aiofiles.open(download_subtitle_path, "wb") as dst:
                await dst.write(await src.read())
        
        result = {
            "subtitle_url": f"/download/{download_subtitle_path.name}"
        }
        
        # Optionally burn subtitles into video
        if burn_into_video:
            await manager.send_progress(connection_id, 60, "Burning subtitles into video...")
            
            output_video_path = work_dir / f"{video_path.stem}_subtitled.mp4"
            
            # More advanced subtitle styling options
            subtitles_filter = (
                f"subtitles='{subtitle_path}'"
                f":force_style='FontName=Arial,FontSize={font_size},PrimaryColour=&H{font_color},"
                f"BackColour=&H000000&{int(background_opacity*255):X},Bold=1,BorderStyle=4,Outline=1,"
                f"Shadow=1,MarginV=20'"
            )
            
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-vf", subtitles_filter,
                "-c:a", "copy",
                str(output_video_path),
                "-y"
            ]
            
            burn_success = await run_ffmpeg_command(
                ffmpeg_cmd,
                connection_id,
                "Subtitles burned into video successfully"
            )
            
            if burn_success:
                # Copy subtitled video to downloads directory
                download_video_path = SYSTEM_DOWNLOADS / f"{video_path.stem}_subtitled.mp4"
                async with aiofiles.open(output_video_path, "rb") as src:
                    async with aiofiles.open(download_video_path, "wb") as dst:
                        await dst.write(await src.read())
                
                result["video_url"] = f"/download/{download_video_path.name}"
        
        await manager.send_progress(connection_id, 100, "Subtitle generation complete")
        
        return JSONResponse(result)
    
    except Exception as e:
        logger.error(f"Error generating subtitles: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # Clean up
        await async_rmtree(work_dir)

@router.post("/from_srt")
async def add_subtitles_from_srt(
    video_file: UploadFile = File(...),
    subtitle_file: UploadFile = File(...),
    burn_into_video: bool = Form(True),
    subtitle_delay: float = Form(0.0),  # Delay in seconds (can be negative)
    font_size: int = Form(24),
    font_color: str = Form("white"),
    background_opacity: float = Form(0.5),
    output_format: str = Form("mp4"),
    connection_id: Optional[str] = Form(None)
):
    """Add subtitles to a video from an existing SRT file"""
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
        output_filename = f"subtitled_{video_file.filename.split('.')[0]}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # If just attaching subtitles without burning
        if not burn_into_video:
            subtitle_options = []
            if subtitle_delay != 0:
                delay_ms = int(subtitle_delay * 1000)
                subtitle_options = [
                    "-itsoffset", f"{delay_ms}ms" if delay_ms > 0 else f"{-delay_ms}ms",
                    "-i", str(subtitle_path),
                    "-map", "0:v", 
                    "-map", "0:a", 
                    "-map", "1:s",
                    "-c", "copy"
                ]
            else:
                subtitle_options = [
                    "-i", str(subtitle_path),
                    "-map", "0:v", 
                    "-map", "0:a", 
                    "-map", "1:s",
                    "-c", "copy"
                ]
            
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", str(video_path),
                *subtitle_options,
                str(output_path),
                "-y"
            ]
        else:
            # Burn subtitles into the video
            subtitles_filter = (
                f"subtitles='{subtitle_path}'"
                f":force_style='FontName=Arial,FontSize={font_size},PrimaryColour=&H{font_color},"
                f"BackColour=&H000000&{int(background_opacity*255):X},Bold=1,BorderStyle=4,Outline=1,"
                f"Shadow=1,MarginV=20'"
            )
            
            if subtitle_delay != 0:
                # We need to add delay to subtitles
                # Create a temporary adjusted SRT file
                adjusted_subtitle_path = work_dir / f"adjusted_{subtitle_file.filename}"
                
                adjust_cmd = [
                    "ffmpeg",
                    "-itsoffset", f"{subtitle_delay}s",
                    "-i", str(subtitle_path),
                    "-c", "copy",
                    str(adjusted_subtitle_path),
                    "-y"
                ]
                
                adjust_success = await run_ffmpeg_command(
                    adjust_cmd,
                    connection_id,
                    "Subtitle timing adjusted"
                )
                
                if adjust_success:
                    subtitle_path = adjusted_subtitle_path
                
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-vf", subtitles_filter,
                "-c:a", "copy",
                str(output_path),
                "-y"
            ]
        
        # Run FFmpeg command
        success = await run_ffmpeg_command(
            ffmpeg_cmd,
            connection_id,
            "Subtitles added to video successfully"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add subtitles to video")
        
        # Return result
        return JSONResponse({
            "download_url": f"/download/{output_filename}"
        })
    
    except Exception as e:
        logger.error(f"Error adding subtitles: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding subtitles: {str(e)}")
    
    finally:
        if work_dir.exists():
            await async_rmtree(work_dir)

@router.post("/convert_txt_to_srt")
async def convert_txt_subtitle_to_srt(
    subtitle_file: UploadFile = File(...),
    connection_id: Optional[str] = Form(None)
):
    """Convert timestamp format [start-end] text to SRT format"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded file
        subtitle_path = work_dir / subtitle_file.filename
        async with aiofiles.open(subtitle_path, "wb") as f:
            await f.write(await subtitle_file.read())
        
        await manager.send_progress(connection_id, 20, "Processing subtitle file...")
        
        # Read the subtitle file
        async with aiofiles.open(subtitle_path, "r", encoding="utf-8") as f:
            subtitle_content = await f.read()
        
        # Convert TXT timestamp format to SRT
        srt_content = convert_txt_to_srt(subtitle_content)
        
        # Create the output file
        output_filename = f"{subtitle_file.filename.split('.')[0]}.srt"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            await f.write(srt_content)
        
        await manager.send_progress(connection_id, 100, "Subtitle conversion complete")
        
        return JSONResponse({
            "download_url": f"/download/{output_filename}"
        })
    
    except Exception as e:
        logger.error(f"Error converting TXT to SRT: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        await async_rmtree(work_dir)

@router.post("/translate_subtitles")
async def translate_subtitles(
    subtitle_file: UploadFile = File(...),
    target_language: str = Form(...),  # Language code like "en", "es", "fr"
    output_format: str = Form("srt"),
    connection_id: Optional[str] = Form(None)
):
    """Translate existing subtitles to another language"""
    if not connection_id:
        connection_id = str(uuid.uuid4())
    
    work_dir = TEMP_DIR / connection_id
    work_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded file
        subtitle_path = work_dir / subtitle_file.filename
        async with aiofiles.open(subtitle_path, "wb") as f:
            await f.write(await subtitle_file.read())
        
        await manager.send_progress(connection_id, 20, "Processing subtitle file...")
        
        # Read the subtitle file
        async with aiofiles.open(subtitle_path, "r", encoding="utf-8") as f:
            subtitle_content = await f.read()
        
        # Parse SRT content to extract text segments
        # This is a simple parsing, might need to be more robust
        subtitle_segments = []
        current_block = {}
        lines = subtitle_content.strip().split("\n")
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Empty line indicates end of a subtitle block
            if not line:
                if current_block and "text" in current_block:
                    subtitle_segments.append(current_block)
                    current_block = {}
                i += 1
                continue
            
            # Try to parse as a subtitle number
            if line.isdigit() and not current_block:
                current_block = {"number": int(line)}
                i += 1
                continue
            
            # Try to parse as a timestamp
            if "-->" in line and "number" in current_block and "timestamp" not in current_block:
                current_block["timestamp"] = line
                i += 1
                continue
            
            # Must be subtitle text
            if "timestamp" in current_block:
                if "text" not in current_block:
                    current_block["text"] = line
                else:
                    current_block["text"] += "\n" + line
                    
            i += 1
        
        # Add the last block if not empty
        if current_block and "text" in current_block:
            subtitle_segments.append(current_block)
        
        # Extract just the text for translation
        texts_to_translate = [segment["text"] for segment in subtitle_segments]
        
        # Join all texts with a special separator that's unlikely to appear in normal text
        combined_text = "\n===SUBTITLE_SEPARATOR===\n".join(texts_to_translate)
        
        await manager.send_progress(connection_id, 40, "Translating subtitles...")
        
        # Use OpenAI for translation
        from config import client
        
        completion = await client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "gpt-3.5-turbo"),
            messages=[
                {"role": "system", "content": f"You are a professional translator. Translate the following subtitles to {target_language}, preserving line breaks and formatting. Only respond with the translated text, nothing else."},
                {"role": "user", "content": combined_text}
            ]
        )
        
        translated_text = completion.choices[0].message.content
        
        # Split the translated text back into segments
        translated_segments = translated_text.split("===SUBTITLE_SEPARATOR===")
        
        # Make sure we have the same number of segments
        if len(translated_segments) != len(subtitle_segments):
            # Handle mismatch - this is a simplistic approach
            translated_segments = translated_segments[:len(subtitle_segments)]
            while len(translated_segments) < len(subtitle_segments):
                translated_segments.append("Translation error")
        
        # Create a new subtitle file with translated text
        translated_subtitle_content = []
        
        for i, segment in enumerate(subtitle_segments):
            translated_subtitle_content.append(str(segment["number"]))
            translated_subtitle_content.append(segment["timestamp"])
            translated_subtitle_content.append(translated_segments[i].strip())
            translated_subtitle_content.append("")  # Empty line between subtitle blocks
        
        # Create the output file
        output_filename = f"{subtitle_file.filename.split('.')[0]}_{target_language}.{output_format}"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            await f.write("\n".join(translated_subtitle_content))
        
        await manager.send_progress(connection_id, 100, "Subtitle translation complete")
        
        return JSONResponse({
            "download_url": f"/download/{output_filename}"
        })
    
    except Exception as e:
        logger.error(f"Error translating subtitles: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        await async_rmtree(work_dir)