/**
 * VideoEditor Utilities
 * Common utility functions used throughout the application
 */

const VideoEditorUtils = {
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
    
    // Format file size for display
    formatFileSize: function(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    
    // Generate a UUID v4
    generateUUID: function() {
        return crypto.randomUUID();
    },
    
    // Initialize WebSocket for progress updates
    initWebSocket: function(connectionId) {
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${connectionId}`);
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                // Find progress elements
                const progressBar = document.getElementById('progressBar');
                const statusText = document.getElementById('statusText');
                
                // Update progress UI
                if (progressBar) progressBar.style.width = data.progress + "%";
                if (statusText) statusText.textContent = data.status;
            } catch (error) {
                console.error("WebSocket message parsing error:", error);
            }
        };
        
        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
        };
        
        return ws;
    },
    
    // Check if a string is a valid URL
    isValidURL: function(str) {
        try {
            new URL(str);
            return true;
        } catch (e) {
            return false;
        }
    },
    
    // Show processing dialog and setup abort
    showProcessingDialog: function(processingText = "Processing...") {
        const processingSection = document.getElementById('processingSection');
        const progressBar = document.getElementById('progressBar');
        const statusText = document.getElementById('statusText');
        const stopBtn = document.getElementById('stopProcessingBtn');
        
        // Create abort controller
        const abortController = new AbortController();
        
        // Show processing UI
        if (processingSection) processingSection.classList.remove('hidden');
        if (progressBar) progressBar.style.width = "0%";
        if (statusText) statusText.textContent = processingText;
        
        // Setup stop button
        if (stopBtn) {
            stopBtn.onclick = () => {
                abortController.abort();
                if (statusText) statusText.textContent = "Process cancelled by user";
                if (progressBar) progressBar.classList.add("bg-red-500");
            };
        }
        
        return {
            abortSignal: abortController.signal,
            abortController: abortController
        };
    }
};

// Export the utilities
window.VideoEditorUtils = VideoEditorUtils;