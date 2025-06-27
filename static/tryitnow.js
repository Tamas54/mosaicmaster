document.addEventListener("DOMContentLoaded", function() {
  console.log("tryitnow.js loaded");
  
  // Globális file méret formázó függvény
  function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
  
  // Változók
  let currentFile = null;
  let currentMode = 'translator';
  let connectionId = "";
  
  // Elemek lekérése
  const translatorModeBtn = document.getElementById('translatorModeBtnFunc');
  const videoModeBtn = document.getElementById('videoModeBtnFunc');
  const transcribeModeBtn = document.getElementById('transcribeModeBtnFunc');
  const converterModeBtn = document.getElementById('converterModeBtnFunc');
  
  const dropZone = document.getElementById('functionalDropZone');
  const fileInfo = document.getElementById('functionalFileInfo');
  const progressSection = document.getElementById('functionalProgressSection');
  const progressBar = document.getElementById('functionalProgressBar');
  const statusText = document.getElementById('functionalStatusText');
  const actionBtn = document.getElementById('functionalActionBtn');
  const redDownloadBtn = document.getElementById('redDownloadBtn');
  const downloadButtons = document.getElementById('downloadButtons');
  
  const languageSelectContainer = document.getElementById('languageSelectContainer');
  const formatSelectContainer = document.getElementById('formatSelectContainer');
  const transcribeOptionsSection = document.getElementById('transcribeOptionsSection');
  const startMicBtn = document.getElementById('startMicBtn');
  
  // Mikrofon engedélyezése
  startMicBtn.addEventListener('click', async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      alert("Mikrofon engedélyezve! (A valódi live funkcióhoz backend/WebRTC megoldás szükséges.)");
    } catch (err) {
      alert("Mikrofon-hozzáférés sikertelen: " + err.message);
    }
  });
  
  // Módváltó függvény
  function updateUI(mode) {
    currentMode = mode;
  
    // Rejtjük az extra elemeket
    document.getElementById('videoSourceOptions').classList.add('hidden');
    document.getElementById('videoOptions').classList.add('hidden');
    document.getElementById('videoLocalUpload') && document.getElementById('videoLocalUpload').classList.add('hidden');
    document.getElementById('functionalSelectSection').classList.add('hidden');
    transcribeOptionsSection.classList.add('hidden');
    dropZone.classList.remove('dragover');
  
    // Frissítjük a gombok stílusát
    translatorModeBtn.className = (mode === 'translator') 
      ? 'mode-switch active px-6 py-3 rounded-xl bg-blue-500 text-white flex items-center gap-2'
      : 'mode-switch px-6 py-3 rounded-xl bg-gray-200 text-gray-600 flex items-center gap-2 hover:bg-gray-300';
    videoModeBtn.className = (mode === 'video')
      ? 'mode-switch active px-6 py-3 rounded-xl bg-red-500 text-white flex items-center gap-2'
      : 'mode-switch px-6 py-3 rounded-xl bg-gray-200 text-gray-600 flex items-center gap-2 hover:bg-gray-300';
    transcribeModeBtn.className = (mode === 'transcribe')
      ? 'mode-switch active px-6 py-3 rounded-xl bg-purple-500 text-white flex items-center gap-2'
      : 'mode-switch px-6 py-3 rounded-xl bg-gray-200 text-gray-600 flex items-center gap-2 hover:bg-gray-300';
    converterModeBtn.className = (mode === 'converter')
      ? 'mode-switch active px-6 py-3 rounded-xl bg-green-500 text-white flex items-center gap-2'
      : 'mode-switch px-6 py-3 rounded-xl bg-gray-200 text-gray-600 flex items-center gap-2 hover:bg-gray-300';
  
    // Töröljük a korábbi file információkat
    currentFile = null;
    fileInfo.classList.add('hidden');
    downloadButtons.innerHTML = '';
    downloadButtons.classList.add('hidden');
    redDownloadBtn.classList.add('hidden');
  
    if (mode === 'translator') {
      dropZone.innerHTML = `
        <input type="file" id="functionalFileInput" class="hidden" accept=".pdf,.docx,.doc,.odt,.txt,.rtf,.ppt,.pptx,.epub,.srt,.mobi,.sub">
        <div>
          <i data-lucide="upload-cloud" class="w-16 h-16 mx-auto text-blue-500 mb-4 opacity-80"></i>
          <p class="text-lg font-medium text-gray-700">Drag file here or click to upload</p>
          <p class="text-sm text-gray-500 mt-2">Supported: PDF, DOCX, DOC, ODT, TXT, RTF, PPT, PPTX, EPUB, SRT, MOBI, SUB</p>
        </div>`;
      document.getElementById('functionalSelectSection').classList.remove('hidden');
      languageSelectContainer.style.display = 'block';
      formatSelectContainer.style.display = 'block';
    } else if (mode === 'video') {
      dropZone.innerHTML = `
        <input type="file" id="functionalFileInput" class="hidden">
        <div>
          <i data-lucide="upload-cloud" class="w-16 h-16 mx-auto text-red-500 mb-4 opacity-80"></i>
          <p class="text-lg font-medium text-gray-700">[Video mode: see options below]</p>
        </div>`;
      document.getElementById('videoSourceOptions').classList.remove('hidden');
      const sourceType = document.querySelector('input[name="videoSource"]:checked').value;
      if (sourceType === 'url') {
        document.getElementById('videoOptions').classList.remove('hidden');
        document.getElementById('videoLocalUpload') && document.getElementById('videoLocalUpload').classList.add('hidden');
      } else {
        document.getElementById('videoOptions').classList.remove('hidden');
        document.getElementById('videoLocalUpload') && document.getElementById('videoLocalUpload').classList.remove('hidden');
      }
    } else if (mode === 'transcribe') {
      dropZone.innerHTML = `
        <input type="file" id="functionalFileInput" class="hidden" accept=".mp3,.wav,.ogg,.m4a">
        <div>
          <i data-lucide="mic" class="w-16 h-16 mx-auto text-purple-500 mb-4 opacity-80"></i>
          <p class="text-lg font-medium text-gray-700">Drag audio file here or click to upload</p>
          <p class="text-sm text-gray-500 mt-2">Supported: MP3, WAV, OGG, M4A</p>
        </div>`;
      transcribeOptionsSection.classList.remove('hidden');
      checkTranscribeMode();
    } else if (mode === 'converter') {
      dropZone.innerHTML = `
        <input type="file" id="functionalFileInput" class="hidden" accept=".pdf,.doc,.docx,.odt,.txt,.rtf,.ppt,.pptx,.epub,.srt,.mobi,.sub,.jpg,.jpeg,.png,.gif">
        <div>
          <i data-lucide="upload-cloud" class="w-16 h-16 mx-auto text-green-500 mb-4 opacity-80"></i>
          <p class="text-lg font-medium text-gray-700">Drag file or image here or click to upload</p>
          <p class="text-sm text-gray-500 mt-2">Supported: PDF, DOC, DOCX, ODT, TXT, RTF, PPT, PPTX, EPUB, SRT, MOBI, SUB, JPG, JPEG, PNG, GIF</p>
        </div>`;
      document.getElementById('functionalSelectSection').classList.remove('hidden');
      // Converter módban nincs nyelvválasztó
      languageSelectContainer.style.display = 'none';
      formatSelectContainer.style.display = 'block';
    }
  
    const fInput = document.getElementById('functionalFileInput');
    if (fInput) {
      fInput.value = '';
    }
    lucide.createIcons();
    attachFileInputListener();
  }
  
  function checkTranscribeMode() {
    const modeVal = document.getElementById('transcribeModeSelect').value;
    if (modeVal === 'live_transcription' || modeVal === 'live_translation') {
      startMicBtn.style.display = 'flex';
    } else {
      startMicBtn.style.display = 'none';
    }
  }
  document.getElementById('transcribeModeSelect').addEventListener('change', checkTranscribeMode);
  
  function attachFileInputListener() {
    const fileInput = document.getElementById('functionalFileInput');
    if (fileInput) {
      fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
          handleFile(e.target.files[0]);
        }
      });
    }
  }
  
  function handleFile(file) {
    currentFile = file;
    document.getElementById('functionalFileName').textContent = file.name;
    document.getElementById('functionalFileSize').textContent = formatFileSize(file.size);
    document.getElementById('functionalFileInfo').classList.remove('hidden');
  }
  
  // Drop zone események
  dropZone.addEventListener('click', () => {
    const fInput = document.getElementById('functionalFileInput');
    if (fInput) fInput.click();
  });
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });
  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
  });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  });
  
  document.getElementById('functionalRemoveFile').addEventListener('click', () => {
    currentFile = null;
    document.getElementById('functionalFileInfo').classList.add('hidden');
    const fInput = document.getElementById('functionalFileInput');
    if (fInput) fInput.value = '';
    const fInputLocal = document.getElementById('functionalFileInputLocal');
    if (fInputLocal) fInputLocal.value = '';
  });
  
  // Video source radio gombok
  document.getElementById('videoSourceURL').addEventListener('change', () => {
    document.getElementById('videoOptions').classList.remove('hidden');
    document.getElementById('videoLocalUpload').classList.add('hidden');
  });
  document.getElementById('videoSourceLocal').addEventListener('change', () => {
    document.getElementById('videoOptions').classList.remove('hidden');
    document.getElementById('videoLocalUpload').classList.remove('hidden');
  });
  
  // Subtitle checkbox
  document.getElementById('videoGenerateSubtitles').addEventListener('change', (e) => {
    if (e.target.checked) {
      document.getElementById('videoSubtitleFormatSection').classList.remove('hidden');
    } else {
      document.getElementById('videoSubtitleFormatSection').classList.add('hidden');
    }
  });
  
  function startProgressWebSocket(connId) {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${connId}`);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      progressBar.style.width = data.progress + "%";
      statusText.textContent = data.status;
    };
    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };
  }
  
  function createDownloadButtons(result) {
    let html = "";
    if (currentMode === 'translator') {
      if (result.download_url) {
        html += `<button onclick="window.open('${result.download_url}', '_blank')" class="bg-blue-500 text-white px-4 py-2 rounded mr-2">Download Translated File</button>`;
      }
      if (result.transcript_download_url) {
        html += `<button onclick="window.open('${result.transcript_download_url}', '_blank')" class="bg-blue-500 text-white px-4 py-2 rounded">Download Transcript</button>`;
      }
    } else if (currentMode === 'converter') {
      if (result.download_url) {
        html += `<button onclick="window.open('${result.download_url}', '_blank')" class="bg-green-500 text-white px-4 py-2 rounded">Download Converted File</button>`;
      }
    } else if (currentMode === 'transcribe') {
      if (result.transcription_text) {
        const blob = new Blob([result.transcription_text], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        html += `<button onclick="window.open('${url}', '_blank')" class="bg-purple-500 text-white px-4 py-2 rounded">Download Transcription</button>`;
      }
    } else if (currentMode === 'video') {
      if (result.download_urls) {
        if (result.download_urls.video_mp4) {
          html += `<button onclick="window.open('${result.download_urls.video_mp4}', '_blank')" class="bg-red-500 text-white px-4 py-2 rounded mr-2 mb-2">Download Video (MP4)</button>`;
        }
        for (const key in result.download_urls) {
          if (key !== "video_mp4") {
            let btnText = "";
            if (key.includes("audio")) {
              btnText = "Download Audio (MP3)";
            } else if (key.includes("subtitles")) {
              btnText = "Download Subtitles";
            } else {
              btnText = "Download";
            }
            html += `<button onclick="window.open('${result.download_urls[key]}', '_blank')" class="bg-red-500 text-white px-4 py-2 rounded mr-2 mb-2">${btnText}</button>`;
          }
        }
      }
    }
    downloadButtons.innerHTML = html;
    downloadButtons.classList.remove('hidden');
  }
  
  actionBtn.addEventListener('click', async () => {
    let formData = new FormData();
    connectionId = crypto.randomUUID();
    formData.append("connection_id", connectionId);
    startProgressWebSocket(connectionId);
  
    let endpoint = "";
    if (currentMode === "translator" || currentMode === "converter" || currentMode === "transcribe") {
      if (!currentFile) {
        alert("Please upload a file first!");
        return;
      }
      formData.append("file", currentFile);
  
      if (currentMode === "translator") {
        const lang = document.getElementById('functionalTargetLang').value;
        if (!lang) {
          alert("Please select a target language!");
          return;
        }
        formData.append("target_lang", lang);
        formData.append("target_format", document.getElementById('functionalTargetFormat').value || "pdf");
        endpoint = "/api/translate";
      } else if (currentMode === "converter") {
        const convFormat = document.getElementById('functionalTargetFormat').value;
        if (!convFormat) {
          alert("Please select a target format!");
          return;
        }
        formData.append("target_format", convFormat);
        endpoint = "/api/convert";
      } else if (currentMode === "transcribe") {
        const modeSelect = document.getElementById('transcribeModeSelect').value;
        formData.append("transcribe_mode", modeSelect);
        endpoint = "/api/transcribe";
      }
    } else if (currentMode === "video") {
      const sourceType = document.querySelector('input[name="videoSource"]:checked').value;
      if (sourceType === "url") {
        const videoURL = document.getElementById('videoURLInput').value.trim();
        if (!videoURL) {
          alert("Please enter a video URL!");
          return;
        }
        formData.append("url", videoURL);
      } else if (sourceType === "local") {
        if (!currentFile) {
          alert("Please upload a local video file!");
          return;
        }
        formData.append("file", currentFile);
      }
      formData.append("platform", document.getElementById('videoPlatform').value);
      formData.append("convert_mp3", document.getElementById('videoConvertMP3').checked);
      formData.append("generate_subtitles", document.getElementById('videoGenerateSubtitles').checked);
      formData.append("subtitle_format", document.getElementById('videoSubtitleFormat').value || "srt");
      formData.append("target_video_format", document.getElementById('targetVideoFormat').value);
      formData.append("resolution", document.getElementById('videoResolution').value);
      formData.append("bitrate", document.getElementById('videoBitrate').value);
      endpoint = "/api/video";
    }
  
    actionBtn.disabled = true;
    progressSection.classList.remove("hidden");
    progressBar.style.width = "0%";
    statusText.textContent = "";
  
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const result = await response.json();
      progressBar.style.width = "100%";
      if (currentMode === "translator") {
        statusText.textContent = "Translation complete!";
      } else if (currentMode === "converter") {
        statusText.textContent = "Conversion complete!";
      } else if (currentMode === "transcribe") {
        statusText.textContent = "Transcription complete!";
      } else if (currentMode === "video") {
        statusText.textContent = "Video processing complete!";
      }
      createDownloadButtons(result);
  
      if (currentMode === 'translator' || currentMode === 'converter') {
        if (result.download_url) {
          redDownloadBtn.onclick = () => window.open(result.download_url, '_blank');
          redDownloadBtn.classList.remove('hidden');
        }
      } else if (currentMode === 'transcribe') {
        if (result.transcription_text) {
          const blob = new Blob([result.transcription_text], { type: "text/plain" });
          const url = URL.createObjectURL(blob);
          redDownloadBtn.onclick = () => window.open(url, '_blank');
          redDownloadBtn.classList.remove('hidden');
        }
      } else if (currentMode === 'video') {
        if (result.download_urls && result.download_urls.video_mp4) {
          redDownloadBtn.onclick = () => window.open(result.download_urls.video_mp4, '_blank');
          redDownloadBtn.classList.remove('hidden');
        }
      }
    } catch (err) {
      alert(err.message);
      progressBar.classList.add("bg-red-500");
    } finally {
      actionBtn.disabled = false;
    }
  });
  
  // Mód gomb események
  translatorModeBtn.addEventListener('click', () => updateUI('translator'));
  videoModeBtn.addEventListener('click', () => updateUI('video'));
  transcribeModeBtn.addEventListener('click', () => updateUI('transcribe'));
  converterModeBtn.addEventListener('click', () => updateUI('converter'));
  
  // Alapértelmezett mód
  updateUI('translator');
});

