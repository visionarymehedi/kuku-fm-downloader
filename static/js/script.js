// static/js/script.js
document.addEventListener('DOMContentLoaded', function() {
    // --- DOM Element Selections ---
    const downloadForm = document.getElementById('downloadForm');
    const downloaderFormContainer = document.getElementById('downloaderFormContainer');
    const cookieNoticeDownloader = document.getElementById('cookieNoticeDownloader');
    
    const statusMessagesDiv = document.getElementById('statusMessages');
    const kukuUrlInput = document.getElementById('kuku_url');
    const submitButton = document.getElementById('submitDownloadBtn');
    
    const downloadProcessDisplay = document.getElementById('downloadProcessDisplay');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');

    // Sidebar Navigation & Header
    const navLinks = document.querySelectorAll('.main-nav a');
    const contentSections = document.querySelectorAll('.content-section');
    const mainHeaderTitleElement = document.getElementById('mainHeaderTitle');
    const mainHeaderSubtitleElement = document.querySelector('.main-header .subtitle');
    const sidebar = document.querySelector('.sidebar');
    const contentArea = document.querySelector('.content-area');
    const sidebarToggleBtn = document.getElementById('sidebarToggleBtn'); 

    // Theme Toggle
    const themeToggleBtn = document.getElementById('themeToggleBtn');

    // Cookie Management Elements
    const cookieJsonInput = document.getElementById('cookieJsonInput');
    const saveCookiesBtn = document.getElementById('saveCookiesBtn');
    const clearCookiesBtn = document.getElementById('clearCookiesBtn');
    const cookieStatusMessage = document.getElementById('cookieStatusMessage');

    let pollingInterval = null;
    let currentTaskId = null; 

    // --- Initialization ---
    loadInitialSettings();
    setupEventListeners();
    checkInitialCookieStatus(); // Check cookie status on load

    function loadInitialSettings() {
        const lastUrl = localStorage.getItem('kukuHarvesterLastUrl');
        if (lastUrl && kukuUrlInput) kukuUrlInput.value = lastUrl;

        const savedTheme = localStorage.getItem('kukuHarvesterTheme') || 'dark'; // Default to dark
        applyTheme(savedTheme);
        
        const currentHash = window.location.hash || '#downloader-section'; // Default to downloader
        activateSection(currentHash.substring(1));

        if (window.innerWidth > 768) {
            const isSidebarCollapsed = localStorage.getItem('kukuHarvesterSidebarDesktop') === 'collapsed';
            if (isSidebarCollapsed && sidebar) {
                sidebar.classList.add('collapsed');
                if(contentArea) contentArea.classList.add('sidebar-collapsed');
            }
        } else { 
            if(sidebar) sidebar.classList.remove('open', 'collapsed');
            if(contentArea) contentArea.classList.remove('sidebar-collapsed');
        }
        updateSidebarToggleButton(); 
    }

    function setupEventListeners() {
        if (downloadForm) downloadForm.addEventListener('submit', handleDownloadFormSubmit);
        navLinks.forEach(link => link.addEventListener('click', handleNavLinkClick));
        if (themeToggleBtn) themeToggleBtn.addEventListener('click', toggleTheme);
        if (sidebarToggleBtn) sidebarToggleBtn.addEventListener('click', toggleSidebar);
        
        if(saveCookiesBtn) saveCookiesBtn.addEventListener('click', handleSaveCookies);
        if(clearCookiesBtn) clearCookiesBtn.addEventListener('click', handleClearCookies);

        window.addEventListener('hashchange', () => {
            const currentHash = window.location.hash || '#downloader-section';
            activateSection(currentHash.substring(1));
        });
        window.addEventListener('resize', updateSidebarToggleButton);
    }

    // --- Theme Management ---
    function applyTheme(themeName) {
        document.body.className = ''; 
        document.body.classList.add(`${themeName}-theme`); 
        if (themeToggleBtn) {
            themeToggleBtn.innerHTML = themeName === 'dark' ? '☀️<span class="tooltiptext">Light Mode</span>' : '🌓<span class="tooltiptext">Dark Mode</span>';
        }
        localStorage.setItem('kukuHarvesterTheme', themeName);
    }

    function toggleTheme() {
        const newTheme = (localStorage.getItem('kukuHarvesterTheme') || 'dark') === 'dark' ? 'light' : 'dark';
        applyTheme(newTheme);
    }

    // --- Sidebar Management ---
    function toggleSidebar() { 
        if (!sidebar) return;
        if (window.innerWidth > 768) { 
            sidebar.classList.toggle('collapsed');
            if(contentArea) contentArea.classList.toggle('sidebar-collapsed');
            localStorage.setItem('kukuHarvesterSidebarDesktop', sidebar.classList.contains('collapsed') ? 'collapsed' : 'expanded');
        } else { 
            sidebar.classList.toggle('open');
        }
        updateSidebarToggleButton(); 
    }
    
    function updateSidebarToggleButton() {
        if (!sidebarToggleBtn || !sidebar) return;
        if (window.innerWidth <= 768) {
            sidebarToggleBtn.style.display = 'inline-flex'; 
            sidebarToggleBtn.innerHTML = sidebar.classList.contains('open') ? '✕' : '☰'; 
            if (sidebar.classList.contains('collapsed')) {
                sidebar.classList.remove('collapsed');
                if(contentArea) contentArea.classList.remove('sidebar-collapsed');
            }
        } else {
            sidebarToggleBtn.style.display = 'inline-flex'; 
            sidebarToggleBtn.innerHTML = sidebar.classList.contains('collapsed') ? '➔' : ''; 
            if (sidebar.classList.contains('open')) {
                sidebar.classList.remove('open');
            }
        }
    }

    // --- Sidebar Navigation & Content Switching ---
    function handleNavLinkClick(event) {
        event.preventDefault();
        const targetId = this.getAttribute('href').substring(1); 
        activateSection(targetId);
        window.location.hash = targetId; 
        if (window.innerWidth <= 768 && sidebar && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open'); 
            updateSidebarToggleButton();
        }
    }

    function activateSection(targetId) {
        navLinks.forEach(link => {
            link.classList.remove('nav-active');
            if (link.getAttribute('href') === `#${targetId}`) {
                link.classList.add('nav-active');
                const navTextElement = link.querySelector('.nav-text');
                const sectionTitle = navTextElement ? navTextElement.textContent.trim() : 'Downloader';
                if (mainHeaderTitleElement) mainHeaderTitleElement.textContent = sectionTitle;
                if (mainHeaderSubtitleElement) { 
                    if (targetId === 'downloader-section') mainHeaderSubtitleElement.textContent = "Download your favorite shows using your cookies.";
                    else if (targetId === 'cookie-section') mainHeaderSubtitleElement.textContent = "Manage your KuKu FM session cookies.";
                    else mainHeaderSubtitleElement.textContent = "Your KuKu FM Harvester Dashboard";
                }
            }
        });
        contentSections.forEach(section => {
            if (section.id === targetId) {
                if (section.style.display !== 'block') { 
                    section.style.display = 'block';
                    section.classList.remove('active-section'); 
                    void section.offsetWidth; 
                    section.classList.add('active-section'); 
                }
            } else {
                section.style.display = 'none';
                section.classList.remove('active-section');
            }
        });
    }

    // --- Cookie Management UI ---
    async function checkInitialCookieStatus() {
        try {
            const response = await fetch('/api/check_user_cookies');
            const result = await response.json();
            updateDownloaderFormAccess(result.cookies_set);
            if (result.cookies_set && cookieStatusMessage) {
                cookieStatusMessage.textContent = "Your KuKu FM cookies are active for this session.";
                cookieStatusMessage.className = 'cookie-status success';
            } else if (cookieStatusMessage) {
                 cookieStatusMessage.textContent = "Please provide your KuKu FM cookies to enable downloading.";
                 cookieStatusMessage.className = 'cookie-status info';
            }
        } catch (error) {
            console.error("Error checking initial cookie status:", error);
            if (cookieStatusMessage) {
                cookieStatusMessage.textContent = "Could not verify cookie status with server.";
                cookieStatusMessage.className = 'cookie-status error';
            }
            updateDownloaderFormAccess(false); // Assume no cookies if check fails
        }
    }

    async function handleSaveCookies() {
        if (!cookieJsonInput || !cookieStatusMessage) return;
        const cookiesJsonString = cookieJsonInput.value.trim();
        if (!cookiesJsonString) {
            cookieStatusMessage.textContent = "Please paste your cookie JSON data.";
            cookieStatusMessage.className = 'cookie-status error';
            return;
        }
        cookieStatusMessage.textContent = "Saving cookies...";
        cookieStatusMessage.className = 'cookie-status info';

        try {
            const response = await fetch('/api/set_user_cookies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cookies_json_string: cookiesJsonString })
            });
            const result = await response.json();
            cookieStatusMessage.textContent = result.message;
            cookieStatusMessage.className = result.status === 'success' ? 'cookie-status success' : 'cookie-status error';
            updateDownloaderFormAccess(result.status === 'success');
        } catch (error) {
            console.error("Error saving cookies:", error);
            cookieStatusMessage.textContent = "Failed to save cookies. Network or server error.";
            cookieStatusMessage.className = 'cookie-status error';
            updateDownloaderFormAccess(false);
        }
    }

    async function handleClearCookies() {
        if (!cookieStatusMessage) return;
        cookieStatusMessage.textContent = "Clearing cookies...";
        cookieStatusMessage.className = 'cookie-status info';
        try {
            const response = await fetch('/api/clear_user_cookies', { method: 'POST' });
            const result = await response.json();
            cookieStatusMessage.textContent = result.message;
            cookieStatusMessage.className = result.status === 'success' ? 'cookie-status success' : 'cookie-status info';
            updateDownloaderFormAccess(false);
            if(cookieJsonInput) cookieJsonInput.value = ''; // Clear the textarea
        } catch (error) {
            console.error("Error clearing cookies:", error);
            cookieStatusMessage.textContent = "Failed to clear cookies. Network or server error.";
            cookieStatusMessage.className = 'cookie-status error';
        }
    }

    function updateDownloaderFormAccess(cookiesAreSet) {
        if (cookiesAreSet) {
            if(cookieNoticeDownloader) cookieNoticeDownloader.classList.add('hidden');
            if(downloadForm) downloadForm.classList.remove('hidden');
        } else {
            if(cookieNoticeDownloader) cookieNoticeDownloader.classList.remove('hidden');
            if(downloadForm) downloadForm.classList.add('hidden');
        }
    }


    // --- Download Form Handling & Status Polling ---
    async function handleDownloadFormSubmit(event) {
        event.preventDefault();
        if (submitButton.disabled) return;
        if (pollingInterval) clearInterval(pollingInterval);
        currentTaskId = null; 

        const kukuUrl = kukuUrlInput.value.trim();
        if (!isValidKukuUrl(kukuUrl)) {
            showDownloadProcessAreaIfNeeded(); 
            addMessageToLog('Please enter a valid KuKu FM show URL (e.g., https://kukufm.com/show/...).', 'error', true);
            kukuUrlInput.focus(); return;
        }
        
        localStorage.setItem('kukuHarvesterLastUrl', kukuUrl);
        showDownloadProcessAreaIfNeeded(); 
        clearStatusLogAndPlaceholder(); 
        addMessageToLog('🚀 Initiating download... Contacting server.', 'info');
        setSubmitButtonState(true, 'Processing...', true); 
        updateProgressBar(0, 'Connecting to server...');

        try {
            const response = await fetch('/download', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kuku_url: kukuUrl }), // Only send URL now
            });
            const result = await response.json();

            if (response.ok && result.task_id) {
                currentTaskId = result.task_id;
                addMessageToLog(result.message || `Server accepted (Task ID: ${currentTaskId}). Polling...`, 
                           result.status === 'processing_queued' ? 'processing_queued' : 'info');
                updateProgressBar(5, result.show_title ? `Task Queued: '${result.show_title}'` : 'Task Queued');
                pollStatus(currentTaskId);
            } else {
                throw new Error(result.message || `Server error: ${response.status}`);
            }
        } catch (error) {
            addMessageToLog(`Failed to start download: ${error.message}`, 'error');
            setSubmitButtonState(false, 'Initiate Download', false);
            hideProgressBarAfterDelay();
        }
    }

    function isValidKukuUrl(string) {
        try {
            const url = new URL(string);
            return (url.protocol==="http:"||url.protocol==="https:") && url.hostname.includes("kukufm.com") && url.pathname.includes("/show/");
        } catch (_) { return false; }
    }

    function pollStatus(taskId) {
        let currentProgress = 10; 
        updateProgressBar(currentProgress, 'Fetching show details...');

        pollingInterval = setInterval(async () => {
            if (!currentTaskId || taskId !== currentTaskId) { clearInterval(pollingInterval); return; }
            try {
                const response = await fetch(`/status/${taskId}`);
                if (!response.ok) throw new Error(`Server status check error: ${response.status}`);
                const statusResult = await response.json();
                const showTitle = statusResult.show_title || 'Show';
                let overallMessage = statusResult.message || `Processing '${showTitle}'...`;
                
                // Clear previous *individual episode* log entries before adding new ones for this poll cycle
                // This prevents the episode log from growing indefinitely with old updates from previous polls.
                // We only want to show the latest batch of episode updates.
                const existingEpisodeUpdates = statusMessagesDiv.querySelectorAll('.episode-update-item');
                existingEpisodeUpdates.forEach(el => el.remove());

                if (statusResult.episode_updates && statusResult.episode_updates.length > 0) {
                    statusResult.episode_updates.forEach(epUpdate => { // Log all updates from this poll
                        addMessageToLog(
                            `Ep. ${epUpdate.processed_count}/${epUpdate.total_episodes} - ${epUpdate.title}: ${epUpdate.status_message}`, 
                            epUpdate.success ? 'info' : 'warning',
                            false, // Not an initial message for the whole task
                            true // Mark as an episode update item
                        );
                    });
                    // Update overall progress based on the latest counts from the batch
                    const latestEpUpdate = statusResult.episode_updates[statusResult.episode_updates.length - 1];
                    if (latestEpUpdate.total_episodes > 0) {
                        currentProgress = Math.floor((latestEpUpdate.processed_count / latestEpUpdate.total_episodes) * 100);
                        overallMessage = `Processing '${showTitle}': Ep ${latestEpUpdate.processed_count} of ${latestEpUpdate.total_episodes}`;
                    }
                } else if (statusResult.processed_count && statusResult.total_episodes) {
                     currentProgress = Math.floor((statusResult.processed_count / statusResult.total_episodes) * 100);
                     overallMessage = `Processing '${showTitle}': ${statusResult.processed_count} of ${statusResult.total_episodes}`;
                } else if (statusResult.status === 'processing' || statusResult.status === 'processing_queued') {
                    currentProgress = Math.min(currentProgress + 5, 90); 
                } else if (statusResult.status === 'complete' || statusResult.status === 'error') {
                    currentProgress = 100;
                }
                updateProgressBar(currentProgress, overallMessage);
                // The overall status message is now part of the progress bar text.
                // updateLatestStatusLogEntry(`[${new Date().toLocaleTimeString()}] '${showTitle}': ${statusResult.message}`, statusResult.status);

                if (statusResult.status === 'complete') {
                    clearInterval(pollingInterval);
                    addMessageToLog(`✅ Download & zipping complete for '${showTitle}'! Links below.`, 'success');
                    displayExpiryWarning(); // Display expiry warning
                    if (statusResult.zip_filename) {
                        displayDownloadLinkComponent(taskId, "zip", statusResult.zip_filename, `Download ${showTitle} ZIP`);
                    }
                    // Metadata link removed
                    setSubmitButtonState(false, 'Initiate Download', false);
                    hideProgressBarAfterDelay(2500);
                } else if (statusResult.status === 'error' || statusResult.status === 'not_found') {
                    clearInterval(pollingInterval);
                    addMessageToLog(`❌ Error for '${showTitle}': ${statusResult.message}`, statusResult.status === 'not_found' ? 'warning' : 'error');
                    setSubmitButtonState(false, 'Initiate Download', false);
                    hideProgressBarAfterDelay(statusResult.status === 'not_found' ? 0 : 2500);
                }
            } catch (error) {
                addMessageToLog(`Error polling status for task ${taskId}: ${error.message}`, 'error');
                clearInterval(pollingInterval);
                setSubmitButtonState(false, 'Initiate Download', false);
                hideProgressBarAfterDelay();
            }
        }, 3000);
    }

    function displayDownloadLinkComponent(taskId, fileType, filename, linkText) {
        const downloadLink = document.createElement('a');
        downloadLink.href = `/fetch_zip/${encodeURIComponent(filename)}`; // Only fetch_zip now
        downloadLink.textContent = linkText;
        downloadLink.classList.add('download-link-button'); 
        downloadLink.setAttribute('download', filename); 
        
        const pContainer = document.createElement('p');
        pContainer.classList.add('download-links-container'); // Add class for styling
        pContainer.appendChild(downloadLink);
        
        // Prepend download links container to the status messages div
        if (statusMessagesDiv.firstChild) {
            statusMessagesDiv.insertBefore(pContainer, statusMessagesDiv.firstChild);
        } else {
            statusMessagesDiv.appendChild(pContainer);
        }
    }

    function displayExpiryWarning() {
        const warningP = document.createElement('p');
        warningP.className = 'status-message-item status-warning file-expiry-warning'; // Add specific class
        warningP.innerHTML = `<strong>IMPORTANT:</strong> Download links are temporary and will expire in approximately <strong>5 minutes</strong>. Please download your files promptly!`;
        
        // Prepend warning to the status messages div so it's at the top
        if (statusMessagesDiv.firstChild) {
            statusMessagesDiv.insertBefore(warningP, statusMessagesDiv.firstChild);
        } else {
            statusMessagesDiv.appendChild(warningP);
        }
    }


    function setSubmitButtonState(disabled, text, isProcessing = false) {
        if (!submitButton) return;
        submitButton.disabled = disabled;
        const btnTextSpan = submitButton.querySelector('.btn-text');
        const btnIconSpan = submitButton.querySelector('.btn-icon');
        if (btnTextSpan) btnTextSpan.textContent = text;
        else submitButton.childNodes[submitButton.childNodes.length -1].nodeValue = ` ${text}`;
        if (isProcessing) { if(btnIconSpan) btnIconSpan.innerHTML = '⏳'; submitButton.classList.add('processing'); }
        else { if(btnIconSpan) btnIconSpan.innerHTML = '🚀'; submitButton.classList.remove('processing'); }
    }
        
    function addMessageToLog(message, type = 'info', isInitialMsgForTask = false, isEpisodeUpdate = false) {
        if (isInitialMsgForTask) { 
            clearStatusLogAndPlaceholder();
        }
        const placeholder = statusMessagesDiv.querySelector('.status-placeholder.initial-placeholder');
        if (placeholder) placeholder.remove(); 

        const p = document.createElement('p');
        p.innerHTML = message; // Use innerHTML to allow simple formatting like <strong>
        p.className = `status-message-item status-${type}`;
        if (isEpisodeUpdate) {
            p.classList.add('episode-update-item');
        }
        
        // Insert new messages at the top, but after any existing download links or expiry warnings
        const firstDownloadLinkContainer = statusMessagesDiv.querySelector('p.download-links-container');
        const firstExpiryWarning = statusMessagesDiv.querySelector('p.file-expiry-warning');
        let insertBeforeElement = firstDownloadLinkContainer || firstExpiryWarning || statusMessagesDiv.firstChild;

        statusMessagesDiv.insertBefore(p, insertBeforeElement); 
        if (!isEpisodeUpdate) { // Only scroll for general messages, not every episode update to avoid jumpiness
            statusMessagesDiv.scrollTop = 0; 
        }
    }

    function clearStatusLogAndPlaceholder() {
        statusMessagesDiv.innerHTML = ''; 
    }
    
    function showDownloadProcessAreaIfNeeded() {
        if (downloadProcessDisplay && downloadProcessDisplay.classList.contains('hidden')) {
            downloadProcessDisplay.classList.remove('hidden');
            // Ensure the placeholder is there if the log is empty
            if (statusMessagesDiv.children.length === 0) {
                const placeholderDiv = document.createElement('div');
                placeholderDiv.classList.add('status-placeholder', 'initial-placeholder'); 
                placeholderDiv.innerHTML = `<span class="placeholder-icon">📡</span><p>Status updates will appear here once download begins.</p>`;
                statusMessagesDiv.appendChild(placeholderDiv);
            }
        }
    }

    function showProgressBar(initialPercentage = 0, message = 'Processing...') {
        if (!progressContainer || !progressBar || !progressText) return;
        progressText.textContent = message;
        progressBar.style.width = `${initialPercentage}%`; 
        progressContainer.classList.remove('hidden'); 
        progressBar.classList.remove('indeterminate'); 
        if (initialPercentage === 0 && (message.toLowerCase().includes('connecting') || message.toLowerCase().includes('queued') || message.toLowerCase().includes('awaiting'))) { 
            progressBar.classList.add('indeterminate');
        }
    }

    function updateProgressBar(percentage, message) {
        if (!progressContainer || !progressBar || !progressText) return;
        if (progressContainer.classList.contains('hidden')) progressContainer.classList.remove('hidden');
        
        const clampedPercentage = Math.max(0, Math.min(100, percentage));
        progressBar.style.width = `${clampedPercentage}%`;
        progressText.textContent = message || `Progress: ${clampedPercentage}%`;
        
        if (clampedPercentage > 0 && clampedPercentage < 100) progressBar.classList.remove('indeterminate');
        else if (clampedPercentage === 0 && !progressBar.classList.contains('indeterminate')) progressBar.classList.add('indeterminate'); 
        else if (clampedPercentage >= 100) { progressBar.style.width = '100%'; progressBar.classList.remove('indeterminate');}
    }

    function hideProgressBar() {
        if (!progressContainer) return;
        progressContainer.classList.add('hidden');
        if(progressBar) progressBar.style.width = '0%';
        if(progressText) progressText.textContent = '';
        if(progressBar) progressBar.classList.remove('indeterminate');
    }
    function hideProgressBarAfterDelay(delay = 2000) { setTimeout(hideProgressBar, delay); }

});
