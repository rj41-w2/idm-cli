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
    chrome.runtime.sendNativeMessage('com.idm.cli', { action: "download", url: url }, (response) => {
      if (chrome.runtime.lastError) {
        console.error("Error sending native message:", chrome.runtime.lastError);
      } else {
        console.log("Response from native host:", response);
      }
    });
  }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "fetch_qualities") {
    chrome.runtime.sendNativeMessage('com.idm.cli', request, (response) => {
      sendResponse(response);
    });
    return true; // Keep channel open
  } else if (request.action === "download") {
    chrome.runtime.sendNativeMessage('com.idm.cli', request, (response) => {
      sendResponse(response);
    });
    return true;
  }
});
