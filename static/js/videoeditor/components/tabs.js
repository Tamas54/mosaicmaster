/**
 * Tab System Component
 * Handles switching between different tabs in the application
 */

const TabSystem = {
    // Initialize the tab system
    init: function() {
        console.log("Tab System initialized");
        this.setupModuleTabs();
        this.setupDialogTabs();
    },
    
    // Setup module tabs in the navbar
    setupModuleTabs: function() {
        const tabButtons = document.querySelectorAll('.module-tabs .tab-button');
        
        tabButtons.forEach(button => {
            button.addEventListener('click', this.handleTabButtonClick.bind(this));
        });
        
        // Make sure the current active tab's panel is visible
        const activeTab = document.querySelector('.module-tabs .tab-button.active');
        if (activeTab) {
            this.showTabPanel(activeTab.getAttribute('data-tab'));
        }
    },
    
    // Handle tab button click
    handleTabButtonClick: function(e) {
        const tabButtons = document.querySelectorAll('.module-tabs .tab-button');
        const clickedButton = e.currentTarget;
        const tabId = clickedButton.getAttribute('data-tab');
        
        // Update button states
        tabButtons.forEach(btn => btn.classList.remove('active'));
        clickedButton.classList.add('active');
        
        // Show corresponding panel
        this.showTabPanel(tabId);
        
        // Remember active tab
        window.videoEditorState = window.videoEditorState || {};
        window.videoEditorState.currentActiveTab = tabId;
    },
    
    // Show the specified tab panel, hide others
    showTabPanel: function(tabId) {
        // Hide all panels
        const panels = document.querySelectorAll('.module-panel');
        panels.forEach(panel => panel.style.display = 'none');
        
        // Show only the selected panel
        const activePanel = document.getElementById(tabId + '-panel');
        if (activePanel) {
            activePanel.style.display = 'block';
        }
    },
    
    // Setup tabs within dialogs
    setupDialogTabs: function() {
        const dialogTabButtons = document.querySelectorAll('.dialog-tabs .tab');
        
        dialogTabButtons.forEach(tab => {
            tab.addEventListener('click', function() {
                // Get the tab container and content containers
                const tabContainer = this.closest('.dialog-tabs');
                const contentContainer = tabContainer.nextElementSibling;
                
                if (!tabContainer || !contentContainer) return;
                
                // Get the tab index
                const tabIndex = Array.from(tabContainer.children).indexOf(this);
                
                // Update tab states
                Array.from(tabContainer.children).forEach(t => t.classList.remove('active'));
                this.classList.add('active');
                
                // Show the corresponding content
                Array.from(contentContainer.children).forEach((content, index) => {
                    content.style.display = index === tabIndex ? 'block' : 'none';
                });
            });
        });
        
        // Activate the first tab in each tab container by default
        document.querySelectorAll('.dialog-tabs').forEach(tabContainer => {
            const firstTab = tabContainer.querySelector('.tab');
            if (firstTab) firstTab.click();
        });
    },
    
    // Programmatically switch to a specific tab
    switchToTab: function(tabId) {
        const tabButton = document.querySelector(`.module-tabs .tab-button[data-tab="${tabId}"]`);
        if (tabButton) {
            tabButton.click();
        }
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    TabSystem.init();
});

// Export the component
window.TabSystem = TabSystem;