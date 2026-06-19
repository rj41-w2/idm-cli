document.getElementById('downloadBtn').addEventListener('click', () => {
  chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
    const url = tabs[0].url;
    chrome.runtime.sendMessage({action: "download_url", url: url}, (response) => {
      window.close();
    });
  });
});
