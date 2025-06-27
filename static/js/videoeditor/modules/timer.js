/**
 * Timer Module - Handles time and timeline related functionality
 */

const TimerModule = {
  // Initialize the module
  init: function() {
    console.log("Timer Module initialized");
    this.initTimelineEvents();
    
    // Allow a moment for the DOM to be fully ready
    setTimeout(() => {
      this.initTrimHandles();
      this.updateTrimRegion(); // Make sure trim region is properly positioned initially
    }, 100);
  },
  
  // Initialize timeline related event handlers
  initTimelineEvents: function() {
    const videoTimeline = document.getElementById('videoTimeline');
    const timelineRuler = document.getElementById('timelineRuler');
    const zoomInBtn = document.getElementById('zoomInBtn');
    const zoomOutBtn = document.getElementById('zoomOutBtn');
    
    if (videoTimeline) {
      videoTimeline.addEventListener('click', (e) => {
        if (!window.videoDuration) return;
        
        const rect = videoTimeline.getBoundingClientRect();
        const clickPosition = e.clientX - rect.left;
        const percentage = clickPosition / rect.width;
        const time = percentage * window.videoDuration;
        
        VideoModule.seekTo(time);
      });
    }
    
    if (timelineRuler) {
      timelineRuler.addEventListener('click', (e) => {
        if (!window.videoDuration) return;
        
        const rect = timelineRuler.getBoundingClientRect();
        const clickPosition = e.clientX - rect.left;
        const percentage = clickPosition / rect.width;
        const time = percentage * window.videoDuration;
        
        VideoModule.seekTo(time);
      });
    }
    
    // Zoom controls
    if (zoomInBtn) {
      zoomInBtn.addEventListener('click', () => {
        window.zoomLevel = Math.min(5, (window.zoomLevel || 1) + 0.5);
        this.updateTimelineZoom();
      });
    }
    
    if (zoomOutBtn) {
      zoomOutBtn.addEventListener('click', () => {
        window.zoomLevel = Math.max(1, (window.zoomLevel || 1) - 0.5);
        this.updateTimelineZoom();
      });
    }
  },
  
  // Format time (seconds to HH:MM:SS)
  formatTime: function(seconds) {
    if (isNaN(seconds)) return "00:00:00";
    
    seconds = Math.max(0, seconds);
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  },
  
  // Parse time string (HH:MM:SS) to seconds
  parseTime: function(timeStr) {
    if (!timeStr) return 0;
    
    const parts = timeStr.split(':').map(part => parseInt(part, 10));
    if (parts.length === 3) {
      return parts[0] * 3600 + parts[1] * 60 + parts[2];
    } else if (parts.length === 2) {
      return parts[0] * 60 + parts[1];
    } else {
      return parts[0] || 0;
    }
  },
  
  // Set start time from current video position
  setStartTime: function() {
    const videoPlayer = document.getElementById('videoPlayer');
    const startTimeInput = document.getElementById('startTimeInput');
    
    if (!videoPlayer || !startTimeInput) return;
    
    window.startTime = videoPlayer.currentTime;
    startTimeInput.value = this.formatTime(window.startTime);
    this.updateTrimRegion();
  },
  
  // Set end time from current video position
  setEndTime: function() {
    const videoPlayer = document.getElementById('videoPlayer');
    const endTimeInput = document.getElementById('endTimeInput');
    
    if (!videoPlayer || !endTimeInput) return;
    
    window.endTime = videoPlayer.currentTime;
    endTimeInput.value = this.formatTime(window.endTime);
    this.updateTrimRegion();
  },
  
  // Update trim region indicator on timeline
  updateTrimRegion: function() {
    const trimRegion = document.getElementById('trimRegion');
    const videoTimeline = document.getElementById('videoTimeline');
    const leftHandle = document.getElementById('leftTrimHandle');
    const rightHandle = document.getElementById('rightTrimHandle');
    const leftHandleLabel = document.getElementById('leftHandleLabel');
    const rightHandleLabel = document.getElementById('rightHandleLabel');
    
    if (!trimRegion || !videoTimeline || !window.videoDuration) return;
    
    const timelineWidth = videoTimeline.clientWidth;
    const startPercent = (window.startTime / window.videoDuration) * 100;
    const endPercent = (window.endTime / window.videoDuration) * 100;
    
    // Update region position
    trimRegion.style.left = `${startPercent}%`;
    trimRegion.style.width = `${endPercent - startPercent}%`;
    
    // Make sure handles are visible and properly positioned
    if (leftHandle) {
      leftHandle.style.display = 'flex';
      leftHandle.style.left = `${startPercent}%`;
      leftHandle.style.zIndex = '20';
      leftHandle.style.marginLeft = '-10px'; // Adjust handle to center on position
    }
    
    if (rightHandle) {
      rightHandle.style.display = 'flex';
      rightHandle.style.left = `${endPercent}%`;
      rightHandle.style.right = 'auto'; // Override right positioning
      rightHandle.style.zIndex = '25';
      rightHandle.style.marginLeft = '-10px'; // Adjust handle to center on position
    }
    
    // Update time labels on handles
    if (leftHandleLabel) leftHandleLabel.textContent = this.formatTime(window.startTime);
    if (rightHandleLabel) rightHandleLabel.textContent = this.formatTime(window.endTime);
    
    console.log(`Updating trim region: ${startPercent}% to ${endPercent}%`);
  },
  
  // Initialize drag functionality for trim handles
  initTrimHandles: function() {
    console.log("Initializing trim handles");
    
    const trimRegion = document.getElementById('trimRegion');
    const leftHandle = document.getElementById('leftTrimHandle');
    const rightHandle = document.getElementById('rightTrimHandle');
    const videoTimeline = document.getElementById('videoTimeline');
    const startTimeInput = document.getElementById('startTimeInput');
    const endTimeInput = document.getElementById('endTimeInput');
    
    if (!trimRegion || !leftHandle || !rightHandle || !videoTimeline) {
      console.error("Missing required elements for trim handles", {
        trimRegion: !!trimRegion,
        leftHandle: !!leftHandle,
        rightHandle: !!rightHandle,
        videoTimeline: !!videoTimeline
      });
      return;
    }
    
    // Ensure handle elements have proper z-index and positioning
    leftHandle.style.zIndex = '20';
    rightHandle.style.zIndex = '25';
    leftHandle.style.cursor = 'ew-resize';
    rightHandle.style.cursor = 'ew-resize';
    leftHandle.style.pointerEvents = 'auto';
    rightHandle.style.pointerEvents = 'auto';
    
    let dragType = null; // 'left', 'right', or 'region'
    let startX, initialLeft, initialWidth, timelineWidth;
    
    // Left handle drag
    leftHandle.addEventListener('mousedown', (e) => {
      e.stopPropagation();
      startDrag(e, 'left');
    });
    
    // Right handle drag
    rightHandle.addEventListener('mousedown', (e) => {
      e.stopPropagation();
      startDrag(e, 'right');
    });
    
    // Region drag (moving both handles together)
    trimRegion.addEventListener('mousedown', (e) => {
      if (e.target === trimRegion) {
        startDrag(e, 'region');
      }
    });
    
    function startDrag(e, type) {
      e.preventDefault();
      
      dragType = type;
      startX = e.clientX;
      initialLeft = parseFloat(trimRegion.style.left) || 0;
      initialWidth = parseFloat(trimRegion.style.width) || 100;
      timelineWidth = videoTimeline.offsetWidth;
      
      document.addEventListener('mousemove', onDrag);
      document.addEventListener('mouseup', stopDrag);
      
      console.log(`Started dragging ${dragType}, initial left: ${initialLeft}, width: ${initialWidth}`);
    }
    
    const self = this; // Store reference to TimerModule
    
    function onDrag(e) {
      if (!dragType) return;
      
      const deltaX = e.clientX - startX;
      const deltaPercent = (deltaX / timelineWidth) * 100;
      
      let newLeft = initialLeft;
      let newWidth = initialWidth;
      
      switch (dragType) {
        case 'left':
          // Update left handle (start time)
          newLeft = Math.max(0, Math.min(initialLeft + deltaPercent, initialLeft + initialWidth - 1));
          newWidth = initialWidth - (newLeft - initialLeft);
          break;
          
        case 'right':
          // Update right handle (end time)
          newWidth = Math.max(1, Math.min(initialWidth + deltaPercent, 100 - initialLeft));
          break;
          
        case 'region':
          // Move entire region
          newLeft = Math.max(0, Math.min(initialLeft + deltaPercent, 100 - initialWidth));
          break;
      }
      
      // Update visuals
      trimRegion.style.left = `${newLeft}%`;
      trimRegion.style.width = `${newWidth}%`;
      
      // Update handle positions to match the region
      if (leftHandle) {
        leftHandle.style.left = `${newLeft}%`;
      }
      if (rightHandle) {
        rightHandle.style.left = `${newLeft + newWidth}%`;
        rightHandle.style.right = 'auto';
        rightHandle.style.marginLeft = '-10px';
      }
      
      // Update global state and inputs
      window.startTime = (newLeft / 100) * window.videoDuration;
      window.endTime = ((newLeft + newWidth) / 100) * window.videoDuration;
      
      // Update time inputs if they exist
      if (startTimeInput) startTimeInput.value = self.formatTime(window.startTime);
      if (endTimeInput) endTimeInput.value = self.formatTime(window.endTime);
      
      // Update time labels on handles
      const leftHandleLabel = document.getElementById('leftHandleLabel');
      const rightHandleLabel = document.getElementById('rightHandleLabel');
      
      if (leftHandleLabel) leftHandleLabel.textContent = self.formatTime(window.startTime);
      if (rightHandleLabel) rightHandleLabel.textContent = self.formatTime(window.endTime);
    }
    
    function stopDrag() {
      document.removeEventListener('mousemove', onDrag);
      document.removeEventListener('mouseup', stopDrag);
      dragType = null;
      
      // Final update to time values
      const currentLeft = parseFloat(trimRegion.style.left) || 0;
      const currentWidth = parseFloat(trimRegion.style.width) || 100;
      
      window.startTime = (currentLeft / 100) * window.videoDuration;
      window.endTime = ((currentLeft + currentWidth) / 100) * window.videoDuration;
      
      console.log(`Drag ended. New start time: ${window.startTime}, end time: ${window.endTime}`);
    }
  },
  
  // Update timeline marker position
  updateTimelineMarker: function() {
    const videoPlayer = document.getElementById('videoPlayer');
    const timelineMarker = document.getElementById('timelineMarker');
    const currentPositionIndicator = document.getElementById('currentPositionIndicator');
    
    if (!videoPlayer || !window.videoDuration) return;
    
    const currentTime = videoPlayer.currentTime;
    const percentage = (currentTime / window.videoDuration) * 100;
    
    if (timelineMarker) {
      timelineMarker.style.left = `${percentage}%`;
    }
    
    if (currentPositionIndicator) {
      currentPositionIndicator.style.left = `${percentage}%`;
      currentPositionIndicator.textContent = this.formatTime(currentTime);
    }
  },
  
  // Create time markings on timeline
  createTimeMarkings: function() {
    const timeMarkings = document.getElementById('timeMarkings');
    if (!timeMarkings || !window.videoDuration) return;
    
    // Clear existing markings
    timeMarkings.innerHTML = '';
    
    // Calculate intervals based on duration
    const duration = window.videoDuration;
    let interval = 1; // seconds
    let majorInterval = 5; // seconds
    
    if (duration > 60 && duration <= 300) { // 1-5 minutes
      interval = 5;
      majorInterval = 30;
    } else if (duration > 300 && duration <= 1800) { // 5-30 minutes
      interval = 30;
      majorInterval = 300;
    } else if (duration > 1800) { // >30 minutes
      interval = 60;
      majorInterval = 600;
    }
    
    // Create markings
    for (let time = 0; time <= duration; time += interval) {
      const isMajor = time % majorInterval === 0;
      const percentage = (time / duration) * 100;
      
      if (percentage > 100) continue;
      
      const marking = document.createElement('div');
      marking.className = isMajor ? 'time-marking major' : 'time-marking';
      marking.style.left = `${percentage}%`;
      timeMarkings.appendChild(marking);
      
      // Add label for major markings
      if (isMajor) {
        const label = document.createElement('div');
        label.className = 'time-label';
        label.style.left = `${percentage}%`;
        label.textContent = this.formatTime(time);
        timeMarkings.appendChild(label);
      }
    }
  },
  
  // Update timeline zoom level
  updateTimelineZoom: function() {
    this.createTimeMarkings();
    this.updateTrimRegion();
    
    // Update video clips if needed
    const videoTrack = document.getElementById('videoTrack');
    const audioTrack = document.getElementById('audioTrack');
    
    if (videoTrack || audioTrack) {
      // Update track content widths based on zoom
      const tracks = document.querySelectorAll('.track-content');
      const zoomLevel = window.zoomLevel || 1;
      
      tracks.forEach(track => {
        track.style.width = `${100 * zoomLevel}%`;
      });
    }
  }
};

// Export the module
window.TimerModule = TimerModule;