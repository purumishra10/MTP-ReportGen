// ── MTP Report Portal — PA Dashboard Script ───────────────────────────────────
// Handles: file upload consolidation, portal DB generation, tracker, history, modal

// ── Sidebar Toggle ────────────────────────────────────────────────────────────
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('main-content');
    if (!sidebar) return;
    sidebar.classList.toggle('collapsed');
    if (mainContent) mainContent.classList.toggle('sidebar-collapsed');
    // Persist state
    const isCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('sidebar_collapsed', isCollapsed ? '1' : '0');
}

// Restore sidebar state on load
document.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('sidebar_collapsed') === '1') {
        const sidebar = document.getElementById('sidebar');
        const mainContent = document.getElementById('main-content');
        if (sidebar) sidebar.classList.add('collapsed');
        if (mainContent) mainContent.classList.add('sidebar-collapsed');
    }
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function showAlert(message, type = 'error') {
    const banner = document.getElementById('alert-banner');
    if (!banner) return;
    const isError = type === 'error';
    banner.className = `mb-6 p-4 rounded-xl text-sm font-semibold flex items-center gap-3 border ${
        isError
            ? 'bg-error-container text-on-error-container border-error/30'
            : 'bg-[#d1f4e0] text-[#0a4d2e] border-[#85f8c4]'
    }`;
    banner.innerHTML = `<span class="material-symbols-outlined">${isError ? 'error' : 'check_circle'}</span><span>${message}</span>`;
    banner.classList.remove('hidden');
    setTimeout(() => banner.classList.add('hidden'), 7000);
}

function showLoading(submitBtn, loadingBtn, show) {
    if (show) {
        submitBtn.classList.add('hidden');
        loadingBtn.classList.remove('hidden');
    } else {
        submitBtn.classList.remove('hidden');
        loadingBtn.classList.add('hidden');
    }
}

// Download a blob from a fetch response
async function downloadBlobResponse(response, filename) {
    if (!response.ok) {
        let detail = `Request failed (${response.status})`;
        try { const j = await response.json(); detail = j.detail || j.error || detail; } catch {}
        throw new Error(detail);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
        if (a.parentNode) document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }, 60000);
    return url;
}

// ── Initialise date pickers ────────────────────────────────────────────────────
const today = new Date().toISOString().split('T')[0];
const uploadDateEl  = document.getElementById('upload-date');
const dbDateEl      = document.getElementById('db-date');
const trackerDateEl = document.getElementById('tracker-date');

if (uploadDateEl)  uploadDateEl.value  = today;
if (dbDateEl)      dbDateEl.value      = today;
if (trackerDateEl) trackerDateEl.value = today;

// Load username & verify session
fetch('/api/me', { credentials: 'include' })
    .then(r => {
        if (!r.ok) {
            // Not authenticated or session expired after redeploy
            window.location.href = 'index.html';
            return null;
        }
        return r.json();
    })
    .then(data => {
        if (data && data.username) {
            const el = document.getElementById('sidebar-username');
            if (el) el.textContent = data.username;
        }
    }).catch(() => {});

// Logout
const logoutBtn = document.getElementById('logout-btn');
if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
        await fetch('/api/logout', { method: 'POST', credentials: 'include' });
        localStorage.clear();
        window.location.href = 'index.html';
    });
}

// ── File picker label ─────────────────────────────────────────────────────────
const filesInput = document.getElementById('files');
const fileCountLabel = document.getElementById('file-count-label');
if (filesInput) {
    filesInput.addEventListener('change', () => {
        const count = filesInput.files.length;
        if (count > 0 && fileCountLabel) {
            fileCountLabel.textContent = `${count} file${count > 1 ? 's' : ''} selected`;
            fileCountLabel.classList.remove('hidden');
        }
    });
}

// ── 1. File Upload & Consolidate ──────────────────────────────────────────────
const uploadSubmitBtn  = document.getElementById('upload-submit-btn');
const uploadLoadingBtn = document.getElementById('upload-loading-btn');
const uploadResult     = document.getElementById('upload-result');
const uploadResultMeta = document.getElementById('upload-result-meta');
const uploadDownloadLink = document.getElementById('upload-download-link');

// ── Consolidation timer helpers ────────────────────────────────────────────────
const CONSOLIDATION_STAGES = [
    { at: 0,   msg: 'Uploading department files to server...' },
    { at: 2,   msg: 'Reading and parsing DOCX structured tables...' },
    { at: 5,   msg: 'Extracting attendance, infra & department metrics...' },
    { at: 10,  msg: 'Running AI narrative summarisation with Gemini...' },
    { at: 20,  msg: 'Extracting MTP placement & training activities...' },
    { at: 35,  msg: 'Assembling formatted Master DOCX report...' },
    { at: 45,  msg: 'Almost done — finalizing report...' },
    { at: 60,  msg: 'Large batch processing — completing final checks...' },
];

let _consolidationTimer = null;
let _originalDocTitle = document.title;

function startConsolidationTimer() {
    const timerEl   = document.getElementById('upload-timer-display');
    const statusEl  = document.getElementById('upload-progress-text');
    const barEl     = document.getElementById('upload-progress-bar');
    if (!timerEl || !statusEl) return;

    const startTime = Date.now();
    _originalDocTitle = document.title;

    // Simulate progress smoothly based on wall-clock time so tab switches don't stall it
    const getBarPct = (s) => Math.min(92, (s / 45) * 92);

    const tick = () => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        timerEl.textContent = elapsed + 's';
        if (barEl) barEl.style.width = getBarPct(elapsed) + '%';

        // Find the most recent stage message
        const stage = [...CONSOLIDATION_STAGES].reverse().find(s => elapsed >= s.at);
        if (stage) statusEl.textContent = stage.msg;
    };

    tick();
    _consolidationTimer = setInterval(tick, 500);
}

function stopConsolidationTimer() {
    if (_consolidationTimer) { 
        clearInterval(_consolidationTimer); 
        _consolidationTimer = null; 
    }
    const barEl = document.getElementById('upload-progress-bar');
    if (barEl) barEl.style.width = '100%';
}

if (uploadSubmitBtn) {
    uploadSubmitBtn.addEventListener('click', async () => {
        const date  = uploadDateEl ? uploadDateEl.value : '';
        const files = filesInput ? filesInput.files : null;

        if (!date) { showAlert('Please select a report date.'); return; }
        if (!files || files.length === 0) { showAlert('Please select at least one department file.'); return; }

        showLoading(uploadSubmitBtn, uploadLoadingBtn, true);
        startConsolidationTimer();
        if (uploadResult) uploadResult.classList.add('hidden');

        const formData = new FormData();
        formData.append('report_date', date);
        for (const file of files) formData.append('files', file);

        try {
            const response = await fetch('/consolidate', {
                method: 'POST',
                body: formData,
                credentials: 'include'
            });

            if (!response.ok) {
                let detail = `Consolidation failed (HTTP ${response.status})`;
                if (response.status === 504) {
                    detail = 'Server gateway timed out (504). Render killed the connection.';
                } else if (response.status === 502) {
                    detail = 'Server is currently restarting or unavailable (502 Bad Gateway).';
                } else {
                    try {
                        const j = await response.json();
                        if (j.detail) detail = j.detail;
                        else if (j.message) detail = j.message;
                    } catch {
                        try {
                            const txt = await response.text();
                            if (txt) detail = txt.slice(0, 150);
                        } catch {}
                    }
                }
                throw new Error(detail);
            }

            const data = await response.json();
            if (data.download_url) {
                const dlRes = await fetch(data.download_url, { credentials: 'include' });
                await downloadBlobResponse(dlRes, `Master_Daily_Report_${date}.docx`);

                if (uploadResult) uploadResult.classList.remove('hidden');
                if (uploadResultMeta) uploadResultMeta.textContent = `${files.length} file(s) processed for ${date}`;
                if (uploadDownloadLink) {
                    uploadDownloadLink.href = data.download_url;
                    uploadDownloadLink.download = `Master_Daily_Report_${date}.docx`;
                }
                fetchHistory();

                // Notify user if in another tab
                document.title = `✅ Report Ready! — ${date}`;
                const resetTitle = () => {
                    document.title = _originalDocTitle;
                    window.removeEventListener('focus', resetTitle);
                };
                window.addEventListener('focus', resetTitle);

            } else {
                showAlert('Consolidation succeeded but no download URL returned.', 'error');
            }

        } catch (err) {
            showAlert(`Upload failed: ${err.message}`);
        } finally {
            stopConsolidationTimer();
            showLoading(uploadSubmitBtn, uploadLoadingBtn, false);
        }
    });
}

// ── 2. Generate from DB ────────────────────────────────────────────────────────
const dbGenerateBtn  = document.getElementById('db-generate-btn');
const dbLoadingBtn   = document.getElementById('db-loading-btn');
const dbResult       = document.getElementById('db-result');
const dbDownloadLink = document.getElementById('db-download-link');

if (dbGenerateBtn) {
    dbGenerateBtn.addEventListener('click', async () => {
        const date = dbDateEl ? dbDateEl.value : '';
        if (!date) { showAlert('Please select a report date.'); return; }

        showLoading(dbGenerateBtn, dbLoadingBtn, true);
        if (dbResult) dbResult.classList.add('hidden');

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date }),
                credentials: 'include'
            });

            // /api/generate now streams the DOCX directly
            const filename = `Master_Daily_Report_${date}.docx`;
            const blobUrl = await downloadBlobResponse(response, filename);

            if (dbResult) dbResult.classList.remove('hidden');
            if (dbDownloadLink) {
                dbDownloadLink.href = blobUrl;
                dbDownloadLink.download = filename;
            }
            fetchHistory();
        } catch (err) {
            showAlert(`Generation failed: ${err.message}`);
        } finally {
            showLoading(dbGenerateBtn, dbLoadingBtn, false);
        }
    });
}

// ── 3. Tracker ────────────────────────────────────────────────────────────────
window.fetchTrackerData = async function() {
    const trackerGrid = document.getElementById('tracker-grid');
    if (!trackerGrid) return;
    const date = trackerDateEl ? trackerDateEl.value : today;

    trackerGrid.innerHTML = '<div class="col-span-full flex justify-center py-10"><span class="material-symbols-outlined animate-spin text-primary text-3xl">refresh</span></div>';

    try {
        const res = await fetch(`/api/tracker/${date}`, { credentials: 'include' });
        if (!res.ok) { trackerGrid.innerHTML = '<div class="col-span-full py-10 text-center text-sm text-error font-medium">Failed to load tracker (auth error?)</div>'; return; }
        const data = await res.json();

        if (!data.records || data.records.length === 0) {
            trackerGrid.innerHTML = '<div class="col-span-full py-10 text-center text-sm text-on-surface-variant">No submissions found for this date.</div>';
            return;
        }

        let html = '';
        data.records.forEach(r => {
            const statusInfo = {
                draft:          { chip: 'bg-surface-container text-on-surface-variant border-outline-variant',        label: 'Draft',    dot: 'bg-on-surface-variant/40' },
                pending_review: { chip: 'bg-[#fffbeb] text-[#b45309] border-[#fde68a]',                               label: 'Pending',  dot: 'bg-[#f59e0b] animate-pulse' },
                approved:       { chip: 'bg-[#d1f4e0] text-[#0a4d2e] border-[#85f8c4]',                              label: 'Approved', dot: 'bg-[#10b981]' },
                rejected:       { chip: 'bg-error-container text-on-error-container border-error/30',                 label: 'Rejected', dot: 'bg-error' },
            }[r.status] || { chip: 'bg-surface-container text-on-surface-variant border-outline-variant', label: r.status, dot: 'bg-gray-400' };

            const canReview = (r.status === 'pending_review' || r.status === 'approved' || r.status === 'draft');
            const btnHtml = canReview
                ? `<button onclick="openReviewModal(${r.id}, '${r.department}', '${date}', '${r.status}')" class="mt-4 w-full py-2 bg-primary/5 text-primary border border-primary/20 rounded-lg text-xs font-bold hover:bg-primary hover:text-white transition-all">Review Submission</button>`
                : '';

            // Safe content preview (strip JSON if it is JSON)
            let preview = r.content || '';
            try { const parsed = JSON.parse(preview); preview = JSON.stringify(parsed, null, 2); } catch {}
            const safePreview = preview.substring(0, 120).replace(/[<>"']/g, c => ({'<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

            html += `
            <div class="bg-white p-5 rounded-xl border ${r.status === 'pending_review' ? 'border-[#fde68a]' : 'border-outline-variant/60'} shadow-sm hover:shadow-md transition-shadow flex flex-col">
                <div class="flex justify-between items-start mb-3">
                    <h4 class="font-headline font-bold text-primary text-sm">${r.department}</h4>
                    <div class="flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[9px] font-bold uppercase ${statusInfo.chip}">
                        <span class="w-1.5 h-1.5 rounded-full ${statusInfo.dot} inline-block"></span>${statusInfo.label}
                    </div>
                </div>
                <p class="text-[11px] text-on-surface-variant line-clamp-2 flex-1">${safePreview}${preview.length > 120 ? '…' : ''}</p>
                ${btnHtml}
            </div>`;
        });
        trackerGrid.innerHTML = html;
    } catch (err) {
        trackerGrid.innerHTML = `<div class="col-span-full py-10 text-center text-sm text-error">Error: ${err.message}</div>`;
    }
};

// Sync tracker date with upload/db date
if (trackerDateEl) trackerDateEl.addEventListener('change', fetchTrackerData);

// ── Modal ─────────────────────────────────────────────────────────────────────
let currentReviewId   = null;
let currentReviewDept = null;
let currentReviewDate = null;

window.openReviewModal = function(id, dept, date, status) {
    currentReviewId   = id;
    currentReviewDept = dept;
    currentReviewDate = date;

    document.getElementById('modal-dept').textContent = dept;
    document.getElementById('modal-date').textContent = date;

    // Load content
    const contentArea = document.getElementById('modal-content-area');
    contentArea.innerHTML = '<p style="color:#64748b">Loading...</p>';

    fetch(`/api/tracker/${date}`, { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
            const record = data.records?.find(r => r.id === id);
            if (!record) { contentArea.innerHTML = '<p>Record not found.</p>'; return; }
            let content = record.content || '(empty)';

            // Try to parse as structured JSON and render human-readable tables
            try {
                const parsed = JSON.parse(content);
                if (parsed && parsed.sections && Array.isArray(parsed.sections)) {
                    contentArea.innerHTML = renderSectionsAsHTML(parsed.sections);
                    return;
                }
            } catch {}

            // Fallback: show as plain text
            contentArea.textContent = content;
        })
        .catch(() => { contentArea.innerHTML = '<p>Failed to load content.</p>'; });

    // Button states
    const approveBtn = document.getElementById('modal-approve-btn');
    const rejectBtn  = document.getElementById('modal-reject-btn');
    if (status === 'approved') {
        approveBtn.disabled = true;
        approveBtn.classList.add('opacity-50', 'cursor-not-allowed');
    } else {
        approveBtn.disabled = false;
        approveBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    }

    document.getElementById('review-modal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
};

window.closeReviewModal = function() {
    currentReviewId = null;
    document.getElementById('review-modal').classList.add('hidden');
    document.body.style.overflow = '';
};

// Wire modal buttons
const modalApproveBtn = document.getElementById('modal-approve-btn');
const modalRejectBtn  = document.getElementById('modal-reject-btn');

if (modalApproveBtn) modalApproveBtn.addEventListener('click', () => submitReviewAction('approved'));
if (modalRejectBtn)  modalRejectBtn.addEventListener('click',  () => submitReviewAction('draft'));

async function submitReviewAction(status) {
    if (!currentReviewId) return;
    try {
        const res = await fetch('/api/tracker/review', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ id: currentReviewId, status })
        });
        if (!res.ok) { const j = await res.json(); throw new Error(j.detail || 'Update failed'); }
        closeReviewModal();
        fetchTrackerData();
        showAlert(`Submission ${status === 'approved' ? 'approved' : 'sent back'} successfully.`, 'success');
    } catch (err) {
        showAlert(`Failed to update status: ${err.message}`);
    }
}

// ── 4. History Sidebar ────────────────────────────────────────────────────────
async function fetchHistory() {
    const historyList = document.getElementById('history-list');
    if (!historyList) return;

    try {
        const res  = await fetch('/api/history', { credentials: 'include' });
        const data = await res.json();

        historyList.innerHTML = '';
        if (!data.dates || data.dates.length === 0) {
            historyList.innerHTML = '<div class="text-xs text-on-surface-variant text-center py-6">No records yet.</div>';
            return;
        }

        data.dates.forEach(date => {
            const div = document.createElement('div');
            div.className = 'flex items-center justify-between px-3 py-2.5 rounded-xl border border-outline-variant/30 bg-white hover:border-primary/30 cursor-pointer group transition-all';
            div.onclick = () => {
                if (trackerDateEl) trackerDateEl.value = date;
                fetchTrackerData();
            };
            div.innerHTML = `
                <div class="flex items-center gap-3">
                    <div class="w-7 h-7 rounded-full bg-secondary-container flex items-center justify-center shrink-0">
                        <span class="material-symbols-outlined text-on-secondary-container text-[14px]">calendar_today</span>
                    </div>
                    <span class="text-xs font-semibold text-on-surface">${date}</span>
                </div>
                <button title="Delete" onclick="event.stopPropagation(); deleteRecord('${date}')"
                    class="p-1.5 rounded-md text-outline hover:text-error hover:bg-error-container transition opacity-0 group-hover:opacity-100 flex items-center">
                    <span class="material-symbols-outlined text-[16px]">delete</span>
                </button>`;
            historyList.appendChild(div);
        });
    } catch {
        document.getElementById('history-list').innerHTML = '<div class="text-xs text-error text-center py-4">Error loading records.</div>';
    }
}

window.deleteRecord = async function(date) {
    if (!confirm(`Delete all submissions for ${date}?`)) return;
    try {
        const res = await fetch(`/api/history/${date}`, { method: 'DELETE', credentials: 'include' });
        if (res.ok) { fetchHistory(); fetchTrackerData(); showAlert(`Records for ${date} deleted.`, 'success'); }
        else showAlert('Failed to delete record.');
    } catch { showAlert('Network error while deleting.'); }
};

// ── 5. Monthly (stub) ─────────────────────────────────────────────────────────
const monthlyBtn        = document.getElementById('monthly-btn');
const monthlyLoadingBtn = document.getElementById('monthly-loading-btn');

if (monthlyBtn) {
    monthlyBtn.addEventListener('click', async () => {
        showLoading(monthlyBtn, monthlyLoadingBtn, true);
        try {
            const res = await fetch('/api/monthly', { method: 'POST', credentials: 'include' });
            const data = await res.json();
            showAlert(data.message || 'Monthly report not yet implemented.', 'error');
        } catch { showAlert('Monthly report generation failed.'); }
        finally { showLoading(monthlyBtn, monthlyLoadingBtn, false); }
    });
}

// ── Render Sections as Human-Readable HTML ────────────────────────────────────
function renderSectionsAsHTML(sections) {
    let html = '';
    sections.forEach(sec => {
        const title = sec.title || 'Untitled Section';
        html += `<div style="margin-bottom:24px;">`;
        html += `<h3 style="font-family:Manrope,sans-serif;font-size:15px;font-weight:700;color:#002045;margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">${escapeHTML(title)}</h3>`;

        if (sec.nil) {
            html += `<p style="color:#94a3b8;font-style:italic;font-size:13px;">Nil</p>`;
        } else if (!sec.rows || sec.rows.length === 0) {
            html += `<p style="color:#94a3b8;font-style:italic;font-size:13px;">No entries</p>`;
        } else {
            // Build a table from rows
            const headers = Object.keys(sec.rows[0]);
            html += `<table style="width:100%;border-collapse:collapse;font-size:13px;background:#fff;">`;
            html += `<thead><tr>`;
            headers.forEach(h => {
                html += `<th style="background:#f8fafc;color:#475569;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;padding:10px 12px;text-align:left;border-bottom:2px solid #e2e8f0;white-space:nowrap;">${escapeHTML(h)}</th>`;
            });
            html += `</tr></thead><tbody>`;
            sec.rows.forEach(row => {
                html += `<tr>`;
                headers.forEach(h => {
                    const val = row[h] || '';
                    html += `<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;color:#334155;vertical-align:top;">${escapeHTML(val) || '<span style="color:#cbd5e1">—</span>'}</td>`;
                });
                html += `</tr>`;
            });
            html += `</tbody></table>`;
        }
        html += `</div>`;
    });
    return html;
}

function escapeHTML(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
fetchHistory();
fetchTrackerData();
