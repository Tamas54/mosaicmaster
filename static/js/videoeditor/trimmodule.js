// Trim Module for Video Editor
// Handles video trimming functionality

document.addEventListener("DOMContentLoaded", function() {
  console.log("Trim Module Loaded");
  
  // Check if we're on the videocutter page - relaxed condition to allow any path
  // Always load the trim module regardless of path
  
  // Get trim button and add event listener
  const trimVideoBtn = document.getElementById('trimVideoBtn');
  const executeTrimBtn = document.getElementById('executeTrimBtn');
  
  if (trimVideoBtn) {
    trimVideoBtn.addEventListener('click', executeTrim);
  }
  
  if (executeTrimBtn) {
    executeTrimBtn.addEventListener('click', executeTrim);
  }
  
  // Make executeTrim global so it can be called from the main script
  window.executeTrim = executeTrim;
  
  // Execute trim operation
  async function executeTrim() {
    console.log("executeTrim function called");
    
    // Check if we have a video file
    const videoFile = typeof window.getVideoFile === 'function' ? 
      window.getVideoFile() : window.currentVideoFile;
    
    if (!videoFile) {
      alert("Kérjük, először töltsön fel egy videó fájlt!");
      return;
    }
    
    // Show subtitle panel if it exists
    const subtitlesPanel = document.getElementById('subtitles-panel');
    if (subtitlesPanel) {
      subtitlesPanel.style.display = 'block';
    }
    
    // Get form elements
    const startTimeInput = document.getElementById('startTimeInput');
    const endTimeInput = document.getElementById('endTimeInput');
    const outputFormat = document.getElementById('outputFormat');
    const extractAudio = document.getElementById('extractAudio');
    const preserveSubtitles = document.getElementById('preserveSubtitles');
    const outputQuality = document.getElementById('outputQuality');
    const progressBar = document.getElementById('progressBar');
    const processingSection = document.getElementById('processingSection');
    const statusText = document.getElementById('statusText');
    const downloadBtn = document.getElementById('downloadBtn');
    
    // Validate inputs
    if (!startTimeInput || !endTimeInput) {
      alert("Missing required elements");
      return;
    }
    
    const startTime = startTimeInput.value;
    const endTime = endTimeInput.value;
    
    if (!startTime || !endTime) {
      alert("Please set start and end times");
      return;
    }
    
    // Prepare form data
    const formData = new FormData();
    formData.append("file", videoFile);
    formData.append("start_time", startTime);
    formData.append("end_time", endTime);
    formData.append("output_format", outputFormat ? outputFormat.value : "mp4");
    formData.append("extract_audio", extractAudio && extractAudio.checked);
    formData.append("preserve_subtitles", preserveSubtitles && preserveSubtitles.checked);
    
    // Add OpenShot option if available
    const useOpenshot = document.getElementById('useOpenshot');
    if (useOpenshot) {
      formData.append("use_openshot", useOpenshot.checked);
    }
    
    // Add quality settings if available
    if (outputQuality) {
      formData.append("quality", outputQuality.value);
    }
    
    // Generate connection ID for WebSocket
    const connectionId = crypto.randomUUID();
    formData.append("connection_id", connectionId);
    
    // Initialize WebSocket
    const ws = window.VideoEditorCore ? 
      window.VideoEditorCore.initWebSocket(connectionId) : 
      initWebSocket(connectionId);
    
    // Show progress bar
    if (processingSection) processingSection.classList.remove('hidden');
    if (progressBar) progressBar.style.width = "0%";
    if (statusText) statusText.textContent = "Starting video trim...";
    
    // Disable button while processing
    this.disabled = true;
    
    try {
      // Send request to server - use the videocutter endpoint instead of videoeditor
      const response = await fetch('/api/videocutter/trim', {
        method: "POST",
        body: formData
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      // Process response
      const result = await response.json();
      if (progressBar) progressBar.style.width = "100%";
      if (statusText) statusText.textContent = "Video trimming complete!";
      
      // Setup download button
      if (result.download_url) {
        if (downloadBtn) {
          downloadBtn.innerHTML = '<i data-lucide="download" class="w-5 h-5"></i> Download Trimmed Video';
          downloadBtn.onclick = () => window.open(result.download_url, '_blank');
          downloadBtn.classList.remove('hidden');
          lucide.createIcons();
        }
        
        // If audio was extracted, add a separate button
        if (result.audio_download_url) {
          const audioBtn = document.createElement('button');
          audioBtn.className = 'w-full bg-blue-500 text-white py-2 rounded-lg mt-2 flex items-center justify-center gap-2';
          audioBtn.innerHTML = '<i data-lucide="music" class="w-5 h-5"></i> Download Audio Track';
          audioBtn.onclick = () => window.open(result.audio_download_url, '_blank');
          
          // Find a good place to append the button
          if (downloadBtn && downloadBtn.parentElement) {
            downloadBtn.parentElement.appendChild(audioBtn);
            lucide.createIcons();
          }
        }
      }
    } catch (error) {
      console.error("Error trimming video:", error);
      if (statusText) statusText.textContent = "Error: " + error.message;
      if (progressBar) progressBar.classList.add("bg-red-500");
    } finally {
      this.disabled = false;
      if (ws) ws.close();
    }
  }
  
  // Fallback WebSocket function if the core module isn't loaded
  function initWebSocket(connectionId) {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${connectionId}`);
    
    const progressBar = document.getElementById('progressBar');
    const statusText = document.getElementById('statusText');
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (progressBar) progressBar.style.width = data.progress + "%";
      if (statusText) statusText.textContent = data.status;
    };
    
    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };
    
    return ws;
  }
});