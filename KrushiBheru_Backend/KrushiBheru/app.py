from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from model.database import db
from model.field import FieldManager
from model.analysis import FieldAnalyzer
from model.report import ReportGenerator
from model.utils import validate_geojson
from model.models import User, Field
import secrets
import bcrypt
import json

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Hardcoded secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///integrated_field_monitor.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Hardcoded Sentinel Hub credentials
SH_CLIENT_ID = '74ddf553-4555-45ad-a379-14430e3ef19a'
SH_CLIENT_SECRET = 'ntMnIssj7J4rgP7oHqdFPGriPoOWp9u4'

db.init_app(app)
field_manager = FieldManager()
analyzer = FieldAnalyzer()
report_generator = ReportGenerator()

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/mapping', methods=['GET', 'POST'])
def mapping():
    if request.method == 'POST':
        try:
            data = request.get_json()
            required = ('user_id', 'name', 'boundary')
            if not all(k in data for k in required) or not validate_geojson(data['boundary']):
                return jsonify({'status': 'error', 'message': 'Invalid or missing data'}), 400
            field_id = field_manager.create_field(
                user_id=data['user_id'],
                name=data['name'],
                boundary=data['boundary'],
                state=data.get('state'),
                district=data.get('district'),
                crop_type=data.get('crop_type'),
                crop_status=data.get('crop_status'),
                season=data.get('season')
            )
            return jsonify({'status': 'success', 'field_id': field_id}), 201
        except ValueError as e:
            return jsonify({'status': 'error', 'message': str(e)}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'message': f"Server error: {str(e)}"}), 500
    return render_template('mapping.html')

@app.route('/cropanalysis')
def cropanalysis():
    return render_template('cropanalysis.html')

@app.route('/livestream')
def livestream():
    return render_template('live.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not all(k in data for k in ('email', 'password')):
                return jsonify({'status': 'error', 'message': 'Email and password required'}), 400
            user = User.query.filter_by(email=data['email']).first()
            if not user or not bcrypt.checkpw(data['password'].encode('utf-8'), user.password_hash.encode('utf-8')):
                return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401
            return jsonify({'status': 'success', 'message': 'Login successful', 'user_id': user.user_id}), 200
        except Exception as e:
            return jsonify({'status': 'error', 'message': f"Server error: {str(e)}"}), 500
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            data = request.get_json()
            required = ('name', 'contact_no', 'email', 'password', 'state', 'district')
            if not all(k in data for k in required):
                return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
            if User.query.filter_by(email=data['email']).first():
                return jsonify({'status': 'error', 'message': 'Email already registered'}), 400
            if User.query.filter_by(contact_no=data['contact_no']).first():
                return jsonify({'status': 'error', 'message': 'Contact number already registered'}), 400
            password_hash = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            user = User(
                name=data['name'],
                contact_no=data['contact_no'],
                email=data['email'],
                password_hash=password_hash,
                state=data['state'],
                district=data['district']
            )
            db.session.add(user)
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Registration successful', 'user_id': user.user_id}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': f"Server error: {str(e)}"}), 500
    return render_template('registration.html')

@app.route('/field_dashboard')
def field_dashboard():
    try:
        fields = Field.query.all()
        return render_template('field_dashboard.html', fields=fields)
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Server error: {str(e)}"}), 500

@app.route('/field_analysis/<int:field_id>')
def field_analysis(field_id):
    try:
        analysis = analyzer.analyze_field(field_id)
        field = field_manager.get_field(field_id)
        return render_template('field_analysis.html', analysis=analysis, field=field)
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Server error: {str(e)}"}), 500

@app.route('/advisory_report/<int:field_id>')
def advisory_report(field_id):
    try:
        report = report_generator.generate_report(field_id)
        if not report['success']:
            return jsonify({'status': 'error', 'message': report['message']}), 500
        field = field_manager.get_field(field_id)
        return render_template('advisory_report.html', 
                              tech_report=report['report']['metrics'],
                              farmer_report=report['report']['advisories'],
                              map_file=report['report']['map_file'],
                              field=field,
                              history=report['report']['history'])
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Server error: {str(e)}"}), 500

@app.route('/reports/<path:filename>')
def serve_report(filename):
    try:
        return send_from_directory('reports', filename)
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"File not found: {str(e)}"}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)