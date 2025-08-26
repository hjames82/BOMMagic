import os
import logging
from datetime import datetime
from typing import Dict, Any
from redis import Redis
from rq import Worker, Queue

from app import app, db
from models import Job, JobStatus, BOMItem, AccuracyMetric
from services.document_processor import DocumentProcessor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis connection
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
redis_conn = Redis.from_url(redis_url)

# Create RQ queues
high_queue = Queue('high', connection=redis_conn)
default_queue = Queue('default', connection=redis_conn)
low_queue = Queue('low', connection=redis_conn)


def process_document_job(job_id: str, page_number: int = None) -> None:
    """
    Process a document or specific page in Redis RQ worker
    
    Args:
        job_id: Unique job identifier
        page_number: Specific page to process (None for full document)
    """
    with app.app_context():
        try:
            # Get job from database
            job = Job.query.get(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return
            
            # Update job status
            if job.status == JobStatus.PENDING:
                job.status = JobStatus.PROCESSING
                job.started_at = datetime.now()
                db.session.commit()
            
            logger.info(f"Processing job {job_id}, page {page_number or 'all'}")
            
            # Initialize document processor
            processor = DocumentProcessor()
            
            # Validate file
            is_valid, error_message = processor.validate_file(job.file_path)
            if not is_valid:
                _handle_job_failure(job, f"File validation failed: {error_message}")
                return
            
            # Process document with pipeline stages
            results = process_pipeline(job, processor, page_number)
            
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
            
            # Check confidence threshold for auto-export
            confidence_threshold = float(os.getenv('CONFIDENCE_THRESHOLD', '0.92'))
            
            if results['confidence_score'] >= confidence_threshold:
                # Auto-export if confidence is high enough
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now()
                logger.info(f"Job {job_id} auto-exported (confidence: {results['confidence_score']:.2f})")
                
                # Trigger export job
                default_queue.enqueue(
                    'worker.export_results_job',
                    job_id=job_id,
                    format='csv'
                )
            else:
                # Flag for review if confidence is low
                job.status = JobStatus.REQUIRES_REVIEW
                logger.info(f"Job {job_id} requires review (confidence: {results['confidence_score']:.2f})")
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Processing failed for job {job_id}: {str(e)}", exc_info=True)
            with app.app_context():
                job = Job.query.get(job_id)
                if job:
                    _handle_job_failure(job, f"Processing error: {str(e)}")


def process_pipeline(job: Job, processor: DocumentProcessor, page_number: int = None) -> Dict[str, Any]:
    """
    Execute the multi-stage processing pipeline
    
    Stage 1: OCRmyPDF - Add searchable text layer
    Stage 2: Table Detection - Find BOM table regions
    Stage 3: Data Extraction - Parse tables with Camelot/pdfplumber
    Stage 4: Validation - Apply rules and confidence scoring
    """
    try:
        metadata = {}
        processing_times = {}
        
        # Stage 1: OCR Processing
        logger.info(f"Stage 1: OCR processing for job {job.id}")
        ocr_start = datetime.now()
        
        ocr_results = processor.ocr_service.process_document(job.file_path)
        
        processing_times['ocr'] = (datetime.now() - ocr_start).total_seconds()
        metadata['ocr'] = ocr_results
        
        if not ocr_results['success']:
            return {
                'success': False,
                'error_message': f"OCR failed: {ocr_results.get('error_message', 'Unknown error')}"
            }
        
        # Use OCR'd PDF for further processing
        processed_file = ocr_results.get('processed_file_path', job.file_path)
        
        # Stage 2: Table Detection
        logger.info(f"Stage 2: Table detection for job {job.id}")
        detect_start = datetime.now()
        
        table_results = processor.table_detector.detect_tables(processed_file, ocr_results.get('text_data', {}))
        
        processing_times['table_detection'] = (datetime.now() - detect_start).total_seconds()
        metadata['table_detection'] = table_results
        
        if not table_results['success']:
            return {
                'success': False,
                'error_message': f"Table detection failed: {table_results.get('error_message')}"
            }
        
        # Stage 3: Data Extraction
        logger.info(f"Stage 3: Data extraction for job {job.id}")
        extract_start = datetime.now()
        
        extraction_results = processor.data_extractor.extract_bom_data(
            processed_file,
            table_results.get('table_regions', [])
        )
        
        processing_times['data_extraction'] = (datetime.now() - extract_start).total_seconds()
        metadata['data_extraction'] = extraction_results
        
        if not extraction_results['success']:
            return {
                'success': False,
                'error_message': f"Data extraction failed: {extraction_results.get('error_message')}"
            }
        
        # Stage 4: Validation and Confidence Scoring
        logger.info(f"Stage 4: Validation for job {job.id}")
        validate_start = datetime.now()
        
        validation_results = processor.validation_service.validate_bom_data(
            extraction_results['extracted_data']
        )
        
        processing_times['validation'] = (datetime.now() - validate_start).total_seconds()
        metadata['validation'] = validation_results
        
        # Calculate overall confidence
        confidence_components = [
            ocr_results.get('confidence', 0.5),
            table_results.get('confidence', 0.5),
            extraction_results.get('confidence', 0.5),
            validation_results.get('confidence', 0.5)
        ]
        overall_confidence = sum(confidence_components) / len(confidence_components)
        
        processing_times['total'] = sum(processing_times.values())
        
        return {
            'success': True,
            'confidence_score': overall_confidence,
            'extracted_data': validation_results.get('validated_data', extraction_results['extracted_data']),
            'metadata': metadata,
            'processing_times': processing_times,
            'requires_review': overall_confidence < float(os.getenv('CONFIDENCE_THRESHOLD', '0.92'))
        }
        
    except Exception as e:
        logger.error(f"Pipeline processing error: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error_message': f"Pipeline error: {str(e)}"
        }


def export_results_job(job_id: str, format: str = 'csv') -> None:
    """
    Export job results to specified format
    """
    with app.app_context():
        try:
            from services.export_service import ExportService
            
            job = Job.query.get(job_id)
            if not job:
                logger.error(f"Job {job_id} not found for export")
                return
            
            # Get BOM items
            bom_items = BOMItem.query.filter_by(job_id=job_id).all()
            
            # Convert to export format
            export_service = ExportService()
            export_data = []
            
            for item in bom_items:
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
            export_path = f"/tmp/export_{job_id}.{format}"
            
            if format == 'csv':
                export_service.export_to_csv(export_data, export_path)
            elif format == 'xlsx':
                export_service.export_to_xlsx(export_data, export_path)
            
            # Update job with export information
            job.export_path = export_path
            job.export_format = format
            db.session.commit()
            
            logger.info(f"Exported job {job_id} to {format} format")
            
        except Exception as e:
            logger.error(f"Export failed for job {job_id}: {str(e)}", exc_info=True)


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
        for idx, item_data in enumerate(extracted_data):
            bom_item = BOMItem()
            bom_item.job_id = job_id
            bom_item.item_number = item_data.get('item_number')
            bom_item.part_number = item_data.get('part_number')
            bom_item.description = item_data.get('description')
            bom_item.quantity = item_data.get('quantity')
            bom_item.unit = item_data.get('unit')
            bom_item.material = item_data.get('material')
            bom_item.supplier = item_data.get('supplier')
            bom_item.cost = item_data.get('cost')
            bom_item.confidence_score = item_data.get('confidence_score', 0.5)
            bom_item.row_index = item_data.get('row_index', idx)
            bom_item.bbox = item_data.get('bbox')
            
            db.session.add(bom_item)
        
        db.session.commit()
        logger.info(f"Saved {len(extracted_data)} BOM items for job {job_id}")
        
    except Exception as e:
        logger.error(f"Failed to save BOM items for job {job_id}: {str(e)}", exc_info=True)
        db.session.rollback()
        raise


def _save_accuracy_metrics(job_id: str, results: Dict[str, Any]) -> None:
    """Save accuracy metrics to database"""
    try:
        # Extract processing times
        processing_times = results.get('processing_times', {})
        
        # Calculate additional metrics
        metadata = results.get('metadata', {})
        ocr_confidence = metadata.get('ocr', {}).get('confidence', 0.5)
        table_confidence = metadata.get('table_detection', {}).get('confidence', 0.5)
        extraction_confidence = metadata.get('data_extraction', {}).get('confidence', 0.5)
        
        # Count items by confidence level
        extracted_data = results.get('extracted_data', [])
        total_items = len(extracted_data)
        high_confidence_items = sum(1 for item in extracted_data 
                                  if item.get('confidence_score', 0) >= 0.8)
        review_items = total_items - high_confidence_items
        
        # Create accuracy metric record
        metric = AccuracyMetric()
        metric.job_id = job_id
        metric.overall_confidence = results['confidence_score']
        metric.table_detection_confidence = table_confidence
        metric.ocr_confidence = ocr_confidence
        metric.data_extraction_confidence = extraction_confidence
        metric.total_items_detected = total_items
        metric.items_with_high_confidence = high_confidence_items
        metric.items_requiring_review = review_items
        metric.ocr_processing_time = processing_times.get('ocr')
        metric.table_detection_time = processing_times.get('table_detection')
        metric.data_extraction_time = processing_times.get('data_extraction')
        metric.total_processing_time = processing_times.get('total')
        
        db.session.add(metric)
        db.session.commit()
        
        logger.info(f"Saved accuracy metrics for job {job_id}")
        
    except Exception as e:
        logger.error(f"Failed to save accuracy metrics for job {job_id}: {str(e)}", exc_info=True)
        db.session.rollback()
        raise


if __name__ == '__main__':
    # Start RQ worker
    worker = Worker([high_queue, default_queue, low_queue], connection=redis_conn)
    worker.work()