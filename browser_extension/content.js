function addDownloadButton(videoElement) {
    if (videoElement.dataset.idmCliAdded) return;
    videoElement.dataset.idmCliAdded = "true";

    const container = document.createElement('div');
    container.className = 'idm-cli-container';
    
    const btn = document.createElement('button');
    btn.className = 'idm-cli-overlay';
    btn.textContent = 'Download with IDM';

    const dropdown = document.createElement('div');
    dropdown.className = 'idm-cli-overlay-dropdown';
    
    btn.appendChild(dropdown);
    container.appendChild(btn);
    document.body.appendChild(container);

    const reposition = () => {
        const r = videoElement.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) {
            container.style.display = 'none';
        } else {
            container.style.display = 'block';
            container.style.top = (r.top + window.scrollY + 10) + 'px';
            container.style.left = (r.right + window.scrollX - btn.offsetWidth - 10) + 'px';
        }
    };
    
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition);
    setInterval(reposition, 1000);

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        
        if (btn.classList.contains('show-dropdown')) {
            btn.classList.remove('show-dropdown');
            return;
        }

        if (dropdown.children.length > 0) {
            btn.classList.add('show-dropdown');
            return;
        }

        const originalText = btn.firstChild.textContent;
        btn.firstChild.textContent = 'Loading...';
        
        chrome.runtime.sendMessage({ action: "fetch_qualities", url: window.location.href }, (response) => {
            btn.firstChild.textContent = originalText;
            
            if (chrome.runtime.lastError || !response || response.status === 'error' || !response.qualities || response.qualities.length === 0) {
                chrome.runtime.sendMessage({ action: "download", url: window.location.href });
                return;
            }

            dropdown.innerHTML = '';
            response.qualities.forEach(q => {
                const item = document.createElement('div');
                item.className = 'idm-cli-quality-item';
                item.textContent = q;
                item.addEventListener('click', (ev) => {
                    ev.stopPropagation();
                    btn.classList.remove('show-dropdown');
                    chrome.runtime.sendMessage({ action: "download", url: window.location.href, quality: q });
                });
                dropdown.appendChild(item);
            });
            
            btn.classList.add('show-dropdown');
        });
    });

    document.addEventListener('click', () => {
        btn.classList.remove('show-dropdown');
    });
    
    // Initial position
    reposition();

    const showContainer = () => container.classList.add('visible');
    const hideContainer = () => {
        if (!container.matches(':hover')) {
            container.classList.remove('visible');
            btn.classList.remove('show-dropdown'); // Also close dropdown
        }
    };

    videoElement.addEventListener('mouseenter', showContainer);
    videoElement.addEventListener('mouseleave', () => setTimeout(hideContainer, 100));
    container.addEventListener('mouseleave', hideContainer);
}

const observer = new MutationObserver(() => {
    document.querySelectorAll('video').forEach(addDownloadButton);
});

observer.observe(document.body, { childList: true, subtree: true });

document.querySelectorAll('video').forEach(addDownloadButton);
