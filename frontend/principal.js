document.addEventListener('DOMContentLoaded', () => {
    const dateInput = document.getElementById('dash-date');
    const trackerGrid = document.getElementById('tracker-grid');
    const statsDisplay = document.getElementById('stats-display');
    const summaryEditor = document.getElementById('summary-editor');
    const saveSummaryBtn = document.getElementById('save-summary-btn');
    const saveStatus = document.getElementById('save-status');

    const reviewModal = document.getElementById('review-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalContent = document.getElementById('modal-content');

    dateInput.valueAsDate = new Date();
    fetchTrackerData();
    fetchSummary();

    dateInput.addEventListener('change', () => {
        fetchTrackerData();
        fetchSummary();
    });

    async function fetchTrackerData() {
        try {
            const res = await fetch(`/api/tracker/${dateInput.value}`);
            const data = await res.json();
            
            let html = '';
            let count = 0;
            if (data.records && data.records.length > 0) {
                data.records.forEach(r => {
                    let statusChip = '';
                    let actionBtn = '';
                    
                    if (r.status === 'draft') {
                        statusChip = `<span class="bg-surface-container text-secondary/60 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-tight">Draft</span>`;
                    } else if (r.status === 'pending_review') {
                        statusChip = `<span class="bg-secondary-container text-primary px-2 py-1 rounded text-[10px] font-bold uppercase tracking-tight">Pending PA</span>`;
                    } else if (r.status === 'approved') {
                        statusChip = `<span class="bg-primary text-white px-2 py-1 rounded text-[10px] font-bold uppercase tracking-tight">Approved</span>`;
                        actionBtn = `<button onclick="viewReport('${r.department}', \`${r.content.replace(/`/g, '\\`')}\`)" class="w-full py-2 text-xs font-bold text-primary border border-outline-variant rounded hover:bg-white transition-colors">View Report</button>`;
                        count++;
                    }

                    html += `
                    <div class="bg-white p-5 rounded-xl border border-outline-variant/30 shadow-sm transition-all hover:shadow-md">
                        <div class="flex justify-between items-start mb-4">
                            <h4 class="font-headline font-extrabold text-lg text-primary">${r.department}</h4>
                            ${statusChip}
                        </div>
                        <p class="text-[11px] text-secondary/60 line-clamp-2 mb-4">${r.content}</p>
                        ${actionBtn || '<div class="h-8"></div>'}
                    </div>`;
                });
            } else {
                html = `<div class="col-span-full py-20 text-center text-sm text-secondary">No activity found for this date.</div>`;
            }
            trackerGrid.innerHTML = html;
            statsDisplay.innerText = `${count} Approved Submissions`;
        } catch (e) {
            trackerGrid.innerHTML = `<div class="col-span-full py-20 text-center text-sm text-error">Failed to load institutional data.</div>`;
        }
    }

    async function fetchSummary() {
        try {
            const res = await fetch(`/api/principal/summary?date=${dateInput.value}`);
            const data = await res.json();
            summaryEditor.innerHTML = data.summary || '';
            saveStatus.innerText = data.status === 'approved' ? "Finalized" : (data.summary ? "Draft Saved" : "No summary yet");
        } catch (e) {
            console.error(e);
        }
    }

    saveSummaryBtn.addEventListener('click', async () => {
        const content = summaryEditor.innerHTML;
        const date = dateInput.value;
        
        saveStatus.innerText = "Saving...";
        try {
            const res = await fetch('/api/principal/summary', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ date, content, status: 'approved' })
            });
            if (res.ok) {
                saveStatus.innerText = "Summary Finalized";
            }
        } catch (e) {
            saveStatus.innerText = "Error Saving";
        }
    });

    window.viewReport = (dept, content) => {
        modalTitle.innerText = `${dept} Department Report - ${dateInput.value}`;
        modalContent.innerHTML = content.replace(/\\n/g, '<br/>');
        reviewModal.classList.remove('hidden');
    };

    window.closeReviewModal = () => {
        reviewModal.classList.add('hidden');
    };
});
