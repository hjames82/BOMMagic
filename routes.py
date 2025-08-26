from flask import session, render_template, redirect, url_for, request, jsonify
from flask_login import current_user
from app import app, db
from replit_auth import require_login, make_replit_blueprint
from models import Job, JobStatus, AccuracyMetric, Document, Detection
from sqlalchemy import desc
from datetime import datetime
import os

# Import API blueprints  
from api.v1_routes import v1_api
from api.debug_routes import debug_bp

# Register blueprints
app.register_blueprint(make_replit_blueprint(), url_prefix="/auth")
app.register_blueprint(v1_api)
app.register_blueprint(debug_bp)

# Import api.routes to register its routes (uses @app.route directly)
import api.routes  # noqa: F401

# Make session permanent
@app.before_request
def make_session_permanent():
    session.permanent = True


@app.route('/')
def index():
    """Landing page - shows login for anonymous users, dashboard for authenticated users"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/dashboard')
@require_login
def dashboard():
    """Main dashboard showing user's jobs and statistics"""
    user = current_user
    
    # Get user's recent jobs
    recent_jobs = Job.query.filter_by(user_id=user.id).order_by(desc(Job.created_at)).limit(10).all()
    
    # Get statistics
    total_jobs = Job.query.filter_by(user_id=user.id).count()
    completed_jobs = Job.query.filter_by(user_id=user.id, status=JobStatus.COMPLETED).count()
    failed_jobs = Job.query.filter_by(user_id=user.id, status=JobStatus.FAILED).count()
    pending_jobs = Job.query.filter_by(user_id=user.id, status=JobStatus.PENDING).count()
    processing_jobs = Job.query.filter_by(user_id=user.id, status=JobStatus.PROCESSING).count()
    review_jobs = Job.query.filter_by(user_id=user.id, status=JobStatus.REQUIRES_REVIEW).count()
    
    # Calculate average accuracy
    avg_accuracy = db.session.query(db.func.avg(AccuracyMetric.overall_confidence))\
        .join(Job).filter(Job.user_id == user.id).scalar() or 0
    
    stats = {
        'total_jobs': total_jobs,
        'completed_jobs': completed_jobs,
        'failed_jobs': failed_jobs,
        'pending_jobs': pending_jobs,
        'processing_jobs': processing_jobs,
        'review_jobs': review_jobs,
        'avg_accuracy': round(avg_accuracy * 100, 1) if avg_accuracy else 0
    }
    
    return render_template('dashboard.html', user=user, jobs=recent_jobs, stats=stats)


@app.route('/jobs/<job_id>')
@require_login
def job_detail(job_id):
    """Show detailed view of a specific job"""
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    
    # Get accuracy metrics for this job
    metrics = AccuracyMetric.query.filter_by(job_id=job_id).first()
    
    return render_template('job_detail.html', job=job, metrics=metrics)


@app.route('/jobs/<job_id>/review')
@require_login
def review_job(job_id):
    """Review interface for jobs that require manual review"""
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    
    if job.status != JobStatus.REQUIRES_REVIEW:
        return redirect(url_for('job_detail', job_id=job_id))
    
    return render_template('review.html', job=job)


@app.route('/review/<document_id>')
@require_login
def review_document(document_id):
    """Review detected BOM regions."""
    from services.page_image import render_page_png
    
    doc = Document.query.get_or_404(document_id)
    
    # Get all detections for this document
    detections = Detection.query.filter_by(document_id=document_id).order_by(Detection.confidence.desc()).all()
    
    # Group detections by page
    detections_by_page = {}
    for det in detections:
        if det.page not in detections_by_page:
            detections_by_page[det.page] = []
        detections_by_page[det.page].append({
            'id': det.id,
            'bbox': [det.bbox_x0, det.bbox_y0, det.bbox_x1, det.bbox_y1],
            'headers': det.headers,
            'confidence': det.confidence,
            'is_reviewed': det.is_reviewed,
            'is_correct': det.is_correct
        })
    
    return render_template('review_document.html', 
                         document=doc, 
                         detections_by_page=detections_by_page)


@app.route('/review/<document_id>/detection/<int:detection_id>', methods=['POST'])
@require_login  
def update_detection(document_id, detection_id):
    """Update detection review status."""
    detection = Detection.query.get_or_404(detection_id)
    
    # Verify detection belongs to document
    if detection.document_id != document_id:
        return jsonify({'error': 'Invalid detection'}), 400
    
    data = request.json
    detection.is_reviewed = True
    detection.is_correct = data.get('is_correct', False)
    detection.review_notes = data.get('notes', '')
    detection.reviewed_at = datetime.now()
    
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/review/<document_id>/page/<int:page>/image')
@require_login
def get_page_image(document_id, page):
    """Get rendered PNG image for a page."""
    from flask import send_file
    from services.page_image import render_page_png
    
    doc = Document.query.get_or_404(document_id)
    
    # Use OCR'd PDF if available, otherwise original
    pdf_path = doc.ocr_file_path if doc.ocr_file_path else doc.file_path
    
    # Render page to PNG
    png_path = render_page_png(pdf_path, page)
    
    if png_path and os.path.exists(png_path):
        return send_file(png_path, mimetype='image/png')
    else:
        return jsonify({'error': 'Failed to render page'}), 500


@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
