// static/js/script.js
document.addEventListener('DOMContentLoaded', function() {
    // --- DOM Element Selections ---
    const downloadForm = document.getElementById('downloadForm');
    const statusMessagesDiv = document.getElementById('statusMessages');
    const kukuUrlInput = document.getElementById('kuku_url');
    const submitButton = document.getElementById('submitDownloadBtn');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');

    // Sidebar Navigation
    const navLinks = document.querySelectorAll('.main-nav a');
    const contentSections = document.querySelectorAll('.content-section');
    const mainHeaderTitle = document.querySelector('.main-header h2');

    // Theme Toggle
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    const masterContainer = document.querySelector('.master-container'); // Or body for global theme

    let pollingInterval = null;
    let currentTaskId = null;

    // --- Initialization ---
    loadInitialSettings();
    setupEventListeners();

    function loadInitialSettings() {
        // Load last used URL
        const lastUrl = localStorage.getItem('lastKukuUrl');
        if (lastUrl) {
            kukuUrlInput.value = lastUrl;
        }

        // Load and apply theme
        const savedTheme = localStorage.getItem('kukuHarvesterTheme') || 'dark'; // Default to dark
        applyTheme(savedTheme);
        
        // Set initial active section based on hash or default
        const currentHash = window.location.hash || '#downloader-section';
        activateSection(currentHash.substring(1)); // Remove '#'
    }

    function setupEventListeners() {
        downloadForm.addEventListener('submit', handleDownloadFormSubmit);
        navLinks.forEach(link => link.addEventListener('click', handleNavLinkClick));
        themeToggleBtn.addEventListener('click', toggleTheme);
    }

    // --- Theme Management ---
    function applyTheme(themeName) {
        document.body.className = ''; // Clear existing theme classes from body
        document.body.classList.add(`${themeName}-theme`); // Add new theme class to body
        themeToggleBtn.textContent = themeName === 'dark' ? '☀️' : '🌓';
        localStorage.setItem('kukuHarvesterTheme', themeName);
    }

    function toggleTheme() {
        const currentTheme = localStorage.getItem('kukuHarvesterTheme') || 'dark';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        applyTheme(newTheme);
    }


    // --- Sidebar Navigation ---
    function handleNavLinkClick(event) {
        event.preventDefault();
        const targetId = this.getAttribute('href').substring(1); // Get ID from href (e.g., #downloader-section -> downloader-section)
        activateSection(targetId);
        window.location.hash = targetId; // Update URL hash for direct linking/bookmarking
    }

    function activateSection(targetId) {
        navLinks.forEach(link => {
            link.classList.remove('nav-active');
            if (link.getAttribute('href') === `#${targetId}`) {
                link.classList.add('nav-active');
                // Update main header title based on the link text (excluding the icon)
                const linkText = link.textContent.replace(link.querySelector('.nav-icon').textContent, '').trim();
                if (mainHeaderTitle) mainHeaderTitle.textContent = linkText;
            }
        });

        contentSections.forEach(section => {
            if (section.id === targetId) {
                section.style.display = 'block';
                section.classList.add('active-section'); // Ensure animation triggers if needed
            } else {
                section.style.display = 'none';
                section.classList.remove('active-section');
            }
        });
    }


    // --- Download Form Handling & Status Polling ---
    async function handleDownloadFormSubmit(event) {
        event.preventDefault();
        if (submitButton.disabled) return; // Prevent multiple submissions

        if (pollingInterval) clearInterval(pollingInterval);
        currentTaskId = null; // Reset current task ID

        const kukuUrl = kukuUrlInput.value.trim();
        const downloadPath = document.getElementById('download_path').value.trim();
        const convertFormat = document.getElementById('convert_format').value.trim();
        const exportMetadata = document.getElementById('export_metadata').checked;

        if (!isValidUrl(kukuUrl)) {
            addMessage('Please enter a valid KuKu FM show URL (e.g., https://kukufm.com/show/...).', 'error', true);
            kukuUrlInput.focus();
            return;
        }
        
        localStorage.setItem('lastKukuUrl', kukuUrl);
        clearStatusMessages();
        addMessage('🚀 Initiating download... Contacting server.', 'info');
        setSubmitButtonState(true, 'Processing...');
        showProgressBar('Connecting to server...');

        try {
            const response = await fetch('/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    kuku_url: kukuUrl, download_path: downloadPath,
                    convert_format: convertFormat || null, export_metadata: exportMetadata
                }),
            });

            const result = await response.json();

            if (response.ok && result.task_id) {
                currentTaskId = result.task_id;
                addMessage(result.message || `Server accepted request (Task ID: ${currentTaskId}). Polling for status...`, 'info', true);
                updateProgressBar(10, `Task Queued: ${result.show_title || 'Show'}`); // Initial progress
                pollStatus(currentTaskId);
            } else {
                throw new Error(result.message || `Server error: ${response.status}`);
            }
        } catch (error) {
            console.error('Submit /download error:', error);
            addMessage(`Failed to start download: ${error.message}`, 'error', true);
            setSubmitButtonState(false, '🚀 Initiate Download');
            hideProgressBar();
        }
    }

    function isValidUrl(string) {
        try {
            const url = new URL(string);
            return url.protocol === "http:" || url.protocol === "https:"; // Basic check
        } catch (_) {
            return false;
        }
    }

    function pollStatus(taskId) {
        let progress = 15; // Start progress after initial queue
        updateProgressBar(progress, 'Fetching show details...');

        pollingInterval = setInterval(async () => {
            if (!currentTaskId || taskId !== currentTaskId) { // If task changed or cleared
                clearInterval(pollingInterval);
                return;
            }
            try {
                const response = await fetch(`/status/${taskId}`);
                if (!response.ok) {
                    throw new Error(`Server returned ${response.status} while checking status.`);
                }
                const statusResult = await response.json();

                // Simulate progress increment if still processing
                if (statusResult.status === 'processing' || statusResult.status === 'processing_queued') {
                    progress = Math.min(progress + 5, 85); // Increment but don't reach 100 until complete
                    updateProgressBar(progress, statusResult.message || `Processing: ${statusResult.show_title || 'Show'}`);
                } else {
                     updateProgressBar(100, statusResult.message); // For final states
                }
                
                updateLatestStatusMessage(`[${new Date().toLocaleTimeString()}] ${statusResult.show_title || 'Show'}: ${statusResult.message}`, statusResult.status);

                if (statusResult.status === 'complete') {
                    clearInterval(pollingInterval);
                    addMessage(`✅ Download and zipping complete for '${statusResult.show_title || 'show'}'!`, 'success');
                    if (statusResult.zip_filename) {
                        displayDownloadLink(statusResult.zip_filename, statusResult.show_title);
                    }
                    setSubmitButtonState(false, '🚀 Initiate Download');
                    hideProgressBarAfterDelay();
                } else if (statusResult.status === 'error') {
                    clearInterval(pollingInterval);
                    addMessage(`❌ Error processing '${statusResult.show_title || 'Show'}': ${statusResult.message}`, 'error');
                    setSubmitButtonState(false, '🚀 Initiate Download');
                    hideProgressBarAfterDelay();
                } else if (statusResult.status === 'not_found') {
                    clearInterval(pollingInterval);
                    addMessage(`Task ID ${taskId} not found. It might have expired or an error occurred.`, 'warning');
                    setSubmitButtonState(false, '🚀 Initiate Download');
                    hideProgressBarAfterDelay();
                }
            } catch (error) {
                console.error('Polling error:', error);
                addMessage(`Error polling status for task ${taskId}: ${error.message}`, 'error');
                clearInterval(pollingInterval);
                setSubmitButtonState(false, '🚀 Initiate Download');
                hideProgressBarAfterDelay();
            }
        }, 3500); // Poll every 3.5 seconds
    }

    function displayDownloadLink(zipFilename, showTitle) {
        const downloadLink = document.createElement('a');
        downloadLink.href = `/fetch_zip/${encodeURIComponent(zipFilename)}`;
        downloadLink.textContent = `Download ${showTitle || 'Show'} ZIP (${zipFilename})`;
        downloadLink.classList.add('download-link-button');
        downloadLink.setAttribute('download', zipFilename); // Suggest filename to browser
        
        const pContainer = document.createElement('p');
        pContainer.style.textAlign = 'center'; // Center the button
        pContainer.appendChild(downloadLink);
        statusMessagesDiv.appendChild(pContainer); // Append, not prepend, for final action
    }

    function setSubmitButtonState(disabled, text) {
        submitButton.disabled = disabled;
        const btnTextSpan = submitButton.querySelector('.btn-text');
        if (btnTextSpan) btnTextSpan.textContent = text;
        else submitButton.textContent = text; // Fallback if span not found
    }

    // --- UI Update Functions ---
    function clearStatusMessages() {
        statusMessagesDiv.innerHTML = ''; // Clear all messages
        // Remove the placeholder if it exists
        const placeholder = statusMessagesDiv.querySelector('.status-placeholder');
        if (placeholder) placeholder.remove();
    }
    
    let lastStatusP = null; 

    function updateLatestStatusMessage(message, type = 'info') {
        // If no lastStatusP, or its type has changed to a final state (success/error),
        // or if the current message type is different from the last one, create a new paragraph.
        // This helps group processing messages but start new ones for final states or type changes.
        if (!lastStatusP || 
            lastStatusP.classList.contains('status-success') || 
            lastStatusP.classList.contains('status-error') ||
            !lastStatusP.classList.contains(`status-${type}`)) {
            
            lastStatusP = document.createElement('p');
            lastStatusP.classList.add('status-message-item');
            statusMessagesDiv.insertBefore(lastStatusP, statusMessagesDiv.firstChild);
        }
        lastStatusP.textContent = message;
        // Ensure all previous type classes are removed before adding the new one
        lastStatusP.className = 'status-message-item'; // Reset to base class
        lastStatusP.classList.add(`status-${type}`); // Add current type
    }
    
    function addMessage(message, type = 'info', clearPrevious = false) {
        if (clearPrevious) {
            clearStatusMessages();
        }
        const p = document.createElement('p');
        p.textContent = message;
        p.className = `status-message-item status-${type}`;
        statusMessagesDiv.insertBefore(p, statusMessagesDiv.firstChild);
        lastStatusP = p; // The newest message is now the "last status" for updates
    }

    function showProgressBar(message = 'Processing...') {
        progressText.textContent = message;
        progressBar.style.width = '0%'; // Reset width
        progressContainer.style.display = 'block';
        // Start a simple indeterminate animation if no specific progress value
        progressBar.style.animation = 'indeterminateAnimation 2s infinite linear';
    }

    function updateProgressBar(percentage, message) {
        if (progressContainer.style.display !== 'block') {
            progressContainer.style.display = 'block';
        }
        progressBar.style.width = `${percentage}%`;
        progressText.textContent = message || `Progress: ${percentage}%`;
        // If we have a specific percentage, stop indeterminate animation
        if (percentage > 0 && percentage < 100) {
            progressBar.style.animation = 'none'; // Stop if it was indeterminate
        } else if (percentage === 0 || percentage === 100) {
             progressBar.style.animation = 'none';
        }
    }

    function hideProgressBar() {
        progressContainer.style.display = 'none';
        progressBar.style.width = '0%';
        progressText.textContent = '';
        progressBar.style.animation = 'none';
    }
    function hideProgressBarAfterDelay(delay = 1000) {
        setTimeout(hideProgressBar, delay);
    }

});

// Add a new keyframe animation to your CSS for the indeterminate progress bar:
// (This comment is for you, the CSS should be in the style.css file)
/*
@keyframes indeterminateAnimation {
    0% { transform: translateX(-100%); }
    50% { transform: translateX(100%); } // This makes it slide across
    100% { transform: translateX(-100%); }
}
// And modify .progress-bar-inner in CSS:
// .progress-bar-inner {
//     ...
//     position: relative; // Needed for the pseudo-element or direct transform
//     overflow: hidden; // If using a pseudo-element that moves
// }
// A simpler indeterminate animation might just be the gradient moving:
// @keyframes progressBarAnimation {
//     0% { background-position: 200% 0; }
//     100% { background-position: -200% 0; }
// }
// And ensure background-size is large enough for this, e.g., background-size: 200% 100%;
*/
