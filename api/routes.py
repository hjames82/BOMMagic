from flask import request, jsonify, send_file, current_app
from flask_login import current_user
from werkzeug.utils import secure_filename
import os
import uuid
import mimetypes
from datetime import datetime
import hashlib
import traceback

from app import app, db
from replit_auth import require_login
from models import Job, JobStatus, BOMItem, AccuracyMetric
from services.document_processor import DocumentProcessor
from services.export_service import ExportService
from worker import process_document_job
import threading


@app.route('/api/upload', methods=['POST'])
@require_login
def upload_document():
    """Upload a document for BOM extraction with idempotency"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate file type
    allowed_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif'}
    file_ext = os.path.splitext(file.filename or '')[1].lower()
    if file_ext not in allowed_extensions:
        return jsonify({'error': 'Unsupported file type. Please upload PDF or image files.'}), 400
    
    # Check file size (25MB limit)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    max_size = 25 * 1024 * 1024  # 25MB
    if file_size > max_size:
        return jsonify({
            'error': f'File too large. Maximum size: 25MB (your file: {file_size / (1024*1024):.1f}MB)'
        }), 413
    
    try:
        # Calculate SHA256 hash for idempotency
        file_hash = hashlib.sha256()
        file.seek(0)
        while chunk := file.read(8192):
            file_hash.update(chunk)
        file.seek(0)
        hash_hex = file_hash.hexdigest()
        
        # Check if this file was already uploaded
        existing_job = Job.query.filter_by(file_hash=hash_hex, user_id=current_user.id).first()
        if existing_job:
            current_app.logger.info(f"Duplicate upload detected: {hash_hex}")
            return jsonify({
                'job_id': existing_job.id,
                'status': existing_job.status.value,
                'message': 'Document already uploaded',
                'duplicate': True
            }), 200
        
        # Generate unique job ID and filename
        job_id = str(uuid.uuid4())
        filename = secure_filename(file.filename or '')
        safe_filename = f"{job_id}_{filename}"
        
        # Save file
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(file_path)
        
        # Create job record with hash
        job = Job(
            id=job_id,
            user_id=current_user.id,
            original_filename=filename,
            file_path=file_path,
            file_size=file_size,
            file_hash=hash_hex,
            status=JobStatus.PENDING
        )
        
        db.session.add(job)
        db.session.commit()
        
        # Start processing in background
        thread = threading.Thread(target=process_document_job, args=(job_id,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'job_id': job_id,
            'status': 'uploaded',
            'message': 'Document uploaded successfully. Processing started.'
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Upload error: {str(e)}\n{traceback.format_exc()}")
        error_msg = 'Failed to upload document'
        if current_app.debug:
            error_msg += f": {str(e)}"
        return jsonify({'error': error_msg}), 500


@app.route('/api/jobs/<job_id>/status', methods=['GET'])
@require_login
def get_job_status(job_id):
    """Get the current status of a job"""
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    
    return jsonify({
        'job_id': job.id,
        'status': job.status.value,
        'confidence_score': job.confidence_score,
        'created_at': job.created_at.isoformat(),
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'error_message': job.error_message
    })


@app.route('/api/jobs/<job_id>/data', methods=['GET'])
@require_login
def get_job_data(job_id):
    """Get the extracted BOM data for a job"""
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    
    if job.status not in [JobStatus.COMPLETED, JobStatus.REQUIRES_REVIEW, JobStatus.REVIEWED]:
        return jsonify({'error': 'Job processing not completed'}), 400
    
    # Get BOM items
    items = BOMItem.query.filter_by(job_id=job_id).order_by(BOMItem.row_index).all()
    
    bom_data = []
    for item in items:
        bom_data.append({
            'id': item.id,
            'item_number': item.item_number,
            'part_number': item.part_number,
            'description': item.description,
            'quantity': item.quantity,
            'unit': item.unit,
            'material': item.material,
            'supplier': item.supplier,
            'cost': item.cost,
            'confidence_score': item.confidence_score,
            'is_validated': item.is_validated,
            'validation_notes': item.validation_notes,
            'row_index': item.row_index
        })
    
    return jsonify({
        'job_id': job.id,
        'status': job.status.value,
        'confidence_score': job.confidence_score,
        'bom_data': bom_data,
        'total_items': len(bom_data)
    })


@app.route('/api/jobs/<job_id>/review', methods=['POST'])
@require_login
def submit_review(job_id):
    """Submit reviewed and corrected BOM data"""
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    
    if job.status != JobStatus.REQUIRES_REVIEW:
        return jsonify({'error': 'Job is not in review status'}), 400
    
    try:
        reviewed_data = request.json.get('bom_data', [])
        
        # Update BOM items with reviewed data
        for item_data in reviewed_data:
            item_id = item_data.get('id')
            if item_id:
                item = BOMItem.query.filter_by(id=item_id, job_id=job_id).first()
                if item:
                    item.item_number = item_data.get('item_number')
                    item.part_number = item_data.get('part_number')
                    item.description = item_data.get('description')
                    item.quantity = item_data.get('quantity')
                    item.unit = item_data.get('unit')
                    item.material = item_data.get('material')
                    item.supplier = item_data.get('supplier')
                    item.cost = item_data.get('cost')
                    item.is_validated = True
                    item.validation_notes = item_data.get('validation_notes')
                    item.updated_at = datetime.now()
        
        # Update job status
        job.status = JobStatus.REVIEWED
        job.validated_data = reviewed_data
        job.completed_at = datetime.now()
        
        db.session.commit()
        
        return jsonify({
            'message': 'Review submitted successfully',
            'status': 'reviewed'
        })
        
    except Exception as e:
        current_app.logger.error(f"Review submission error: {str(e)}")
        return jsonify({'error': 'Failed to submit review'}), 500


@app.route('/api/jobs/<job_id>/export/<format>', methods=['GET'])
@require_login
def export_job_data(job_id, format):
    """Export BOM data as CSV or XLSX"""
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    
    if job.status not in [JobStatus.COMPLETED, JobStatus.REVIEWED]:
        return jsonify({'error': 'Job not ready for export'}), 400
    
    if format not in ['csv', 'xlsx']:
        return jsonify({'error': 'Unsupported export format'}), 400
    
    try:
        export_service = ExportService()
        
        # Get BOM items
        items = BOMItem.query.filter_by(job_id=job_id).order_by(BOMItem.row_index).all()
        
        # Generate export file
        if format == 'csv':
            file_path = export_service.export_to_csv(items, job.original_filename)
            mimetype = 'text/csv'
        else:
            file_path = export_service.export_to_xlsx(items, job.original_filename)
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        
        # Update job with export information
        job.export_path = file_path
        job.export_format = format
        db.session.commit()
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=f"{os.path.splitext(job.original_filename)[0]}_bom.{format}",
            mimetype=mimetype
        )
        
    except Exception as e:
        current_app.logger.error(f"Export error: {str(e)}")
        return jsonify({'error': 'Failed to export data'}), 500


@app.route('/api/jobs', methods=['GET'])
@require_login
def get_user_jobs():
    """Get all jobs for the current user"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status_filter = request.args.get('status')
    
    query = Job.query.filter_by(user_id=current_user.id)
    
    if status_filter:
        try:
            status_enum = JobStatus(status_filter)
            query = query.filter_by(status=status_enum)
        except ValueError:
            pass
    
    jobs = query.order_by(Job.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    job_list = []
    for job in jobs.items:
        job_list.append({
            'id': job.id,
            'original_filename': job.original_filename,
            'status': job.status.value,
            'confidence_score': job.confidence_score,
            'created_at': job.created_at.isoformat(),
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'file_size': job.file_size
        })
    
    return jsonify({
        'jobs': job_list,
        'total': jobs.total,
        'pages': jobs.pages,
        'current_page': jobs.page,
        'has_next': jobs.has_next,
        'has_prev': jobs.has_prev
    })


@app.route('/api/metrics', methods=['GET'])
@require_login
def get_user_metrics():
    """Get accuracy metrics for the current user"""
    user_jobs = Job.query.filter_by(user_id=current_user.id).subquery()
    
    metrics = db.session.query(AccuracyMetric).join(
        user_jobs, AccuracyMetric.job_id == user_jobs.c.id
    ).all()
    
    if not metrics:
        return jsonify({
            'total_jobs': 0,
            'avg_confidence': 0,
            'avg_processing_time': 0,
            'success_rate': 0
        })
    
    total_jobs = len(metrics)
    avg_confidence = sum(m.overall_confidence for m in metrics) / total_jobs
    avg_processing_time = sum(m.total_processing_time for m in metrics if m.total_processing_time) / total_jobs
    
    successful_jobs = Job.query.filter_by(
        user_id=current_user.id, 
        status=JobStatus.COMPLETED
    ).count()
    total_user_jobs = Job.query.filter_by(user_id=current_user.id).count()
    success_rate = (successful_jobs / total_user_jobs) if total_user_jobs > 0 else 0
    
    return jsonify({
        'total_jobs': total_jobs,
        'avg_confidence': round(avg_confidence * 100, 2),
        'avg_processing_time': round(avg_processing_time, 2) if avg_processing_time else 0,
        'success_rate': round(success_rate * 100, 2)
    })
