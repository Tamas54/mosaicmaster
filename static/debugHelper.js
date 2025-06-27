// Debug helper for videocutter.html and other pages
document.addEventListener("DOMContentLoaded", function() {
  console.log("DebugHelper: DOM fully loaded");
  
  // Check if we're on the video cutter page
  if (window.location.pathname.includes('videocutter.html')) {
    console.log("DebugHelper: Video cutter page detected");
    
    // Initialize UI elements with try-catch to identify any broken elements
    try {
      // Try to find the main drop zone
      const videoDropZone = document.getElementById('videoDropZone');
      if (!videoDropZone) {
        console.error("DebugHelper: videoDropZone element not found");
      } else {
        console.log("DebugHelper: videoDropZone element found");
        
        // Try to attach click event
        try {
          videoDropZone.addEventListener('click', function() {
            console.log("DebugHelper: videoDropZone clicked");
            const videoFileInput = document.getElementById('videoFileInput');
            if (videoFileInput) {
              videoFileInput.click();
            } else {
              console.error("DebugHelper: videoFileInput element not found");
            }
          });
        } catch (e) {
          console.error("DebugHelper: Error attaching click event to videoDropZone:", e);
        }
      }
      
      // Check for critical tab buttons
      const tabs = ['trimTab', 'subtitleTab', 'mergeTab', 'extractTab', 'effectsTab'];
      tabs.forEach(tabId => {
        const tab = document.getElementById(tabId);
        if (!tab) {
          console.error(`DebugHelper: ${tabId} element not found`);
        } else {
          console.log(`DebugHelper: ${tabId} element found`);
          // Attach click handler for diagnostic purposes
          tab.addEventListener('click', function() {
            console.log(`DebugHelper: ${tabId} clicked`);
          });
        }
      });
      
      // Check for video player
      const videoPlayer = document.getElementById('videoPlayer');
      if (!videoPlayer) {
        console.error("DebugHelper: videoPlayer element not found");
      } else {
        console.log("DebugHelper: videoPlayer element found");
      }
      
      // Initialize Lucide icons
      if (typeof lucide !== 'undefined' && typeof lucide.createIcons === 'function') {
        lucide.createIcons();
        console.log("DebugHelper: Lucide icons initialized");
      } else {
        console.error("DebugHelper: Lucide library not available");
      }
      
    } catch (e) {
      console.error("DebugHelper: Critical error during initialization:", e);
    }
  }
  
  // Fix any common UI issues
  try {
    // Ensure all drop zones have proper event handlers
    document.querySelectorAll('.drop-zone').forEach(zone => {
      zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
      });
      
      zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
      });
      
      zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        console.log("DebugHelper: File dropped on drop zone");
      });
    });
    
    // Ensure all inactive tabs are clickable
    document.querySelectorAll('.inactive-tab').forEach(tab => {
      tab.style.cursor = 'pointer';
    });
  } catch (e) {
    console.error("DebugHelper: Error fixing UI issues:", e);
  }
});