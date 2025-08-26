import os
import logging
from datetime import datetime
from typing import Dict, Any

from app import app, db
from models import Job, JobStatus, BOMItem, AccuracyMetric
from services.document_processor import DocumentProcessor

logger = logging.getLogger(__name__)


def process_document_async(job_id: str) -> None:
    """
    Asynchronous worker function to process documents
    
    Args:
        job_id: Unique job identifier
    """
    with app.app_context():
        try:
            # Get job from database
            job = Job.query.get(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return
            
            # Update job status
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.now()
            db.session.commit()
            
            logger.info(f"Starting processing for job {job_id}")
            
            # Initialize document processor
            processor = DocumentProcessor()
            
            # Validate file
            is_valid, error_message = processor.validate_file(job.file_path)
            if not is_valid:
                _handle_job_failure(job, f"File validation failed: {error_message}")
                return
            
            # Process document
            results = processor.process_document(job.file_path, job_id)
            
            if not results['success']:
                _handle_job_failure(job, results['error_message'])
                return
            
            # Store processing results
            job.confidence_score = results['confidence_score']
            job.extracted_data = results['extracted_data']
            job.processing_metadata = results['metadata']
            
            # Save BOM items to database
            _save_bom_items(job_id, results['extracted_data'])
            
            # Save accuracy metrics
            _save_accuracy_metrics(job_id, results)
            
            # Determine final status
            if results.get('requires_review', False):
                job.status = JobStatus.REQUIRES_REVIEW
                logger.info(f"Job {job_id} requires manual review (confidence: {results['confidence_score']:.2f})")
            else:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now()
                logger.info(f"Job {job_id} completed successfully (confidence: {results['confidence_score']:.2f})")
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Processing failed for job {job_id}: {str(e)}")
            with app.app_context():
                job = Job.query.get(job_id)
                if job:
                    _handle_job_failure(job, f"Processing error: {str(e)}")


def _handle_job_failure(job: Job, error_message: str) -> None:
    """Handle job processing failure"""
    try:
        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now()
        db.session.commit()
        
        logger.error(f"Job {job.id} failed: {error_message}")
        
    except Exception as e:
        logger.error(f"Failed to update job failure status: {str(e)}")


def _save_bom_items(job_id: str, extracted_data: list) -> None:
    """Save extracted BOM items to database"""
    try:
        # Clear any existing items for this job
        BOMItem.query.filter_by(job_id=job_id).delete()
        
        # Save new items
        for item_data in extracted_data:
            bom_item = BOMItem(
                job_id=job_id,
                item_number=item_data.get('item_number'),
                part_number=item_data.get('part_number'),
                description=item_data.get('description'),
                quantity=item_data.get('quantity'),
                unit=item_data.get('unit'),
                material=item_data.get('material'),
                supplier=item_data.get('supplier'),
                cost=item_data.get('cost'),
                confidence_score=item_data.get('confidence_score', 0.5),
                row_index=item_data.get('row_index', 0),
                bbox=item_data.get('bbox')
            )
            
            db.session.add(bom_item)
        
        db.session.commit()
        logger.info(f"Saved {len(extracted_data)} BOM items for job {job_id}")
        
    except Exception as e:
        logger.error(f"Failed to save BOM items for job {job_id}: {str(e)}")
        db.session.rollback()
        raise


def _save_accuracy_metrics(job_id: str, results: Dict[str, Any]) -> None:
    """Save accuracy metrics to database"""
    try:
        # Extract processing times
        processing_times = results.get('processing_times', {})
        
        # Calculate additional metrics
        metadata = results.get('metadata', {})
        ocr_confidence = metadata.get('ocr', {}).get('average_confidence', 0) / 100.0
        table_confidence = metadata.get('table_detection', {}).get('bom_tables_likely', 0)
        extraction_confidence = metadata.get('data_extraction', {}).get('confidence', 0)
        
        # Count items by confidence level
        extracted_data = results.get('extracted_data', [])
        total_items = len(extracted_data)
        high_confidence_items = sum(1 for item in extracted_data 
                                  if item.get('confidence_score', 0) >= 0.8)
        review_items = total_items - high_confidence_items
        
        # Create accuracy metric record
        metric = AccuracyMetric(
            job_id=job_id,
            overall_confidence=results['confidence_score'],
            table_detection_confidence=table_confidence,
            ocr_confidence=ocr_confidence,
            data_extraction_confidence=extraction_confidence,
            total_items_detected=total_items,
            items_with_high_confidence=high_confidence_items,
            items_requiring_review=review_items,
            ocr_processing_time=processing_times.get('ocr'),
            table_detection_time=processing_times.get('table_detection'),
            data_extraction_time=processing_times.get('data_extraction'),
            total_processing_time=processing_times.get('total')
        )
        
        db.session.add(metric)
        db.session.commit()
        
        logger.info(f"Saved accuracy metrics for job {job_id}")
        
    except Exception as e:
        logger.error(f"Failed to save accuracy metrics for job {job_id}: {str(e)}")
        db.session.rollback()
        raise
