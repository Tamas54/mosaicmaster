/**
 * Processing Module - Handles video processing operations
 */

const ProcessingModule = {
  // Initialize the module
  init: function() {
    console.log("Processing Module initialized");
  },
  
  // Start video processing operation
  startVideoProcessing: function() {
    console.log("Starting video processing");
    
    // Get video file
    const videoFile = window.currentVideoFile;
    if (!videoFile) {
      alert("Kérjük, először töltsön fel egy videó fájlt!");
      return;
    }
    
    console.log("Processing video file:", videoFile.name, "Type:", videoFile.type, "Size:", videoFile.size);
    
    // Show processing dialog
    const processingDialog = document.getElementById('processingDialog');
    if (processingDialog) processingDialog.style.display = 'flex';
    
    // Update progress indicators
    UIModule.updateProgress(0, "Előkészítés...");
    
    // Get form values
    const startTimeInput = document.getElementById('startTimeInput');
    const endTimeInput = document.getElementById('endTimeInput');
    const outputFormat = document.getElementById('outputFormat');
    const extractAudio = document.getElementById('extractAudio');
    const preserveSubtitles = document.getElementById('preserveSubtitles');
    
    // Validate required inputs
    if (!startTimeInput || !endTimeInput) {
      alert("Hiányzó időpont értékek");
      if (processingDialog) processingDialog.style.display = 'none';
      return;
    }
    
    const startTime = startTimeInput.value;
    const endTime = endTimeInput.value;
    
    if (!startTime || !endTime) {
      alert("Kérjük állítsa be a kezdő és befejező időpontokat");
      if (processingDialog) processingDialog.style.display = 'none';
      return;
    }
    
    // Create form data for API request
    const formData = new FormData();
    // Check if we have a converted file with URL or a real file object
    if (videoFile.convertedUrl) {
      // For converted MKV files, we need to add the file path from the server
      // Extract the filename from the URL
      const downloadPath = videoFile.convertedUrl;
      const serverFilename = downloadPath.split('/').pop();
      formData.append("server_filename", serverFilename);
      formData.append("is_server_file", "true");
      console.log("Using server file:", serverFilename);
    } else {
      // Regular file upload
      formData.append("file", videoFile);
    }
    formData.append("start_time", startTime);
    formData.append("end_time", endTime);
    formData.append("output_format", outputFormat ? outputFormat.value : "mp4");
    formData.append("extract_audio", extractAudio && extractAudio.checked);
    formData.append("preserve_subtitles", preserveSubtitles && preserveSubtitles.checked);
    
    // Optional parameters
    const useOpenshot = document.getElementById('useOpenshot');
    if (useOpenshot) {
      formData.append("use_openshot", useOpenshot.checked);
    }
    
    const outputQuality = document.getElementById('outputQuality');
    if (outputQuality) {
      formData.append("quality", outputQuality.value);
    }
    
    // Setup WebSocket for progress updates
    const connectionId = crypto.randomUUID();
    formData.append("connection_id", connectionId);
    
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${connectionId}`);
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        UIModule.updateProgress(data.progress || 0, data.status || "Feldolgozás...");
      } catch (error) {
        console.error("WebSocket message parsing error:", error);
      }
    };
    
    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      UIModule.showError("WebSocket kapcsolati hiba");
    };
    
    // Execute API request
    this.executeApiRequest(formData, '/api/videocutter/trim', ws);
  },
  
  // Execute API request for video processing
  executeApiRequest: async function(formData, endpoint, ws) {
    const processingDialog = document.getElementById('processingDialog');
    const successDialog = document.getElementById('successDialog');
    const downloadBtn = document.getElementById('downloadBtn');
    const successMessage = document.getElementById('successMessage');
    const timerIndicator = document.querySelector('.timer-indicator');
    
    try {
      // Send request to API
      const response = await fetch(endpoint, {
        method: 'POST',
        body: formData
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      // Process successful response
      const result = await response.json();
      UIModule.updateProgress(100, "Videó feldolgozás kész!");
      
      // Update UI with result
      if (downloadBtn && result.download_url) {
        downloadBtn.onclick = () => window.open(result.download_url, '_blank');
      }
      
      if (successMessage) {
        let message = "A videó feldolgozása sikeresen befejeződött.";
        
        if (result.audio_download_url) {
          message += " Az audio is kinyerésre került.";
          
          // Create audio download button if needed
          const audioBtn = document.createElement('button');
          audioBtn.className = 'dialog-btn btn-primary';
          audioBtn.textContent = 'Audio Letöltése';
          audioBtn.onclick = () => window.open(result.audio_download_url, '_blank');
          
          const actionsDiv = document.querySelector('.dialog-actions');
          if (actionsDiv) {
            actionsDiv.appendChild(audioBtn);
          }
        }
        
        successMessage.textContent = message;
      }
      
      // Switch dialogs
      setTimeout(() => {
        if (processingDialog) processingDialog.style.display = 'none';
        if (successDialog) successDialog.style.display = 'flex';
        if (timerIndicator) timerIndicator.textContent = 'Feldolgozás kész';
      }, 1000);
      
    } catch (error) {
      console.error("API request error:", error);
      UIModule.showError(error.message || "Ismeretlen hiba történt");
      
      // Keep processing dialog open to show error
    } finally {
      // Close WebSocket connection
      if (ws) ws.close();
    }
  },
  
  // Apply subtitle to a video (as separate stream)
  applySubtitle: function() {
    // Assuming video is already playing if the user can see the subtitles panel
    let videoFile = window.currentVideoFile;
    
    // Fallback for accessing video 
    const videoPlayer = document.getElementById('videoPlayer');
    if (!videoFile && videoPlayer && videoPlayer.src) {
      // Create a mock video file object if the video is playing but not properly registered
      videoFile = {
        name: "current_video.mp4",
        type: "video/mp4",
        size: 1000000, // Mock size
        src: videoPlayer.src
      };
      window.currentVideoFile = videoFile;
      console.log("Created mock video file from playing video:", videoFile);
    }
    
    if (!videoFile) {
      alert("Kérjük, először töltsön fel egy videó fájlt!");
      return;
    }
    
    const subtitleFile = window.subtitleFile;
    if (!subtitleFile) {
      alert("Kérjük, először töltsön fel egy felirat fájlt!");
      return;
    }
    
    // Show processing dialog
    const processingDialog = document.getElementById('processingDialog');
    const progressBar = document.getElementById('progressBar');
    const processingStatus = document.getElementById('processingStatus');
    
    if (processingDialog) processingDialog.style.display = 'flex';
    if (progressBar) progressBar.style.width = '10%';
    if (processingStatus) processingStatus.textContent = 'Felirat hozzáadása a videóhoz...';
    
    // Get form options
    const subtitleLanguage = document.getElementById('subtitleLanguage')?.value || 'hun';
    const outputFormat = document.getElementById('outputFormat')?.value || 'mp4';
    
    // Create form data for API request
    const formData = new FormData();
    formData.append("video_file", videoFile);
    formData.append("subtitle_file", subtitleFile);
    formData.append("subtitle_language", subtitleLanguage);
    formData.append("output_format", outputFormat);
    
    // Generate connection ID for WebSocket progress updates
    const connectionId = crypto.randomUUID();
    formData.append("connection_id", connectionId);
    
    // Setup WebSocket for progress updates
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${connectionId}`);
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (progressBar) progressBar.style.width = data.progress + "%";
        if (processingStatus) processingStatus.textContent = data.status;
      } catch (error) {
        console.error("WebSocket message parsing error:", error);
      }
    };
    
    // Send request to API
    fetch('/api/videocutter/apply_subtitle', {
      method: 'POST',
      body: formData
    })
    .then(response => {
      if (!response.ok) {
        throw new Error('Felirat hozzáadása sikertelen: ' + response.statusText);
      }
      return response.json();
    })
    .then(data => {
      // Handle successful response
      if (processingDialog) processingDialog.style.display = 'none';
      
      // Update success dialog
      const successDialog = document.getElementById('successDialog');
      const successMessage = document.getElementById('successMessage');
      const dialogActions = document.querySelector('.dialog-actions');
      
      if (successMessage) {
        successMessage.textContent = data.message || 'A felirat sikeresen hozzáadva a videóhoz.';
      }
      
      if (dialogActions) {
        dialogActions.innerHTML = '';
        
        // Add Continue Editing button
        const continueBtn = document.createElement('button');
        continueBtn.className = 'dialog-btn btn-cancel';
        continueBtn.textContent = 'Szerkesztés Folytatása';
        continueBtn.onclick = () => {
          if (successDialog) successDialog.style.display = 'none';
        };
        
        // Add Download button
        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'dialog-btn btn-primary';
        downloadBtn.textContent = 'Letöltés';
        downloadBtn.onclick = () => {
          window.open(data.download_url, '_blank');
        };
        
        dialogActions.appendChild(continueBtn);
        dialogActions.appendChild(downloadBtn);
      }
      
      if (successDialog) successDialog.style.display = 'flex';
    })
    .catch(error => {
      console.error("Subtitle application error:", error);
      if (processingDialog) processingDialog.style.display = 'none';
      alert("Hiba történt a felirat hozzáadása közben: " + error.message);
    })
    .finally(() => {
      if (ws) ws.close();
    });
  },
  
  // Burn subtitles directly into video
  burnSubtitle: function() {
    // Assuming video is already playing if the user can see the subtitles panel
    let videoFile = window.currentVideoFile;
    
    // Fallback for accessing video 
    const videoPlayer = document.getElementById('videoPlayer');
    if (!videoFile && videoPlayer && videoPlayer.src) {
      // Create a mock video file object if the video is playing but not properly registered
      videoFile = {
        name: "current_video.mp4",
        type: "video/mp4",
        size: 1000000, // Mock size
        src: videoPlayer.src
      };
      window.currentVideoFile = videoFile;
      console.log("Created mock video file from playing video:", videoFile);
    }
    
    if (!videoFile) {
      alert("Kérjük, először töltsön fel egy videó fájlt!");
      return;
    }
    
    const subtitleFile = window.subtitleFile;
    if (!subtitleFile) {
      alert("Kérjük, először töltsön fel egy felirat fájlt!");
      return;
    }
    
    // Show processing dialog
    const processingDialog = document.getElementById('processingDialog');
    const progressBar = document.getElementById('progressBar');
    const processingStatus = document.getElementById('processingStatus');
    
    if (processingDialog) processingDialog.style.display = 'flex';
    if (progressBar) progressBar.style.width = '10%';
    if (processingStatus) processingStatus.textContent = 'Felirat beégetése a videóba...';
    
    // Get form options
    const subtitleDelay = document.getElementById('subtitleDelay')?.value || 0;
    const subtitleFontSize = document.getElementById('subtitleFontSize')?.value || 24;
    const subtitleColor = document.getElementById('subtitleColor')?.value || 'white';
    const subtitleOutline = document.getElementById('subtitleOutline')?.checked || true;
    const outputFormat = document.getElementById('outputFormat')?.value || 'mp4';
    
    // Create form data for API request
    const formData = new FormData();
    formData.append("video_file", videoFile);
    formData.append("subtitle_file", subtitleFile);
    formData.append("subtitle_delay", subtitleDelay);
    formData.append("subtitle_font_size", subtitleFontSize);
    formData.append("subtitle_color", subtitleColor);
    formData.append("subtitle_outline", subtitleOutline);
    formData.append("output_format", outputFormat);
    
    // Generate connection ID for WebSocket progress updates
    const connectionId = crypto.randomUUID();
    formData.append("connection_id", connectionId);
    
    // Setup WebSocket for progress updates
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${connectionId}`);
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (progressBar) progressBar.style.width = data.progress + "%";
        if (processingStatus) processingStatus.textContent = data.status;
      } catch (error) {
        console.error("WebSocket message parsing error:", error);
      }
    };
    
    // Send request to API
    fetch('/api/videocutter/burn_subtitle', {
      method: 'POST',
      body: formData
    })
    .then(response => {
      if (!response.ok) {
        throw new Error('Felirat beégetése sikertelen: ' + response.statusText);
      }
      return response.json();
    })
    .then(data => {
      // Handle successful response
      if (processingDialog) processingDialog.style.display = 'none';
      
      // Update success dialog
      const successDialog = document.getElementById('successDialog');
      const successMessage = document.getElementById('successMessage');
      const dialogActions = document.querySelector('.dialog-actions');
      
      if (successMessage) {
        successMessage.textContent = data.message || 'A felirat sikeresen beégetve a videóba.';
      }
      
      if (dialogActions) {
        dialogActions.innerHTML = '';
        
        // Add Continue Editing button
        const continueBtn = document.createElement('button');
        continueBtn.className = 'dialog-btn btn-cancel';
        continueBtn.textContent = 'Szerkesztés Folytatása';
        continueBtn.onclick = () => {
          if (successDialog) successDialog.style.display = 'none';
        };
        
        // Add Download button
        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'dialog-btn btn-primary';
        downloadBtn.textContent = 'Letöltés';
        downloadBtn.onclick = () => {
          window.open(data.download_url, '_blank');
        };
        
        dialogActions.appendChild(continueBtn);
        dialogActions.appendChild(downloadBtn);
      }
      
      if (successDialog) successDialog.style.display = 'flex';
    })
    .catch(error => {
      console.error("Subtitle burning error:", error);
      if (processingDialog) processingDialog.style.display = 'none';
      alert("Hiba történt a felirat beégetése közben: " + error.message);
    })
    .finally(() => {
      if (ws) ws.close();
    });
  }
};

// Export the module
window.ProcessingModule = ProcessingModule;