@app.post("/api/streams/{stream_id}/transcribe/stop")
async def stop_transcription(stream_id: str):
    """Stream leiratolás leállítása"""
    try:
        # Ellenőrizzük, hogy a stream létezik-e
        if stream_id not in live_stream_handler.active_streams:
            logger.error(f"Cannot stop transcription: Stream {stream_id} not found")
            raise HTTPException(status_code=404, detail="Stream not found")
        
        stream_info = live_stream_handler.active_streams.get(stream_id)
        
        # Ellenőrizzük, hogy van-e folyamatban lévő átiratolás
        # Ha nincs transcription_id, akkor is generáljunk egy letölthető fájlt
        if not stream_info:
            logger.error(f"No stream info for stream {stream_id}")
            raise HTTPException(status_code=404, detail="No stream info found")
        
        # Akár van transcription_id akár nincs, mindenképp generáljunk eredményt
        # Ha nincs aktív feladat, akkor is adjunk vissza egy fájlt
        # Ezzel elkerüljük, hogy a felhasználó "beragadjon" a leállítás gombra kattintással
        timestamp = int(time.time())
        output_filename = f"partial_transcript_{stream_id}_{timestamp}.txt"
        output_path = SYSTEM_DOWNLOADS / output_filename
        
        # Ellenőrizzük, hogy lehet-e leállítani meglévő feladatot
        if stream_info.transcription_id and stream_info.transcription_id in live_stream_handler.transcription_tasks:
            transcription_id = stream_info.transcription_id
            logger.info(f"Found active transcription {transcription_id} for stream {stream_id}")
            
            # Feladat leállítása
            task = live_stream_handler.transcription_tasks[transcription_id]
            if task and not task.done():
                logger.info(f"Cancelling transcription task {transcription_id} for stream {stream_id}")
                task.cancel()
                # Várunk egy rövid ideig, hogy a task leálljon
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Transcription task {transcription_id} did not stop within timeout")
                except asyncio.CancelledError:
                    logger.info(f"Transcription task {transcription_id} was cancelled successfully")
                except Exception as e:
                    logger.error(f"Error waiting for transcription task to cancel: {e}")
            
            # Töröljük a feladatot a nyilvántartásból
            if transcription_id in live_stream_handler.transcription_tasks:
                del live_stream_handler.transcription_tasks[transcription_id]
            
            # Töröljük a hivatkozást a stream információból
            stream_info.transcription_id = None
            
            # Írjunk üzenetet a fájlba, hogy leállítva
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write("A leiratolás megszakítva. Részleges eredmény nem elérhető.")
        else:
            # Ha nem volt aktív feladat, akkor is generáljunk egy fájlt
            # Ez lehet, hogy a feladat már befejeződött vagy eleve nem is indult el
            logger.warning(f"No active transcription task found for stream {stream_id}, but we'll still generate a file")
            
            # Írjunk üzenetet a fájlba
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write("Nem található aktív leiratolási feladat. Ellenőrizd, hogy korábban elkészült-e a leirat.")
            
            # Töröljük a hivatkozást a stream információból (ha létezik)
            if stream_info.transcription_id:
                stream_info.transcription_id = None
        
        # Visszatérünk a letöltési URL-lel
        return {
            "status": "stopped",
            "message": "Transcription stopped successfully",
            "download_url": f"/download/{output_filename}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))
