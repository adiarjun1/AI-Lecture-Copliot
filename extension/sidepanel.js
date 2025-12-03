async function getTabStorageKey() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return `tab_${tab.id}`;
}

let currentSlideId = null;
let currentNotesText = '';
let previousQuestions = [];

const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');
const uploadStatus = document.getElementById('upload-status');
const scanButton = document.getElementById('scan-button');
const compactFilename = document.getElementById('compact-filename');
const removeFileBtn = document.getElementById('remove-file-btn');

removeFileBtn.addEventListener('click', async (e) => {
  e.stopPropagation();
  await removeUploadedFile();
});

uploadArea.addEventListener('click', (e) => {
  if (e.target === removeFileBtn || e.target.closest('.upload-remove-btn')) {
    return;
  }
  fileInput.click();
});

uploadArea.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadArea.style.borderColor = '#1a73e8';
  if (uploadArea.classList.contains('compact')) {
    uploadArea.style.background = '#e3f2fd';
  }
});

uploadArea.addEventListener('dragleave', () => {
  if (uploadArea.classList.contains('compact')) {
    uploadArea.style.borderColor = '#4caf50';
    uploadArea.style.background = '#f0fdf4';
  } else {
    uploadArea.style.borderColor = '#dadce0';
  }
});

uploadArea.addEventListener('drop', (e) => {
  e.preventDefault();
  if (uploadArea.classList.contains('compact')) {
    uploadArea.style.borderColor = '#4caf50';
    uploadArea.style.background = '#f0fdf4';
  } else {
    uploadArea.style.borderColor = '#dadce0';
  }
  const files = e.dataTransfer.files;
  if (files.length > 0) {
    handleFileUpload(files[0]);
  }
});

async function removeUploadedFile() {
  currentSlideId = null;
  previousQuestions = [];
  
  uploadArea.classList.remove('compact');
  uploadStatus.classList.add('hidden');
  scanButton.disabled = true;
  fileInput.value = '';
  
  chrome.storage.local.remove(['slideId']);
  
  const storageKey = await getTabStorageKey();
  const stored = await chrome.storage.local.get([storageKey]);
  if (stored[storageKey]) {
    delete stored[storageKey].uploadStatus;
    delete stored[storageKey].scanResults;
    delete stored[storageKey].previousQuestions;
    await chrome.storage.local.set({ [storageKey]: stored[storageKey] });
  }
  
  const results = document.getElementById('results');
  const resultsContent = document.getElementById('results-content');
  results.classList.add('hidden');
  resultsContent.innerHTML = '';
}

fileInput.addEventListener('change', (e) => {
  if (e.target.files.length > 0) {
    handleFileUpload(e.target.files[0]);
  }
});

async function handleFileUpload(file) {
  const formData = new FormData();
  formData.append('file', file);
  
  uploadStatus.classList.remove('hidden', 'error');
  uploadStatus.textContent = 'Uploading...';
  uploadArea.classList.remove('compact');
  
  try {
    const response = await fetch('http://localhost:8000/api/upload-slides', {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      let errorMessage = 'Upload failed';
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorData.message || `Upload failed: ${response.status}`;
      } catch (e) {
        errorMessage = `Upload failed: ${response.status}`;
      }
      throw new Error(errorMessage);
    }
    
    const data = await response.json();
    
    previousQuestions = [];
    const results = document.getElementById('results');
    const resultsContent = document.getElementById('results-content');
    results.classList.add('hidden');
    resultsContent.innerHTML = '';
    
    uploadArea.classList.add('compact');
    compactFilename.textContent = `${file.name} (${data.pages} slides)`;
    uploadStatus.classList.add('hidden');
    
    currentSlideId = data.slide_id;
    chrome.storage.local.set({ slideId: data.slide_id });
    
    const storageKey = await getTabStorageKey();
    const stored = await chrome.storage.local.get([storageKey]);
    const tabData = stored[storageKey] || {};
    tabData.uploadStatus = {
      filename: file.name,
      pages: data.pages,
      slideId: data.slide_id
    };
    delete tabData.scanResults;
    delete tabData.previousQuestions;
    await chrome.storage.local.set({ [storageKey]: tabData });
    
    scanButton.disabled = false;
  } catch (error) {
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      uploadStatus.textContent = 'Error: Backend not running on localhost:8000';
    } else {
      uploadStatus.textContent = `Error: ${error.message}`;
    }
    uploadStatus.classList.add('error');
  }
}

scanButton.addEventListener('click', async () => {
  const scanProgress = document.getElementById('scan-progress');
  const results = document.getElementById('results');
  const resultsContent = document.getElementById('results-content');
  const buttonText = scanButton.querySelector('.button-text');
  const spinner = scanButton.querySelector('.spinner');
  
  scanButton.disabled = true;
  buttonText.textContent = 'Scanning...';
  spinner.classList.remove('hidden');
  scanProgress.classList.remove('hidden');
  scanProgress.textContent = 'Analyzing your notes...';
  scanProgress.style.color = '#5f6368';
  
  results.classList.add('hidden');
  resultsContent.innerHTML = '';
  previousQuestions = [];
  
  try {
    const storageKey = await getTabStorageKey();
    chrome.storage.local.remove(storageKey);
  } catch (err) {}
  
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (!tab.url || !tab.url.includes('docs.google.com/document')) {
      throw new Error('Please open a Google Docs document first.');
    }
    
    let docContent;
    try {
      docContent = await chrome.tabs.sendMessage(tab.id, { action: 'getDocContent' });
    } catch (error) {
      if (error.message.includes('Could not establish connection') || 
          error.message.includes('Receiving end does not exist')) {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['content.js']
        });
        await new Promise(resolve => setTimeout(resolve, 100));
        docContent = await chrome.tabs.sendMessage(tab.id, { action: 'getDocContent' });
      } else {
        throw error;
      }
    }
    
    const { slideId } = await chrome.storage.local.get(['slideId']);
    if (!slideId) throw new Error('Please upload slides first');
    
    currentSlideId = slideId;
    currentNotesText = docContent.text;
    
    const response = await fetch('http://localhost:8000/api/scan-notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        slide_id: slideId,
        notes_text: docContent.text,
        doc_id: docContent.docId
      })
    });
    
    if (!response.ok) throw new Error('Scan failed');
    
    const data = await response.json();
    
    if (data.question && data.question.question) {
      previousQuestions = [data.question];
    }
    
    const storageKey = await getTabStorageKey();
    await chrome.storage.local.set({
      [storageKey]: {
        scanResults: data,
        previousQuestions: previousQuestions,
        timestamp: Date.now()
      }
    });
    
    displayResults(data);
    scanProgress.classList.add('hidden');
    
    if (data.misconceptions && data.misconceptions.length > 0) {
      await chrome.tabs.sendMessage(tab.id, {
        action: 'highlightMisconceptions',
        misconceptions: data.misconceptions
      });
    }
    
  } catch (error) {
    scanProgress.textContent = `Error: ${error.message}`;
    scanProgress.style.color = '#c62828';
  } finally {
    scanButton.disabled = false;
    buttonText.textContent = 'Scan Notes';
    spinner.classList.add('hidden');
  }
});

function displayResults(data) {
  const results = document.getElementById('results');
  const resultsContent = document.getElementById('results-content');
  
  results.classList.remove('hidden');
  resultsContent.innerHTML = '';
  
  // Misconceptions
  if (data.misconceptions && data.misconceptions.length > 0) {
    const section = document.createElement('div');
    section.style.marginBottom = '16px';
    section.innerHTML = '<h4 style="color: #c62828; margin-bottom: 8px; font-size: 13px;">🚫 Misconceptions</h4>';
    data.misconceptions.forEach(m => {
      const item = document.createElement('div');
      item.className = 'misconception-item';
      item.innerHTML = `<div style="font-weight:500;margin-bottom:3px;">${m.text}</div><div style="color:#1a73e8;">→ ${m.suggestion}</div>`;
      section.appendChild(item);
    });
    resultsContent.appendChild(section);
  }
  
  // Single quiz question
  if (data.question && data.question.question) {
    const section = document.createElement('div');
    
    // Header with info message
    const header = document.createElement('div');
    header.style.marginBottom = '12px';
    header.style.display = 'flex';
    header.style.alignItems = 'center';
    header.style.justifyContent = 'space-between';
    
    const title = document.createElement('h4');
    title.style.color = '#1a73e8';
    title.style.fontSize = '13px';
    title.style.margin = '0';
    title.textContent = '🧠 Quiz Yourself';
    header.appendChild(title);
    
    const refreshBtn = document.createElement('button');
    refreshBtn.className = 'refresh-question-btn';
    refreshBtn.innerHTML = '↻ New Question';
    refreshBtn.title = 'Get a new question from your covered slides';
    refreshBtn.addEventListener('click', () => refreshQuestion());
    header.appendChild(refreshBtn);
    
    section.appendChild(header);
    
    // Info message about covered slides
    const infoMsg = document.createElement('div');
    infoMsg.className = 'quiz-info-msg';
    infoMsg.textContent = `Questions are based only on slides covered by your notes (${data.covered_slides || 0} of ${data.total_slides || 0} slides)`;
    section.appendChild(infoMsg);
    
    // Question card
    const card = createQuizCard(data.question);
    section.appendChild(card);
    
    resultsContent.appendChild(section);
  }
  
  if ((!data.misconceptions || data.misconceptions.length === 0) &&
      (!data.question || !data.question.question)) {
    resultsContent.innerHTML = '<div class="no-results-msg">ℹ️ Couldn\'t generate a quiz question. Try adding more notes that cover the lecture slides.</div>';
  }
}

function createQuizCard(q) {
  const card = document.createElement('div');
  card.className = 'quiz-card';
  
  // Question text
  const questionEl = document.createElement('div');
  questionEl.className = 'quiz-question';
  questionEl.textContent = q.question;
  card.appendChild(questionEl);
  
  // Options
  const optionsContainer = document.createElement('div');
  optionsContainer.className = 'quiz-options';
  
  const letters = ['A', 'B', 'C', 'D', 'E'];
  q.options.forEach((opt, optIdx) => {
    const optionEl = document.createElement('div');
    optionEl.className = 'quiz-option';
    optionEl.dataset.index = optIdx;
    optionEl.dataset.correct = q.correct_index;
    
    const letterSpan = document.createElement('span');
    letterSpan.className = 'quiz-option-letter';
    letterSpan.textContent = letters[optIdx] + ')';
    
    const textSpan = document.createElement('span');
    textSpan.textContent = opt;
    
    optionEl.appendChild(letterSpan);
    optionEl.appendChild(textSpan);
    optionEl.addEventListener('click', () => handleOptionClick(optionEl, optionsContainer, q.explanation));
    optionsContainer.appendChild(optionEl);
  });
  
  card.appendChild(optionsContainer);
  return card;
}

async function refreshQuestion() {
  if (!currentSlideId || !currentNotesText) {
    // Try to get notes again
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab.url && tab.url.includes('docs.google.com/document')) {
        let docContent;
        try {
          docContent = await chrome.tabs.sendMessage(tab.id, { action: 'getDocContent' });
          currentNotesText = docContent.text;
        } catch (error) {
          if (error.message.includes('Could not establish connection')) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: ['content.js']
            });
            await new Promise(resolve => setTimeout(resolve, 100));
            docContent = await chrome.tabs.sendMessage(tab.id, { action: 'getDocContent' });
            currentNotesText = docContent.text;
          }
        }
      }
    } catch (err) {
      console.error('Failed to get notes:', err);
    }
  }
  
  const refreshBtn = document.querySelector('.refresh-question-btn');
  const resultsContent = document.getElementById('results-content');
  
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.textContent = 'Loading...';
  }
  
  try {
    const response = await fetch('http://localhost:8000/api/refresh-question', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        slide_id: currentSlideId,
        notes_text: currentNotesText,
        previous_questions: previousQuestions
      })
    });
    
    if (!response.ok) throw new Error('Failed to refresh');
    
    const data = await response.json();
    
    if (data.question && data.question.question) {
      previousQuestions.push(data.question);
      
      const storageKey = await getTabStorageKey();
      const stored = await chrome.storage.local.get([storageKey]);
      if (stored[storageKey]) {
        stored[storageKey].previousQuestions = previousQuestions;
        chrome.storage.local.set({ [storageKey]: stored[storageKey] });
      }
      
      const oldCard = resultsContent.querySelector('.quiz-card');
      const newCard = createQuizCard(data.question);
      
      const infoMsg = resultsContent.querySelector('.quiz-info-msg');
      if (infoMsg) {
        infoMsg.textContent = `Questions are based only on slides covered by your notes (${data.covered_slides || 0} of ${data.total_slides || 0} slides)`;
      }
      
      if (oldCard) {
        oldCard.replaceWith(newCard);
      } else {
        resultsContent.appendChild(newCard);
      }
    }
  } catch (error) {
    console.error('Refresh failed:', error);
    if (refreshBtn) {
      refreshBtn.textContent = '↻ New Question';
    }
  } finally {
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.textContent = '↻ New Question';
    }
  }
}

function handleOptionClick(clickedOption, optionsContainer, explanation) {
  if (clickedOption.classList.contains('disabled')) return;
  
  const selectedIndex = parseInt(clickedOption.dataset.index);
  const correctIndex = parseInt(clickedOption.dataset.correct);
  
  const allOptions = optionsContainer.querySelectorAll('.quiz-option');
  allOptions.forEach(opt => opt.classList.add('disabled'));
  
  allOptions[correctIndex].classList.add('correct');
  
  if (selectedIndex !== correctIndex) {
    clickedOption.classList.add('incorrect');
  }
  
  if (explanation) {
    // Remove existing explanation if any
    const existing = optionsContainer.parentElement.querySelector('.quiz-explanation');
    if (existing) existing.remove();
    
    const explanationEl = document.createElement('div');
    explanationEl.className = 'quiz-explanation';
    explanationEl.textContent = explanation;
    optionsContainer.parentElement.appendChild(explanationEl);
  }
}

async function initializePopup() {
  try {
    const { slideId } = await chrome.storage.local.get(['slideId']);
    if (slideId) {
      currentSlideId = slideId;
      scanButton.disabled = false;
    }
    
    const storageKey = await getTabStorageKey();
    const stored = await chrome.storage.local.get([storageKey]);
    
    if (stored[storageKey]) {
      const tabData = stored[storageKey];
      
      if (tabData.uploadStatus) {
        uploadArea.classList.add('compact');
        compactFilename.textContent = `${tabData.uploadStatus.filename} (${tabData.uploadStatus.pages} slides)`;
        scanButton.disabled = false;
      }
      
      if (tabData.scanResults) {
        if (tabData.previousQuestions) {
          previousQuestions = tabData.previousQuestions;
        }
        displayResults(tabData.scanResults);
        results.classList.remove('hidden');
      }
    }
  } catch (error) {
    console.log('Error initializing:', error);
  }
}

initializePopup();
