"use strict";
// A deadline releases the queue; it does not imply that a send did not happen.
// The durable permit journal remains the authority for uncertain submissions.
function companionMessage(tab, message, options) {
  const ms = message.type === 'project:send' ? 180000 :
    message.type === 'project:ready' ? 1500 : message.type === 'project:ad-blob' ? 25000 : 8000;
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('Companion page response timed out; checking the saved checkpoint.')), ms);
  });
  return Promise.race([Promise.resolve().then(() => chrome.tabs.sendMessage(tab, message, options)), deadline])
    .finally(() => clearTimeout(timer));
}
