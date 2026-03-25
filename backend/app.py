import os
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from main import main as generate_report
from database import get_daily_reports, delete_record
from generators.monthly_report import generate_monthly_report
from datetime import datetime

app = Flask(__name__, static_folder='../frontend')
CORS(app)

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        reports = get_daily_reports()
        return jsonify({"dates": reports})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/history/<date>', methods=['DELETE'])
def delete_history_record(date):
    try:
        delete_record(date)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def handle_generate():
    try:
        date_str = request.form.get('date')
        if not date_str:
            return jsonify({"error": "Report Date is required"}), 400
            
        tmp_dir = os.path.join(os.path.dirname(__file__), 'tmp_uploads')
        os.makedirs(tmp_dir, exist_ok=True)
        
        # Clear existing files
        for f in os.listdir(tmp_dir):
            if os.path.isfile(os.path.join(tmp_dir, f)):
                os.remove(os.path.join(tmp_dir, f))
                
        # Save uploaded files
        if 'files' not in request.files:
            return jsonify({"error": "No files uploaded"}), 400
            
        files = request.files.getlist('files')
        
        for file in files:
            if file.filename:
                filepath = os.path.join(tmp_dir, file.filename)
                file.save(filepath)
                    
        # Generate Report
        output_file = generate_report(
            date_str=date_str,
            source_dir=tmp_dir
        )
        
        # Return the file directly
        if os.path.exists(output_file):
            return send_file(output_file, as_attachment=True, download_name=os.path.basename(output_file))
        else:
            return jsonify({"error": "Failed to generate file"}), 500
            
    except Exception as e:
        print(f"Error generating report: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/monthly', methods=['POST'])
def handle_monthly():
    try:
        month_name = datetime.now().strftime("%B_%Y")
        output_dir = os.path.join(os.path.dirname(__file__), "..", month_name)
        
        output_file = generate_monthly_report(output_dir)
        
        if os.path.exists(output_file):
            return send_file(output_file, as_attachment=True, download_name=os.path.basename(output_file))
        else:
            return jsonify({"error": "Failed to generate monthly file"}), 500
    except Exception as e:
        print(f"Error generating monthly report: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
