document.addEventListener('DOMContentLoaded', async () => {
    const submitBtn = document.getElementById('submit-dept-btn');
    const saveDraftBtn = document.getElementById('save-draft-btn');
    const dateInput = document.getElementById('dept-date');
    const statusChip = document.getElementById('save-status-chip');
    
    dateInput.valueAsDate = new Date();

    const deptCode = localStorage.getItem('dept_code') || "cse";
    const deptTitle = document.getElementById('sidebar-dept-name');
    const mainTitle = document.getElementById('main-dept-title');
    const formatBadge = document.getElementById('dept-format-badge');

    if (deptTitle) deptTitle.innerText = `${deptCode.toUpperCase()} Dept`;
    if (mainTitle) mainTitle.innerText = `${deptCode.toUpperCase()} Daily Report`;

    let activeSchema = null;

    // ─── Fetch Department Schema ────────────────────────────────
    async function loadAndRenderFormat() {
        try {
            const response = await fetch(`/api/formats/${deptCode}`);
            const schema = await response.json();
            if (schema && schema.format) {
                activeSchema = schema;
                if (formatBadge) {
                    if (schema.departments && schema.departments.length > 0) {
                        formatBadge.innerText = `Fixed Schema: ${schema.departments.join(', ')}`;
                    } else {
                        formatBadge.innerText = `Fixed Format Schema (${deptCode.toUpperCase()})`;
                    }
                }
                renderFormat(schema.format);
            }
        } catch(e) {
            console.error("Failed to fetch schema", e);
        }
    }

    const icons = ['groups', 'engineering', 'event', 'person', 'school', 'transfer_within_a_station', 'swap_horiz', 'warning', 'assignment'];
    const colors = ['blue', 'orange', 'purple', 'teal', 'indigo', 'emerald', 'amber', 'red', 'slate'];

    function renderFormat(sections) {
        const nav = document.getElementById('section-nav');
        const editor = document.getElementById('table-editor');
        
        let navHTML = `<p class="px-4 text-[10px] font-bold text-on-surface-variant uppercase tracking-widest mb-3">Report Sections</p>`;
        let editorHTML = '';

        sections.forEach((sec, idx) => {
            const icon = icons[idx % icons.length];
            const color = colors[idx % colors.length];
            const title = sec.section_title || `Section ${idx + 1}`;
            const cols = sec.columns || [];
            
            navHTML += `
                <a href="#section-${idx}" class="nav-link flex items-center space-x-3 px-4 py-2.5 text-slate-600 hover:bg-surface-container-high transition-colors rounded-md text-[13px]">
                    <span class="material-symbols-outlined text-[18px]">${icon}</span>
                    <span class="truncate" title="${title}">${title.replace(':', '').substring(0, 22)}</span>
                </a>
            `;

            // Special table layout check
            const titleLower = title.toLowerCase();
            const isBatchPills = titleLower.includes('batch pills');
            const isStaffAttendance = titleLower.includes('staff attendance');
            const isStudentAttendance = titleLower.includes('students attendance') || titleLower.includes('b.tech students') || titleLower.includes('m.tech students');

            let thead = '';
            let tbody = '';

            if (isBatchPills) {
                // Horizontal Branch Pills table
                thead = cols.map(c => `<th>${c}</th>`).join('');
                tbody = `<tr>${cols.map(c => `<td><input type="number" class="form-input text-center font-bold" data-col="${c}" placeholder="0"></td>`).join('')}</tr>`;
            } else {
                thead = cols.map((col, i) => i === 0 ? `<th class="w-14">${col}</th>` : `<th>${col}</th>`).join('');
                
                // Initial rows generator
                let initialRows = [];
                if (isStaffAttendance) {
                    initialRows = [
                        { "Category": "Teaching" },
                        { "Category": "Non-Teaching" }
                    ];
                } else if (isStudentAttendance) {
                    initialRows = [
                        { "Year": "I Year" },
                        { "Year": "II Year" },
                        { "Year": "III Year" },
                        { "Year": "IV Year" }
                    ];
                } else {
                    initialRows = [{}];
                }

                tbody = initialRows.map((preset, rIdx) => {
                    return `<tr>` + cols.map((col, cIdx) => {
                        if (cIdx === 0) return `<td class="sno-cell">${rIdx + 1}</td>`;
                        const presetVal = preset[col] || '';
                        if (presetVal) {
                            return `<td><input type="text" class="form-input font-semibold bg-slate-50" value="${presetVal}" readonly></td>`;
                        }
                        return `<td>${getInputHTML(col, deptCode)}</td>`;
                    }).join('') + `</tr>`;
                }).join('');
            }

            editorHTML += `
            <div class="section-card" id="section-${idx}" data-section-idx="${idx}">
                <div class="section-header" onclick="toggleSection(this)">
                    <div class="flex items-center gap-3">
                        <div class="section-icon bg-${color}-50 text-${color}-600">
                            <span class="material-symbols-outlined text-[20px]">${icon}</span>
                        </div>
                        <div>
                            <h3 class="font-headline font-bold text-base text-on-surface">${title}</h3>
                        </div>
                    </div>
                    <div class="flex items-center gap-3">
                        <label class="nil-toggle" onclick="event.stopPropagation()">
                            <input type="checkbox" class="nil-checkbox" data-section="${idx}">
                            <span class="nil-label">Nil</span>
                        </label>
                        <span class="material-symbols-outlined section-chevron text-on-surface-variant transition-transform">expand_more</span>
                    </div>
                </div>
                <div class="section-body">
                    <div class="table-wrapper overflow-x-auto">
                        <table class="report-table w-full" data-section="${idx}">
                            <thead>
                                <tr>${thead}</tr>
                            </thead>
                            <tbody>
                                ${tbody}
                            </tbody>
                        </table>
                    </div>
                    ${!isBatchPills && !isStaffAttendance && !isStudentAttendance ? `
                    <div class="table-actions mt-3 flex gap-2">
                        <button class="add-row-btn px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded flex items-center gap-1" onclick="addRow(this)">
                            <span class="material-symbols-outlined text-[16px]">add</span> Add Row
                        </button>
                        <button class="remove-row-btn px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-700 text-xs font-bold rounded flex items-center gap-1" onclick="removeRow(this)">
                            <span class="material-symbols-outlined text-[16px]">remove</span> Remove
                        </button>
                    </div>` : ''}
                </div>
            </div>`;
        });

        nav.innerHTML = navHTML;
        editor.innerHTML = editorHTML;
        
        initInteractions();
        loadSubmissionForDate();
    }

    function initInteractions() {
        document.querySelectorAll('.nil-checkbox').forEach(cb => {
            updateNilState(cb);
            cb.addEventListener('change', () => updateNilState(cb));
        });

        const sections = document.querySelectorAll('.section-card');
        const navLinks = document.querySelectorAll('.nav-link');

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    navLinks.forEach(l => l.classList.remove('active'));
                    const id = entry.target.id;
                    const link = document.querySelector(`.nav-link[href="#${id}"]`);
                    if (link) link.classList.add('active');
                }
            });
        }, { threshold: 0, rootMargin: '-20% 0px -40% 0px' });

        sections.forEach(s => observer.observe(s));

        navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const target = document.querySelector(link.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        });

        // Auto-resizing for textareas
        document.addEventListener('input', function(e) {
            if (e.target.tagName.toLowerCase() === 'textarea' && e.target.classList.contains('auto-resize')) {
                e.target.style.height = 'auto';
                e.target.style.height = (e.target.scrollHeight) + 'px';
            }
        });
    }

    // Initialize Schema fetching and building
    await loadAndRenderFormat();

    // ─── Save/Submit Handlers ───────────────────────────────────
    async function sendToServer(statusVal) {
        const dateVal = dateInput.value;

        if (!dateVal) {
            alert('Please select a report date.');
            return;
        }

        const payload = collectAllData();
        statusChip.innerText = "Processing...";

        try {
            const response = await fetch('/api/department/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    date: dateVal,
                    content: JSON.stringify(payload),
                    status: statusVal
                })
            });

            if (response.ok) {
                if (statusVal === 'draft') {
                    statusChip.innerText = "Draft Saved";
                    statusChip.parentNode.className = "flex items-center gap-2 bg-[#f0fdf4] px-4 py-2 rounded-full border border-[#bbf7d0]";
                    statusChip.className = "text-xs font-bold text-[#166534] uppercase tracking-widest";
                } else if (statusVal === 'pending_review') {
                    statusChip.innerText = "Submitted";
                    statusChip.parentNode.className = "flex items-center gap-2 bg-[#eef4ff] px-4 py-2 rounded-full border border-[#bfdbfe]";
                    statusChip.className = "text-xs font-bold text-[#1e40af] uppercase tracking-widest";
                    alert('Report submitted successfully to PA Office for review!');
                }
            } else {
                const err = await response.json();
                alert('Error: ' + (err.detail || err.error));
                statusChip.innerText = "Failed";
            }
        } catch (error) {
            console.error(error);
            alert('Network Error occurred.');
            statusChip.innerText = "Error";
        }
    }

    submitBtn.addEventListener('click', () => sendToServer('pending_review'));
    saveDraftBtn.addEventListener('click', () => sendToServer('draft'));

    // ─── Collect All Table Data ─────────────────────────────────
    function collectAllData() {
        const sectionsData = [];
        let reportTextLines = [];

        document.querySelectorAll('.section-card').forEach(card => {
            const title = card.querySelector('.section-header h3')?.innerText || '';
            const nilCheckbox = card.querySelector('.nil-checkbox');
            const isNil = nilCheckbox ? nilCheckbox.checked : false;

            const secObj = {
                title: title,
                nil: isNil,
                rows: []
            };

            reportTextLines.push(`[${title}]`);

            if (isNil) {
                reportTextLines.push("Nil\n");
            } else {
                const table = card.querySelector('.report-table');
                if (table) {
                    const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.innerText.trim());
                    const rows = table.querySelectorAll('tbody tr');

                    let tableTextRows = [];

                    rows.forEach(row => {
                        const rowData = {};
                        const cells = row.querySelectorAll('td');
                        cells.forEach((cell, idx) => {
                            const headerName = headers[idx] || `Col${idx+1}`;
                            if (cell.classList.contains('sno-cell')) {
                                rowData[headerName] = cell.innerText.trim();
                            } else {
                                const input = cell.querySelector('input, textarea');
                                if (input) {
                                    rowData[headerName] = input.value.trim();
                                }
                            }
                        });

                        const hasData = Object.entries(rowData).some(([k, v]) => !k.toLowerCase().includes('s.no') && v !== '');
                        if (hasData) {
                            secObj.rows.push(rowData);
                            tableTextRows.push(headers.map(h => rowData[h] || '').join(' | '));
                        }
                    });

                    if (secObj.rows.length === 0) {
                        reportTextLines.push("Nil\n");
                    } else {
                        reportTextLines.push(headers.join(' | '));
                        reportTextLines.push(...tableTextRows);
                        reportTextLines.push("");
                    }
                }
            }

            sectionsData.push(secObj);
        });

        return {
            sections: sectionsData,
            text: reportTextLines.join('\n').trim()
        };
    }

    // ─── Fetch Submission for Date ──────────────────────────────
    async function loadSubmissionForDate() {
        const dateVal = dateInput.value;
        if (!dateVal) return;

        try {
            const resp = await fetch(`/api/department/submission/${dateVal}`);
            if (!resp.ok) return;
            const data = await resp.json();

            if (!data || !data.content) {
                resetForm();
                return;
            }

            let statusText = (data.status || 'draft').toUpperCase();
            statusChip.innerText = statusText;

            let parsed = null;
            if (typeof data.content === 'string' && data.content.trim().startsWith('{')) {
                try { parsed = JSON.parse(data.content); } catch(e) {}
            }

            if (parsed && parsed.sections) {
                populateFormFromSections(parsed.sections);
            }
        } catch (e) {
            console.warn('Failed to load submission for date:', e);
        }
    }

    function populateFormFromSections(sections) {
        sections.forEach((sec, idx) => {
            const card = document.querySelector(`.section-card[data-section-idx="${idx}"]`);
            if (!card) return;

            const nilCb = card.querySelector('.nil-checkbox');
            if (nilCb) {
                nilCb.checked = sec.nil;
                updateNilState(nilCb);
            }

            if (!sec.nil && sec.rows && sec.rows.length > 0) {
                const table = card.querySelector('.report-table');
                const tbody = table?.querySelector('tbody');
                if (!tbody) return;

                const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.innerText.trim());
                
                // Clear extra dynamic rows beyond presets
                const existingRows = tbody.querySelectorAll('tr');
                if (sec.rows.length > existingRows.length) {
                    for (let r = existingRows.length; r < sec.rows.length; r++) {
                        const newTr = createRowFromHeaders(headers, r + 1);
                        tbody.appendChild(newTr);
                    }
                }

                const currentTrs = tbody.querySelectorAll('tr');
                sec.rows.forEach((rowData, rIdx) => {
                    if (currentTrs[rIdx]) {
                        headers.forEach((h, cIdx) => {
                            const td = currentTrs[rIdx].children[cIdx];
                            if (td) {
                                const input = td.querySelector('input, textarea');
                                if (input && rowData[h] !== undefined) {
                                    input.value = rowData[h];
                                }
                            }
                        });
                    }
                });
            }
        });
    }

    function createRowFromHeaders(headers, sno) {
        const tr = document.createElement('tr');
        headers.forEach((header, idx) => {
            const td = document.createElement('td');
            if (idx === 0) {
                td.className = 'sno-cell';
                td.textContent = sno;
            } else {
                td.innerHTML = getInputHTML(header, deptCode);
            }
            tr.appendChild(td);
        });
        return tr;
    }

    function resetForm() {
        document.querySelectorAll('.nil-checkbox').forEach(cb => {
            cb.checked = false;
            updateNilState(cb);
        });
        document.querySelectorAll('.report-table tbody input, .report-table tbody textarea').forEach(inp => {
            if (!inp.readOnly) inp.value = '';
        });
    }

    dateInput.addEventListener('change', () => {
        statusChip.innerText = "Drafting";
        statusChip.parentNode.className = "flex items-center gap-2 bg-[#fffbeb] px-4 py-2 rounded-full border border-[#fde68a]";
        statusChip.className = "text-xs font-bold text-[#b45309] uppercase tracking-widest";
        loadSubmissionForDate();
    });
});


// ═══════════════════════════════════════════════════════════
// GLOBAL FUNCTIONS (called from onclick in HTML)
// ═══════════════════════════════════════════════════════════

function toggleSection(headerEl) {
    const card = headerEl.closest('.section-card');
    card.classList.toggle('collapsed');
}

function updateNilState(checkbox) {
    const card = checkbox.closest('.section-card');
    if (checkbox.checked) {
        card.classList.add('nil-active');
    } else {
        card.classList.remove('nil-active');
    }
}

function addRow(button) {
    const card = button.closest('.section-card');
    const tbody = card.querySelector('.report-table tbody');
    const thead = card.querySelector('.report-table thead');
    if (!tbody || !thead) return;

    const headers = Array.from(thead.querySelectorAll('th')).map(th => th.innerText.trim());
    const colCount = headers.length;
    const rowCount = tbody.querySelectorAll('tr').length;
    const newRow = document.createElement('tr');
    const deptName = localStorage.getItem('dept_code') || "CSE";

    for (let i = 0; i < colCount; i++) {
        const td = document.createElement('td');
        if (i === 0) {
            td.className = 'sno-cell';
            td.textContent = rowCount + 1;
        } else {
            td.innerHTML = getInputHTML(headers[i], deptName);
        }
        newRow.appendChild(td);
    }

    newRow.style.animation = 'slideDown 0.2s ease';
    tbody.appendChild(newRow);
    
    const firstInput = newRow.querySelector('input');
    if (firstInput) firstInput.focus();
}

function removeRow(button) {
    const card = button.closest('.section-card');
    const tbody = card.querySelector('.report-table tbody');
    if (!tbody) return;

    const rows = tbody.querySelectorAll('tr');
    if (rows.length <= 1) return;

    const lastRow = rows[rows.length - 1];
    lastRow.style.animation = 'fadeOut 0.15s ease';
    setTimeout(() => {
        lastRow.remove();
        renumberRows(tbody);
    }, 150);
}

function renumberRows(tbody) {
    const rows = tbody.querySelectorAll('tr');
    rows.forEach((row, idx) => {
        const snoCell = row.querySelector('.sno-cell');
        if (snoCell) snoCell.textContent = idx + 1;
    });
}

function getInputHTML(colName, dept) {
    let name = colName.toLowerCase();
    let placeholder = getPlaceholderStr(colName, dept);
    
    if (name === 'reported on' || name === 'attended on' || name === 'completed on' || name.includes('date of joining') || name === 'date') {
        return `<input type="date" class="form-input">`;
    }
    
    if (name.includes('rolls') || name.includes('absent') || name.includes('participants') || name.includes('no’s') || name.includes('no. of')) {
        return `<input type="number" class="form-input text-center" placeholder="${placeholder}">`;
    }
    
    if (name.includes('remarks') || name.includes('details') || name.includes('problem') || name.includes('statement') || name.includes('description') || name.includes('event')) {
        return `<textarea rows="1" class="form-input auto-resize" placeholder="${placeholder}"></textarea>`;
    }
    
    return `<input type="text" class="form-input" placeholder="${placeholder}">`;
}

function getPlaceholderStr(colName, dept) {
    let text = colName.toLowerCase();
    if (text.includes('dept') || text.includes('department')) return "e.g. " + dept.toUpperCase();
    if (text.includes('category')) return "Teaching / Non";
    if (text.includes('rolls') || text.includes('absent') || text.includes('participants')) return "0";
    if (text.includes('name')) return "e.g. Dr. A. Sharma";
    if (text.includes('remarks') || text.includes('details')) return "Brief notes...";
    if (text.includes('problem')) return "e.g. AC not working in Lab";
    if (text.includes('reported') || text.includes('attended') || text.includes('completed')) return "DD/MM/YYYY";
    if (text.includes('event')) return "e.g. Workshop on AI";
    if (text.includes('duration') && !text.includes('date')) return "e.g. 2 Days";
    if (text.includes('whom')) return "e.g. III Year";
    if (text.includes('resource person')) return "e.g. Dr. Srinivas";
    if (text.includes('status')) return "e.g. Presenter";
    if (text.includes('date and duration')) return "e.g. 19-20 Apr";
    if (text.includes('designation')) return "e.g. Asst. Prof";
    if (text.includes('joining/leaving') || text.includes('date of joining')) return "e.g. Joined 15th April";
    if (text.includes('subject')) return "e.g. Data Structures";
    if (text.includes('time')) return "e.g. 10:00 - 11:00 AM";
    if (text.includes('adjusted')) return "e.g. Dr. Reddy";
    if (text.includes('r. no') || text.includes('id no')) return "e.g. 21A21A0501";
    if (text.includes('brief statement')) return "Describe incident";
    return "Enter " + colName.replace(/[^a-zA-Z ]/g, "").trim();
}
