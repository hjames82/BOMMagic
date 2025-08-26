from datetime import datetime
from enum import Enum

from app import db
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, JSON


# (IMPORTANT) This table is mandatory for Replit Auth, don't drop it.
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=True)
    first_name = db.Column(db.String, nullable=True)
    last_name = db.Column(db.String, nullable=True)
    profile_image_url = db.Column(db.String, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationship to jobs
    jobs = db.relationship('Job', backref='user', lazy=True)


# (IMPORTANT) This table is mandatory for Replit Auth, don't drop it.
class OAuth(OAuthConsumerMixin, db.Model):
    user_id = db.Column(db.String, db.ForeignKey(User.id))
    browser_session_key = db.Column(db.String, nullable=False)
    user = db.relationship(User)

    __table_args__ = (UniqueConstraint(
        'user_id',
        'browser_session_key',
        'provider',
        name='uq_user_browser_session_key_provider',
    ),)


class JobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_REVIEW = "requires_review"
    REVIEWED = "reviewed"


class Job(db.Model):
    __tablename__ = 'jobs'
    
    id = db.Column(db.String, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    
    # File information
    original_filename = db.Column(db.String, nullable=False)
    file_path = db.Column(db.String, nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    file_hash = db.Column(db.String, unique=True, index=True, nullable=False)  # SHA256 hash
    
    # Processing status
    status = db.Column(db.Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    
    # Processing results
    confidence_score = db.Column(db.Float, nullable=True)
    extracted_data = db.Column(JSON, nullable=True)  # Raw extracted BOM data
    validated_data = db.Column(JSON, nullable=True)  # Validated/corrected BOM data
    
    # Error information
    error_message = db.Column(db.Text, nullable=True)
    
    # Export information
    export_path = db.Column(db.String, nullable=True)
    export_format = db.Column(db.String, nullable=True)  # csv, xlsx
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Processing metadata
    processing_metadata = db.Column(JSON, nullable=True)  # OCR results, table detection info, etc.


class BOMItem(db.Model):
    __tablename__ = 'bom_items'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String, db.ForeignKey('jobs.id'), nullable=False)
    
    # BOM fields
    item_number = db.Column(db.String, nullable=True)
    part_number = db.Column(db.String, nullable=True)
    description = db.Column(db.Text, nullable=True)
    quantity = db.Column(db.String, nullable=True)  # String to handle various formats
    unit = db.Column(db.String, nullable=True)
    material = db.Column(db.String, nullable=True)
    supplier = db.Column(db.String, nullable=True)
    cost = db.Column(db.String, nullable=True)  # String to handle currency and formats
    
    # Validation information
    confidence_score = db.Column(db.Float, nullable=True)
    is_validated = db.Column(db.Boolean, default=False)
    validation_notes = db.Column(db.Text, nullable=True)
    
    # Position in original document
    row_index = db.Column(db.Integer, nullable=True)
    bbox = db.Column(JSON, nullable=True)  # Bounding box coordinates
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class AccuracyMetric(db.Model):
    __tablename__ = 'accuracy_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String, db.ForeignKey('jobs.id'), nullable=False)
    
    # Accuracy measurements
    overall_confidence = db.Column(db.Float, nullable=False)
    table_detection_confidence = db.Column(db.Float, nullable=True)
    ocr_confidence = db.Column(db.Float, nullable=True)
    data_extraction_confidence = db.Column(db.Float, nullable=True)
    
    # Quality metrics
    total_items_detected = db.Column(db.Integer, nullable=True)
    items_with_high_confidence = db.Column(db.Integer, nullable=True)
    items_requiring_review = db.Column(db.Integer, nullable=True)
    
    # Processing times
    ocr_processing_time = db.Column(db.Float, nullable=True)
    table_detection_time = db.Column(db.Float, nullable=True)
    data_extraction_time = db.Column(db.Float, nullable=True)
    total_processing_time = db.Column(db.Float, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)


class ValidationRule(db.Model):
    __tablename__ = 'validation_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    rule_name = db.Column(db.String, nullable=False)
    rule_type = db.Column(db.String, nullable=False)  # header, data_type, format, etc.
    rule_config = db.Column(JSON, nullable=False)  # Rule configuration
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class Document(db.Model):
    __tablename__ = 'documents'
    
    id = db.Column(db.String, primary_key=True)
    original_filename = db.Column(db.String, nullable=False)
    file_path = db.Column(db.String, nullable=False)
    ocr_file_path = db.Column(db.String, nullable=True)
    file_size = db.Column(db.Integer, nullable=False)
    file_hash = db.Column(db.String, unique=True, index=True, nullable=False)  # SHA256 hash
    page_count = db.Column(db.Integer, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    detections = db.relationship('Detection', backref='document', lazy=True)


class Detection(db.Model):
    __tablename__ = 'detections'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.String, db.ForeignKey('documents.id'), nullable=False)
    page = db.Column(db.Integer, nullable=False)
    bbox_x0 = db.Column(db.Float, nullable=False)
    bbox_y0 = db.Column(db.Float, nullable=False)
    bbox_x1 = db.Column(db.Float, nullable=False)
    bbox_y1 = db.Column(db.Float, nullable=False)
    headers = db.Column(JSON, nullable=False)  # List of detected headers
    confidence = db.Column(db.Float, nullable=False)
    scores = db.Column(JSON, nullable=True)  # Detailed scoring breakdown
    
    # Review fields
    is_reviewed = db.Column(db.Boolean, default=False)
    is_correct = db.Column(db.Boolean, nullable=True)  # True if marked correct, False if not a BOM
    review_notes = db.Column(db.Text, nullable=True)
    human_verified = db.Column(db.Boolean, default=False)
    corrected_bbox = db.Column(JSON, nullable=True)  # User-corrected bbox
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    reviewed_at = db.Column(db.DateTime, nullable=True)


class OCRCache(db.Model):
    __tablename__ = 'ocr_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    page_hash = db.Column(db.String, nullable=False, unique=True, index=True)  # SHA256 of page
    pdf_path = db.Column(db.String, nullable=False)
    page_index = db.Column(db.Integer, nullable=False)
    text_content = db.Column(db.Text, nullable=True)
    text_xml = db.Column(db.Text, nullable=True)
    ocr_completed = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    used_count = db.Column(db.Integer, default=1)
    last_used = db.Column(db.DateTime, default=datetime.now)
