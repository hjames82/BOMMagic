import os
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file
from flask_login import current_user
from werkzeug.utils import secure_filename
from redis import Redis
from rq import Queue

from app import app, db
from replit_auth import require_login
from models import Job, JobStatus, User, Document, Detection
from services.ocr_cli import ensure_text_layer
from services.bom_detect import detect_bom_regions
from services.page_image import render_page_png
import subprocess
import json
import time

# Create blueprint for v1 API
v1_api = Blueprint('v1_api', __name__, url_prefix='/v1')

# Redis connection for job queue
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
redis_conn = Redis.from_url(redis_url)
default_queue = Queue('default', connection=redis_conn)

# Storage configuration
STORAGE_BASE = os.getenv('PRIVATE_OBJECT_DIR', '/tmp/storage')
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', '104857600'))  # 100MB default
ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif'}


def ensure_storage_dirs():
    """Ensure storage directories exist"""
    dirs = [
        f"{STORAGE_BASE}/originals",
        f"{STORAGE_BASE}/processed",
        f"{STORAGE_BASE}/exports",
        "/tmp/ocr_debug"
    ]
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)


@v1_api.route('/documents', methods=['POST'])
@require_login
def upload_document():
    """
    Upload a document for BOM extraction
    
    Accepts PDF or image files, stores originals, and enqueues processing jobs.
    Returns job ID for status tracking.
    """
    ensure_storage_dirs()
    
    # Validate file presence
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            'error': f'Unsupported file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'
        }), 400
    
    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({
            'error': f'File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024):.1f}MB'
        }), 413
    
    try:
        # Generate unique identifiers
        job_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = secure_filename(file.filename)
        
        # Create storage path
        storage_filename = f"{job_id}_{timestamp}_{safe_filename}"
        storage_path = f"{STORAGE_BASE}/originals/{storage_filename}"
        
        # Save file to storage
        file.save(storage_path)
        
        # Create job record in database
        job = Job(
            id=job_id,
            user_id=current_user.id,
            original_filename=safe_filename,
            file_path=storage_path,
            file_size=file_size,
            status=JobStatus.PENDING,
            created_at=datetime.now(),
            processing_metadata={
                'upload_timestamp': timestamp,
                'file_extension': file_ext,
                'storage_backend': 'local'  # Will be 'replit_storage' when integrated
            }
        )
        
        db.session.add(job)
        db.session.commit()
        
        # Determine if document needs page-by-page processing
        if file_ext == '.pdf':
            # For PDFs, check page count and enqueue per-page jobs if large
            from PyPDF2 import PdfReader
            reader = PdfReader(storage_path)
            page_count = len(reader.pages)
            
            if page_count > 10:
                # Process pages in parallel for large documents
                for page_num in range(1, page_count + 1):
                    default_queue.enqueue(
                        'worker.process_document_job',
                        job_id=job_id,
                        page_number=page_num,
                        job_timeout='10m'
                    )
                app.logger.info(f"Enqueued {page_count} page jobs for job {job_id}")
            else:
                # Process entire document for small PDFs
                default_queue.enqueue(
                    'worker.process_document_job',
                    job_id=job_id,
                    page_number=None,
                    job_timeout='15m'
                )
                app.logger.info(f"Enqueued full document job for {job_id}")
        else:
            # For images, process as single page
            default_queue.enqueue(
                'worker.process_document_job',
                job_id=job_id,
                page_number=1,
                job_timeout='5m'
            )
            app.logger.info(f"Enqueued image processing job for {job_id}")
        
        return jsonify({
            'job_id': job_id,
            'status': 'processing',
            'message': 'Document uploaded successfully and queued for processing'
        }), 201
        
    except Exception as e:
        app.logger.error(f"Document upload error: {str(e)}", exc_info=True)
        
        # Clean up on failure
        if 'storage_path' in locals() and os.path.exists(storage_path):
            os.remove(storage_path)
        
        return jsonify({
            'error': 'Failed to process document upload',
            'details': str(e) if app.debug else None
        }), 500


@v1_api.route('/jobs/<job_id>', methods=['GET'])
@require_login  
def get_job_status(job_id):
    """
    Get detailed job status and metadata
    
    Returns current processing status, confidence scores, and export URLs if available.
    """
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first()
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    response = {
        'job_id': job.id,
        'status': job.status.value,
        'original_filename': job.original_filename,
        'file_size': job.file_size,
        'confidence': job.confidence_score,
        'created_at': job.created_at.isoformat(),
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'processing_metadata': job.processing_metadata
    }
    
    # Add export URL if available
    if job.export_path and job.status in [JobStatus.COMPLETED, JobStatus.REVIEWED]:
        response['export_url'] = f"/v1/jobs/{job_id}/export/{job.export_format or 'csv'}"
    
    # Add error details if failed
    if job.status == JobStatus.FAILED:
        response['error_message'] = job.error_message
    
    # Add review URL if needed
    if job.status == JobStatus.REQUIRES_REVIEW:
        response['review_url'] = f"/review/{job_id}"
        response['message'] = 'Manual review required due to low confidence score'
    
    return jsonify(response)


@v1_api.route('/jobs/<job_id>/export/<format>', methods=['GET']) 
@require_login
def export_job_results(job_id, format):
    """
    Export processed BOM data in specified format
    
    Formats: csv, xlsx
    """
    if format not in ['csv', 'xlsx']:
        return jsonify({'error': f'Unsupported format: {format}'}), 400
    
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first()
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    if job.status not in [JobStatus.COMPLETED, JobStatus.REVIEWED]:
        return jsonify({
            'error': 'Export not available',
            'status': job.status.value,
            'message': 'Job must be completed or reviewed before export'
        }), 400
    
    # Check if export already exists
    if job.export_path and os.path.exists(job.export_path):
        from flask import send_file
        
        mimetype = 'text/csv' if format == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        download_name = f"{os.path.splitext(job.original_filename)[0]}_bom.{format}"
        
        return send_file(
            job.export_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype
        )
    
    # Generate export if not exists
    try:
        from services.export_service import ExportService
        from models import BOMItem
        
        export_service = ExportService()
        items = BOMItem.query.filter_by(job_id=job_id).order_by(BOMItem.row_index).all()
        
        export_data = []
        for item in items:
            export_data.append({
                'item_number': item.item_number,
                'part_number': item.part_number,
                'description': item.description,
                'quantity': item.quantity,
                'unit': item.unit,
                'material': item.material,
                'supplier': item.supplier,
                'cost': item.cost,
                'confidence': item.confidence_score
            })
        
        # Generate export file
        export_path = f"{STORAGE_BASE}/exports/{job_id}.{format}"
        
        if format == 'csv':
            export_service.export_to_csv(export_data, export_path)
        else:
            export_service.export_to_excel(export_data, export_path)
        
        # Update job record
        job.export_path = export_path
        job.export_format = format
        db.session.commit()
        
        from flask import send_file
        mimetype = 'text/csv' if format == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        download_name = f"{os.path.splitext(job.original_filename)[0]}_bom.{format}"
        
        return send_file(
            export_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype
        )
        
    except Exception as e:
        app.logger.error(f"Export generation failed: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to generate export',
            'details': str(e) if app.debug else None
        }), 500


@v1_api.route('/analyze', methods=['POST'])
@require_login
def analyze_document():
    """
    Analyze a PDF document for BOM regions.
    """
    ensure_storage_dirs()
    
    # Validate file presence
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext != '.pdf':
        return jsonify({'error': 'Only PDF files are supported for analysis'}), 400
    
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
        # Generate document ID
        document_id = str(uuid.uuid4())
        safe_filename = secure_filename(file.filename)
        
        # Save file
        orig_path = f"{STORAGE_BASE}/originals/{document_id}_{safe_filename}"
        file.save(orig_path)
        
        # Time the operations
        timings = {}
        
        # Ensure text layer
        ocr_start = time.time()
        ocr_path = f"{STORAGE_BASE}/processed/{document_id}_ocr.pdf"
        ensure_text_layer(orig_path, ocr_path)
        timings['ocr_ms'] = int((time.time() - ocr_start) * 1000)
        
        # Detect BOM regions
        detect_start = time.time()
        detections = detect_bom_regions(ocr_path)
        timings['detection_ms'] = int((time.time() - detect_start) * 1000)
        
        # Get page count and check limits
        from PyPDF2 import PdfReader
        try:
            reader = PdfReader(ocr_path)
            page_count = len(reader.pages)
            
            # Check page limit
            if page_count > 200:
                return jsonify({
                    'error': f'Document too large. Maximum 200 pages (your document: {page_count} pages)'
                }), 413
            
            # Check if encrypted
            if reader.is_encrypted:
                return jsonify({'error': 'Encrypted PDFs are not supported'}), 400
                
        except Exception as e:
            return jsonify({
                'error': 'Failed to read PDF',
                'details': str(e) if app.debug else None
            }), 400
        
        # Store in database
        doc = Document(
            id=document_id,
            original_filename=safe_filename,
            file_path=orig_path,
            ocr_file_path=ocr_path,
            file_size=file_size,
            page_count=page_count
        )
        db.session.add(doc)
        
        # Store detections
        for detection in detections:
            det = Detection(
                document_id=document_id,
                page=detection['page'],
                bbox_x0=detection['bbox'][0],
                bbox_y0=detection['bbox'][1],
                bbox_x1=detection['bbox'][2],
                bbox_y1=detection['bbox'][3],
                headers=detection['headers'],
                confidence=detection['confidence'],
                scores=detection.get('scores', {})  # Include detailed scores
            )
            db.session.add(det)
        
        db.session.commit()
        
        return jsonify({
            'document_id': document_id,
            'detections': detections,
            'timings': timings,
            'page_count': page_count
        }), 201
        
    except Exception as e:
        app.logger.error(f"Document analysis error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to analyze document',
            'details': str(e) if app.debug else None
        }), 500


@v1_api.route('/documents/<document_id>', methods=['GET'])
@require_login
def get_document(document_id):
    """
    Get document metadata and last detections.
    """
    doc = Document.query.get(document_id)
    
    if not doc:
        return jsonify({'error': 'Document not found'}), 404
    
    # Get detections
    detections = []
    for det in doc.detections:
        detections.append({
            'id': det.id,
            'page': det.page,
            'bbox': [det.bbox_x0, det.bbox_y0, det.bbox_x1, det.bbox_y1],
            'headers': det.headers,
            'confidence': det.confidence,
            'is_reviewed': det.is_reviewed,
            'is_correct': det.is_correct
        })
    
    return jsonify({
        'document_id': doc.id,
        'original_filename': doc.original_filename,
        'file_size': doc.file_size,
        'page_count': doc.page_count,
        'created_at': doc.created_at.isoformat(),
        'detections': detections
    })


@v1_api.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint returning system versions.
    """
    versions = {}
    
    # System tools version checks
    tools = [
        ('tesseract', ['tesseract', '--version']),
        ('ocrmypdf', ['ocrmypdf', '--version']),
        ('pdftotext', ['pdftotext', '-v']),
        ('pdftohtml', ['pdftohtml', '-v']),
        ('pdftoppm', ['pdftoppm', '-v'])
    ]
    
    for tool_name, cmd in tools:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            output = result.stdout or result.stderr
            if output:
                lines = output.split('\n')
                if lines:
                    # Extract version from first line
                    version_line = lines[0]
                    import re
                    version_match = re.search(r'\d+\.\d+(?:\.\d+)?', version_line)
                    if version_match:
                        versions[tool_name] = version_match.group()
                    else:
                        versions[tool_name] = 'installed'
            else:
                versions[tool_name] = 'unavailable'
        except Exception:
            versions[tool_name] = 'unavailable'
    
    # Configuration info
    config = {
        'max_file_size_mb': 25,
        'max_pages': 200,
        'confidence_threshold': float(os.getenv('CONFIDENCE_THRESHOLD', '0.70'))
    }
    
    return jsonify({
        'ok': True,
        'versions': versions,
        'config': config
    })


@v1_api.route('/metrics/detect', methods=['GET'])
def get_detection_metrics():
    """
    Get detection metrics and statistics.
    """
    from sqlalchemy import func
    from datetime import datetime, timedelta
    from models import Detection
    
    # Get time range parameter
    hours = request.args.get('hours', 24, type=int)
    since = datetime.now() - timedelta(hours=hours)
    
    # Query detection statistics
    total_detections = Detection.query.filter(Detection.created_at >= since).count()
    reviewed_detections = Detection.query.filter(
        Detection.created_at >= since,
        Detection.is_reviewed == True
    ).count()
    
    # Confidence statistics
    confidence_stats = db.session.query(
        func.avg(Detection.confidence).label('avg'),
        func.min(Detection.confidence).label('min'),
        func.max(Detection.confidence).label('max'),
        func.stddev(Detection.confidence).label('stddev')
    ).filter(Detection.created_at >= since).first()
    
    # Score breakdowns
    score_stats = {}
    detections_with_scores = Detection.query.filter(
        Detection.created_at >= since,
        Detection.scores.isnot(None)
    ).all()
    
    if detections_with_scores:
        header_scores = [d.scores.get('header_score', 0) for d in detections_with_scores if d.scores]
        col_scores = [d.scores.get('col_count_score', 0) for d in detections_with_scores if d.scores]
        qty_scores = [d.scores.get('qty_numeric_score', 0) for d in detections_with_scores if d.scores]
        
        score_stats = {
            'header_score': {
                'avg': sum(header_scores) / len(header_scores) if header_scores else 0,
                'min': min(header_scores) if header_scores else 0,
                'max': max(header_scores) if header_scores else 0
            },
            'col_count_score': {
                'avg': sum(col_scores) / len(col_scores) if col_scores else 0,
                'min': min(col_scores) if col_scores else 0,
                'max': max(col_scores) if col_scores else 0
            },
            'qty_numeric_score': {
                'avg': sum(qty_scores) / len(qty_scores) if qty_scores else 0,
                'min': min(qty_scores) if qty_scores else 0,
                'max': max(qty_scores) if qty_scores else 0
            }
        }
    
    # Confidence histogram
    histogram_bins = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    histogram = {}
    for i in range(len(histogram_bins) - 1):
        count = Detection.query.filter(
            Detection.created_at >= since,
            Detection.confidence >= histogram_bins[i],
            Detection.confidence < histogram_bins[i + 1]
        ).count()
        histogram[f"{histogram_bins[i]:.1f}-{histogram_bins[i+1]:.1f}"] = count
    
    # Accuracy from reviewed detections
    correct_detections = Detection.query.filter(
        Detection.created_at >= since,
        Detection.is_reviewed == True,
        Detection.is_correct == True
    ).count()
    
    accuracy = correct_detections / reviewed_detections if reviewed_detections > 0 else None
    
    return jsonify({
        'time_range_hours': hours,
        'total_detections': total_detections,
        'reviewed_detections': reviewed_detections,
        'confidence': {
            'average': confidence_stats.avg if confidence_stats.avg else 0,
            'min': confidence_stats.min if confidence_stats.min else 0,
            'max': confidence_stats.max if confidence_stats.max else 0,
            'stddev': confidence_stats.stddev if confidence_stats.stddev else 0
        },
        'score_breakdown': score_stats,
        'confidence_histogram': histogram,
        'accuracy': accuracy
    })


@v1_api.route('/jobs/<job_id>/approve', methods=['POST'])
@require_login
def approve_job_review(job_id):
    """
    Approve reviewed BOM data with corrections
    
    Accepts corrected BOM data and marks job as reviewed.
    """
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first()
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    if job.status != JobStatus.REQUIRES_REVIEW:
        return jsonify({
            'error': 'Job not in review status',
            'current_status': job.status.value
        }), 400
    
    try:
        reviewed_data = request.json.get('bom_data', [])
        corrections_made = request.json.get('corrections_made', 0)
        reviewer_notes = request.json.get('notes', '')
        
        # Update BOM items with reviewed data
        from models import BOMItem
        
        for item_data in reviewed_data:
            item_id = item_data.get('id')
            if item_id:
                item = BOMItem.query.filter_by(id=item_id, job_id=job_id).first()
                if item:
                    # Update all fields
                    for field in ['item_number', 'part_number', 'description', 
                                 'quantity', 'unit', 'material', 'supplier', 'cost']:
                        if field in item_data:
                            setattr(item, field, item_data[field])
                    
                    item.is_validated = True
                    item.validation_notes = reviewer_notes
                    item.confidence_score = 1.0  # Manual review gives full confidence
                    item.updated_at = datetime.now()
        
        # Update job status
        job.status = JobStatus.REVIEWED
        job.validated_data = reviewed_data
        job.completed_at = datetime.now()
        
        # Update metadata
        if not job.processing_metadata:
            job.processing_metadata = {}
        job.processing_metadata['review'] = {
            'reviewed_at': datetime.now().isoformat(),
            'corrections_made': corrections_made,
            'reviewer_id': current_user.id,
            'notes': reviewer_notes
        }
        
        db.session.commit()
        
        # Trigger export generation
        default_queue.enqueue(
            'worker.export_results_job',
            job_id=job_id,
            format='csv'
        )
        
        return jsonify({
            'message': 'Review approved successfully',
            'status': 'reviewed',
            'export_queued': True
        })
        
    except Exception as e:
        app.logger.error(f"Review approval error: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'error': 'Failed to approve review',
            'details': str(e) if app.debug else None
        }), 500


# Register blueprint with main app
app.register_blueprint(v1_api)