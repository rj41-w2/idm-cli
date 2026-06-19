const INTERCEPT_EXTENSIONS = ['3gp','7z','aac','ace','aif','arj','asf','avi','bin','bz2','exe','gz','gzip','img','iso','lzh','m4a','m4v','mkv','mov','mp3','mp4','mpa','mpe','mpeg','mpg','msi','msu','ogg','ogv','pdf','plj','pps','ppt','qt','rar','rm','rmvb','sea','sit','sitx','tar','tif','tiff','wav','wma','wmv','z','zip'];

chrome.downloads.onDeterminingFilename.addListener((downloadItem, suggest) => {
    if (downloadItem.url.startsWith('data:') || downloadItem.url.startsWith('blob:')) {
        return;
    }

    const filename = (downloadItem.filename || "").toLowerCase();
    let urlPath = "";
    try {
        urlPath = new URL(downloadItem.url).pathname.toLowerCase();
    } catch(e) {}

    const isMatch = INTERCEPT_EXTENSIONS.some(ext => filename.endsWith('.' + ext) || urlPath.endsWith('.' + ext));

    if (isMatch) {
        chrome.downloads.cancel(downloadItem.id, () => {
            let err = chrome.runtime.lastError; // Check silently to avoid unchecked error
            chrome.runtime.sendNativeMessage('com.idm.cli', { 
                action: "download", 
                url: downloadItem.finalUrl || downloadItem.url, 
                filename: downloadItem.filename 
            });
        });
    }
});

chrome.runtime.onInstalled.addListener(() => {
    chrome.contextMenus.create({
        id: "download_idm",
        title: "Download with IDM-CLI",
        contexts: ["link", "page", "video", "audio"]
    });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
    if (info.menuItemId === "download_idm") {
        const url = info.linkUrl || info.srcUrl || info.pageUrl;
        chrome.runtime.sendNativeMessage('com.idm.cli', { action: "download", url: url });
    }
});
