/**
 * Video Module - Handles video player and file management
 */

const VideoModule = {
  videoPlayer: null,  // Will hold reference to the video element
  currentVideoFile: null,  // Current video file object
  
  // Initialize the module
  init: function() {
    console.log("Video Module initialized");
    this.videoPlayer = document.getElementById('videoPlayer');
    
    // Add listener for the custom videoloaded event
    document.addEventListener('videoloaded', (event) => {
      console.log("Video loaded event received, notifying other modules");
      
      // Update timeline and trim tools
      setTimeout(() => {
        if (typeof TimerModule !== 'undefined' && TimerModule.updateTrimRegion) {
          TimerModule.updateTrimRegion();
          TimerModule.createTimeMarkings();
        }
        
        // Check if we should initialize subtitle tools
        const subtitleEditor = document.getElementById('subtitleEditorPanel');
        if (subtitleEditor) {
          subtitleEditor.classList.remove('hidden');
          console.log("Enabling subtitle editor for loaded video");
        }
      }, 200);
    });
    
    // Wait for Video.js initialization
    // We're relying on the global window.vjsPlayer being set in the HTML
    this.checkVideoJsInitialized();
  },
  
  // Check if Video.js is initialized
  checkVideoJsInitialized: function() {
    if (window.vjsPlayer) {
      console.log("Found Video.js player:", window.vjsPlayer);
      this.vjsPlayer = window.vjsPlayer;
    } else {
      console.warn("Video.js player not found yet, will check again in 100ms");
      setTimeout(() => this.checkVideoJsInitialized(), 100);
    }
    
    if (this.videoPlayer) {
      // Set up video player event listeners
      this.videoPlayer.addEventListener('timeupdate', () => {
        this.updateTimeDisplay();
        TimerModule.updateTimelineMarker();
        
        // Update the current position in the UI
        const currentTime = this.videoPlayer.currentTime;
        const duration = this.videoPlayer.duration;
        
        // When playing video, if we're outside trim region, snap to start
        if (currentTime < window.startTime || currentTime > window.endTime) {
          // We're outside the selected region - snap back to start
          if (currentTime < window.startTime) {
            this.videoPlayer.currentTime = window.startTime;
          } else if (currentTime > window.endTime) {
            this.videoPlayer.pause();
            this.videoPlayer.currentTime = window.startTime;
          }
        }
      });
      
      this.videoPlayer.addEventListener('loadedmetadata', () => {
        console.log("Video metadata loaded");
        console.log("Video element properties:", {
          duration: this.videoPlayer.duration,
          videoWidth: this.videoPlayer.videoWidth,
          videoHeight: this.videoPlayer.videoHeight,
          readyState: this.videoPlayer.readyState,
          networkState: this.videoPlayer.networkState,
          error: this.videoPlayer.error
        });
        
        window.videoDuration = this.videoPlayer.duration;
        window.startTime = 0;
        window.endTime = this.videoPlayer.duration;
        
        const startTimeInput = document.getElementById('startTimeInput');
        const endTimeInput = document.getElementById('endTimeInput');
        
        if (startTimeInput) startTimeInput.value = TimerModule.formatTime(window.startTime);
        if (endTimeInput) endTimeInput.value = TimerModule.formatTime(window.endTime);
        
        // Initialize trim region and time markings
        TimerModule.updateTrimRegion();
        TimerModule.createTimeMarkings();
        
        // Make sure the trim handles are properly positioned
        const leftHandle = document.getElementById('leftTrimHandle');
        const rightHandle = document.getElementById('rightTrimHandle');
        const leftHandleLabel = document.getElementById('leftHandleLabel');
        const rightHandleLabel = document.getElementById('rightHandleLabel');
        
        if (leftHandle && rightHandle) {
          leftHandle.style.display = 'flex';
          rightHandle.style.display = 'flex';
        }
        
        // Update handle time labels
        if (leftHandleLabel) leftHandleLabel.textContent = TimerModule.formatTime(window.startTime);
        if (rightHandleLabel) rightHandleLabel.textContent = TimerModule.formatTime(window.endTime);
        
        // Update project info
        this.updateProjectInfo();
      });
      
      this.videoPlayer.addEventListener('play', () => this.updatePlayPauseButton());
      this.videoPlayer.addEventListener('pause', () => this.updatePlayPauseButton());
    }
  },
  
  // Handle a new video file
  handleVideoFile: function(file) {
    // Support video files with different MIME types or file extensions
    // Some AVI/MKV files have different MIME types or unrecognized MIME types
    const acceptedExtensions = ['.mp4', '.webm', '.avi', '.mov', '.mkv', '.ogg', '.ogv', '.flv', '.wmv'];
    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
    
    console.log("File info:", file.name, "Type:", file.type || "unknown MIME type", "Extension:", fileExtension);
    
    // Diagnosztikai célból kiírom a File objektum összes tulajdonságát
    console.log("Full file object properties:", Object.getOwnPropertyNames(file));
    for (const prop of Object.getOwnPropertyNames(file)) {
      try {
        console.log(`File.${prop} =`, file[prop]);
      } catch (e) {
        console.log(`Unable to access File.${prop}:`, e);
      }
    }
    
    // Check only file extension since MIME types can be unreliable for MKV and other formats
    // We'll skip the MIME type check entirely for simplicity
    if (!file || !acceptedExtensions.includes(fileExtension)) {
      console.error("Invalid file extension:", fileExtension, "Accepted extensions:", acceptedExtensions);
      alert("Nem támogatott fájlformátum. Támogatott formátumok: " + acceptedExtensions.join(', '));
      return;
    }
    
    // Log successful acceptance
    console.log("File accepted based on extension:", fileExtension);
    
    // Special handling for MKV files - auto convert to MP4
    if (fileExtension === '.mkv') {
      console.warn("MKV file detected - automatically converting to MP4 for better compatibility");
      
      // Show conversion dialog
      const processingDialog = document.getElementById('processingDialog');
      const progressBar = document.getElementById('progressBar');
      const processingStatus = document.getElementById('processingStatus');
      
      if (processingDialog) processingDialog.style.display = 'flex';
      if (progressBar) progressBar.style.width = '10%';
      if (processingStatus) processingStatus.textContent = 'MKV fájl konvertálása MP4 formátumra... (Ez eltarthat néhány percig)';
      
      // Debug log entire file object
      console.log("Converting MKV file:", file);
      console.log("File details:", {
        name: file.name,
        size: file.size,
        type: file.type,
        lastModified: file.lastModified
      });
      
      // Try direct conversion approach that we know works - use videocutter API
      const formData = new FormData();
      formData.append("file", file);
      formData.append("target_format", "mp4");
      
      // Generate connection ID for WebSocket progress updates
      const connectionId = crypto.randomUUID();
      formData.append("connection_id", connectionId);
      console.log("Using connection ID:", connectionId);
      
      // Setup WebSocket for progress updates
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const wsUrl = `${protocol}://${window.location.host}/ws/${connectionId}`;
      console.log("WebSocket URL:", wsUrl);
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = (event) => {
        console.log("WebSocket connection opened:", event);
      };
      
      ws.onerror = (event) => {
        console.error("WebSocket error:", event);
      };
      
      ws.onclose = (event) => {
        console.log("WebSocket connection closed:", event);
      };
      
      ws.onmessage = (event) => {
        console.log("WebSocket message received:", event.data);
        try {
          const data = JSON.parse(event.data);
          console.log("Parsed WebSocket data:", data);
          if (progressBar) progressBar.style.width = data.progress + "%";
          if (processingStatus) processingStatus.textContent = data.status;
        } catch (error) {
          console.error("WebSocket message parsing error:", error);
        }
      };
      
      // Send request to API for conversion using videocutter API endpoint
      console.log("Sending conversion request to /api/videocutter/convert");
      fetch('/api/videocutter/convert', {
        method: 'POST',
        body: formData
      })
      .then(response => {
        console.log("Conversion response status:", response.status);
        console.log("Conversion response headers:", Array.from(response.headers.entries()));
        if (!response.ok) {
          console.error("Conversion response error:", response.statusText);
          throw new Error('Konvertálási hiba: ' + response.statusText);
        }
        return response.json();
      })
      .then(data => {
        console.log("Conversion successful, received data:", data);
        
        // Hide processing dialog
        if (processingDialog) processingDialog.style.display = 'none';
        
        // Determine the correct video URL
        const videoURL = data.download_url;
        console.log("Using converted video URL:", videoURL);
        
        // This is important - we create a new video element to replace the existing one
        // to ensure the browser recognizes the new video format
        this.currentVideoFile = {
          name: file.name.replace('.mkv', '_converted.mp4'),
          size: file.size, 
          type: 'video/mp4',
          convertedUrl: videoURL
        };
        window.currentVideoFile = this.currentVideoFile;
        
        // Now, let's load this video into the player
        if (this.videoPlayer) {
          // First remove old sources
          while (this.videoPlayer.firstChild) {
            this.videoPlayer.removeChild(this.videoPlayer.firstChild);
          }
          
          // Fetch the MP4 file 
          fetch(videoURL)
            .then(response => response.blob())
            .then(blob => {
              // Create a File object from the blob
              const mp4File = new File([blob], this.currentVideoFile.name, {
                type: 'video/mp4'
              });
              
              console.log("Created MP4 File object:", mp4File);
              
              // Create an object URL
              const objectUrl = URL.createObjectURL(mp4File);
              
              // Set up video source
              const source = document.createElement('source');
              source.src = objectUrl;
              source.type = 'video/mp4';
              this.videoPlayer.appendChild(source);
              
              // Also set src attribute
              this.videoPlayer.src = objectUrl;
              
              // Load video
              this.videoPlayer.load();
              
              // Update Plyr player if available
              if (window.plyrPlayer) {
                try {
                  window.plyrPlayer.source = {
                    type: 'video',
                    title: this.currentVideoFile.name,
                    sources: [{
                      src: objectUrl,
                      type: 'video/mp4'
                    }]
                  };
                  
                  // Test playback
                  setTimeout(() => {
                    window.plyrPlayer.play().then(() => {
                      console.log("Plyr playback started successfully");
                      setTimeout(() => window.plyrPlayer.pause(), 100);
                    }).catch(err => {
                      console.error("Plyr playback failed:", err);
                    });
                  }, 500);
                } catch (e) {
                  console.error("Error setting Plyr source:", e);
                }
              }
              
              // Try playing the video briefly to initialize codec
              this.videoPlayer.play().then(() => {
                console.log("Converted video playback started successfully");
                setTimeout(() => this.videoPlayer.pause(), 100);
              }).catch(err => {
                console.error("Error starting converted video playback:", err);
              });
              
              // Show success message
              console.log("MKV video successfully converted and loaded");
              
              // Update UI elements 
              const videoFileName = document.getElementById('videoFileName');
              const videoFileSize = document.getElementById('videoFileSize');
              const videoFileInfo = document.getElementById('videoFileInfo');
              const videoPreviewSection = document.getElementById('videoPreviewSection');
              const editingOptions = document.getElementById('editingOptions');
              const trimVideoBtn = document.getElementById('trimVideoBtn');
              
              if (videoFileName) videoFileName.textContent = this.currentVideoFile.name;
              if (videoFileSize) videoFileSize.textContent = this.formatFileSize(this.currentVideoFile.size);
              if (videoFileInfo) videoFileInfo.classList.remove('hidden');
              
              // Create a direct download button
              const downloadBtn = document.createElement('button');
              downloadBtn.className = 'btn btn-primary';
              downloadBtn.textContent = 'MP4 letöltése';
              downloadBtn.style.marginTop = '10px';
              downloadBtn.style.display = 'block';
              downloadBtn.onclick = () => window.open(videoURL, '_blank');
              
              if (videoFileInfo && !videoFileInfo.querySelector('.btn.btn-primary')) {
                videoFileInfo.appendChild(downloadBtn);
              }
              
              // Show relevant sections
              if (videoPreviewSection) videoPreviewSection.classList.remove('hidden');
              if (editingOptions) editingOptions.classList.remove('hidden');
              if (trimVideoBtn) trimVideoBtn.classList.remove('hidden');
              
              // Show notification to the user
              alert("Az MKV fájl sikeresen konvertálva MP4 formátumra és betöltve a lejátszóba.");
              
              // Important: trigger the video loaded event manually
              const videoLoadedEvent = new Event('videoloaded');
              document.dispatchEvent(videoLoadedEvent);
            })
            .catch(error => {
              console.error("Error loading converted file:", error);
              alert("Hiba történt a konvertált fájl betöltése közben.");
            });
        }
      })
      .catch(error => {
        console.error("Conversion error:", error);
        
        // Hide processing dialog
        if (processingDialog) processingDialog.style.display = 'none';
        
        // Show error message
        alert("Hiba történt az MKV fájl konvertálása közben: " + error.message);
      })
      .finally(() => {
        // Close WebSocket
        ws.close();
      });
      
      // Return early - we'll handle the converted file later
      return;
    }
    
    this.currentVideoFile = file;
    window.currentVideoFile = file;  // For global access
    
    // Update UI elements
    const videoFileName = document.getElementById('videoFileName');
    const videoFileSize = document.getElementById('videoFileSize');
    const videoFileInfo = document.getElementById('videoFileInfo');
    const videoPreviewSection = document.getElementById('videoPreviewSection');
    const editingOptions = document.getElementById('editingOptions');
    const trimVideoBtn = document.getElementById('trimVideoBtn');
    
    if (videoFileName) videoFileName.textContent = file.name;
    if (videoFileSize) videoFileSize.textContent = this.formatFileSize(file.size);
    if (videoFileInfo) videoFileInfo.classList.remove('hidden');
    
    // Create a URL for the video player
    if (this.videoPlayer) {
      try {
        console.log("Creating object URL for video player");
        const videoURL = URL.createObjectURL(file);
        console.log("Created URL:", videoURL);
        
        // Clear existing sources
        while (this.videoPlayer.firstChild) {
          this.videoPlayer.removeChild(this.videoPlayer.firstChild);
        }
        
        // Create new source element with the correct type
        const source = document.createElement('source');
        source.src = videoURL;
        
        // Try to determine the correct type or use a generic video type
        if (file.type) {
          source.type = file.type;
        } else {
          // Guess the type based on extension
          if (fileExtension === '.mkv') {
            source.type = 'video/x-matroska';
          } else if (fileExtension === '.avi') {
            source.type = 'video/x-msvideo';
          } else if (fileExtension === '.mov') {
            source.type = 'video/quicktime';
          } else if (fileExtension === '.mp4') {
            source.type = 'video/mp4';
          } else if (fileExtension === '.webm') {
            source.type = 'video/webm';
          } else {
            source.type = 'video/mp4'; // Generic fallback
          }
        }
        
        console.log("Created source element with type:", source.type);
        this.videoPlayer.appendChild(source);
        
        // Also set src attribute for older browsers
        this.videoPlayer.src = videoURL;
        
        // Force browser to reload the video element
        this.videoPlayer.load();
        
        // Update Plyr player if available
        if (window.plyrPlayer) {
          console.log("Updating Plyr player source");
          
          // Set source for Plyr
          try {
            // Update Plyr source
            window.plyrPlayer.source = {
              type: 'video',
              title: file.name,
              sources: [{
                src: videoURL,
                type: source.type
              }]
            };
            
            console.log("Plyr source set successfully");
            
            // Force play to check if it works
            setTimeout(() => {
              window.plyrPlayer.play().then(() => {
                console.log("Plyr playback started successfully");
                // Pause after a moment
                setTimeout(() => window.plyrPlayer.pause(), 100);
              }).catch(err => {
                console.error("Plyr playback failed:", err);
              });
            }, 500);
          } catch (e) {
            console.error("Error setting Plyr source:", e);
          }
        }
        
        // Add error event listener
        this.videoPlayer.addEventListener('error', (e) => {
          console.error("Video element error:", this.videoPlayer.error);
          console.error("Error event:", e);
          alert(`Videó betöltési hiba: ${this.videoPlayer.error ? this.videoPlayer.error.message : 'Ismeretlen hiba'}`);
        });
        
        // Try playing the video (even if just for a moment) to force codec initialization
        this.videoPlayer.play().then(() => {
          console.log("Video playback started successfully");
          // Pause it immediately
          setTimeout(() => this.videoPlayer.pause(), 100);
          
          // Important: trigger the video loaded event manually
          const videoLoadedEvent = new Event('videoloaded');
          document.dispatchEvent(videoLoadedEvent);
        }).catch(err => {
          console.error("Error starting video playback:", err);
        });
      } catch (error) {
        console.error("Error creating object URL:", error);
        alert("Hiba történt a videó betöltése közben. Részletek a konzolban.");
      }
      
      // Show relevant sections
      if (videoPreviewSection) videoPreviewSection.classList.remove('hidden');
      if (editingOptions) editingOptions.classList.remove('hidden');
      if (trimVideoBtn) trimVideoBtn.classList.remove('hidden');
    }
    
    console.log(`Video file loaded: ${file.name} (${this.formatFileSize(file.size)})`);
  },
  
  // Toggle play/pause
  togglePlayPause: function() {
    if (!this.videoPlayer) return;
    
    // Use Video.js if available
    if (this.vjsPlayer || window.vjsPlayer) {
      const player = this.vjsPlayer || window.vjsPlayer;
      
      if (player.paused()) {
        // Make sure we're starting at the correct position
        if (player.currentTime() < window.startTime || player.currentTime() > window.endTime) {
          player.currentTime(window.startTime);
        }
        player.play();
      } else {
        player.pause();
      }
    } else {
      // Fallback to standard HTML5 video
      if (this.videoPlayer.paused) {
        // Make sure we're starting at the correct position
        if (this.videoPlayer.currentTime < window.startTime || this.videoPlayer.currentTime > window.endTime) {
          this.videoPlayer.currentTime = window.startTime;
        }
        this.videoPlayer.play();
      } else {
        this.videoPlayer.pause();
      }
    }
    
    this.updatePlayPauseButton();
  },
  
  // Update play/pause button appearance
  updatePlayPauseButton: function() {
    const playPauseBtn = document.getElementById('playPauseBtn');
    if (!playPauseBtn) return;
    
    // Determine if the video is paused
    let isPaused = true;
    
    // Check Video.js player first if available
    if (this.vjsPlayer || window.vjsPlayer) {
      const player = this.vjsPlayer || window.vjsPlayer;
      isPaused = player.paused();
    } 
    // Fallback to standard HTML5 video element
    else if (this.videoPlayer) {
      isPaused = this.videoPlayer.paused;
    }
    
    // Clear existing icon
    playPauseBtn.innerHTML = '';
    
    // Create new icon
    const icon = document.createElement('i');
    icon.setAttribute('data-lucide', isPaused ? 'play' : 'pause');
    icon.className = 'w-4 h-4';
    
    playPauseBtn.appendChild(icon);
    
    // Create icons if lucide is available
    if (typeof lucide !== 'undefined' && typeof lucide.createIcons === 'function') {
      lucide.createIcons();
    }
  },
  
  // Update time display
  updateTimeDisplay: function() {
    if (!this.videoPlayer) return;
    
    const currentTimeDisplay = document.getElementById('currentTimeDisplay');
    const playbackInfo = document.getElementById('playbackInfo');
    const timerIndicator = document.querySelector('.timer-indicator');
    
    // Get current time and duration from appropriate player
    let currentTime = 0;
    let duration = 0;
    
    if (this.vjsPlayer || window.vjsPlayer) {
      const player = this.vjsPlayer || window.vjsPlayer;
      currentTime = player.currentTime() || 0;
      duration = player.duration() || 0;
    } else {
      currentTime = this.videoPlayer.currentTime || 0;
      duration = this.videoPlayer.duration || 0;
    }
    
    const formattedCurrentTime = TimerModule.formatTime(currentTime);
    const formattedDuration = TimerModule.formatTime(duration);
    
    if (currentTimeDisplay) {
      currentTimeDisplay.textContent = `${formattedCurrentTime} / ${formattedDuration}`;
    }
    
    if (playbackInfo) {
      playbackInfo.textContent = `${formattedCurrentTime} / ${formattedDuration}`;
    }
    
    if (timerIndicator) {
      timerIndicator.textContent = formattedCurrentTime;
    }
  },
  
  // Seek to a specific time
  seekTo: function(time) {
    if (!this.videoPlayer) return;
    
    // Get video duration
    let duration = 0;
    if (this.vjsPlayer || window.vjsPlayer) {
      const player = this.vjsPlayer || window.vjsPlayer;
      duration = player.duration() || 0;
    } else {
      duration = this.videoPlayer.duration || 0;
    }
    
    // Choose a target time within the allowed range
    let targetTime = Math.max(0, Math.min(time, duration));
    
    // If we're in preview mode, constrain to selection boundaries
    const previewSelection = document.getElementById('previewSelection');
    if (previewSelection && previewSelection.checked) {
      targetTime = Math.max(window.startTime, Math.min(targetTime, window.endTime));
    }
    
    // Set current time in the appropriate player
    if (this.vjsPlayer || window.vjsPlayer) {
      const player = this.vjsPlayer || window.vjsPlayer;
      player.currentTime(targetTime);
    } else {
      this.videoPlayer.currentTime = targetTime;
    }
    
    this.updateTimeDisplay();
    TimerModule.updateTimelineMarker();
  },
  
  // Seek relative to current position
  seekRelative: function(offset) {
    if (!this.videoPlayer) return;
    
    let currentTime = 0;
    
    // Get current time from appropriate player
    if (this.vjsPlayer || window.vjsPlayer) {
      const player = this.vjsPlayer || window.vjsPlayer;
      currentTime = player.currentTime();
    } else {
      currentTime = this.videoPlayer.currentTime;
    }
    
    const newTime = currentTime + offset;
    this.seekTo(newTime);
  },
  
  // Format file size for display
  formatFileSize: function(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  },
  
  // Update project info display
  updateProjectInfo: function() {
    const projectInfo = document.getElementById('projectInfo');
    if (!projectInfo || !this.currentVideoFile) return;
    
    projectInfo.textContent = `${this.currentVideoFile.name} - ${this.formatFileSize(this.currentVideoFile.size)}`;
  },
  
  // Clean up resources
  cleanup: function() {
    // Clean up Video.js player if available
    if (this.vjsPlayer || window.vjsPlayer) {
      const player = this.vjsPlayer || window.vjsPlayer;
      try {
        player.dispose();
      } catch (e) {
        console.error("Error disposing Video.js player:", e);
      }
      this.vjsPlayer = null;
      window.vjsPlayer = null;
    }
    
    // Clean up standard video player
    if (this.videoPlayer && this.videoPlayer.src) {
      URL.revokeObjectURL(this.videoPlayer.src);
      this.videoPlayer.src = '';
    }
    
    this.currentVideoFile = null;
    window.currentVideoFile = null;
    window.videoDuration = 0;
  }
};

// Export the module
window.VideoModule = VideoModule;