// Initialization module for Video Editor
// This handles proper loading and coordination of all modules

document.addEventListener('DOMContentLoaded', function() {
  console.log("🚀 Video Editor Initialization Started");
  
  // Check if we're on the video editor page
  if (!window.location.pathname.includes('videocutter') && 
      !window.location.pathname.includes('videoeditor')) {
    console.log("Not on video editor page, skipping initialization");
    return;
  }
  
  console.log("📋 Video Editor Page Detected");
  
  // Ensure lucide icons are created
  if (typeof lucide !== 'undefined' && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
    console.log("✅ Lucide icons initialized");
  } else {
    console.error("❌ Lucide library not available");
  }
  
  // Initialize global variables
  window.videoEditorState = {
    currentVideoFile: null,
    currentSubtitleFile: null,
    videoDuration: 0,
    startTime: 0,
    endTime: 0,
    connectionId: crypto.randomUUID(),
    currentActiveTab: 'trim',
    zoomLevel: 1,
    scrollOffset: 0
  };
  
  // Make getVideoFile available to other modules
  window.getVideoFile = function() {
    return window.videoEditorState.currentVideoFile;
  };
  
  // Main DOM elements
  const elements = {
    // Video elements
    videoDropZone: document.getElementById('videoDropZone'),
    videoFileInput: document.getElementById('videoFileInput'),
    videoFileInfo: document.getElementById('videoFileInfo'),
    videoFileName: document.getElementById('videoFileName'),
    videoFileSize: document.getElementById('videoFileSize'),
    removeVideoFile: document.getElementById('removeVideoFile'),
    videoPreviewSection: document.getElementById('videoPreviewSection'),
    videoPlayer: document.getElementById('videoPlayer'),
    
    // Tab elements
    trimTab: document.getElementById('trimTab'),
    subtitleTab: document.getElementById('subtitleTab'),
    effectsTab: document.getElementById('effectsTab'),
    
    // Options panels
    editingOptions: document.getElementById('editingOptions'),
    trimOptionsPanel: document.getElementById('trimOptionsPanel'),
    subtitleOptionsPanel: document.getElementById('subtitleOptionsPanel'),
    effectsOptionsPanel: document.getElementById('effectsOptionsPanel'),
    
    // Timeline elements
    timelineMarker: document.getElementById('timelineMarker'),
    trimRegion: document.getElementById('trimRegion'),
    startTimeInput: document.getElementById('startTimeInput'),
    endTimeInput: document.getElementById('endTimeInput'),
    setStartTimeBtn: document.getElementById('setStartTimeBtn'),
    setEndTimeBtn: document.getElementById('setEndTimeBtn'),
    
    // Action buttons
    trimVideoBtn: document.getElementById('trimVideoBtn'),
    executeTrimBtn: document.getElementById('executeTrimBtn'),
    
    // Progress and download
    processingSection: document.getElementById('processingSection'),
    progressBar: document.getElementById('progressBar'),
    statusText: document.getElementById('statusText'),
    downloadBtn: document.getElementById('downloadBtn')
  };
  
  // Check if critical elements exist
  let criticalElementsMissing = false;
  for (const [key, element] of Object.entries(elements)) {
    if (element === null) {
      console.error(`❌ Critical element missing: ${key}`);
      criticalElementsMissing = true;
    }
  }
  
  if (criticalElementsMissing) {
    console.error("❌ Some critical elements are missing. Functionality may be limited.");
  } else {
    console.log("✅ All critical DOM elements found");
  }
  
  // Function to format file size
  function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
  
  // Function to handle video file selection
  function handleVideoFile(file) {
    console.log("📺 Video file selected:", file.name);
    window.videoEditorState.currentVideoFile = file;
    
    if (elements.videoFileName) elements.videoFileName.textContent = file.name;
    if (elements.videoFileSize) elements.videoFileSize.textContent = formatFileSize(file.size);
    if (elements.videoFileInfo) elements.videoFileInfo.classList.remove('hidden');
    
    // Create object URL for video preview
    if (elements.videoPlayer) {
      const videoURL = URL.createObjectURL(file);
      elements.videoPlayer.src = videoURL;
      
      // Show preview section and options
      if (elements.videoPreviewSection) elements.videoPreviewSection.classList.remove('hidden');
      if (elements.editingOptions) elements.editingOptions.classList.remove('hidden');
      if (elements.trimVideoBtn) elements.trimVideoBtn.classList.remove('hidden');
      
      // Show subtitle panel after video is loaded
      const subtitlesPanel = document.getElementById('subtitles-panel');
      if (subtitlesPanel) {
        subtitlesPanel.style.display = 'block';
        console.log("Subtitle panel displayed");
      }
      
      // Reset timeline when a new video is loaded
      elements.videoPlayer.onloadedmetadata = function() {
        window.videoEditorState.videoDuration = elements.videoPlayer.duration;
        window.videoEditorState.startTime = 0;
        window.videoEditorState.endTime = elements.videoPlayer.duration;
        
        if (elements.startTimeInput) {
          elements.startTimeInput.value = formatTime(window.videoEditorState.startTime);
        }
        if (elements.endTimeInput) {
          elements.endTimeInput.value = formatTime(window.videoEditorState.endTime);
        }
        
        updateTrimRegion();
        
        // Display initial time
        const currentTimeDisplay = document.getElementById('currentTimeDisplay');
        if (currentTimeDisplay) {
          currentTimeDisplay.textContent = `${formatTime(0)} / ${formatTime(window.videoEditorState.videoDuration)}`;
        }
      };
    }
  }
  
  // Format time (seconds to HH:MM:SS)
  function formatTime(seconds) {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  
  // Update trim region on the timeline
  function updateTrimRegion() {
    if (!elements.trimRegion) return;
    
    const videoTimeline = document.getElementById('videoTimeline');
    if (!videoTimeline || window.videoEditorState.videoDuration <= 0) return;
    
    const timelineWidth = videoTimeline.clientWidth;
    const startPos = (window.videoEditorState.startTime / window.videoEditorState.videoDuration) * timelineWidth;
    const endPos = (window.videoEditorState.endTime / window.videoEditorState.videoDuration) * timelineWidth;
    
    elements.trimRegion.style.left = startPos + 'px';
    elements.trimRegion.style.width = (endPos - startPos) + 'px';
  }
  
  // Tab switching
  function switchTab(tabName) {
    console.log(`🔄 Switching to tab: ${tabName}`);
    
    // Hide all panels
    if (elements.trimOptionsPanel) elements.trimOptionsPanel.classList.add('hidden');
    if (elements.subtitleOptionsPanel) elements.subtitleOptionsPanel.classList.add('hidden');
    if (elements.effectsOptionsPanel) elements.effectsOptionsPanel.classList.add('hidden');
    
    // Reset all tabs
    const tabClass = 'inactive-tab border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 whitespace-nowrap py-2 px-4 border-b-2 font-medium text-sm';
    const activeTabClass = 'active-tab border-[var(--editor-accent)] text-[var(--editor-accent)] whitespace-nowrap py-2 px-4 border-b-2 font-medium text-sm';
    
    if (elements.trimTab) elements.trimTab.className = tabClass;
    if (elements.subtitleTab) elements.subtitleTab.className = tabClass;
    if (elements.effectsTab) elements.effectsTab.className = tabClass;
    
    // Show selected panel and activate tab
    if (tabName === 'trim') {
      if (elements.trimOptionsPanel) elements.trimOptionsPanel.classList.remove('hidden');
      if (elements.trimTab) elements.trimTab.className = activeTabClass;
      if (elements.trimVideoBtn) elements.trimVideoBtn.classList.remove('hidden');
    } else if (tabName === 'subtitle') {
      if (elements.subtitleOptionsPanel) elements.subtitleOptionsPanel.classList.remove('hidden');
      if (elements.subtitleTab) elements.subtitleTab.className = activeTabClass;
      if (elements.trimVideoBtn) elements.trimVideoBtn.classList.add('hidden');
    } else if (tabName === 'effects') {
      if (elements.effectsOptionsPanel) elements.effectsOptionsPanel.classList.remove('hidden');
      if (elements.effectsTab) elements.effectsTab.className = activeTabClass;
      if (elements.trimVideoBtn) elements.trimVideoBtn.classList.add('hidden');
    }
    
    window.videoEditorState.currentActiveTab = tabName;
  }
  
  // Attach event listeners
  // 1. Video drop zone
  if (elements.videoDropZone) {
    console.log("🔌 Attaching video drop zone events");
    
    elements.videoDropZone.addEventListener('click', () => {
      console.log("🖱️ Video drop zone clicked");
      if (elements.videoFileInput) elements.videoFileInput.click();
    });
    
    elements.videoDropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      elements.videoDropZone.classList.add('dragover');
    });
    
    elements.videoDropZone.addEventListener('dragleave', () => {
      elements.videoDropZone.classList.remove('dragover');
    });
    
    elements.videoDropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      console.log("📥 File dropped");
      elements.videoDropZone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0 && e.dataTransfer.files[0].type.startsWith('video/')) {
        handleVideoFile(e.dataTransfer.files[0]);
      }
    });
  }
  
  // 2. File input
  if (elements.videoFileInput) {
    elements.videoFileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        console.log("📁 File selected via input");
        handleVideoFile(e.target.files[0]);
      }
    });
  }
  
  // 3. Remove file button
  if (elements.removeVideoFile) {
    elements.removeVideoFile.addEventListener('click', () => {
      console.log("🗑️ Removing video file");
      window.videoEditorState.currentVideoFile = null;
      
      if (elements.videoFileInfo) elements.videoFileInfo.classList.add('hidden');
      if (elements.videoPreviewSection) elements.videoPreviewSection.classList.add('hidden');
      if (elements.editingOptions) elements.editingOptions.classList.add('hidden');
      if (elements.trimVideoBtn) elements.trimVideoBtn.classList.add('hidden');
      if (elements.downloadBtn) elements.downloadBtn.classList.add('hidden');
      
      if (elements.videoFileInput) elements.videoFileInput.value = '';
      
      // Reset video player
      if (elements.videoPlayer) {
        elements.videoPlayer.src = '';
        if (elements.videoPlayer.src && typeof URL.revokeObjectURL === 'function') {
          URL.revokeObjectURL(elements.videoPlayer.src);
        }
      }
    });
  }
  
  // 4. Tab switching
  if (elements.trimTab) {
    elements.trimTab.addEventListener('click', () => switchTab('trim'));
  }
  
  if (elements.subtitleTab) {
    elements.subtitleTab.addEventListener('click', () => switchTab('subtitle'));
  }
  
  if (elements.effectsTab) {
    elements.effectsTab.addEventListener('click', () => switchTab('effects'));
  }
  
  // 5. Time inputs
  if (elements.startTimeInput) {
    elements.startTimeInput.addEventListener('change', function() {
      const timeArr = this.value.split(':').map(part => parseInt(part, 10));
      let seconds = 0;
      if (timeArr.length === 3) {
        seconds = timeArr[0] * 3600 + timeArr[1] * 60 + timeArr[2];
      } else if (timeArr.length === 2) {
        seconds = timeArr[0] * 60 + timeArr[1];
      }
      
      window.videoEditorState.startTime = seconds;
      updateTrimRegion();
    });
  }
  
  if (elements.endTimeInput) {
    elements.endTimeInput.addEventListener('change', function() {
      const timeArr = this.value.split(':').map(part => parseInt(part, 10));
      let seconds = 0;
      if (timeArr.length === 3) {
        seconds = timeArr[0] * 3600 + timeArr[1] * 60 + timeArr[2];
      } else if (timeArr.length === 2) {
        seconds = timeArr[0] * 60 + timeArr[1];
      }
      
      window.videoEditorState.endTime = seconds;
      updateTrimRegion();
    });
  }
  
  // 6. Set current time as start/end time
  if (elements.setStartTimeBtn && elements.videoPlayer) {
    elements.setStartTimeBtn.addEventListener('click', function() {
      window.videoEditorState.startTime = elements.videoPlayer.currentTime;
      if (elements.startTimeInput) {
        elements.startTimeInput.value = formatTime(window.videoEditorState.startTime);
      }
      updateTrimRegion();
    });
  }
  
  if (elements.setEndTimeBtn && elements.videoPlayer) {
    elements.setEndTimeBtn.addEventListener('click', function() {
      window.videoEditorState.endTime = elements.videoPlayer.currentTime;
      if (elements.endTimeInput) {
        elements.endTimeInput.value = formatTime(window.videoEditorState.endTime);
      }
      updateTrimRegion();
    });
  }
  
  // 7. Trim video button
  if (elements.trimVideoBtn || elements.executeTrimBtn) {
    console.log("🔌 Attaching trim button events");
    const executeTrim = async function() {
      if (!window.videoEditorState.currentVideoFile) {
        alert("Please upload a video file first");
        return;
      }
      
      // Get form elements
      const startTime = elements.startTimeInput ? elements.startTimeInput.value : formatTime(window.videoEditorState.startTime);
      const endTime = elements.endTimeInput ? elements.endTimeInput.value : formatTime(window.videoEditorState.endTime);
      const outputFormat = document.getElementById('outputFormat');
      const extractAudio = document.getElementById('extractAudio');
      const preserveSubtitles = document.getElementById('preserveSubtitles');
      
      // Prepare form data
      const formData = new FormData();
      formData.append("file", window.videoEditorState.currentVideoFile);
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
      
      // Generate connection ID for WebSocket
      const connectionId = crypto.randomUUID();
      formData.append("connection_id", connectionId);
      
      // Initialize WebSocket
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${connectionId}`);
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (elements.progressBar) elements.progressBar.style.width = data.progress + "%";
        if (elements.statusText) elements.statusText.textContent = data.status;
      };
      
      // Show progress bar
      if (elements.processingSection) elements.processingSection.classList.remove('hidden');
      if (elements.progressBar) elements.progressBar.style.width = "0%";
      if (elements.statusText) elements.statusText.textContent = "Starting video trim...";
      
      // Disable button while processing
      this.disabled = true;
      
      try {
        console.log("📤 Sending video trim request");
        // Send request to server
        const response = await fetch('/api/videoeditor/trim', {
          method: "POST",
          body: formData
        });
        
        if (!response.ok) {
          throw new Error(await response.text());
        }
        
        // Process response
        const result = await response.json();
        console.log("✅ Trim complete, result:", result);
        if (elements.progressBar) elements.progressBar.style.width = "100%";
        if (elements.statusText) elements.statusText.textContent = "Video trimming complete!";
        
        // Setup download button
        if (result.download_url && elements.downloadBtn) {
          elements.downloadBtn.innerHTML = '<i data-lucide="download" class="w-5 h-5"></i> Download Trimmed Video';
          elements.downloadBtn.onclick = () => window.open(result.download_url, '_blank');
          elements.downloadBtn.classList.remove('hidden');
          lucide.createIcons();
        }
      } catch (error) {
        console.error("❌ Error trimming video:", error);
        if (elements.statusText) elements.statusText.textContent = "Error: " + error.message;
        if (elements.progressBar) elements.progressBar.style.width = "0%";
      } finally {
        this.disabled = false;
        ws.close();
      }
    };
    
    if (elements.trimVideoBtn) {
      elements.trimVideoBtn.addEventListener('click', executeTrim);
    }
    
    if (elements.executeTrimBtn) {
      elements.executeTrimBtn.addEventListener('click', executeTrim);
    }
  }
  
  // Initialize UI with default tab
  switchTab('trim');
  console.log("🎬 Video Editor Initialization Complete");
});