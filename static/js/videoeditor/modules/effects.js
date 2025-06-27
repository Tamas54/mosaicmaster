/**
 * Effects Module - Handles video effects processing
 */

const EffectsModule = {
  // Initialize the module
  init: function() {
    console.log("Effects Module initialized");
    this.setupEventListeners();
  },
  
  // Setup event listeners for effects controls
  setupEventListeners: function() {
    const applyEffectsBtn = document.getElementById('applyEffectsBtn');
    
    if (applyEffectsBtn) {
      applyEffectsBtn.addEventListener('click', this.applyVideoEffects.bind(this));
    }
  },
  
  // Apply video effects
  applyVideoEffects: function() {
    console.log("Applying video effects");
    
    // Get video file
    const videoFile = typeof window.getVideoFile === 'function' ? 
      window.getVideoFile() : window.currentVideoFile;
    
    if (!videoFile) {
      alert("Please upload a video file first!");
      return;
    }
    
    // Show processing dialog
    const processingSection = document.getElementById('processingSection');
    if (processingSection) processingSection.classList.remove('hidden');
    
    // Update progress indicators
    const progressBar = document.getElementById('progressBar');
    const statusText = document.getElementById('statusText');
    const stopBtn = document.getElementById('stopProcessingBtn');
    
    if (progressBar) progressBar.style.width = "0%";
    if (statusText) statusText.textContent = "Preparing effects...";
    
    // Setup stop button
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
      };
    }
    
    // Get form values
    const effectType = document.getElementById('effectType').value;
    const rotationAngle = document.getElementById('rotationAngle').value;
    const flipHorizontal = document.getElementById('flipHorizontal').checked;
    const flipVertical = document.getElementById('flipVertical').checked;
    const outputFormat = document.getElementById('effectsOutputFormat').value;
    
    // Create form data for API request
    const formData = new FormData();
    formData.append("file", videoFile);
    formData.append("effect_type", effectType);
    formData.append("rotate", rotationAngle);
    formData.append("flip_horizontal", flipHorizontal);
    formData.append("flip_vertical", flipVertical);
    formData.append("output_format", outputFormat);
    
    // Setup WebSocket for progress updates
    const connectionId = crypto.randomUUID();
    formData.append("connection_id", connectionId);
    
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${connectionId}`);
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (progressBar) progressBar.style.width = (data.progress || 0) + "%";
        if (statusText) statusText.textContent = data.status || "Processing...";
      } catch (error) {
        console.error("WebSocket message parsing error:", error);
      }
    };
    
    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      if (statusText) statusText.textContent = "Error: WebSocket connection failed";
      if (progressBar) progressBar.classList.add("bg-red-500");
    };
    
    // Submit the form data
    fetch('/api/videocutter/effects', {
      method: 'POST',
      body: formData,
      signal: signal
    })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then(data => {
      console.log("Effects applied successfully:", data);
      if (progressBar) progressBar.style.width = "100%";
      if (statusText) statusText.textContent = "Effects applied successfully!";
      
      // Setup download button
      const downloadBtn = document.getElementById('downloadBtn');
      if (downloadBtn && data.download_url) {
        downloadBtn.innerHTML = '<i class="fas fa-download"></i> Download Processed Video';
        downloadBtn.onclick = () => window.open(data.download_url, '_blank');
        downloadBtn.classList.remove('hidden');
      }
    })
    .catch(error => {
      console.error("Error applying effects:", error);
      if (statusText) statusText.textContent = "Error: " + error.message;
      if (progressBar) progressBar.classList.add("bg-red-500");
    })
    .finally(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    });
  }
};

// Export the module
window.EffectsModule = EffectsModule;