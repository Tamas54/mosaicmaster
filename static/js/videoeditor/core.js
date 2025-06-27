// Core functionality for Video Editor
// This module handles initialization, video file handling, and timeline

// Global variables
let currentVideoFile = null;
let videoDuration = 0;
let startTime = 0;
let endTime = 0;
let connectionId = crypto.randomUUID();
let currentActiveTab = 'trim';
let zoomLevel = 1;
let scrollOffset = 0;

// Make videoFile available to other modules
window.getVideoFile = function() {
  return currentVideoFile;
};

// Platform presets for different social media
const platformPresets = {
  youtube: {
    aspectRatio: '16:9',
    maxDuration: 720, // 12 hours
    class: 'platform-youtube'
  },
  youtube_shorts: {
    aspectRatio: '9:16',
    maxDuration: 60, // 60 seconds
    class: 'platform-youtube_shorts'
  },
  tiktok: {
    aspectRatio: '9:16',
    maxDuration: 180, // 3 minutes
    class: 'platform-tiktok'
  },
  instagram: {
    aspectRatio: '1:1',
    maxDuration: 60, // 60 seconds for feed
    class: 'platform-instagram'
  },
  instagram_reels: {
    aspectRatio: '9:16',
    maxDuration: 90, // 90 seconds
    class: 'platform-instagram_reels'
  }
};

// Format time (seconds to HH:MM:SS)
function formatTime(seconds) {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Parse time (HH:MM:SS to seconds)
function parseTime(timeStr) {
  const parts = timeStr.split(':').map(part => parseInt(part, 10));
  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  } else if (parts.length === 2) {
    return parts[0] * 60 + parts[1];
  } else {
    return parts[0] || 0;
  }
}

// Format file size
function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Initialize the application when DOM is loaded
document.addEventListener("DOMContentLoaded", function() {
  console.log("Video Editor Core Module Loaded");
  initializeUI();
  initializeEventListeners();
  switchTab('trim'); // Default to trim tab
});

// Initialize UI elements
function initializeUI() {
  // Create Lucide icons
  if (typeof lucide !== 'undefined' && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  } else {
    console.error("Lucide library not available");
  }
}

// Main initializer for event listeners
function initializeEventListeners() {
  // Video drop zone events
  const videoDropZone = document.getElementById('videoDropZone');
  if (videoDropZone) {
    videoDropZone.addEventListener('click', () => {
      const videoFileInput = document.getElementById('videoFileInput');
      if (videoFileInput) videoFileInput.click();
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
      if (e.dataTransfer.files.length > 0 && e.dataTransfer.files[0].type.startsWith('video/')) {
        handleVideoFile(e.dataTransfer.files[0]);
      }
    });
  }
  
  // File input change event
  const videoFileInput = document.getElementById('videoFileInput');
  if (videoFileInput) {
    videoFileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        handleVideoFile(e.target.files[0]);
      }
    });
  }
  
  // Remove file button
  const removeVideoFile = document.getElementById('removeVideoFile');
  if (removeVideoFile) {
    removeVideoFile.addEventListener('click', () => {
      currentVideoFile = null;
      const videoFileInfo = document.getElementById('videoFileInfo');
      const videoPreviewSection = document.getElementById('videoPreviewSection');
      const editingOptions = document.getElementById('editingOptions');
      const trimVideoBtn = document.getElementById('trimVideoBtn');
      const downloadBtn = document.getElementById('downloadBtn');
      
      if (videoFileInfo) videoFileInfo.classList.add('hidden');
      if (videoPreviewSection) videoPreviewSection.classList.add('hidden');
      if (editingOptions) editingOptions.classList.add('hidden');
      if (trimVideoBtn) trimVideoBtn.classList.add('hidden');
      if (downloadBtn) downloadBtn.classList.add('hidden');
      
      if (videoFileInput) videoFileInput.value = '';
      
      // Reset video player
      const videoPlayer = document.getElementById('videoPlayer');
      if (videoPlayer) {
        videoPlayer.src = '';
        if (videoPlayer.src && typeof URL.revokeObjectURL === 'function') {
          URL.revokeObjectURL(videoPlayer.src);
        }
      }
    });
  }
  
  // Tab switching
  const tabs = ['trimTab', 'subtitleTab', 'mergeTab', 'extractTab', 'effectsTab'];
  tabs.forEach(tabId => {
    const tab = document.getElementById(tabId);
    if (tab) {
      tab.addEventListener('click', () => switchTab(tabId.replace('Tab', '')));
    }
  });
  
  // Time input fields
  const startTimeInput = document.getElementById('startTimeInput');
  const endTimeInput = document.getElementById('endTimeInput');
  
  if (startTimeInput) {
    startTimeInput.addEventListener('change', function() {
      startTime = parseTime(this.value);
      updateTrimRegion();
    });
  }
  
  if (endTimeInput) {
    endTimeInput.addEventListener('change', function() {
      endTime = parseTime(this.value);
      updateTrimRegion();
    });
  }
  
  // Set current time as start/end time
  const setStartTimeBtn = document.getElementById('setStartTimeBtn');
  const setEndTimeBtn = document.getElementById('setEndTimeBtn');
  const videoPlayer = document.getElementById('videoPlayer');
  
  if (setStartTimeBtn && videoPlayer) {
    setStartTimeBtn.addEventListener('click', function() {
      startTime = videoPlayer.currentTime;
      if (startTimeInput) startTimeInput.value = formatTime(startTime);
      updateTrimRegion();
    });
  }
  
  if (setEndTimeBtn && videoPlayer) {
    setEndTimeBtn.addEventListener('click', function() {
      endTime = videoPlayer.currentTime;
      if (endTimeInput) endTimeInput.value = formatTime(endTime);
      updateTrimRegion();
    });
  }
  
  // Handling timeline clicks
  const videoTimeline = document.getElementById('videoTimeline');
  if (videoTimeline && videoPlayer) {
    videoTimeline.addEventListener('click', function(e) {
      if (videoDuration <= 0) return;
      
      const rect = videoTimeline.getBoundingClientRect();
      const pos = (e.clientX - rect.left) / rect.width;
      const newTime = pos * videoDuration;
      videoPlayer.currentTime = newTime;
    });
  }
  
  // Video player event listeners
  if (videoPlayer) {
    videoPlayer.addEventListener('timeupdate', updateTimelineMarker);
    videoPlayer.addEventListener('play', updatePlayPauseButton);
    videoPlayer.addEventListener('pause', updatePlayPauseButton);
  }
  
  // Play/Pause button functions
  const playPauseBtn = document.getElementById('playPauseBtn');
  if (playPauseBtn && videoPlayer) {
    playPauseBtn.addEventListener('click', function() {
      if (videoPlayer.paused) {
        videoPlayer.play();
      } else {
        videoPlayer.pause();
      }
      updatePlayPauseButton();
    });
  }
  
  // Aspect ratio selector
  const aspectRatioSelector = document.getElementById('aspectRatioSelector');
  if (aspectRatioSelector) {
    aspectRatioSelector.addEventListener('change', function() {
      applyAspectRatio(this.value);
    });
  }
  
  // Apply platform preset
  const applyPresetBtn = document.getElementById('applyPresetBtn');
  if (applyPresetBtn) {
    applyPresetBtn.addEventListener('click', function() {
      const platform = document.getElementById('platformPreset').value;
      const preset = platformPresets[platform];
      
      if (!preset) return;
      
      // Apply aspect ratio
      if (aspectRatioSelector) {
        aspectRatioSelector.value = platform;
        applyAspectRatio(platform);
      }
      
      // Apply duration limit
      if (preset.maxDuration && videoDuration > preset.maxDuration) {
        endTime = Math.min(preset.maxDuration, videoDuration);
        if (endTimeInput) endTimeInput.value = formatTime(endTime);
        alert(`${platform} has a maximum duration of ${formatTime(preset.maxDuration)}. End time adjusted.`);
        updateTrimRegion();
      }
    });
  }
  
  // Zoom controls
  const zoomInBtn = document.getElementById('zoomInBtn');
  const zoomOutBtn = document.getElementById('zoomOutBtn');
  const resetZoomBtn = document.getElementById('resetZoomBtn');
  
  if (zoomInBtn) {
    zoomInBtn.addEventListener('click', function() {
      zoomLevel = Math.min(5, zoomLevel + 0.5);
      updateTimelineZoom();
    });
  }
  
  if (zoomOutBtn) {
    zoomOutBtn.addEventListener('click', function() {
      zoomLevel = Math.max(1, zoomLevel - 0.5);
      updateTimelineZoom();
    });
  }
  
  if (resetZoomBtn) {
    resetZoomBtn.addEventListener('click', function() {
      zoomLevel = 1;
      scrollOffset = 0;
      updateTimelineZoom();
    });
  }
  
  // Timeline scrolling for zoomed view
  if (videoTimeline) {
    videoTimeline.addEventListener('wheel', function(e) {
      if (zoomLevel <= 1) return;
      
      e.preventDefault();
      const timelineWidth = videoTimeline.clientWidth;
      const maxScroll = timelineWidth * (zoomLevel - 1);
      
      // Update scroll offset
      scrollOffset = Math.max(0, Math.min(maxScroll, scrollOffset + e.deltaX));
      
      // Update view
      createTimeMarkings();
      updateTrimRegion();
    });
  }
  
  // Window resize event to update trim region
  window.addEventListener('resize', () => {
    updateTrimRegion();
    createTimeMarkings();
    setTimeout(createFrameThumbnails, 200);
  });
}

// Handle file selection
function handleVideoFile(file) {
  currentVideoFile = file;
  const videoFileName = document.getElementById('videoFileName');
  const videoFileSize = document.getElementById('videoFileSize');
  const videoFileInfo = document.getElementById('videoFileInfo');
  const videoPreviewSection = document.getElementById('videoPreviewSection');
  const editingOptions = document.getElementById('editingOptions');
  const trimVideoBtn = document.getElementById('trimVideoBtn');
  const videoPlayer = document.getElementById('videoPlayer');
  
  if (videoFileName) videoFileName.textContent = file.name;
  if (videoFileSize) videoFileSize.textContent = formatFileSize(file.size);
  if (videoFileInfo) videoFileInfo.classList.remove('hidden');
  
  // Create object URL for video preview
  if (videoPlayer) {
    const videoURL = URL.createObjectURL(file);
    videoPlayer.src = videoURL;
    
    // Show preview section and options
    if (videoPreviewSection) videoPreviewSection.classList.remove('hidden');
    if (editingOptions) editingOptions.classList.remove('hidden');
    if (trimVideoBtn) trimVideoBtn.classList.remove('hidden');
    
    // Reset timeline when a new video is loaded
    videoPlayer.onloadedmetadata = function() {
      videoDuration = videoPlayer.duration;
      startTime = 0;
      endTime = videoDuration;
      
      const startTimeInput = document.getElementById('startTimeInput');
      const endTimeInput = document.getElementById('endTimeInput');
      const currentTimeDisplay = document.getElementById('currentTimeDisplay');
      
      if (startTimeInput) startTimeInput.value = formatTime(startTime);
      if (endTimeInput) endTimeInput.value = formatTime(endTime);
      
      updateTrimRegion();
      createTimeMarkings();
      setTimeout(createFrameThumbnails, 500); // Delay to ensure video is ready
      
      // Display initial time
      if (currentTimeDisplay) {
        currentTimeDisplay.textContent = `${formatTime(0)} / ${formatTime(videoDuration)}`;
      }
    };
  }
}

// Tab switching logic
function switchTab(tabName) {
  // Get panel elements
  const trimOptionsPanel = document.getElementById('trimOptionsPanel');
  const subtitleOptionsPanel = document.getElementById('subtitleOptionsPanel');
  const mergeOptionsPanel = document.getElementById('mergeOptionsPanel');
  const extractOptionsPanel = document.getElementById('extractOptionsPanel');
  const effectsOptionsPanel = document.getElementById('effectsOptionsPanel');
  
  // Get tab elements
  const trimTab = document.getElementById('trimTab');
  const subtitleTab = document.getElementById('subtitleTab');
  const mergeTab = document.getElementById('mergeTab');
  const extractTab = document.getElementById('extractTab');
  const effectsTab = document.getElementById('effectsTab');
  
  // Get trim button
  const trimVideoBtn = document.getElementById('trimVideoBtn');
  
  // Hide all panels
  if (trimOptionsPanel) trimOptionsPanel.classList.add('hidden');
  if (subtitleOptionsPanel) subtitleOptionsPanel.classList.add('hidden');
  if (mergeOptionsPanel) mergeOptionsPanel.classList.add('hidden');
  if (extractOptionsPanel) extractOptionsPanel.classList.add('hidden');
  if (effectsOptionsPanel) effectsOptionsPanel.classList.add('hidden');
  
  // Reset all tabs
  const tabClass = 'inactive-tab border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 whitespace-nowrap py-2 px-4 border-b-2 font-medium text-sm';
  const activeTabClass = 'active-tab border-[var(--editor-accent)] text-[var(--editor-accent)] whitespace-nowrap py-2 px-4 border-b-2 font-medium text-sm';
  
  if (trimTab) trimTab.className = tabClass;
  if (subtitleTab) subtitleTab.className = tabClass;
  if (mergeTab) mergeTab.className = tabClass;
  if (extractTab) extractTab.className = tabClass;
  if (effectsTab) effectsTab.className = tabClass;
  
  // Show selected panel and activate tab
  if (tabName === 'trim') {
    if (trimOptionsPanel) trimOptionsPanel.classList.remove('hidden');
    if (trimTab) trimTab.className = activeTabClass;
    if (trimVideoBtn) trimVideoBtn.classList.remove('hidden');
  } else if (tabName === 'subtitle') {
    if (subtitleOptionsPanel) subtitleOptionsPanel.classList.remove('hidden');
    if (subtitleTab) subtitleTab.className = activeTabClass;
    if (trimVideoBtn) trimVideoBtn.classList.add('hidden');
  } else if (tabName === 'merge') {
    if (mergeOptionsPanel) mergeOptionsPanel.classList.remove('hidden');
    if (mergeTab) mergeTab.className = activeTabClass;
    if (trimVideoBtn) trimVideoBtn.classList.add('hidden');
  } else if (tabName === 'extract') {
    if (extractOptionsPanel) extractOptionsPanel.classList.remove('hidden');
    if (extractTab) extractTab.className = activeTabClass;
    if (trimVideoBtn) trimVideoBtn.classList.add('hidden');
  } else if (tabName === 'effects') {
    if (effectsOptionsPanel) effectsOptionsPanel.classList.remove('hidden');
    if (effectsTab) effectsTab.className = activeTabClass;
    if (trimVideoBtn) trimVideoBtn.classList.add('hidden');
  }
  
  currentActiveTab = tabName;
}

// Timeline functions
function createTimeMarkings() {
  const videoTimeline = document.getElementById('videoTimeline');
  const timeMarkings = document.getElementById('timeMarkings');
  
  if (!videoTimeline || !timeMarkings || videoDuration <= 0) return;
  
  // Clear existing markings
  timeMarkings.innerHTML = '';
  
  // Calculate interval based on duration
  let interval = 1; // 1 second default
  let majorInterval = 5; // 5 seconds default
  
  if (videoDuration > 60 && videoDuration <= 300) {
    interval = 5;
    majorInterval = 30;
  } else if (videoDuration > 300 && videoDuration <= 900) {
    interval = 15;
    majorInterval = 60;
  } else if (videoDuration > 900 && videoDuration <= 3600) {
    interval = 30;
    majorInterval = 300;
  } else if (videoDuration > 3600) {
    interval = 60;
    majorInterval = 600;
  }
  
  const timelineWidth = videoTimeline.clientWidth;
  const visibleStart = scrollOffset / timelineWidth * videoDuration;
  
  // Create markings for the visible portion
  for (let time = 0; time <= videoDuration; time += interval) {
    const isMajor = time % majorInterval === 0;
    const pos = ((time - visibleStart) * zoomLevel);
    
    // Skip if outside visible range
    if (pos < -interval*zoomLevel || pos > timelineWidth + interval*zoomLevel) continue;
    
    const marking = document.createElement('div');
    marking.className = isMajor ? 'time-marking major' : 'time-marking';
    marking.style.left = `${pos}px`;
    timeMarkings.appendChild(marking);
    
    if (isMajor) {
      const label = document.createElement('div');
      label.className = 'time-label';
      label.style.left = `${pos}px`;
      label.textContent = formatTime(time);
      timeMarkings.appendChild(label);
    }
  }
}

// Create video thumbnails for timeline
function createFrameThumbnails() {
  const videoPlayer = document.getElementById('videoPlayer');
  const frameContainer = document.getElementById('frameContainer');
  
  if (!videoPlayer || !frameContainer || !videoPlayer.videoWidth) return;
  
  frameContainer.innerHTML = '';
  
  // Only generate if video duration is valid
  if (videoDuration <= 0) return;
  
  // Calculate how many thumbnails to show
  const thumbnailCount = Math.min(20, Math.ceil(videoDuration / 2));
  const interval = videoDuration / thumbnailCount;
  
  // Get video dimensions
  const videoRatio = videoPlayer.videoWidth / videoPlayer.videoHeight;
  
  // Create a canvas to capture frames
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = 160;
  canvas.height = 160 / videoRatio;
  
  // Generate thumbnails at regular intervals
  for (let i = 0; i < thumbnailCount; i++) {
    const time = i * interval;
    const thumbnail = document.createElement('div');
    thumbnail.className = 'frame-thumbnail';
    thumbnail.dataset.time = time;
    thumbnail.style.width = `${100 / thumbnailCount * zoomLevel}%`;
    
    // Add click event to seek to this position
    thumbnail.addEventListener('click', () => {
      videoPlayer.currentTime = time;
    });
    
    frameContainer.appendChild(thumbnail);
    
    // Use setTimeout to stagger the frame capture, avoiding UI freeze
    setTimeout(() => {
      try {
        videoPlayer.currentTime = time;
        // Wait a bit for the frame to be ready
        setTimeout(() => {
          try {
            ctx.drawImage(videoPlayer, 0, 0, canvas.width, canvas.height);
            const dataUrl = canvas.toDataURL('image/jpeg', 0.5);
            thumbnail.style.backgroundImage = `url(${dataUrl})`;
          } catch (e) {
            console.error('Error capturing frame:', e);
          }
        }, 100);
      } catch(e) {
        console.error('Error seeking to time:', e);
      }
    }, i * 200);
  }
}

// Update trim region on the timeline
function updateTrimRegion() {
  const trimRegion = document.getElementById('trimRegion');
  const videoTimeline = document.getElementById('videoTimeline');
  
  if (!trimRegion || !videoTimeline || videoDuration <= 0) return;
  
  const timelineWidth = videoTimeline.clientWidth;
  const startPos = (startTime / videoDuration) * timelineWidth;
  const endPos = (endTime / videoDuration) * timelineWidth;
  
  trimRegion.style.left = startPos + 'px';
  trimRegion.style.width = (endPos - startPos) + 'px';
}

// Update timeline marker position based on video playback
function updateTimelineMarker() {
  const timelineMarker = document.getElementById('timelineMarker');
  const videoTimeline = document.getElementById('videoTimeline');
  const currentTimeDisplay = document.getElementById('currentTimeDisplay');
  const videoPlayer = document.getElementById('videoPlayer');
  
  if (!timelineMarker || !videoTimeline || !currentTimeDisplay || !videoPlayer || videoDuration <= 0) return;
  
  const pos = (videoPlayer.currentTime / videoDuration) * videoTimeline.clientWidth;
  timelineMarker.style.left = pos + 'px';
  currentTimeDisplay.textContent = `${formatTime(videoPlayer.currentTime)} / ${formatTime(videoDuration)}`;
}

// Update play/pause button icon
function updatePlayPauseButton() {
  const playPauseBtn = document.getElementById('playPauseBtn');
  const videoPlayer = document.getElementById('videoPlayer');
  
  if (!playPauseBtn || !videoPlayer) return;
  
  // Clear existing icon
  playPauseBtn.innerHTML = '';
  
  // Create new icon
  const icon = document.createElement('i');
  icon.setAttribute('data-lucide', videoPlayer.paused ? 'play' : 'pause');
  icon.className = 'w-4 h-4';
  
  playPauseBtn.appendChild(icon);
  if (typeof lucide !== 'undefined' && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
}

// Aspect ratio functions
function applyAspectRatio(platform) {
  const videoContainer = document.getElementById('videoContainer');
  if (!videoContainer) return;
  
  // Remove all platform classes
  videoContainer.className = 'video-preview';
  
  // Apply new platform class
  if (platform === 'original') {
    // For original, just keep the base class
  } else if (platformPresets[platform]) {
    videoContainer.classList.add(platformPresets[platform].class);
    
    // Apply max duration if needed
    if (videoDuration > 0 && platformPresets[platform].maxDuration) {
      // If current end time exceeds the max duration, update it
      if (endTime > platformPresets[platform].maxDuration) {
        endTime = Math.min(platformPresets[platform].maxDuration, videoDuration);
        const endTimeInput = document.getElementById('endTimeInput');
        if (endTimeInput) endTimeInput.value = formatTime(endTime);
        updateTrimRegion();
      }
    }
  } else {
    // Default to YouTube
    videoContainer.classList.add('platform-youtube');
  }
}

// WebSocket for progress updates
function initWebSocket(connectionId) {
  if (!connectionId) connectionId = crypto.randomUUID();
  
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

// Export functions and variables for other modules
window.VideoEditorCore = {
  formatTime,
  parseTime,
  formatFileSize,
  handleVideoFile,
  switchTab,
  updateTrimRegion,
  updateTimelineMarker,
  createTimeMarkings,
  createFrameThumbnails,
  initWebSocket
};