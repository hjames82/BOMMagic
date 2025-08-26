from flask import session, render_template, redirect, url_for
from flask_login import current_user
from app import app, db
from replit_auth import require_login, make_replit_blueprint
from models import Job, JobStatus, AccuracyMetric
from sqlalchemy import desc

app.register_blueprint(make_replit_blueprint(), url_prefix="/auth")

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


@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
