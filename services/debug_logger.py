"""
Debug logging utilities for the extraction pipeline
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

class DebugLogger:
    """Enhanced debug logger for extraction pipeline"""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.logs = []
        self.logger = logging.getLogger(__name__)
        
    def log_step(self, step_name: str, details: Dict[str, Any] = None):
        """Log a processing step with optional details"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'step': step_name,
            'job_id': self.job_id,
            'details': details or {}
        }
        
        self.logs.append(log_entry)
        
        # Also log to standard logger
        self.logger.debug(f"[Job {self.job_id}] Step: {step_name} | Details: {json.dumps(details or {})}")
        
        return log_entry
    
    def log_subprocess(self, command: List[str], stdout: str = None, stderr: str = None, 
                      exit_code: int = None, duration_ms: int = None):
        """Log subprocess execution details"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'subprocess',
            'job_id': self.job_id,
            'command': ' '.join(command),
            'exit_code': exit_code,
            'duration_ms': duration_ms,
            'stdout_size': len(stdout) if stdout else 0,
            'stderr_size': len(stderr) if stderr else 0,
            'stderr_preview': stderr[:500] if stderr else None
        }
        
        self.logs.append(log_entry)
        
        if stderr:
            self.logger.warning(f"[Job {self.job_id}] Subprocess stderr: {stderr[:500]}")
        
        return log_entry
    
    def log_detection(self, page_index: int, bbox: List[float], confidence: float,
                     pdf_path: str, headers: List[str] = None):
        """Log table detection details"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'detection',
            'job_id': self.job_id,
            'page_index': page_index,
            'bbox': bbox,
            'confidence': confidence,
            'pdf_path': pdf_path,
            'headers': headers
        }
        
        self.logs.append(log_entry)
        
        self.logger.debug(f"[Job {self.job_id}] Detection on page {page_index}: bbox={bbox}, confidence={confidence:.2f}")
        
        return log_entry
    
    def log_extraction(self, document_id: str, page_index: int, table_region: Dict[str, Any],
                      items_extracted: int = 0, error: str = None):
        """Log data extraction details"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'extraction',
            'job_id': self.job_id,
            'document_id': document_id,
            'page_index': page_index,
            'table_region': table_region,
            'items_extracted': items_extracted,
            'error': error
        }
        
        self.logs.append(log_entry)
        
        msg = f"[Job {self.job_id}] Extraction from document {document_id}, page {page_index}: {items_extracted} items"
        if error:
            self.logger.error(f"{msg} - Error: {error}")
        else:
            self.logger.debug(msg)
        
        return log_entry
    
    def log_error(self, step_name: str, error_message: str, exception: Exception = None):
        """Log an error that occurred during processing"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'error',
            'job_id': self.job_id,
            'step': step_name,
            'error_message': error_message,
            'exception_type': type(exception).__name__ if exception else None,
            'exception_str': str(exception) if exception else None
        }
        
        self.logs.append(log_entry)
        
        self.logger.error(f"[Job {self.job_id}] Error in {step_name}: {error_message}", exc_info=exception)
        
        return log_entry
    
    def get_logs(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get the collected logs, optionally limited to recent entries"""
        if limit and limit > 0:
            return self.logs[-limit:]
        return self.logs
    
    def get_stderr_summary(self) -> str:
        """Get a summary of all stderr outputs from subprocesses"""
        stderr_entries = [log for log in self.logs if log.get('type') == 'subprocess' and log.get('stderr_preview')]
        
        if not stderr_entries:
            return ""
        
        summary = []
        for entry in stderr_entries:
            summary.append(f"[{entry['timestamp']}] Command: {entry['command']}")
            summary.append(f"Exit Code: {entry.get('exit_code', 'N/A')}")
            summary.append(f"Stderr: {entry['stderr_preview']}")
            summary.append("-" * 40)
        
        return "\n".join(summary)
    
    def to_json(self) -> str:
        """Export logs as JSON string"""
        return json.dumps(self.logs, indent=2)