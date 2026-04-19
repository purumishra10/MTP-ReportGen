const form = document.getElementById('generator-form');
const submitBtn = document.getElementById('submit-btn');
const loading = document.getElementById('loading');
const dateInput = document.getElementById('date');

const uploadForm = document.getElementById('upload-form');
const uploadSubmitBtn = document.getElementById('upload-submit-btn');
const uploadLoading = document.getElementById('upload-loading');

const monthlyBtn = document.getElementById('monthly-btn');
const monthlyLoading = document.getElementById('monthly-loading');
const historyList = document.getElementById('history-list');

// Tracker Elements
const trackerGrid = document.querySelector('.grid.grid-cols-2.lg\\:grid-cols-4.gap-4'); // The Bento grid

// Modal Elements
const reviewModal = document.getElementById('review-modal');
const modalDept = document.getElementById('modal-dept');
const modalDate = document.getElementById('modal-date');
const modalContentArea = document.getElementById('modal-content-area');
let currentReviewId = null;

// Initialize
dateInput.valueAsDate = new Date();
fetchHistory();
fetchTrackerData();

dateInput.addEventListener('change', fetchTrackerData);

// Fetch Status from API and Render Grid
async function fetchTrackerData() {
    if (!trackerGrid) return;
    
    const dateVal = dateInput.value;
    try {
        const res = await fetch(`/api/tracker/${dateVal}`);
        const data = await res.json();
        
        let html = '';
        if (data.records && data.records.length > 0) {
            data.records.forEach(r => {
                let statusChip = '';
                let reviewBtn = '';
                
                if (r.status === 'draft') {
                    statusChip = `<div class="bg-surface-container text-on-surface-variant px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-on-surface-variant/50"></span>Draft</div>`;
                } else if (r.status === 'pending_review') {
                    statusChip = `<div class="bg-[#fffbeb] text-[#b45309] border border-[#fde68a] px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-[#f59e0b] animate-pulse"></span>Pending</div>`;
                    reviewBtn = `<button onclick="openReviewModal(${r.id}, '${r.department}', \`${r.content.replace(/`/g, '\\`')}\`)" class="mt-4 w-full py-2 bg-on-surface text-surface rounded-md text-xs font-bold hover:bg-primary transition-colors">Review Submission</button>`;
                } else if (r.status === 'approved') {
                    statusChip = `<div class="bg-[#d1f4e0] text-[#0a4d2e] border border-[#85f8c4] px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-[#10b981]"></span>Approved</div>`;
                }

                html += `
                <div class="bg-surface-container-lowest p-5 rounded-2xl border ${r.status==='pending_review' ? 'border-[#fde68a]' : 'border-outline-variant'} shadow-sm flex flex-col justify-between group transition-shadow hover:shadow-md">
                    <div>
                        <div class="flex justify-between items-start mb-3">
                            <h4 class="font-headline font-bold text-primary">${r.department}</h4>
                            ${statusChip}
                        </div>
                        <p class="text-xs text-on-surface-variant line-clamp-2">${r.content}</p>
                    </div>
                    ${reviewBtn}
                </div>
                `;
            });
        } else {
            html = `<div class="col-span-full py-12 text-center text-sm font-medium text-on-surface-variant">No submissions found for this date.</div>`;
        }
        
        trackerGrid.innerHTML = html;
        
    } catch (e) {
        console.error(e);
        trackerGrid.innerHTML = `<div class="col-span-full py-12 text-center text-sm text-error">Failed to load tracker data.</div>`;
    }
}

// Modal Functions
window.openReviewModal = function(id, dept, content) {
    currentReviewId = id;
    modalDept.innerText = dept;
    modalDate.innerText = dateInput.value;
    modalContentArea.innerHTML = content.replace(/\\n/g, '<br/>'); // basic line break mapping
    
    reviewModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden'; 
};

window.closeReviewModal = function() {
    currentReviewId = null;
    reviewModal.classList.add('hidden');
    document.body.style.overflow = '';
};

window.submitReviewAction = async function(status) {
    if (!currentReviewId) return;
    
    try {
        const res = await fetch('/api/tracker/review', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: currentReviewId, status: status})
        });
        if (res.ok) {
            closeReviewModal();
            fetchTrackerData(); // refresh grid
        } else {
            alert('Failed to update status');
        }
    } catch(e) {
        alert('Network error during review');
    }
}

// Fetch History Sidebar
async function fetchHistory() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        
        historyList.innerHTML = '';
        if (data.dates && data.dates.length > 0) {
            data.dates.forEach(date => {
                const li = document.createElement('div');
                li.className = "bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 flex justify-between items-center group transition-colors hover:border-primary/30 cursor-pointer";
                li.onclick = () => { dateInput.value = date; fetchTrackerData(); };
                li.innerHTML = `
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center shrink-0">
                            <span class="material-symbols-outlined text-on-secondary-container text-[16px]">calendar_today</span>
                        </div>
                        <span class="text-xs font-bold text-on-surface">${date}</span>
                    </div>
                    <button type="button" title="Delete Record" onclick="event.stopPropagation(); deleteRecord('${date}')" class="p-1.5 text-outline hover:text-error hover:bg-error-container rounded-md transition-colors opacity-0 group-hover:opacity-100 flex items-center justify-center">
                        <span class="material-symbols-outlined text-[18px]">delete</span>
                    </button>
                `;
                historyList.appendChild(li);
            });
        }
    } catch (e) {
        historyList.innerHTML = '<div class="text-xs text-error text-center p-4">Error loading history.</div>';
    }
}

// Generate Daily from Database
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    submitBtn.classList.add('hidden');
    loading.classList.remove('hidden');

    const payload = { date: dateInput.value };

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        await handleDownloadResponse(response, `Master_Daily_Report_${payload.date}.docx`);
        fetchHistory(); 

    } catch (error) {
        alert(error.message);
    } finally {
        submitBtn.classList.remove('hidden');
        loading.classList.add('hidden');
    }
});

// Generate via Upload
if(uploadForm) {
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        uploadSubmitBtn.classList.add('hidden');
        uploadLoading.classList.remove('hidden');

        const formData = new FormData(uploadForm);
        const reportDate = formData.get('report_date');

        try {
            const response = await fetch('/consolidate', {
                method: 'POST',
                body: formData
            });

            // The /consolidate API returns a JSON with a redirect URL or success, not a direct file stream right now in my implementation
            if(!response.ok) {
                const errBody = await response.json();
                throw new Error(errBody.detail || 'Failed to upload and consolidate');
            }
            
            const data = await response.json();
            if(data.download_url) {
                // Download it
                const dlRes = await fetch(data.download_url);
                await handleDownloadResponse(dlRes, `Master_Daily_Report_${reportDate}.docx`);
            } else {
                alert('Success, but no download url provided');
            }

            fetchHistory(); 

        } catch (error) {
            alert(error.message);
        } finally {
            uploadSubmitBtn.classList.remove('hidden');
            uploadLoading.classList.add('hidden');
        }
    });
}

// Generate Monthly
monthlyBtn.addEventListener('click', async () => {
    monthlyBtn.classList.add('hidden');
    monthlyLoading.classList.remove('hidden');
    
    try {
        const response = await fetch('/api/monthly', { method: 'POST' });
        await handleDownloadResponse(response, `MTP_Monthly_Report.docx`);
    } catch (error) {
        alert(error.message);
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
    
    a.download = defaultFilename;
    document.body.appendChild(a);
    a.click();
    
    window.URL.revokeObjectURL(url);
}

async function deleteRecord(date) {
    try {
        const res = await fetch(`/api/history/${date}`, { method: 'DELETE' });
        if (res.ok) {
            fetchHistory();
            fetchTrackerData();
        }
    } catch (e) {
        alert('Network error while deleting record');
    }
}

window.deleteRecord = deleteRecord;
