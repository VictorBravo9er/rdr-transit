import './style.css';
import QRCode from 'qrcode';
import { Html5Qrcode } from 'html5-qrcode';
import { registerSW } from 'virtual:pwa-register';
import { WebRTCManager, type ConnectionStatus, type ProgressInfo, type ReceivedFile } from './webrtc';
import { formatBytes, formatSpeed } from './protocol';

// Register Service Worker for instant offline & F5 reload without refetching assets from web
const updateSW = registerSW({
  onNeedRefresh() {
    showToast('New version available! Refreshing to update...', 'info');
    setTimeout(() => {
      updateSW(true);
    }, 1500);
  },
  onOfflineReady() {
    console.log('App ready for offline use and instantaneous cache reload.');
  },
});

// DOM Elements
const statusPill = document.getElementById('connection-status-pill') as HTMLDivElement;
const statusText = document.getElementById('connection-status-text') as HTMLSpanElement;
const btnDisconnect = document.getElementById('btn-disconnect') as HTMLButtonElement;
const viewPairing = document.getElementById('view-pairing') as HTMLElement;
const viewDashboard = document.getElementById('view-dashboard') as HTMLElement;

// Tabs for pairing
const tabBtnHost = document.getElementById('tab-btn-host') as HTMLButtonElement;
const tabBtnJoin = document.getElementById('tab-btn-join') as HTMLButtonElement;
const tabContentHost = document.getElementById('tab-content-host') as HTMLDivElement;
const tabContentJoin = document.getElementById('tab-content-join') as HTMLDivElement;

// Host controls
const hostInitialStep = document.getElementById('host-initial-step') as HTMLDivElement;
const hostQrStep = document.getElementById('host-qr-step') as HTMLDivElement;
const btnCreateOffer = document.getElementById('btn-create-offer') as HTMLButtonElement;
const hostQrCanvas = document.getElementById('host-qr-canvas') as HTMLCanvasElement;
const hostOfferTokenInput = document.getElementById('host-offer-token-input') as HTMLInputElement;
const btnCopyOfferToken = document.getElementById('btn-copy-offer-token') as HTMLButtonElement;
const hostAnswerInput = document.getElementById('host-answer-input') as HTMLInputElement;
const btnSubmitAnswer = document.getElementById('btn-submit-answer') as HTMLButtonElement;
const btnScanAnswerCamera = document.getElementById('btn-scan-answer-camera') as HTMLButtonElement;

// Join controls
const btnOpenScanner = document.getElementById('btn-open-scanner') as HTMLButtonElement;
const joinOfferInput = document.getElementById('join-offer-input') as HTMLTextAreaElement;
const btnProcessOffer = document.getElementById('btn-process-offer') as HTMLButtonElement;
const joinAnswerStep = document.getElementById('join-answer-step') as HTMLDivElement;
const joinQrCanvas = document.getElementById('join-qr-canvas') as HTMLCanvasElement;
const joinAnswerTokenInput = document.getElementById('join-answer-token-input') as HTMLInputElement;
const btnCopyAnswerToken = document.getElementById('btn-copy-answer-token') as HTMLButtonElement;

// Camera modal
const cameraModal = document.getElementById('camera-modal') as HTMLDivElement;
const btnCloseScanner = document.getElementById('btn-close-scanner') as HTMLButtonElement;
let html5QrCode: Html5Qrcode | null = null;
let scannerTarget: 'offer' | 'answer' = 'offer';

// Dashboard controls
const modeBtnFiles = document.getElementById('mode-btn-files') as HTMLButtonElement;
const modeBtnSnippet = document.getElementById('mode-btn-snippet') as HTMLButtonElement;
const panelSendFiles = document.getElementById('panel-send-files') as HTMLDivElement;
const panelSendSnippet = document.getElementById('panel-send-snippet') as HTMLDivElement;
const dropzone = document.getElementById('dropzone') as HTMLDivElement;
const fileInput = document.getElementById('file-input') as HTMLInputElement;
const stagedFilesContainer = document.getElementById('staged-files-container') as HTMLDivElement;
const stagedCountLabel = document.getElementById('staged-count-label') as HTMLSpanElement;
const btnClearStaged = document.getElementById('btn-clear-staged') as HTMLButtonElement;
const btnStartSend = document.getElementById('btn-start-send') as HTMLButtonElement;

// Transfer progress meter
const activeTransferPanel = document.getElementById('active-transfer-panel') as HTMLDivElement;
const transferDirectionLabel = document.getElementById('transfer-direction-label') as HTMLSpanElement;
const transferFilename = document.getElementById('transfer-filename') as HTMLSpanElement;
const btnCancelTransfer = document.getElementById('btn-cancel-transfer') as HTMLButtonElement;
const transferProgressBar = document.getElementById('transfer-progress-bar') as HTMLDivElement;
const transferBytesLabel = document.getElementById('transfer-bytes-label') as HTMLSpanElement;
const transferSpeedLabel = document.getElementById('transfer-speed-label') as HTMLSpanElement;
const transferPercentLabel = document.getElementById('transfer-percent-label') as HTMLSpanElement;

// Snippet controls
const snippetInput = document.getElementById('snippet-input') as HTMLTextAreaElement;
const btnPasteClipboard = document.getElementById('btn-paste-clipboard') as HTMLButtonElement;
const btnSendSnippet = document.getElementById('btn-send-snippet') as HTMLButtonElement;

// Received list
const receivedItemsList = document.getElementById('received-items-list') as HTMLDivElement;
const emptyReceivedPlaceholder = document.getElementById('empty-received-placeholder') as HTMLDivElement;
const receivedCountBadge = document.getElementById('received-count-badge') as HTMLSpanElement;
const btnClearHistory = document.getElementById('btn-clear-history') as HTMLButtonElement;
const toastContainer = document.getElementById('toast-container') as HTMLDivElement;

// State
let stagedFiles: File[] = [];
let receivedCount = 0;

// Initialize WebRTC Manager
const rtc = new WebRTCManager({
  onStatusChange: handleStatusChange,
  onSendProgress: handleSendProgress,
  onReceiveProgress: handleReceiveProgress,
  onFileReceived: handleFileReceived,
  onSnippetReceived: handleSnippetReceived,
  onError: (msg) => showToast(msg, 'error'),
});

function showToast(message: string, type: 'info' | 'success' | 'error' = 'info') {
  const toast = document.createElement('div');
  const colors = {
    info: 'bg-[#161b22] text-cyan-300 border-cyan-800/80',
    success: 'bg-[#161b22] text-emerald-300 border-emerald-800/80',
    error: 'bg-[#161b22] text-rose-300 border-rose-800/80',
  }[type];

  toast.className = `px-4 py-3 rounded-xl border text-xs font-medium shadow-2xl flex items-center gap-2 pointer-events-auto transform transition-all duration-200 translate-y-2 opacity-0 ${colors}`;
  const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
  toast.innerHTML = `<span class="font-bold">${icon}</span> <span>${message}</span>`;

  toastContainer.appendChild(toast);
  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-2', 'opacity-0');
  });

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 250);
  }, 4000);
}

function handleStatusChange(status: ConnectionStatus, message?: string) {
  if (status === 'connected') {
    statusPill.className = 'flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800';
    statusText.textContent = 'Connected (P2P)';
    btnDisconnect.classList.remove('hidden');

    viewPairing.classList.add('hidden');
    viewDashboard.classList.remove('hidden');

    showToast('Direct P2P Link Established!', 'success');
  } else if (status === 'connecting') {
    statusPill.className = 'flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-amber-950 text-amber-400 border border-amber-800';
    statusText.textContent = message || 'Connecting...';
  } else {
    statusPill.className = 'flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700';
    statusText.textContent = 'Disconnected';
    btnDisconnect.classList.add('hidden');

    viewPairing.classList.remove('hidden');
    viewDashboard.classList.add('hidden');
    activeTransferPanel.classList.add('hidden');
  }
}

// ----------------------------------------------------
// Pairing Handshake Flow
// ----------------------------------------------------

tabBtnHost.addEventListener('click', () => {
  tabBtnHost.className = 'flex-1 py-3 text-sm font-semibold text-cyan-400 border-b-2 border-cyan-400 bg-[#161b22] transition';
  tabBtnJoin.className = 'flex-1 py-3 text-sm font-semibold text-slate-400 hover:text-white border-b-2 border-transparent transition';
  tabContentHost.classList.remove('hidden');
  tabContentJoin.classList.add('hidden');
});

tabBtnJoin.addEventListener('click', () => {
  tabBtnJoin.className = 'flex-1 py-3 text-sm font-semibold text-emerald-400 border-b-2 border-emerald-400 bg-[#161b22] transition';
  tabBtnHost.className = 'flex-1 py-3 text-sm font-semibold text-slate-400 hover:text-white border-b-2 border-transparent transition';
  tabContentJoin.classList.remove('hidden');
  tabContentHost.classList.add('hidden');
});

btnCreateOffer.addEventListener('click', async () => {
  btnCreateOffer.disabled = true;
  btnCreateOffer.textContent = 'Generating...';

  try {
    const offerToken = await rtc.createOfferToken();
    hostInitialStep.classList.add('hidden');
    hostQrStep.classList.remove('hidden');

    hostOfferTokenInput.value = offerToken;
    await QRCode.toCanvas(hostQrCanvas, offerToken, {
      width: 240,
      margin: 2,
      color: { dark: '#000000', light: '#ffffff' },
    });
  } catch (err) {
    showToast(`Failed to create offer: ${err}`, 'error');
  } finally {
    btnCreateOffer.disabled = false;
    btnCreateOffer.textContent = 'Generate Pairing Code';
  }
});

btnCopyOfferToken.addEventListener('click', () => {
  navigator.clipboard.writeText(hostOfferTokenInput.value);
  showToast('Offer token copied to clipboard!', 'success');
});

btnSubmitAnswer.addEventListener('click', async () => {
  const token = hostAnswerInput.value.trim();
  if (!token) {
    showToast('Please enter the Answer token', 'error');
    return;
  }
  btnSubmitAnswer.disabled = true;
  try {
    await rtc.acceptAnswerToken(token);
  } catch (err) {
    showToast(`Failed to accept answer: ${err}`, 'error');
  } finally {
    btnSubmitAnswer.disabled = false;
  }
});

btnProcessOffer.addEventListener('click', async () => {
  const token = joinOfferInput.value.trim();
  if (!token) {
    showToast('Please paste the Host Offer token', 'error');
    return;
  }
  btnProcessOffer.disabled = true;
  btnProcessOffer.textContent = 'Connecting...';

  try {
    const answerToken = await rtc.acceptOfferAndCreateAnswerToken(token);
    joinAnswerStep.classList.remove('hidden');
    joinAnswerTokenInput.value = answerToken;

    await QRCode.toCanvas(joinQrCanvas, answerToken, {
      width: 240,
      margin: 2,
      color: { dark: '#000000', light: '#ffffff' },
    });
  } catch (err) {
    showToast(`Failed to process offer: ${err}`, 'error');
  } finally {
    btnProcessOffer.disabled = false;
    btnProcessOffer.textContent = 'Process Offer & Generate Answer';
  }
});

btnCopyAnswerToken.addEventListener('click', () => {
  navigator.clipboard.writeText(joinAnswerTokenInput.value);
  showToast('Answer token copied to clipboard!', 'success');
});

// Camera Scanner Handling
btnOpenScanner.addEventListener('click', () => {
  scannerTarget = 'offer';
  openCameraScanner();
});

btnScanAnswerCamera.addEventListener('click', () => {
  scannerTarget = 'answer';
  openCameraScanner();
});

btnCloseScanner.addEventListener('click', () => {
  closeCameraScanner();
});

async function openCameraScanner() {
  cameraModal.classList.remove('hidden');
  try {
    html5QrCode = new Html5Qrcode('camera-reader');
    await html5QrCode.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: { width: 250, height: 250 } },
      async (decodedText) => {
        closeCameraScanner();
        if (scannerTarget === 'offer') {
          joinOfferInput.value = decodedText;
          btnProcessOffer.click();
        } else if (scannerTarget === 'answer') {
          hostAnswerInput.value = decodedText;
          btnSubmitAnswer.click();
        }
      },
      () => {}
    );
  } catch (err) {
    console.error('Camera open error:', err);
    showToast(`Could not open camera: ${err}`, 'error');
    closeCameraScanner();
  }
}

async function closeCameraScanner() {
  if (html5QrCode) {
    try {
      await html5QrCode.stop();
      html5QrCode.clear();
    } catch {}
    html5QrCode = null;
  }
  cameraModal.classList.add('hidden');
}

btnDisconnect.addEventListener('click', () => {
  rtc.close();
});

// ----------------------------------------------------
// File Transmission Controls
// ----------------------------------------------------

modeBtnFiles.addEventListener('click', () => {
  modeBtnFiles.className = 'text-sm font-bold text-cyan-400 border-b-2 border-cyan-400 pb-1 transition';
  modeBtnSnippet.className = 'text-sm font-medium text-slate-400 hover:text-white pb-1 transition';
  panelSendFiles.classList.remove('hidden');
  panelSendSnippet.classList.add('hidden');
});

modeBtnSnippet.addEventListener('click', () => {
  modeBtnSnippet.className = 'text-sm font-bold text-cyan-400 border-b-2 border-cyan-400 pb-1 transition';
  modeBtnFiles.className = 'text-sm font-medium text-slate-400 hover:text-white pb-1 transition';
  panelSendSnippet.classList.remove('hidden');
  panelSendFiles.classList.add('hidden');
});

dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('border-cyan-400', 'bg-cyan-950/20');
});
dropzone.addEventListener('dragleave', () => {
  dropzone.classList.remove('border-cyan-400', 'bg-cyan-950/20');
});
dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('border-cyan-400', 'bg-cyan-950/20');
  if (e.dataTransfer && e.dataTransfer.files) {
    addFilesToStaging(Array.from(e.dataTransfer.files));
  }
});

fileInput.addEventListener('change', () => {
  if (fileInput.files) {
    addFilesToStaging(Array.from(fileInput.files));
    fileInput.value = '';
  }
});

function addFilesToStaging(files: File[]) {
  stagedFiles = [...stagedFiles, ...files];
  renderStagedFiles();
}

function renderStagedFiles() {
  stagedCountLabel.textContent = `${stagedFiles.length} file${stagedFiles.length === 1 ? '' : 's'} staged`;
  btnStartSend.disabled = stagedFiles.length === 0;

  if (stagedFiles.length === 0) {
    stagedFilesContainer.classList.add('hidden');
    stagedFilesContainer.innerHTML = '';
    return;
  }

  stagedFilesContainer.classList.remove('hidden');
  stagedFilesContainer.innerHTML = '';

  stagedFiles.forEach((file, index) => {
    const row = document.createElement('div');
    row.className = 'flex items-center justify-between p-2 rounded-lg bg-[#0d1117] border border-[#30363d] text-xs';
    row.innerHTML = `
      <div class="flex items-center gap-2 truncate pr-2">
        <span class="text-slate-400">📄</span>
        <span class="font-mono text-white truncate">${file.name}</span>
        <span class="text-slate-500">(${formatBytes(file.size)})</span>
      </div>
      <button data-index="${index}" class="btn-remove-staged text-slate-500 hover:text-rose-400 transition font-bold px-1.5">✕</button>
    `;
    stagedFilesContainer.appendChild(row);
  });

  stagedFilesContainer.querySelectorAll('.btn-remove-staged').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const idx = parseInt((e.currentTarget as HTMLButtonElement).dataset.index || '0');
      stagedFiles.splice(idx, 1);
      renderStagedFiles();
    });
  });
}

btnClearStaged.addEventListener('click', () => {
  stagedFiles = [];
  renderStagedFiles();
});

btnStartSend.addEventListener('click', async () => {
  if (stagedFiles.length === 0) return;

  btnStartSend.disabled = true;
  const queue = [...stagedFiles];

  for (const file of queue) {
    activeTransferPanel.classList.remove('hidden');
    transferDirectionLabel.textContent = 'Sending';
    transferDirectionLabel.className = 'text-xs font-bold uppercase tracking-wider text-cyan-400';
    transferFilename.textContent = file.name;

    const ok = await rtc.sendFile(file);
    if (!ok) break;

    // Remove from staging as sent
    stagedFiles = stagedFiles.filter((f) => f !== file);
    renderStagedFiles();
  }

  activeTransferPanel.classList.add('hidden');
  btnStartSend.disabled = stagedFiles.length === 0;
  showToast('Finished transmitting batch!', 'success');
});

btnCancelTransfer.addEventListener('click', () => {
  rtc.cancelSend();
});

// Progress handlers
function handleSendProgress(p: ProgressInfo) {
  activeTransferPanel.classList.remove('hidden');
  transferProgressBar.style.width = `${p.percentage}%`;
  transferBytesLabel.textContent = `${formatBytes(p.bytesTransferred)} / ${formatBytes(p.totalBytes)}`;
  transferSpeedLabel.textContent = formatSpeed(p.speed);
  transferPercentLabel.textContent = `${Math.floor(p.percentage)}%`;
}

function handleReceiveProgress(p: ProgressInfo) {
  activeTransferPanel.classList.remove('hidden');
  transferDirectionLabel.textContent = 'Receiving';
  transferDirectionLabel.className = 'text-xs font-bold uppercase tracking-wider text-emerald-400';
  transferFilename.textContent = p.name;
  transferProgressBar.style.width = `${p.percentage}%`;
  transferBytesLabel.textContent = `${formatBytes(p.bytesTransferred)} / ${formatBytes(p.totalBytes)}`;
  transferSpeedLabel.textContent = formatSpeed(p.speed);
  transferPercentLabel.textContent = `${Math.floor(p.percentage)}%`;

  if (p.bytesTransferred >= p.totalBytes && p.totalBytes > 0) {
    setTimeout(() => {
      activeTransferPanel.classList.add('hidden');
    }, 600);
  }
}

function handleFileReceived(file: ReceivedFile) {
  emptyReceivedPlaceholder.classList.add('hidden');
  receivedCount++;
  receivedCountBadge.textContent = receivedCount.toString();

  const card = document.createElement('div');
  card.className = 'p-3 rounded-xl bg-[#0d1117] border border-[#30363d] space-y-2';

  const downloadUrl = URL.createObjectURL(file.blob);

  card.innerHTML = `
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2 truncate pr-2">
        <span>📦</span>
        <span class="font-mono text-xs text-white truncate font-medium">${file.name}</span>
      </div>
      <span class="text-[10px] text-slate-500 font-mono">${formatBytes(file.size)}</span>
    </div>
    <div class="flex items-center justify-between pt-1">
      <span class="text-[10px] text-slate-500">${file.receivedAt.toLocaleTimeString()}</span>
      <a href="${downloadUrl}" download="${file.name}" class="px-2.5 py-1 text-xs rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold transition flex items-center gap-1">
        ⬇ Download
      </a>
    </div>
  `;

  receivedItemsList.prepend(card);
  showToast(`Received: ${file.name} (${formatBytes(file.size)})`, 'success');

  // Trigger download automatically
  const autoAnchor = document.createElement('a');
  autoAnchor.href = downloadUrl;
  autoAnchor.download = file.name;
  document.body.appendChild(autoAnchor);
  autoAnchor.click();
  autoAnchor.remove();
}

function handleSnippetReceived(text: string) {
  emptyReceivedPlaceholder.classList.add('hidden');
  receivedCount++;
  receivedCountBadge.textContent = receivedCount.toString();

  const card = document.createElement('div');
  card.className = 'p-3 rounded-xl bg-[#0d1117] border border-cyan-900/50 space-y-2';

  card.innerHTML = `
    <div class="flex items-center justify-between text-xs text-cyan-400 font-semibold">
      <span>📋 Text Snippet</span>
      <span class="text-[10px] text-slate-500">${new Date().toLocaleTimeString()}</span>
    </div>
    <pre class="p-2 rounded bg-black/40 text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap select-all max-h-32">${escapeHtml(text)}</pre>
    <div class="flex justify-end">
      <button class="btn-copy-snippet px-2 py-0.5 text-xs text-slate-300 hover:text-white bg-slate-800 rounded border border-slate-700 transition">
        Copy
      </button>
    </div>
  `;

  card.querySelector('.btn-copy-snippet')?.addEventListener('click', () => {
    navigator.clipboard.writeText(text);
    showToast('Snippet copied to clipboard!', 'success');
  });

  receivedItemsList.prepend(card);
  showToast('Received text snippet!', 'info');
}

function escapeHtml(str: string): string {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

btnClearHistory.addEventListener('click', () => {
  receivedItemsList.innerHTML = '';
  receivedItemsList.appendChild(emptyReceivedPlaceholder);
  emptyReceivedPlaceholder.classList.remove('hidden');
  receivedCount = 0;
  receivedCountBadge.textContent = '0';
});

// Snippet Sending
btnPasteClipboard.addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    snippetInput.value = text;
  } catch {
    showToast('Clipboard access denied', 'error');
  }
});

btnSendSnippet.addEventListener('click', () => {
  const text = snippetInput.value.trim();
  if (!text) {
    showToast('Snippet text is empty', 'error');
    return;
  }
  const ok = rtc.sendSnippet(text);
  if (ok) {
    snippetInput.value = '';
    showToast('Snippet sent successfully!', 'success');
  }
});
