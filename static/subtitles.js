// Subtitles handler for video editor
document.addEventListener('DOMContentLoaded', function() {
  console.log("Subtitles.js loaded");
  
  // Check if we're on the videocutter page
  const isVideoCutterPage = window.location.pathname.includes('videocutter.html');
  if (!isVideoCutterPage) return;
  
  // Listen for video loaded events - this handles all cases including MKV conversion
  document.addEventListener('videoloaded', function(event) {
    console.log("Video loaded event detected in subtitles.js!");
    const subtitlePanel = document.getElementById('subtitles-panel');
    if (subtitlePanel) {
      subtitlePanel.style.display = 'block';
      console.log("Subtitle panel displayed after video load event");
    }
    
    // Also show the subtitle tab panel if available
    const subtitleOptionsPanel = document.getElementById('subtitleOptionsPanel');
    if (subtitleOptionsPanel) {
      console.log("Found subtitle options panel, making visible");
      subtitleOptionsPanel.classList.remove('hidden');
    }
    
    // Make subtitle editor visible
    const subtitleEditorPanel = document.getElementById('subtitleEditorPanel'); 
    if (subtitleEditorPanel) {
      subtitleEditorPanel.classList.remove('hidden');
      console.log("Subtitle editor panel displayed after video load");
    }
  });
  
  // Common variables
  const connectionId = crypto.randomUUID();
  let currentVideoFile = null;
  let currentSubtitleFile = null;
  
  // DOM Elements
  const videoDropZone = document.getElementById('videoDropZone');
  const videoFileInput = document.getElementById('videoFileInput');
  const subtitleDropZone = document.getElementById('subtitleDropZone');
  const subtitleFileInput = document.getElementById('subtitleFileInput');
  const subtitleFileInfo = document.getElementById('subtitleFileInfo');
  const subtitleFileName = document.getElementById('subtitleFileName');
  const removeSubtitleFile = document.getElementById('removeSubtitleFile');
  const generateSubtitlesBtn = document.getElementById('generateSubtitlesBtn');
  const burnSubtitlesBtn = document.getElementById('burnSubtitlesBtn');
  const translateSubtitlesBtn = document.getElementById('translateSubtitlesBtn');
  const convertTxtToSrtBtn = document.createElement('button');
  convertTxtToSrtBtn.id = 'convertTxtToSrtBtn';
  convertTxtToSrtBtn.className = 'button accent-btn w-full mt-3';
  convertTxtToSrtBtn.innerHTML = '<i class="fas fa-exchange-alt mr-2"></i> Konvertálás TXT-ből SRT-be';
  const progressBar = document.getElementById('progressBar');
  const statusText = document.getElementById('statusText');
  const downloadSubtitlesBtn = document.getElementById('downloadSubtitlesBtn');
  
  // Add the convert button to the subtitle panel
  const subtitlePanel = document.getElementById('subtitles-panel');
  if (subtitlePanel) {
    subtitlePanel.appendChild(convertTxtToSrtBtn);
  }
  
  // Check if required elements exist before attaching event handlers
  if (generateSubtitlesBtn) {
    generateSubtitlesBtn.addEventListener('click', generateSubtitles);
  }
  
  if (burnSubtitlesBtn) {
    burnSubtitlesBtn.addEventListener('click', burnSubtitles);
  }
  
  if (translateSubtitlesBtn) {
    translateSubtitlesBtn.addEventListener('click', translateSubtitles);
  }
  
  if (convertTxtToSrtBtn) {
    convertTxtToSrtBtn.addEventListener('click', convertTxtToSrt);
  }
  
  // Add Advanced Subtitle Editor button
  const subtitlePanel = document.getElementById('subtitles-panel');
  if (subtitlePanel) {
    const advancedEditorBtn = document.createElement('button');
    advancedEditorBtn.className = 'button accent-btn w-full mt-3';
    advancedEditorBtn.innerHTML = '<i class="fas fa-closed-captioning mr-2"></i> Fejlett Feliratszerkesztő';
    advancedEditorBtn.addEventListener('click', openAdvancedSubtitleEditor);
    subtitlePanel.appendChild(advancedEditorBtn);
  }
  
  // Function to open the advanced subtitle editor
  function openAdvancedSubtitleEditor() {
    // Store the current video and subtitle data
    const videoFile = getCurrentVideoFile();
    const subtitleFile = currentSubtitleFile;
    
    // Save current state to localStorage
    if (videoFile) {
      localStorage.setItem('currentVideoSrc', videoFile.src || videoFile.convertedUrl || '');
      localStorage.setItem('currentVideoName', videoFile.name || 'video.mp4');
    }
    
    if (subtitleFile) {
      // We can't store the actual file in localStorage, but we'll handle this scenario in the editor
      localStorage.setItem('hasSubtitleFile', 'true');
    }
    
    // Navigate to the subtitle editor in a new tab
    window.open('/static/subtitle_editor.html', '_blank');
  }
  
  if (subtitleDropZone) {
    subtitleDropZone.addEventListener('click', () => {
      if (subtitleFileInput) subtitleFileInput.click();
    });
    
    subtitleDropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      subtitleDropZone.classList.add('dragover');
    });
    
    subtitleDropZone.addEventListener('dragleave', () => {
      subtitleDropZone.classList.remove('dragover');
    });
    
    subtitleDropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      subtitleDropZone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        handleSubtitleFile(e.dataTransfer.files[0]);
      }
    });
  }
  
  if (subtitleFileInput) {
    subtitleFileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        handleSubtitleFile(e.target.files[0]);
      }
    });
  }
  
  if (removeSubtitleFile) {
    removeSubtitleFile.addEventListener('click', () => {
      currentSubtitleFile = null;
      subtitleFileInfo.classList.add('hidden');
      subtitleFileInput.value = '';
    });
  }
  
  // Get the current video file from main videocutter.js
  function getCurrentVideoFile() {
    if (typeof window.getVideoFile === 'function') {
      return window.getVideoFile();
    } else if (window.currentVideoFile) {
      return window.currentVideoFile;
    } else {
      // Try to find the video player and get the source
      const videoPlayer = document.getElementById('videoPlayer');
      if (videoPlayer && videoPlayer.src) {
        // This is a fallback that won't actually work for uploads
        // but may help with debugging
        console.log("Warning: Using fallback video source method");
        return { name: "video.mp4", size: 0, type: "video/mp4" };
      }
      return null;
    }
  }
  
  function handleSubtitleFile(file) {
    currentSubtitleFile = file;
    if (subtitleFileName) subtitleFileName.textContent = file.name;
    if (subtitleFileInfo) subtitleFileInfo.classList.remove('hidden');
  }
  
  // WebSocket connection for progress updates
  function initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${connectionId}`);
    
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
  
  // Generate subtitles from video automatically
  async function generateSubtitles() {
    const videoFile = getCurrentVideoFile();
    if (!videoFile) {
      alert("Please upload a video file first");
      return;
    }
    
    const formData = new FormData();
    formData.append("file", videoFile);
    formData.append("subtitle_format", document.getElementById('subtitleFormat').value);
    formData.append("identify_speakers", true); // Enable speaker identification
    formData.append("burn_into_video", false); // Don't burn by default, just generate
    formData.append("connection_id", connectionId);
    
    // Show progress
    const processingSection = document.getElementById('processingSection');
    if (processingSection) processingSection.classList.remove('hidden');
    if (progressBar) progressBar.style.width = "0%";
    if (statusText) statusText.textContent = "Generating subtitles...";
    
    // Setup stop button and abort controller
    const stopBtn = document.getElementById('stopProcessingBtn');
    let abortController = new AbortController();
    let signal = abortController.signal;
    
    if (stopBtn) {
      stopBtn.onclick = () => {
        abortController.abort();
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
        if (statusText) statusText.textContent = "Process cancelled by user";
        if (progressBar) progressBar.classList.add("bg-red-500");
        this.disabled = false;
      };
    }
    
    const ws = initWebSocket();
    this.disabled = true;
    
    try {
      const response = await fetch('/api/subtitles/auto_generate', {
        method: "POST",
        body: formData,
        signal: signal
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      const result = await response.json();
      if (progressBar) progressBar.style.width = "100%";
      if (statusText) statusText.textContent = "Subtitles generated successfully!";
      
      // Setup download button
      if (result.subtitle_url) {
        if (downloadSubtitlesBtn) {
          downloadSubtitlesBtn.textContent = "Download Subtitles";
          downloadSubtitlesBtn.onclick = () => window.open(result.subtitle_url, '_blank');
          downloadSubtitlesBtn.classList.remove('hidden');
        }
      }
    } catch (error) {
      console.error("Error generating subtitles:", error);
      if (statusText) statusText.textContent = "Error: " + error.message;
      if (progressBar) progressBar.classList.add("bg-red-500");
    } finally {
      this.disabled = false;
      ws.close();
    }
  }
  
  // Burn subtitles into video
  async function burnSubtitles() {
    const videoFile = getCurrentVideoFile();
    if (!videoFile) {
      alert("Please upload a video file first");
      return;
    }
    
    // Either use existing subtitle file or generate new
    if (!currentSubtitleFile) {
      const generateFirst = confirm("No subtitle file selected. Generate subtitles automatically?");
      if (generateFirst) {
        await generateSubtitles();
        
        // Now we need to get the generated subtitle file
        // This would be complex - in a real implementation, we might 
        // download the subtitle file and then use it
        alert("Please download the generated subtitles and then upload them to burn into the video.");
        return;
      } else {
        alert("Please upload a subtitle file first");
        return;
      }
    }
    
    const formData = new FormData();
    formData.append("video_file", videoFile);
    formData.append("subtitle_file", currentSubtitleFile);
    formData.append("burn_into_video", true);
    formData.append("subtitle_delay", document.getElementById('subtitleDelay').value);
    formData.append("font_size", 24); // Default font size
    formData.append("font_color", "white"); // Default color
    formData.append("background_opacity", 0.5); // Default opacity
    formData.append("connection_id", connectionId);
    
    // Show progress
    const processingSection = document.getElementById('processingSection');
    if (processingSection) processingSection.classList.remove('hidden');
    if (progressBar) progressBar.style.width = "0%";
    if (statusText) statusText.textContent = "Burning subtitles into video...";
    
    // Setup stop button and abort controller
    const stopBtn = document.getElementById('stopProcessingBtn');
    let abortController = new AbortController();
    let signal = abortController.signal;
    
    if (stopBtn) {
      stopBtn.onclick = () => {
        abortController.abort();
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
        if (statusText) statusText.textContent = "Process cancelled by user";
        if (progressBar) progressBar.classList.add("bg-red-500");
        this.disabled = false;
      };
    }
    
    const ws = initWebSocket();
    this.disabled = true;
    
    try {
      const response = await fetch('/api/subtitles/from_srt', {
        method: "POST",
        body: formData,
        signal: signal
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      const result = await response.json();
      if (progressBar) progressBar.style.width = "100%";
      if (statusText) statusText.textContent = "Subtitles burned into video!";
      
      // Setup download button
      if (result.download_url) {
        if (downloadSubtitlesBtn) {
          downloadSubtitlesBtn.textContent = "Download Video with Subtitles";
          downloadSubtitlesBtn.onclick = () => window.open(result.download_url, '_blank');
          downloadSubtitlesBtn.classList.remove('hidden');
        }
      }
    } catch (error) {
      console.error("Error burning subtitles:", error);
      if (statusText) statusText.textContent = "Error: " + error.message;
      if (progressBar) progressBar.classList.add("bg-red-500");
    } finally {
      this.disabled = false;
      ws.close();
    }
  }
  
  // Translate subtitles to another language
  async function translateSubtitles() {
    if (!currentSubtitleFile) {
      alert("Please upload a subtitle file first");
      return;
    }
    
    const targetLang = document.getElementById('translateLanguage').value;
    if (!targetLang) {
      alert("Please select a target language");
      return;
    }
    
    const formData = new FormData();
    formData.append("subtitle_file", currentSubtitleFile);
    formData.append("target_language", targetLang);
    formData.append("output_format", "srt");
    formData.append("connection_id", connectionId);
    
    // Show progress
    const processingSection = document.getElementById('processingSection');
    if (processingSection) processingSection.classList.remove('hidden');
    if (progressBar) progressBar.style.width = "0%";
    if (statusText) statusText.textContent = "Translating subtitles...";
    
    // Setup stop button and abort controller
    const stopBtn = document.getElementById('stopProcessingBtn');
    let abortController = new AbortController();
    let signal = abortController.signal;
    
    if (stopBtn) {
      stopBtn.onclick = () => {
        abortController.abort();
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
        if (statusText) statusText.textContent = "Process cancelled by user";
        if (progressBar) progressBar.classList.add("bg-red-500");
        this.disabled = false;
      };
    }
    
    const ws = initWebSocket();
    this.disabled = true;
    
    try {
      const response = await fetch('/api/subtitles/translate_subtitles', {
        method: "POST",
        body: formData,
        signal: signal
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      const result = await response.json();
      if (progressBar) progressBar.style.width = "100%";
      if (statusText) statusText.textContent = "Subtitles translated successfully!";
      
      // Setup download button
      if (result.download_url) {
        if (downloadSubtitlesBtn) {
          downloadSubtitlesBtn.textContent = `Download Translated Subtitles (${targetLang})`;
          downloadSubtitlesBtn.onclick = () => window.open(result.download_url, '_blank');
          downloadSubtitlesBtn.classList.remove('hidden');
        }
      }
    } catch (error) {
      console.error("Error translating subtitles:", error);
      if (statusText) statusText.textContent = "Error: " + error.message;
      if (progressBar) progressBar.classList.add("bg-red-500");
    } finally {
      this.disabled = false;
      ws.close();
    }
  }
  
  // Convert TXT to SRT function
  async function convertTxtToSrt() {
    if (!currentSubtitleFile) {
      alert("Kérem, töltsön fel egy feliratfájlt először");
      return;
    }
    
    // Check file extension - should be .txt
    const fileExt = currentSubtitleFile.name.split('.').pop().toLowerCase();
    if (fileExt !== 'txt') {
      alert("Kérem, töltsön fel egy TXT formátumú feliratfájlt");
      return;
    }
    
    const formData = new FormData();
    formData.append("subtitle_file", currentSubtitleFile);
    formData.append("connection_id", connectionId);
    
    // Show progress
    const processingSection = document.getElementById('processingSection');
    if (processingSection) processingSection.classList.remove('hidden');
    if (progressBar) progressBar.style.width = "0%";
    if (statusText) statusText.textContent = "TXT fájl konvertálása SRT formátumba...";
    
    // Setup stop button and abort controller
    const stopBtn = document.getElementById('stopProcessingBtn');
    let abortController = new AbortController();
    let signal = abortController.signal;
    
    if (stopBtn) {
      stopBtn.onclick = () => {
        abortController.abort();
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
        if (statusText) statusText.textContent = "A felhasználó megszakította a folyamatot";
        if (progressBar) progressBar.classList.add("bg-red-500");
        this.disabled = false;
      };
    }
    
    const ws = initWebSocket();
    this.disabled = true;
    
    try {
      const response = await fetch('/api/subtitles/convert_txt_to_srt', {
        method: "POST",
        body: formData,
        signal: signal
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      const result = await response.json();
      if (progressBar) progressBar.style.width = "100%";
      if (statusText) statusText.textContent = "TXT felirat sikeresen konvertálva SRT formátumba!";
      
      // Setup download button
      if (result.download_url) {
        if (downloadSubtitlesBtn) {
          downloadSubtitlesBtn.textContent = "Konvertált SRT felirat letöltése";
          downloadSubtitlesBtn.onclick = () => window.open(result.download_url, '_blank');
          downloadSubtitlesBtn.classList.remove('hidden');
        }
      }
    } catch (error) {
      console.error("Hiba a TXT→SRT konvertálás során:", error);
      if (statusText) statusText.textContent = "Hiba: " + error.message;
      if (progressBar) progressBar.classList.add("bg-red-500");
    } finally {
      this.disabled = false;
      ws.close();
    }
  }
});