const button = document.getElementById("read");
const status = document.getElementById("status");
button.addEventListener("click", async () => {
  button.disabled = true;
  status.textContent = "Reading the tab you selected…";
  try {
    const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
    if (!tab?.id) throw new Error("Select your Facebook dashboard tab first.");
    await chrome.scripting.executeScript({target:{tabId:tab.id},files:["capture.js"]});
    const [result] = await chrome.scripting.executeScript({target:{tabId:tab.id},func:() => captureFacebook()});
    if (!result?.result) throw new Error("The page could not be read.");
    const response = await chrome.runtime.sendNativeMessage("com.macooii.browser",result.result);
    if (!response?.ok) throw new Error(response?.message || "Macooii could not receive the capture.");
    status.textContent = response.message;
  } catch (error) {
    status.textContent = "Could not send the capture. " + error.message + " If the native host is missing, run Install Browser Bridge.cmd from the Macooii folder.";
  } finally { button.disabled = false; }
});
