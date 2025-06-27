/**
 * Video Editor Main Initialization
 * Coordinates initialization of all modules and components
 */

const VideoEditorInitializer = {
    // Initialize the editor
    init: function() {
        console.log("🚀 Video Editor Initialization Started");
        
        // Check if we're on the video editor page
        if (!this.isVideoEditorPage()) {
            console.log("Not on video editor page, skipping initialization");
            return;
        }
        
        console.log("📋 Video Editor Page Detected");
        
        // Initialize global state
        this.initializeState();
        
        // Setup video file drag and drop
        this.setupFileHandling();
        
        // Setup video player interactions
        this.setupVideoPlayer();
        
        // Create subtitle display element
        this.setupSubtitleDisplay();
        
        // Initialize UI components
        this.initializeComponents();
        
        console.log("🎬 Video Editor Initialization Complete");
    },
    
    // Check if we're on the video editor page
    isVideoEditorPage: function() {
        return window.location.pathname.includes('videocutter') || 
               window.location.pathname.includes('videoeditor');
    },
    
    // Initialize global state
    initializeState: function() {
        // Initialize lucide icons if available
        if (typeof lucide !== 'undefined' && typeof lucide.createIcons === 'function') {
            lucide.createIcons();
            console.log("✅ Lucide icons initialized");
        }
        
        // Set up global state object
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
        
        // Set up global file getter for other modules
        window.getVideoFile = function() {
            return window.videoEditorState.currentVideoFile;
        };
    },
    
    // Setup file upload handling
    setupFileHandling: function() {
        const videoDropZone = document.getElementById('videoDropZone');
        const videoFileInput = document.getElementById('videoFileInput');
        
        if (videoDropZone && videoFileInput) {
            // Click on drop zone to trigger file input
            videoDropZone.addEventListener('click', () => {
                videoFileInput.click();
            });
            
            // Handle drag events
            videoDropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                videoDropZone.classList.add('dragover');
            });
            
            videoDropZone.addEventListener('dragleave', () => {
                videoDropZone.classList.remove('dragover');
            });
            
            // Handle file drop
            videoDropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                videoDropZone.classList.remove('dragover');
                
                if (e.dataTransfer.files.length > 0) {
                    const file = e.dataTransfer.files[0];
                    if (file.type.startsWith('video/')) {
                        this.handleVideoFile(file);
                    } else {
                        alert("Please upload a valid video file.");
                    }
                }
            });
            
            // Handle file selection via input
            videoFileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.handleVideoFile(e.target.files[0]);
                }
            });
            
            // Remove file handling
            const removeFileBtn = document.getElementById('removeVideoFile');
            if (removeFileBtn) {
                removeFileBtn.addEventListener('click', this.removeVideoFile.bind(this));
            }
        }
    },
    
    // Handle video file selection
    handleVideoFile: function(file) {
        console.log("📺 Video file selected:", file.name);
        window.videoEditorState.currentVideoFile = file;
        
        // Update UI to show file info
        const videoFileName = document.getElementById('videoFileName');
        const videoFileSize = document.getElementById('videoFileSize');
        const videoFileInfo = document.getElementById('videoFileInfo');
        
        if (videoFileName) videoFileName.textContent = file.name;
        if (videoFileSize && window.VideoEditorUtils) videoFileSize.textContent = window.VideoEditorUtils.formatFileSize(file.size);
        if (videoFileInfo) videoFileInfo.classList.remove('hidden');
        
        // Detect AVI and other non-standard formats
        const fileExt = file.name.split('.').pop().toLowerCase();
        console.log("File extension detected:", fileExt);
        
        // Check if this is AVI or MKV format - which might need conversion
        if (fileExt === 'avi' || fileExt === 'mkv') {
            console.log("Detected AVI/MKV file which may need conversion");
            
            // Show a warning message to the user
            const processingDialog = document.getElementById('processingDialog');
            const processingStatus = document.getElementById('processingStatus');
            
            if (processingDialog) processingDialog.style.display = 'flex';
            if (processingStatus) processingStatus.textContent = `${fileExt.toUpperCase()} formátumú fájl észlelve. A böngésző lejátszásához konvertálás szükséges lehet.`;
            
            // You can initiate conversion here if needed
            // For now, let's try to play the file as-is
        }
        
        // Set up video preview
        const videoPlayer = document.getElementById('videoPlayer');
        if (videoPlayer) {
            const videoURL = URL.createObjectURL(file);
            videoPlayer.src = videoURL;
            
            // Show relevant elements
            const videoPreviewSection = document.getElementById('videoPreviewSection');
            const editingOptions = document.getElementById('editingOptions');
            const trimVideoBtn = document.getElementById('trimVideoBtn');
            
            if (videoPreviewSection) videoPreviewSection.classList.remove('hidden');
            if (editingOptions) editingOptions.classList.remove('hidden');
            if (trimVideoBtn) trimVideoBtn.classList.remove('hidden');
            
            // Setup video metadata events
            videoPlayer.onloadedmetadata = () => {
                window.videoEditorState.videoDuration = videoPlayer.duration;
                window.videoEditorState.startTime = 0;
                window.videoEditorState.endTime = videoPlayer.duration > 0 ? videoPlayer.duration : 60; // Default to 60 seconds if duration is unknown
                
                // Update time inputs
                const startTimeInput = document.getElementById('startTimeInput');
                const endTimeInput = document.getElementById('endTimeInput');
                
                if (startTimeInput && window.VideoEditorUtils) {
                    startTimeInput.value = window.VideoEditorUtils.formatTime(window.videoEditorState.startTime);
                }
                
                if (endTimeInput && window.VideoEditorUtils) {
                    endTimeInput.value = window.VideoEditorUtils.formatTime(window.videoEditorState.endTime);
                }
                
                // Update trim region
                if (window.TimerModule) {
                    window.TimerModule.updateTrimRegion();
                }
                
                // Update time display
                const currentTimeDisplay = document.getElementById('currentTimeDisplay');
                if (currentTimeDisplay && window.VideoEditorUtils) {
                    currentTimeDisplay.textContent = `${window.VideoEditorUtils.formatTime(0)} / ${window.VideoEditorUtils.formatTime(window.videoEditorState.videoDuration)}`;
                }
            };
        }
    },
    
    // Remove current video file
    removeVideoFile: function() {
        window.videoEditorState.currentVideoFile = null;
        
        // Reset UI
        const videoFileInfo = document.getElementById('videoFileInfo');
        const videoPreviewSection = document.getElementById('videoPreviewSection');
        const editingOptions = document.getElementById('editingOptions');
        const trimVideoBtn = document.getElementById('trimVideoBtn');
        const downloadBtn = document.getElementById('downloadBtn');
        const videoFileInput = document.getElementById('videoFileInput');
        
        if (videoFileInfo) videoFileInfo.classList.add('hidden');
        if (videoPreviewSection) videoPreviewSection.classList.add('hidden');
        if (editingOptions) editingOptions.classList.add('hidden');
        if (trimVideoBtn) trimVideoBtn.classList.add('hidden');
        if (downloadBtn) downloadBtn.classList.add('hidden');
        if (videoFileInput) videoFileInput.value = '';
        
        // Reset video player
        const videoPlayer = document.getElementById('videoPlayer');
        if (videoPlayer) {
            if (videoPlayer.src && typeof URL.revokeObjectURL === 'function') {
                URL.revokeObjectURL(videoPlayer.src);
            }
            videoPlayer.src = '';
        }
    },
    
    // Setup video player interactions
    setupVideoPlayer: function() {
        const videoPlayer = document.getElementById('videoPlayer');
        const playPauseBtn = document.getElementById('playPauseBtn');
        const firstFrameBtn = document.getElementById('firstFrameBtn');
        const lastFrameBtn = document.getElementById('lastFrameBtn');
        const prevFrameBtn = document.getElementById('prevFrameBtn');
        const nextFrameBtn = document.getElementById('nextFrameBtn');
        const setStartBtn = document.getElementById('setStartBtn');
        const setEndBtn = document.getElementById('setEndBtn');
        
        // Play/Pause button
        if (videoPlayer && playPauseBtn) {
            playPauseBtn.addEventListener('click', () => {
                if (videoPlayer.paused) {
                    videoPlayer.play();
                    playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
                } else {
                    videoPlayer.pause();
                    playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
                }
            });
            
            // Update button icon when play/pause state changes
            videoPlayer.addEventListener('play', () => {
                playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
            });
            
            videoPlayer.addEventListener('pause', () => {
                playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
            });
        }
        
        // Navigation buttons
        if (videoPlayer) {
            // First frame
            if (firstFrameBtn) {
                firstFrameBtn.addEventListener('click', () => {
                    videoPlayer.currentTime = 0;
                });
            }
            
            // Last frame
            if (lastFrameBtn) {
                lastFrameBtn.addEventListener('click', () => {
                    videoPlayer.currentTime = videoPlayer.duration;
                });
            }
            
            // Previous frame (approximately 1/30 second)
            if (prevFrameBtn) {
                prevFrameBtn.addEventListener('click', () => {
                    videoPlayer.currentTime = Math.max(0, videoPlayer.currentTime - 0.033);
                });
            }
            
            // Next frame (approximately 1/30 second)
            if (nextFrameBtn) {
                nextFrameBtn.addEventListener('click', () => {
                    videoPlayer.currentTime = Math.min(videoPlayer.duration, videoPlayer.currentTime + 0.033);
                });
            }
            
            // Set start and end times
            if (setStartBtn && window.TimerModule) {
                setStartBtn.addEventListener('click', window.TimerModule.setStartTime.bind(window.TimerModule));
            }
            
            if (setEndBtn && window.TimerModule) {
                setEndBtn.addEventListener('click', window.TimerModule.setEndTime.bind(window.TimerModule));
            }
            
            // Update timeline on time change
            videoPlayer.addEventListener('timeupdate', () => {
                if (window.TimerModule) {
                    window.TimerModule.updateTimelineMarker();
                }
                
                // Update time display
                const currentTimeDisplay = document.getElementById('currentTimeDisplay');
                if (currentTimeDisplay && window.VideoEditorUtils) {
                    const timeStr = window.VideoEditorUtils.formatTime(videoPlayer.currentTime);
                    const durationStr = window.VideoEditorUtils.formatTime(videoPlayer.duration);
                    currentTimeDisplay.textContent = `${timeStr} / ${durationStr}`;
                }
            });
        }
    },
    
    // Setup subtitle display
    setupSubtitleDisplay: function() {
        const videoContainer = document.getElementById('videoContainer');
        if (!videoContainer) return;
        
        // Create subtitle display element if it doesn't exist
        let subtitleDisplay = document.getElementById('subtitleDisplay');
        if (!subtitleDisplay) {
            subtitleDisplay = document.createElement('div');
            subtitleDisplay.id = 'subtitleDisplay';
            subtitleDisplay.style.display = 'none';
            videoContainer.appendChild(subtitleDisplay);
        }
    },
    
    // Initialize all components
    initializeComponents: function() {
        // Initialize each module if available
        if (window.TimerModule) window.TimerModule.init();
        if (window.VideoModule) window.VideoModule.init();
        if (window.EffectsModule) window.EffectsModule.init();
    }
};

// Initialize editor when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    VideoEditorInitializer.init();
});

// Export the initializer
window.VideoEditorInitializer = VideoEditorInitializer;