import os
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from .ocr_service import OCRService
from .table_detector import TableDetector
from .data_extractor import DataExtractor
from .validation_service import ValidationService

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Main document processing pipeline for BOM extraction"""
    
    def __init__(self):
        self.ocr_service = OCRService()
        self.table_detector = TableDetector()
        self.data_extractor = DataExtractor()
        self.validation_service = ValidationService()
    
    def process_document(self, file_path: str, job_id: str) -> Dict[str, Any]:
        """
        Complete document processing pipeline
        
        Args:
            file_path: Path to the document file
            job_id: Unique job identifier
            
        Returns:
            Dictionary containing processing results and metadata
        """
        start_time = time.time()
        results = {
            'job_id': job_id,
            'success': False,
            'confidence_score': 0.0,
            'extracted_data': [],
            'metadata': {},
            'error_message': None,
            'processing_times': {}
        }
        
        try:
            logger.info(f"Starting document processing for job {job_id}")
            
            # Step 1: OCR Processing
            logger.info(f"Step 1: OCR processing for job {job_id}")
            ocr_start = time.time()
            ocr_result = self.ocr_service.process_document(file_path)
            ocr_time = time.time() - ocr_start
            results['processing_times']['ocr'] = ocr_time
            
            if not ocr_result['success']:
                results['error_message'] = f"OCR failed: {ocr_result.get('error', 'Unknown error')}"
                return results
            
            results['metadata']['ocr'] = ocr_result['metadata']
            
            # Step 2: Table Detection
            logger.info(f"Step 2: Table detection for job {job_id}")
            table_start = time.time()
            table_result = self.table_detector.detect_tables(
                ocr_result['processed_file_path'],
                ocr_result['text_data']
            )
            table_time = time.time() - table_start
            results['processing_times']['table_detection'] = table_time
            
            if not table_result['success']:
                results['error_message'] = f"Table detection failed: {table_result.get('error', 'Unknown error')}"
                return results
            
            results['metadata']['table_detection'] = table_result['metadata']
            
            # Step 3: Data Extraction
            logger.info(f"Step 3: Data extraction for job {job_id}")
            extraction_start = time.time()
            extraction_result = self.data_extractor.extract_bom_data(
                file_path,
                table_result['tables']
            )
            extraction_time = time.time() - extraction_start
            results['processing_times']['data_extraction'] = extraction_time
            
            if not extraction_result['success']:
                results['error_message'] = f"Data extraction failed: {extraction_result.get('error', 'Unknown error')}"
                return results
            
            results['metadata']['data_extraction'] = extraction_result['metadata']
            results['extracted_data'] = extraction_result['bom_data']
            
            # Step 4: Validation
            logger.info(f"Step 4: Validation for job {job_id}")
            validation_start = time.time()
            validation_result = self.validation_service.validate_bom_data(
                results['extracted_data']
            )
            validation_time = time.time() - validation_start
            results['processing_times']['validation'] = validation_time
            
            results['metadata']['validation'] = validation_result['metadata']
            results['confidence_score'] = validation_result['overall_confidence']
            
            # Update extracted data with validation results
            for i, item in enumerate(results['extracted_data']):
                if i < len(validation_result['item_validations']):
                    item.update(validation_result['item_validations'][i])
            
            # Calculate total processing time
            total_time = time.time() - start_time
            results['processing_times']['total'] = total_time
            
            # Determine if manual review is required
            confidence_threshold = float(os.getenv('CONFIDENCE_THRESHOLD', '0.8'))
            results['requires_review'] = results['confidence_score'] < confidence_threshold
            
            results['success'] = True
            logger.info(f"Document processing completed for job {job_id} in {total_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Document processing failed for job {job_id}: {str(e)}")
            results['error_message'] = f"Processing failed: {str(e)}"
            results['processing_times']['total'] = time.time() - start_time
        
        return results
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported file formats"""
        return ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif']
    
    def validate_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if file can be processed
        
        Args:
            file_path: Path to the file
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not os.path.exists(file_path):
            return False, "File does not exist"
        
        if os.path.getsize(file_path) == 0:
            return False, "File is empty"
        
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in self.get_supported_formats():
            return False, f"Unsupported file format: {file_ext}"
        
        # Check file size (max 50MB)
        max_size = 50 * 1024 * 1024
        if os.path.getsize(file_path) > max_size:
            return False, "File size exceeds 50MB limit"
        
        return True, None
