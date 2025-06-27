/**
 * Help System Component
 * Manages the help dialog and documentation
 */

const HelpSystem = {
    // Initialize the help system
    init: function() {
        console.log("Help System initialized");
        this.setupHelpButton();
        this.setupSettingsButton();
    },
    
    // Setup help button and panel
    setupHelpButton: function() {
        const helpButton = document.getElementById('helpMenuButton');
        const helpPanel = document.getElementById('help-panel');
        const closeHelpBtn = document.getElementById('closeHelpBtn');
        
        if (helpButton && helpPanel) {
            helpButton.addEventListener('click', () => {
                // Close settings panel if open
                const settingsPanel = document.getElementById('settings-panel');
                if (settingsPanel && settingsPanel.style.display === 'block') {
                    settingsPanel.style.display = 'none';
                }
                
                // Toggle help panel
                helpPanel.style.display = helpPanel.style.display === 'none' ? 'block' : 'none';
            });
            
            // Setup close button if it exists
            if (closeHelpBtn) {
                closeHelpBtn.addEventListener('click', () => {
                    helpPanel.style.display = 'none';
                });
            }
        }
    },
    
    // Setup settings button and panel
    setupSettingsButton: function() {
        const settingsButton = document.getElementById('settingsMenuButton');
        const settingsPanel = document.getElementById('settings-panel');
        const closeSettingsBtn = document.getElementById('closeSettingsBtn');
        
        if (settingsButton && settingsPanel) {
            settingsButton.addEventListener('click', () => {
                // Close help panel if open
                const helpPanel = document.getElementById('help-panel');
                if (helpPanel && helpPanel.style.display === 'block') {
                    helpPanel.style.display = 'none';
                }
                
                // Toggle settings panel
                settingsPanel.style.display = settingsPanel.style.display === 'none' ? 'block' : 'none';
            });
            
            // Setup close button if it exists
            if (closeSettingsBtn) {
                closeSettingsBtn.addEventListener('click', () => {
                    settingsPanel.style.display = 'none';
                });
            }
        }
    },
    
    // Show help for a specific topic
    showTopicHelp: function(topicId) {
        const helpPanel = document.getElementById('help-panel');
        
        // Show the help panel if not already visible
        if (helpPanel && helpPanel.style.display === 'none') {
            helpPanel.style.display = 'block';
        }
        
        // Find and highlight the specific topic
        const topicElement = document.getElementById(topicId);
        if (topicElement) {
            // Scroll to the topic
            topicElement.scrollIntoView({ behavior: 'smooth' });
            
            // Highlight the topic temporarily
            topicElement.classList.add('highlight-topic');
            setTimeout(() => {
                topicElement.classList.remove('highlight-topic');
            }, 2000);
        }
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    HelpSystem.init();
});

// Export the component
window.HelpSystem = HelpSystem;