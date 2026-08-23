chrome.runtime.onMessage.addListener((message, _sender, respond) => {
  if (message?.type === "zhihu_tab_ready") respond({ ready: true, url: location.href });
});
