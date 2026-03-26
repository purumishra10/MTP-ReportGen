# 📄 MTP Master Report Generator

Welcome to the **MTP Master Report Generator**! This tool is designed to save you hours of manual copy-pasting by automatically merging scattered daily reports from various departments into one perfectly formatted master document.

## ✨ Features
* **Lightning Fast Merging:** Drag and drop all your department `.docx` files at once. The app instantly merges Attendance data, MTP (Placement/Training) text, and images into your master template.
* **Smart Organization:** MTP paragraphs are automatically mapped to their respective HODs (Head of Departments) in the template table. If a department isn't explicitly listed, the app automatically generates a new customized row for it!
* **Library Stats Extraction:** It automatically detects library reports and mathematically pulls out the "books issued", "returned", and "visitor" counts without you lifting a finger. 
* **One-Click Monthly Consolidation:** At the end of the month, simply click the "Generate Monthly" button to instantly compile all the daily MTP records you've generated over the last 30 days into a single comprehensive file.
* **Mistake Forgiveness:** Made a mistake? The "Database Records" panel lets you seamlessly delete erroneous daily record tags from the database with a single click of a red '❌'.

---

## 🚀 How to Install (For Beginners)

Even if you aren't a programmer, getting this running on your computer is easy.

### Prerequisites
1. You must have **Python** installed on your computer. (Download it from [python.org](https://www.python.org/downloads/)). Make sure you check the box that says "Add Python to PATH" during installation.

### Setup Instructions
1. Download or clone this folder to your computer.
2. Open your computer's terminal (or Command Prompt / PowerShell) and navigate into the `Project` folder.
3. **Create a virtual environment** (this keeps the app's files cleanly isolated):
   ```bash
   python -m venv venv
   ```
4. **Activate the environment**:
   * On **Windows**: `venv\Scripts\activate`
   * On **Mac/Linux**: `source venv/bin/activate`
5. **Install the required libraries**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 💻 How to Run the App

1. Ensure your terminal is open inside the `Project` folder and your `venv` is activated (you should see `(venv)` at the start of your terminal line).
2. Move into the backend folder:
   ```bash
   cd backend
   ```
3. Start the server:
   ```bash
   python app.py
   ```
---

## 📝 How to Use the App

1. **Pick the Date**: Use the calendar picker to select the official date of the reports.
2. **Upload the Files**: Drag and drop all the individual department `.docx` reports (CSE, ECE, Civil, Library, etc.) into the dotted box.
3. **Generate**: Click "Generate Daily Report". The app will instantly download a compiled `Master_Daily_Report.docx` file to your Downloads folder!
4. **Manage History**: If you realize you uploaded the wrong file, simply find the date in the "Database Records" list on the right and click the red **`✕`** to delete it. Then, upload and generate it again.
5. **Monthly Report**: When the month is over, just click the "Generate Monthly MTP Report" button to download a master compilation of all MTP data accumulated over the month.

---

## 📂 Project Structure (For Developers)
- `backend/app.py`: The Flask server that glues everything together and runs the API.
- `backend/main.py`: The core python script that coordinates the extractors and generators.
- `backend/database.py`: Manages the lightweight local SQLite database (`daily_data.db`).
- `frontend/`: Contains the pure Vanilla HTML, CSS, and JS used for the drag-and-drop dashboard interface.
- `Sample_DRs/`: Contains the blank `Empty Daily DR.docx` template that all content gets safely injected into.
