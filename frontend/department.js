document.addEventListener('DOMContentLoaded', () => {
    const submitBtn = document.getElementById('submit-dept-btn');
    const saveDraftBtn = document.getElementById('save-draft-btn');
    const editorCanvas = document.getElementById('editor-canvas');
    const dateInput = document.getElementById('dept-date');
    const statusChip = document.getElementById('save-status-chip');
    
    dateInput.valueAsDate = new Date();

    async function sendToServer(statusVal) {
        const content = editorCanvas.innerText.trim();
        const dateVal = dateInput.value;
        const dept = "CSE"; // Hardcoded for preview

        if (!content || !dateVal) {
            alert('Please ensure both Date and Content are provided.');
            return;
        }

        statusChip.innerText = "Processing...";

        try {
            const response = await fetch('/api/department/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    date: dateVal,
                    department: dept,
                    content: content,
                    status: statusVal
                })
            });

            if (response.ok) {
                if (statusVal === 'draft') {
                    statusChip.innerText = "Draft Saved";
                    statusChip.parentNode.className = "flex items-center gap-2 bg-[#f8fafc] px-4 py-2 rounded-full border border-outline-variant";
                    statusChip.className = "text-xs font-bold text-on-surface-variant uppercase tracking-widest";
                } else if (statusVal === 'pending_review') {
                    statusChip.innerText = "Pending PA Review";
                    statusChip.parentNode.className = "flex items-center gap-2 bg-[#fffbeb] px-4 py-2 rounded-full border border-[#fde68a]";
                    statusChip.className = "text-xs font-bold text-[#b45309] uppercase tracking-widest";
                    alert('Submitted for PA Review!');
                }
            } else {
                const err = await response.json();
                alert('Error: ' + err.error);
                statusChip.innerText = "Failed";
            }
        } catch (error) {
            console.error(error);
            alert('Network Error occurred.');
        }
    }

    submitBtn.addEventListener('click', () => sendToServer('pending_review'));
    saveDraftBtn.addEventListener('click', () => sendToServer('draft'));
});
