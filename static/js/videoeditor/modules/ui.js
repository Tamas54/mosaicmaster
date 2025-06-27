/**
 * UI Module - Handles UI initialization and interactions
 */

// UI Module namespace
const UIModule = {
  // Initialize UI elements and attach event listeners
  init: function() {
    console.log("UI Module initialized");
    this.setupDropZone();
    this.setupButtons();
    this.setupSliders();
    this.setupTimeInputs();
    
    // Initialize Lucide icons if available
    if (typeof lucide !== 'undefined' && typeof lucide.createIcons === 'function') {
      lucide.createIcons();
      console.log("Lucide icons initialized");
    } else {
      console.warn("Lucide library not found");
    }
    
    // Initialize collapse buttons
    this.initCollapsePanels();
  },
  
  // Setup file drop zone
  setupDropZone: function() {
    const videoDropZone = document.getElementById('videoDropZone');
    const videoFileInput = document.getElementById('videoFileInput');
    
    if (!videoDropZone || !videoFileInput) return;
    
    videoDropZone.addEventListener('click', () => {
      videoFileInput.click();
    });
    
    videoDropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      videoDropZone.classList.add('dragover');
    });
    
    videoDropZone.addEventListener('dragleave', () => {
      videoDropZone.classList.remove('dragover');
    });
    
    videoDropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      videoDropZone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        // Let the VideoModule determine if it's a valid video file
        if (window.VideoModule && typeof window.VideoModule.handleVideoFile === 'function') {
          window.VideoModule.handleVideoFile(e.dataTransfer.files[0]);
        } else {
          console.warn("VideoModule not available - falling back to default handler");
          // Fallback to simple file handler
          const file = e.dataTransfer.files[0];
          if (file.type.startsWith('video/')) {
            const videoPlayer = document.getElementById('videoPlayer');
            if (videoPlayer) {
              videoPlayer.src = URL.createObjectURL(file);
              videoPlayer.load();
            }
          }
        }
      }
    });
    
    videoFileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        if (window.VideoModule && typeof window.VideoModule.handleVideoFile === 'function') {
          window.VideoModule.handleVideoFile(e.target.files[0]);
        } else {
          console.warn("VideoModule not available - falling back to default handler");
          // Fallback to simple file handler
          const file = e.target.files[0];
          if (file.type.startsWith('video/')) {
            const videoPlayer = document.getElementById('videoPlayer');
            if (videoPlayer) {
              videoPlayer.src = URL.createObjectURL(file);
              videoPlayer.load();
            }
          }
        }
      }
    });
  },
  
  // Setup button event listeners
  setupButtons: function() {
    const buttonMap = {
      'playPauseBtn': () => {
        if (window.VideoModule && typeof window.VideoModule.togglePlayPause === 'function') {
          window.VideoModule.togglePlayPause();
        } else {
          // Fallback to basic video control
          const videoPlayer = document.getElementById('videoPlayer');
          if (videoPlayer) {
            if (videoPlayer.paused) {
              videoPlayer.play();
            } else {
              videoPlayer.pause();
            }
          }
        }
      },
      'firstFrameBtn': () => {
        if (window.VideoModule && typeof window.VideoModule.seekTo === 'function') {
          window.VideoModule.seekTo(0);
        } else {
          const videoPlayer = document.getElementById('videoPlayer');
          if (videoPlayer) videoPlayer.currentTime = 0;
        }
      },
      'lastFrameBtn': () => {
        if (window.VideoModule && typeof window.VideoModule.seekTo === 'function') {
          window.VideoModule.seekTo(window.videoDuration || 0);
        } else {
          const videoPlayer = document.getElementById('videoPlayer');
          if (videoPlayer) videoPlayer.currentTime = videoPlayer.duration || 0;
        }
      },
      'prevFrameBtn': () => {
        if (window.VideoModule && typeof window.VideoModule.seekRelative === 'function') {
          window.VideoModule.seekRelative(-0.033);
        } else {
          const videoPlayer = document.getElementById('videoPlayer');
          if (videoPlayer) videoPlayer.currentTime = Math.max(0, videoPlayer.currentTime - 0.033);
        }
      },
      'nextFrameBtn': () => {
        if (window.VideoModule && typeof window.VideoModule.seekRelative === 'function') {
          window.VideoModule.seekRelative(0.033);
        } else {
          const videoPlayer = document.getElementById('videoPlayer');
          if (videoPlayer) videoPlayer.currentTime = videoPlayer.currentTime + 0.033;
        }
      },
      'setStartBtn': () => {
        if (window.TimerModule && typeof window.TimerModule.setStartTime === 'function') {
          window.TimerModule.setStartTime();
        }
      },
      'setEndBtn': () => {
        if (window.TimerModule && typeof window.TimerModule.setEndTime === 'function') {
          window.TimerModule.setEndTime();
        }
      },
      'executeVideoBtn': () => {
        if (window.ProcessingModule && typeof window.ProcessingModule.startVideoProcessing === 'function') {
          window.ProcessingModule.startVideoProcessing();
        }
      },
      'trimVideoBtn': () => {
        if (window.ProcessingModule && typeof window.ProcessingModule.startVideoProcessing === 'function') {
          window.ProcessingModule.startVideoProcessing();
        }
      },
      'downloadBtn': () => {
        if (window.UIModule && typeof window.UIModule.handleDownload === 'function') {
          window.UIModule.handleDownload();
        }
      },
      'closeSuccessDialog': () => {
        if (window.UIModule && typeof window.UIModule.hideDialog === 'function') {
          window.UIModule.hideDialog('successDialog');
        }
      },
      'continueEditingBtn': () => {
        if (window.UIModule && typeof window.UIModule.hideDialog === 'function') {
          window.UIModule.hideDialog('successDialog');
        }
      }
    };
    
    // Attach event listeners for each button
    Object.entries(buttonMap).forEach(([id, callback]) => {
      const button = document.getElementById(id);
      if (button) {
        button.addEventListener('click', callback);
        console.log(`Button handler attached: ${id}`);
      }
    });
  },
  
  // Setup sliders and their value displays
  setupSliders: function() {
    const sliderMap = {
      'qualitySlider': 'qualityValue',
      'fontSizeSlider': 'fontSizeValue'
    };
    
    Object.entries(sliderMap).forEach(([sliderId, valueId]) => {
      const slider = document.getElementById(sliderId);
      const value = document.getElementById(valueId);
      
      if (slider && value) {
        slider.addEventListener('input', () => {
          if (sliderId === 'qualitySlider') {
            value.textContent = `${slider.value}%`;
          } else if (sliderId === 'fontSizeSlider') {
            value.textContent = `${slider.value}px`;
          }
        });
      }
    });
  },
  
  // Setup time input fields
  setupTimeInputs: function() {
    const startTimeInput = document.getElementById('startTimeInput');
    const endTimeInput = document.getElementById('endTimeInput');
    
    if (startTimeInput) {
      startTimeInput.addEventListener('change', function() {
        window.startTime = TimerModule.parseTime(this.value);
        TimerModule.updateTrimRegion();
      });
    }
    
    if (endTimeInput) {
      endTimeInput.addEventListener('change', function() {
        window.endTime = TimerModule.parseTime(this.value);
        TimerModule.updateTrimRegion();
      });
    }
  },
  
  // Initialize collapsible panels
  initCollapsePanels: function() {
    const collapseBtns = document.querySelectorAll('.collapse-btn');
    collapseBtns.forEach(btn => {
      btn.addEventListener('click', function() {
        const panel = this.closest('.panel, .timeline');
        const contents = panel.querySelectorAll('.property-row, .thumbnail-grid, .filter-tabs, .video-preview, .controls, .timeline-content, .tabs, .timeline-toolbar, .property-table');
        
        if (this.textContent === '-') {
          contents.forEach(content => {
            if (content) content.style.display = 'none';
          });
          this.textContent = '+';
        } else {
          contents.forEach(content => {
            if (content) content.style.display = '';
          });
          this.textContent = '-';
        }
      });
    });
  },
  
  // Show a dialog by ID
  showDialog: function(dialogId) {
    const dialog = document.getElementById(dialogId);
    if (dialog) dialog.style.display = 'flex';
  },
  
  // Hide a dialog by ID
  hideDialog: function(dialogId) {
    const dialog = document.getElementById(dialogId);
    if (dialog) dialog.style.display = 'none';
  },
  
  // Handle download button click
  handleDownload: function() {
    this.hideDialog('successDialog');
    // The actual download URL should be set by the processing module
  },
  
  // Update progress bar
  updateProgress: function(percent, message) {
    const progressBar = document.getElementById('progressBar');
    const statusText = document.getElementById('processingStatus');
    
    if (progressBar) progressBar.style.width = `${percent}%`;
    if (statusText && message) statusText.textContent = message;
  },
  
  // Show error message
  showError: function(message) {
    const statusText = document.getElementById('processingStatus');
    const progressBar = document.getElementById('progressBar');
    
    if (statusText) statusText.textContent = `Error: ${message}`;
    if (progressBar) progressBar.classList.add('bg-red-500');
  }
};

// Export the module
window.UIModule = UIModule;