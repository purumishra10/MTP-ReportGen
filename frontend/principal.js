// ── Auth Fetch Helper ────────────────────────────────────────────────────────
async function authFetch(url, options = {}) {
    const token = localStorage.getItem('session_token') || '';
    const headers = new Headers(options.headers || {});
    if (token && !headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token}`);
    }
    const opts = { ...options, headers, credentials: 'include' };
    const res = await fetch(url, opts);
    if (res.status === 401) {
        localStorage.removeItem('session_token');
        alert('Session expired. Redirecting to login...');
        window.location.href = 'index.html';
    }
    return res;
}

// ── Sidebar Toggle ────────────────────────────────────────────────────────────
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('main-content');
    if (!sidebar) return;
    sidebar.classList.toggle('collapsed');
    if (mainContent) mainContent.classList.toggle('sidebar-collapsed');
    const isCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('sidebar_collapsed', isCollapsed ? '1' : '0');
}

// Restore sidebar state immediately
(function() {
    if (localStorage.getItem('sidebar_collapsed') === '1') {
        document.addEventListener('DOMContentLoaded', () => {
            const sidebar = document.getElementById('sidebar');
            const mainContent = document.getElementById('main-content');
            if (sidebar) sidebar.classList.add('collapsed');
            if (mainContent) mainContent.classList.add('sidebar-collapsed');
        });
    }
})();

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

    let lastRecords = [];

    async function fetchTrackerData() {
        try {
            const res = await authFetch(`/api/tracker/${dateInput.value}`);
            const data = await res.json();
            
            let html = '';
            let count = 0;
            lastRecords = data.records || [];
            if (lastRecords.length > 0) {
                lastRecords.forEach(r => {
                    let statusChip = '';
                    let actionBtn = '';
                    
                    if (r.status === 'draft') {
                        statusChip = `<span class="bg-surface-container text-secondary/60 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-tight">Draft</span>`;
                    } else if (r.status === 'pending_review') {
                        statusChip = `<span class="bg-secondary-container text-primary px-2 py-1 rounded text-[10px] font-bold uppercase tracking-tight">Pending PA</span>`;
                    } else if (r.status === 'approved') {
                        statusChip = `<span class="bg-primary text-white px-2 py-1 rounded text-[10px] font-bold uppercase tracking-tight">Approved</span>`;
                        actionBtn = `<button onclick="viewReport('${r.department}')" class="w-full py-2 text-xs font-bold text-primary border border-outline-variant rounded hover:bg-white transition-colors">View Report</button>`;
                        count++;
                    }

                    html += `
                    <div class="bg-white p-5 rounded-xl border border-outline-variant/30 shadow-sm transition-all hover:shadow-md">
                        <div class="flex justify-between items-start mb-4">
                            <h4 class="font-headline font-extrabold text-lg text-primary">${r.department}</h4>
                            ${statusChip}
                        </div>
                        <p class="text-[11px] text-secondary/60 line-clamp-2 mb-4">${previewContent(r.content)}</p>
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
            const res = await authFetch(`/api/principal/summary/${dateInput.value}`);
            const data = await res.json();
            if (data.record) {
                summaryEditor.innerHTML = data.record.content || '';
                saveStatus.innerText = data.record.status === 'finalized' ? 'Finalized ✓' : 'Draft Saved';
            } else {
                summaryEditor.innerHTML = '';
                saveStatus.innerText = 'No summary yet';
            }
        } catch (e) {
            console.error(e);
        }
    }

    saveSummaryBtn.addEventListener('click', async () => {
        const content = summaryEditor.innerHTML;
        const date = dateInput.value;
        
        saveStatus.innerText = 'Saving...';
        try {
            const res = await authFetch('/api/principal/summary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date, content, status: 'finalized' })
            });
            if (res.ok) {
                saveStatus.innerText = 'Summary Finalized ✓';
            } else {
                const j = await res.json();
                saveStatus.innerText = `Error: ${j.detail || 'Save failed'}`;
            }
        } catch (e) {
            saveStatus.innerText = 'Error saving';
        }
    });

    window.viewReport = (dept) => {
        modalTitle.innerText = `${dept} Department Report - ${dateInput.value}`;
        const record = lastRecords.find(r => r.department === dept);
        const content = record ? record.content : '';
        try {
            const parsed = JSON.parse(content);
            if (parsed && parsed.sections) {
                modalContent.innerHTML = renderSectionsAsHTML(parsed.sections);
            } else {
                modalContent.textContent = content || '(empty)';
            }
        } catch {
            modalContent.textContent = content || '(empty)';
        }
        reviewModal.classList.remove('hidden');
    };

    window.closeReviewModal = () => {
        reviewModal.classList.add('hidden');
    };

    function previewContent(content) {
        if (!content) return '';
        try {
            const parsed = JSON.parse(content);
            if (parsed && parsed.sections) {
                const filled = parsed.sections.filter(s => !s.nil && s.rows && s.rows.length).length;
                return `${filled} section(s) with entries`;
            }
        } catch {}
        return String(content).slice(0, 120);
    }

    function renderSectionsAsHTML(sections) {
        let html = '';
        sections.forEach(sec => {
            const title = sec.title || 'Untitled Section';
            html += `<div class="mb-6"><h3 class="font-headline font-bold text-primary mb-2">${escapeHTML(title)}</h3>`;
            if (sec.nil) {
                html += `<p class="text-sm italic text-secondary">Nil</p>`;
            } else if (!sec.rows || !sec.rows.length) {
                html += `<p class="text-sm italic text-secondary">No entries</p>`;
            } else {
                const headers = Object.keys(sec.rows[0]);
                html += `<table class="w-full text-sm border-collapse"><thead><tr>`;
                headers.forEach(h => { html += `<th class="text-left p-2 border-b">${escapeHTML(h)}</th>`; });
                html += `</tr></thead><tbody>`;
                sec.rows.forEach(row => {
                    html += `<tr>`;
                    headers.forEach(h => { html += `<td class="p-2 border-b">${escapeHTML(row[h] || '—')}</td>`; });
                    html += `</tr>`;
                });
                html += `</tbody></table>`;
            }
            html += `</div>`;
        });
        return html;
    }

    function escapeHTML(str) {
        return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
});
