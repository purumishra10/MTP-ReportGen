document.addEventListener('DOMContentLoaded', () => {
    const archiveList = document.getElementById('archive-list');
    const emptyState = document.getElementById('empty-state');
    const reportDetails = document.getElementById('report-details');
    const reportBody = document.getElementById('report-body');
    const reportTitle = document.getElementById('report-title');
    const reportRef = document.getElementById('report-ref');
    const downloadBtn = document.getElementById('download-report-btn');
    const roleTag = document.getElementById('role-tag');

    // Update role tag
    const role = localStorage.getItem('user_role');
    if (role) roleTag.innerText = role.charAt(0).toUpperCase() + role.slice(1);

    // Back to Dashboard button - role-aware navigation
    const backBtn = document.getElementById('back-to-dashboard-btn');
    if (backBtn) {
        backBtn.addEventListener('click', () => {
            if (role === 'pa') {
                window.location.href = 'pa-dashboard.html';
            } else if (role === 'principal') {
                window.location.href = 'principal.html';
            } else {
                window.location.href = 'pa-dashboard.html';
            }
        });
    }

    fetchArchive();

    async function fetchArchive() {
        try {
            const res = await fetch('/api/history', { credentials: 'include' });
            const data = await res.json();
            
            if (data.dates && data.dates.length > 0) {
                archiveList.innerHTML = data.dates.map(date => `
                    <div onclick="loadReport('${date}')" class="flex items-center justify-between px-4 py-4 text-secondary hover:bg-white hover:shadow-sm rounded-lg transition-all cursor-pointer group">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-sm">calendar_today</span>
                            <span class="font-bold text-sm font-headline">${date}</span>
                        </div>
                        <span class="text-[10px] font-bold uppercase tracking-widest text-primary opacity-0 group-hover:opacity-100 transition-opacity">View</span>
                    </div>
                `).join('');
            } else {
                archiveList.innerHTML = '<p class="text-xs text-secondary/50 text-center py-10">No reports archived.</p>';
            }
        } catch (e) {
            console.error(e);
        }
    }

    window.loadReport = async (date) => {
        try {
            emptyState.classList.add('hidden');
            reportDetails.classList.remove('hidden');
            reportTitle.innerText = `Master Consolidated Institutional Report - ${date}`;
            reportRef.innerText = `REF: ARCH-${date.replace(/-/g, '')}`;

            // Fetch Summary
            let summaryData = {};
            try {
                const summaryRes = await fetch(`/api/principal/summary/${date}`, { credentials: 'include' });
                if (summaryRes.ok) {
                    const data = await summaryRes.json();
                    summaryData = data.record ? { summary: data.record.content } : {};
                }
            } catch (e) { console.error('No summary found'); }

            // Fetch Approved Records
            const recordsRes = await fetch(`/api/tracker/${date}`, { credentials: 'include' });
            const recordsData = await recordsRes.json();

            let contentHtml = '';

            // 1. Executive Summary
            if (summaryData.summary) {
                contentHtml += `
                    <section>
                        <h3 class="font-headline text-xl font-bold text-primary mb-4">I. Executive Summary</h3>
                        <div class="prose prose-slate max-w-none">${summaryData.summary}</div>
                    </section>
                `;
            }

            // 2. Departmental Progress
            const approved = recordsData.records ? recordsData.records.filter(r => r.status === 'approved') : [];
            if (approved.length > 0) {
                contentHtml += `
                    <section>
                        <h3 class="font-headline text-xl font-bold text-primary mb-4">II. Departmental Performance</h3>
                        <div class="space-y-6">
                            ${approved.map(r => `
                                <div>
                                    <h4 class="font-headline font-bold text-primary/80 mb-2">${r.department}</h4>
                                    <div class="text-sm border-l-2 border-surface-container-high pl-4">${formatRecordContent(r.content)}</div>
                                </div>
                            `).join('')}
                        </div>
                    </section>
                `;
            }

            if (!contentHtml) {
                contentHtml = '<p class="text-center py-20 text-secondary italic">No finalized content available for this report.</p>';
            }

            reportBody.innerHTML = contentHtml;

            // Update Download Button — /api/generate now streams DOCX directly
            downloadBtn.onclick = async () => {
                try {
                    const res = await fetch('/api/generate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({ date })
                    });
                    if (!res.ok) {
                        const j = await res.json();
                        alert(`Error: ${j.detail || 'Failed to generate report'}`);
                        return;
                    }
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `Master_Report_${date}.docx`;
                    a.style.display = 'none';
                    document.body.appendChild(a);
                    a.click();
                    URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                } catch (e) {
                    alert(`Download error: ${e.message}`);
                }
            };

        } catch (e) {
            console.error(e);
        }
    };

    function formatRecordContent(content) {
        if (!content) return '<span class="italic text-secondary">Empty</span>';
        try {
            const parsed = JSON.parse(content);
            if (parsed && parsed.sections) {
                return parsed.sections.map(sec => {
                    const title = escapeHTML(sec.title || '');
                    if (sec.nil) return `<p><strong>${title}</strong> — Nil</p>`;
                    const n = (sec.rows || []).length;
                    return `<p><strong>${title}</strong> — ${n} row(s)</p>`;
                }).join('');
            }
        } catch {}
        return `<pre class="whitespace-pre-wrap text-xs">${escapeHTML(String(content).slice(0, 2000))}</pre>`;
    }

    function escapeHTML(str) {
        return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
});
