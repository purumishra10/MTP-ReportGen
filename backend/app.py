import os
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from database import get_daily_reports, delete_record, save_mtp_record, init_db, get_records_by_date, update_status
from generators.monthly_report import generate_monthly_report
from datetime import datetime

app = Flask(__name__, static_folder='../frontend')
CORS(app)

# Ensure db is initialized before routes answer to client queries
init_db()

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

@app.route('/api/department/submit', methods=['POST'])
def handle_department_submit():
    try:
        data = request.json
        if not data or 'date' not in data or 'department' not in data or 'content' not in data:
            return jsonify({"error": "Missing payload data"}), 400
        status = data.get('status', 'draft')
        save_mtp_record(data['date'], data['department'], data['content'], status)
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error saving department submission: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/tracker/<date>', methods=['GET'])
def get_tracker_data(date):
    try:
        # returns department, placement_and_training, status, id
        records = get_records_by_date(date, require_approved=False)
        result = []
        for r in records:
            result.append({
                "department": r[0],
                "content": r[1],
                "status": r[2],
                "id": r[3]
            })
        return jsonify({"records": result})
    except Exception as e:
        print(f"Error fetching tracker data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/tracker/review', methods=['POST'])
def review_submission():
    try:
        data = request.json
        if not data or 'id' not in data or 'status' not in data:
            return jsonify({"error": "Missing payload"}), 400
        
        update_status(data['id'], data['status'])
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error updating status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def handle_generate():
    try:
        # We now accept either form data or json
        date_str = request.form.get('date') if request.form.get('date') else request.json.get('date') if request.is_json else None
        
        if not date_str:
            return jsonify({"error": "Report Date is required"}), 400
            
        # Use our new DB generator
        from main import generate_from_db
        output_file = generate_from_db(date_str)
        
        if os.path.exists(output_file):
            return send_file(output_file, as_attachment=True, download_name=os.path.basename(output_file))
        else:
            return jsonify({"error": "Failed to generate file"}), 500
            
    except Exception as e:
        print(f"Error generating report from DB: {e}")
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
