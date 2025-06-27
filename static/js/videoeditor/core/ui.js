/**
 * UI Module
 * Handles general UI interactions and updates
 */

const UIModule = {
    // Initialize the UI module
    init: function() {
        console.log("UI Module initialized");
        this.setupCollapsePanels();
        this.setupTimeInputs();
        this.setupSliders();
    },
    
    // Initialize collapsible panels
    setupCollapsePanels: function() {
        const collapseBtns = document.querySelectorAll('.collapse-btn');
        
        collapseBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const panel = this.closest('.panel, .timeline');
                if (!panel) return;
                
                const contents = panel.querySelectorAll('.property-row, .thumbnail-grid, .filter-tabs, .video-preview, .controls, .timeline-content, .tabs, .timeline-toolbar, .property-table, .panel-content');
                
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
    
    // Setup time input fields
    setupTimeInputs: function() {
        const startTimeInput = document.getElementById('startTimeInput');
        const endTimeInput = document.getElementById('endTimeInput');
        
        if (startTimeInput && window.TimerModule) {
            startTimeInput.addEventListener('change', function() {
                window.videoEditorState.startTime = window.TimerModule.parseTime(this.value);
                window.TimerModule.updateTrimRegion();
            });
        }
        
        if (endTimeInput && window.TimerModule) {
            endTimeInput.addEventListener('change', function() {
                window.videoEditorState.endTime = window.TimerModule.parseTime(this.value);
                window.TimerModule.updateTrimRegion();
            });
        }
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
    
    // Update progress bar
    updateProgress: function(percent, message) {
        const progressBar = document.getElementById('progressBar');
        const statusText = document.getElementById('statusText');
        
        if (progressBar) progressBar.style.width = `${percent}%`;
        if (statusText && message) statusText.textContent = message;
    },
    
    // Reset progress indicators
    resetProgress: function() {
        const progressBar = document.getElementById('progressBar');
        const statusText = document.getElementById('statusText');
        
        if (progressBar) {
            progressBar.style.width = "0%";
            progressBar.classList.remove("bg-red-500");
        }
        
        if (statusText) statusText.textContent = "";
    },
    
    // Show error message
    showError: function(message) {
        const statusText = document.getElementById('statusText');
        const progressBar = document.getElementById('progressBar');
        
        if (statusText) statusText.textContent = `Error: ${message}`;
        if (progressBar) progressBar.classList.add("bg-red-500");
    },
    
    // Setup download button
    setupDownloadButton: function(url, text = "Download File") {
        const downloadBtn = document.getElementById('downloadBtn');
        
        if (downloadBtn && url) {
            downloadBtn.textContent = text;
            downloadBtn.onclick = () => window.open(url, '_blank');
            downloadBtn.classList.remove('hidden');
        }
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    UIModule.init();
});

// Export the module
window.UIModule = UIModule;