/**
 * Main Module - Entry point for the modular video editor
 */

// Initialize global state
window.zoomLevel = 1;
window.scrollOffset = 0;
window.videoDuration = 0;
window.startTime = 0;
window.endTime = 0;

// Main initialization function
function initVideoEditor() {
  console.log("Initializing MosaicMaster Video Editor");
  
  // Initialize all modules
  if (window.UIModule) {
    window.UIModule.init();
    console.log("UI Module initialized");
  } else {
    console.error("UI Module not found");
  }
  
  if (window.TimerModule) {
    window.TimerModule.init();
    console.log("Timer Module initialized");
  } else {
    console.error("Timer Module not found");
  }
  
  if (window.VideoModule) {
    window.VideoModule.init();
    console.log("Video Module initialized");
  } else {
    console.error("Video Module not found");
  }
  
  if (window.ProcessingModule) {
    window.ProcessingModule.init();
    console.log("Processing Module initialized");
  } else {
    console.error("Processing Module not found");
  }
  
  console.log("MosaicMaster Video Editor initialization complete");
}

// Run initialization when DOM is loaded
document.addEventListener('DOMContentLoaded', initVideoEditor);

// Log any errors during initialization
window.addEventListener('error', function(e) {
  console.error('Video Editor Error:', e.message, 'at', e.filename, ':', e.lineno);
});