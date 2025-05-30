// static/js/script.js
document.addEventListener('DOMContentLoaded', function() {
    // --- DOM Element Selections ---
    const downloadForm = document.getElementById('downloadForm');
    const statusMessagesDiv = document.getElementById('statusMessages');
    const kukuUrlInput = document.getElementById('kuku_url');
    const submitButton = document.getElementById('submitDownloadBtn');
    
    const downloadProcessDisplay = document.getElementById('downloadProcessDisplay');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');

    const navLinks = document.querySelectorAll('.main-nav a');
    const contentSections = document.querySelectorAll('.content-section');
    const mainHeaderTitleElement = document.getElementById('mainHeaderTitle');
    const mainHeaderSubtitleElement = document.querySelector('.main-header .subtitle');
    const sidebar = document.querySelector('.sidebar');
    const contentArea = document.querySelector('.content-area');
    const sidebarToggleBtn = document.getElementById('sidebarToggleBtn'); 
    const themeToggleBtn = document.getElementById('themeToggleBtn');

    let pollingInterval = null;
    let currentTaskId = null; 

    loadInitialSettings();
    setupEventListeners();

    function loadInitialSettings() {
        const lastUrl = localStorage.getItem('kukuHarvesterLastUrl');
        if (lastUrl) kukuUrlInput.value = lastUrl;
        const savedTheme = localStorage.getItem('kukuHarvesterTheme') || 'dark';
        applyTheme(savedTheme);
        const currentHash = window.location.hash || '#downloader-section';
        activateSection(currentHash.substring(1));
        if (window.innerWidth > 768) {
            const isSidebarCollapsed = localStorage.getItem('kukuHarvesterSidebarDesktop') === 'collapsed';
            if (isSidebarCollapsed) {
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
        window.addEventListener('hashchange', () => {
            const currentHash = window.location.hash || '#downloader-section';
            activateSection(currentHash.substring(1));
        });
        window.addEventListener('resize', updateSidebarToggleButton);
    }

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
                    if (targetId === 'downloader-section') mainHeaderSubtitleElement.textContent = "Download your favorite shows with ease 🚀";
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
                body: JSON.stringify({ kuku_url: kukuUrl }), 
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
                
                if (statusResult.episode_updates && statusResult.episode_updates.length > 0) {
                    const latestEpUpdate = statusResult.episode_updates[statusResult.episode_updates.length - 1];
                    addMessageToLog( // Add each new episode update to the log
                        `Ep. ${latestEpUpdate.processed_count}/${latestEpUpdate.total_episodes} - ${latestEpUpdate.title}: ${latestEpUpdate.status_message}`, 
                        latestEpUpdate.success ? 'info' : 'warning' 
                    );
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

                if (statusResult.status === 'complete') {
                    clearInterval(pollingInterval);
                    // Final completion message is added after download links
                    if (statusResult.zip_filename) {
                        displayDownloadLinkComponent(taskId, "zip", statusResult.zip_filename, `Download ${showTitle} ZIP`);
                    }
                    // Metadata link removed
                    addMessageToLog(`✅ Download & zipping complete for '${showTitle}'! Links above.`, 'success');
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
        downloadLink.href = `/fetch_file/${fileType}/${encodeURIComponent(filename)}`;
        downloadLink.textContent = linkText;
        downloadLink.classList.add('download-link-button'); 
        downloadLink.setAttribute('download', filename); 
        
        const pContainer = document.createElement('p');
        pContainer.style.textAlign = 'center'; 
        pContainer.appendChild(downloadLink);
        // Insert the download link container at the TOP of the statusMessagesDiv
        if (statusMessagesDiv.firstChild) {
            statusMessagesDiv.insertBefore(pContainer, statusMessagesDiv.firstChild);
        } else {
            statusMessagesDiv.appendChild(pContainer);
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
        
    function addMessageToLog(message, type = 'info', isInitialMsgForTask = false) {
        if (isInitialMsgForTask) { 
            clearStatusLogAndPlaceholder();
        }
        const placeholder = statusMessagesDiv.querySelector('.status-placeholder.initial-placeholder');
        if (placeholder) placeholder.remove(); 

        const p = document.createElement('p');
        p.innerHTML = message; 
        p.className = `status-message-item status-${type}`;
        statusMessagesDiv.insertBefore(p, statusMessagesDiv.firstChild); 
        statusMessagesDiv.scrollTop = 0; 
    }

    function clearStatusLogAndPlaceholder() {
        statusMessagesDiv.innerHTML = ''; 
    }
    
    function showDownloadProcessAreaIfNeeded() {
        if (downloadProcessDisplay && downloadProcessDisplay.classList.contains('hidden')) {
            downloadProcessDisplay.classList.remove('hidden');
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
