const dropArea = document.getElementById('drop-area');
const fileInput = document.getElementById('files');
const fileList = document.getElementById('file-list');
const form = document.getElementById('generator-form');
const submitBtn = document.getElementById('submit-btn');
const loading = document.getElementById('loading');
const errorMsg = document.getElementById('error-msg');
const successMsg = document.getElementById('success-msg');

const monthlyBtn = document.getElementById('monthly-btn');
const monthlyLoading = document.getElementById('monthly-loading');
const historyList = document.getElementById('history-list');

let selectedFiles = [];

// Initialize
document.getElementById('date').valueAsDate = new Date();
fetchHistory();

// Handle Drag and Drop
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    dropArea.addEventListener(eventName, () => dropArea.classList.add('drag-over'), false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, () => dropArea.classList.remove('drag-over'), false);
});

dropArea.addEventListener('drop', handleDrop, false);

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    handleFiles(files);
}

fileInput.addEventListener('change', function() {
    handleFiles(this.files);
});

function handleFiles(files) {
    const newFiles = Array.from(files).filter(f => f.name.endsWith('.docx'));
    selectedFiles = [...selectedFiles, ...newFiles];
    updateFileList();
}

function updateFileList() {
    fileList.innerHTML = '';
    selectedFiles.forEach((file, index) => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span>${file.name}</span>
            <span style="color: #c92a2a; cursor: pointer;" onclick="removeFile(${index})">✕</span>
        `;
        fileList.appendChild(li);
    });
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    updateFileList();
}

// Fetch History
async function fetchHistory() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        
        historyList.innerHTML = '';
        if (data.dates && data.dates.length > 0) {
            data.dates.forEach(date => {
                const li = document.createElement('li');
                li.style.display = 'flex';
                li.style.justifyContent = 'space-between';
                li.style.alignItems = 'center';
                li.innerHTML = `
                    <span>${date}</span>
                    <span style="color: #c92a2a; cursor: pointer; font-weight: bold; font-size: 1.1em;" title="Delete Record" onclick="deleteRecord('${date}')">✕</span>
                `;
                historyList.appendChild(li);
            });
        } else {
            historyList.innerHTML = '<li>No records found.</li>';
        }
    } catch (e) {
        historyList.innerHTML = '<li>Error loading history.</li>';
    }
}

// Generate Daily
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    errorMsg.classList.add('hidden');
    successMsg.classList.add('hidden');
    
    if (selectedFiles.length === 0) {
        showError("Please upload at least one .docx report.");
        return;
    }

    submitBtn.classList.add('hidden');
    loading.classList.remove('hidden');

    const formData = new FormData();
    formData.append('date', document.getElementById('date').value);

    selectedFiles.forEach(file => {
        formData.append('files', file);
    });

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            body: formData
        });

        await handleDownloadResponse(response, `Master_Daily_Report_${document.getElementById('date').value}.docx`);
        fetchHistory(); // refresh db list

    } catch (error) {
        showError(error.message);
    } finally {
        submitBtn.classList.remove('hidden');
        loading.classList.add('hidden');
    }
});

// Generate Monthly
monthlyBtn.addEventListener('click', async () => {
    errorMsg.classList.add('hidden');
    successMsg.classList.add('hidden');
    monthlyBtn.classList.add('hidden');
    monthlyLoading.classList.remove('hidden');
    
    try {
        const response = await fetch('/api/monthly', { method: 'POST' });
        await handleDownloadResponse(response, `MTP_Monthly_Report.docx`);
    } catch (error) {
        showError(error.message);
    } finally {
        monthlyBtn.classList.remove('hidden');
        monthlyLoading.classList.add('hidden');
    }
});

async function handleDownloadResponse(response, defaultFilename) {
    if (!response.ok) {
        const errBody = await response.json();
        throw new Error(errBody.error || 'Failed to generate report');
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    
    const disposition = response.headers.get('Content-Disposition');
    let filename = defaultFilename;
    if (disposition && disposition.indexOf('attachment') !== -1) {
        const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
        const matches = filenameRegex.exec(disposition);
        if (matches != null && matches[1]) {
            filename = matches[1].replace(/['"]/g, '');
        }
    }
    
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    
    window.URL.revokeObjectURL(url);
    successMsg.classList.remove('hidden');
}

function showError(msg) {
    errorMsg.textContent = msg;
    errorMsg.classList.remove('hidden');
}

async function deleteRecord(date) {
    try {
        const res = await fetch(`/api/history/${date}`, { method: 'DELETE' });
        if (res.ok) {
            fetchHistory();
        } else {
            const data = await res.json();
            showError(data.error || 'Failed to delete record');
        }
    } catch (e) {
        showError('Network error while deleting record');
    }
}

// Make accessible globally for inline onclick
window.removeFile = removeFile;
window.deleteRecord = deleteRecord;
