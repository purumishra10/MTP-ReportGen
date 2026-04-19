document.addEventListener('DOMContentLoaded', async () => {
    const submitBtn = document.getElementById('submit-dept-btn');
    const saveDraftBtn = document.getElementById('save-draft-btn');
    const editorCanvas = document.getElementById('editor-canvas');
    const dateInput = document.getElementById('dept-date');
    const statusChip = document.getElementById('save-status-chip');
    
    dateInput.valueAsDate = new Date();

    // Dynamically set department name from login
    const deptName = localStorage.getItem('dept_code') || "CSE";
    const deptTitle = document.getElementById('sidebar-dept-name');
    if (deptTitle) deptTitle.innerText = `${deptName} Dept`;

    // Exceptional departments logic (from user prompt)
    // For English, Library, MTP, Staff Attendance, Staff Student Attendance, Chemistry
    // we use their specific schemas dynamically!
    async function loadAndRenderFormat() {
        try {
            const response = await fetch(`/api/formats/${deptName}`);
            const schema = await response.json();
            if (schema && schema.format) {
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
        
        let navHTML = `<p class="px-4 text-[10px] font-bold text-on-surface-variant uppercase tracking-widest mb-3">Sections</p>`;
        let editorHTML = '';

        sections.forEach((sec, idx) => {
            const icon = icons[idx % icons.length];
            const color = colors[idx % colors.length];
            
            navHTML += `
                <a href="#section-${idx}" class="nav-link flex items-center space-x-3 px-4 py-2.5 text-slate-600 hover:bg-surface-container-high transition-colors rounded-md text-[13px]">
                    <span class="material-symbols-outlined text-[18px]">${icon}</span>
                    <span class="truncate" title="${sec.section_title}">${sec.section_title.replace(':', '').substring(0, 22)}</span>
                </a>
            `;



            function getInputHTML(colName, dept) {
                let name = colName.toLowerCase();
                let placeholder = getPlaceholderStr(colName, dept);
                
                // Dates
                if (name === 'reported on' || name === 'attended on' || name === 'completed on' || name.includes('date of joining') || name === 'date') {
                    return `<input type="date" class="form-input">`;
                }
                
                // Numbers
                if (name.includes('rolls') || name.includes('absent') || name.includes('participants')) {
                    return `<input type="number" class="form-input text-center" placeholder="${placeholder}">`;
                }
                
                // Long Text Blocks
                if (name.includes('remarks') || name.includes('details') || name.includes('problem') || name.includes('statement') || name.includes('description') || name.includes('event')) {
                    return `<textarea rows="1" class="form-input auto-resize" placeholder="${placeholder}"></textarea>`;
                }
                
                // Default text
                return `<input type="text" class="form-input" placeholder="${placeholder}">`;
            }

            let thead = sec.columns.map((col, i) => i === 0 ? `<th class="w-14">S.No</th>` : `<th>${col}</th>`).join('');
            let tbody = sec.columns.map((col, i) => i === 0 ? `<td class="sno-cell">1</td>` : `<td>${getInputHTML(col, deptName)}</td>`).join('');

            editorHTML += `
            <div class="section-card" id="section-${idx}">
                <div class="section-header" onclick="toggleSection(this)">
                    <div class="flex items-center gap-3">
                        <div class="section-icon bg-${color}-50 text-${color}-600">
                            <span class="material-symbols-outlined text-[20px]">${icon}</span>
                        </div>
                        <div>
                            <h3 class="font-headline font-bold text-base text-on-surface">${sec.section_title}</h3>
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
                    <div class="table-wrapper">
                        <table class="report-table" data-section="${idx}">
                            <thead>
                                <tr>${thead}</tr>
                            </thead>
                            <tbody>
                                <tr>${tbody}</tr>
                            </tbody>
                        </table>
                    </div>
                    <div class="table-actions">
                        <button class="add-row-btn" onclick="addRow(this)">
                            <span class="material-symbols-outlined text-[16px]">add</span> Add Row
                        </button>
                        <button class="remove-row-btn" onclick="removeRow(this)">
                            <span class="material-symbols-outlined text-[16px]">remove</span> Remove
                        </button>
                    </div>
                </div>
            </div>`;
        });
        
        navHTML += `<div class="h-px bg-outline-variant/30 my-3"></div>
            <a href="#section-notes" class="nav-link flex items-center space-x-3 px-4 py-2.5 text-slate-600 hover:bg-surface-container-high transition-colors rounded-md text-[13px]">
                <span class="material-symbols-outlined text-[18px]">edit_note</span>
                <span>Additional Notes</span>
            </a>`;

        nav.innerHTML = navHTML;
        editor.innerHTML = editorHTML;
        
        initInteractions();
        loadDraft();
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
        const dept = deptName;

        if (!dateVal) {
            alert('Please select a report date.');
            return;
        }

        const content = collectAllData();
        statusChip.innerText = "Processing...";

        try {
            const response = await fetch('/api/department/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    date: dateVal,
                    content: JSON.stringify(content),
                    status: statusVal
                })
            });

            if (response.ok) {
                if (statusVal === 'draft') {
                    statusChip.innerText = "Draft Saved";
                    statusChip.parentNode.className = "flex items-center gap-2 bg-[#f0fdf4] px-4 py-2 rounded-full border border-[#bbf7d0]";
                    statusChip.className = "text-xs font-bold text-[#166534] uppercase tracking-widest";
                    // Also save locally
                    saveDraftLocally(content);
                } else if (statusVal === 'pending_review') {
                    statusChip.innerText = "Submitted";
                    statusChip.parentNode.className = "flex items-center gap-2 bg-[#eef4ff] px-4 py-2 rounded-full border border-[#bfdbfe]";
                    statusChip.className = "text-xs font-bold text-[#1e40af] uppercase tracking-widest";
                    alert('Submitted for PA Review!');
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
        const data = { sections: [], notes: '' };

        document.querySelectorAll('.section-card').forEach(card => {
            if (card.id === 'section-notes') return;

            const title = card.querySelector('.section-header h3')?.innerText || '';
            const nilCheckbox = card.querySelector('.nil-checkbox');
            const isNil = nilCheckbox ? nilCheckbox.checked : false;

            const sectionData = {
                title: title,
                nil: isNil,
                rows: []
            };

            if (!isNil) {
                const table = card.querySelector('.report-table');
                if (table) {
                    const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.innerText.trim());
                    const rows = table.querySelectorAll('tbody tr');

                    rows.forEach(row => {
                        const rowData = {};
                        const cells = row.querySelectorAll('td');
                        cells.forEach((cell, idx) => {
                            if (idx === 0) {
                                rowData[headers[0]] = cell.innerText.trim();
                            } else {
                                const input = cell.querySelector('input, textarea');
                                if (input) {
                                    rowData[headers[idx]] = input.value.trim();
                                }
                            }
                        });

                        // Only include row if at least one non-sno field has data
                        const hasData = Object.entries(rowData).some(([k, v]) => k !== headers[0] && v !== '');
                        if (hasData) {
                            sectionData.rows.push(rowData);
                        }
                    });
                }
            }

            data.sections.push(sectionData);
        });

        // Collect free-text notes
        if (editorCanvas) {
            data.notes = editorCanvas.innerHTML.trim();
        }

        return data;
    }

    // ─── Local Draft Save/Load ──────────────────────────────────
    function saveDraftLocally(data) {
        const key = `draft_${deptName}_${dateInput.value}`;
        localStorage.setItem(key, JSON.stringify(data));
    }

    function loadDraft() {
        const key = `draft_${deptName}_${dateInput.value}`;
        const saved = localStorage.getItem(key);
        if (!saved) return;

        try {
            const data = JSON.parse(saved);
            if (data.sections) {
                data.sections.forEach((sec, idx) => {
                    const card = document.getElementById(`section-${idx}`);
                    if (!card) return;

                    const nilCb = card.querySelector('.nil-checkbox');
                    if (nilCb && sec.nil) {
                        nilCb.checked = true;
                        updateNilState(nilCb);
                    }

                    if (!sec.nil && sec.rows && sec.rows.length > 0) {
                        const table = card.querySelector('.report-table');
                        const tbody = table?.querySelector('tbody');
                        if (!tbody) return;

                        // Clear existing rows
                        tbody.innerHTML = '';

                        sec.rows.forEach((rowData, rIdx) => {
                            const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.innerText.trim());
                            const tr = createRowFromHeaders(headers, rIdx + 1, rowData);
                            tbody.appendChild(tr);
                        });
                    }
                });
            }

            if (data.notes && editorCanvas) {
                editorCanvas.innerHTML = data.notes;
            }
        } catch (e) {
            console.warn('Failed to load draft:', e);
        }
    }

    function createRowFromHeaders(headers, sno, rowData) {
        const tr = document.createElement('tr');
        headers.forEach((header, idx) => {
            const td = document.createElement('td');
            if (idx === 0) {
                td.className = 'sno-cell';
                td.textContent = sno;
            } else {
                td.innerHTML = getInputHTML(header, deptName);
                const input = td.querySelector('input, textarea');
                if (input) input.value = rowData?.[header] || '';
            }
            tr.appendChild(td);
        });
        return tr;
    }

    // Reload draft when date changes
    dateInput.addEventListener('change', () => {
        statusChip.innerText = "Drafting";
        statusChip.parentNode.className = "flex items-center gap-2 bg-[#fffbeb] px-4 py-2 rounded-full border border-[#fde68a]";
        statusChip.className = "text-xs font-bold text-[#b45309] uppercase tracking-widest";
        loadDraft();
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

    // Subtle animation
    newRow.style.animation = 'slideDown 0.2s ease';
    tbody.appendChild(newRow);
    
    // Focus first input in new row
    const firstInput = newRow.querySelector('input');
    if (firstInput) firstInput.focus();
}

function removeRow(button) {
    const card = button.closest('.section-card');
    const tbody = card.querySelector('.report-table tbody');
    if (!tbody) return;

    const rows = tbody.querySelectorAll('tr');
    if (rows.length <= 1) return; // Keep at least one row

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
    
    // Exact Date matches
    if (name === 'reported on' || name === 'attended on' || name === 'completed on' || name.includes('date of joining') || name === 'date') {
        return `<input type="date" class="form-input">`;
    }
    
    // Numbers
    if (name.includes('rolls') || name.includes('absent') || name.includes('participants')) {
        return `<input type="number" class="form-input text-center" placeholder="${placeholder}">`;
    }
    
    // Long Text Blocks
    if (name.includes('remarks') || name.includes('details') || name.includes('problem') || name.includes('statement') || name.includes('description') || name.includes('event')) {
        return `<textarea rows="1" class="form-input auto-resize" placeholder="${placeholder}"></textarea>`;
    }
    
    // Default text
    return `<input type="text" class="form-input" placeholder="${placeholder}">`;
}

function getPlaceholderStr(colName, dept) {
    let text = colName.toLowerCase();
    if (text.includes('dept') || text.includes('department')) return "e.g. " + dept;
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
