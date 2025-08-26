"""
Debug endpoints for job inspection and troubleshooting
"""

from flask import Blueprint, jsonify
from models import Job
import json
import logging

logger = logging.getLogger(__name__)

debug_bp = Blueprint('debug', __name__)


@debug_bp.route('/v1/jobs/<job_id>/debug', methods=['GET'])
def get_job_debug(job_id):
    """
    Get detailed debug information for a job
    
    Returns:
        - Full job JSON
        - last_step: The last processing step executed
        - error_message: Any error message with details
        - exit_code: Exit code from subprocess if applicable
        - stderr_logs: Recent stderr output from subprocesses  
        - recent_logs: Recent debug log entries
    """
    try:
        # Get job from database
        job = Job.query.get(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Build debug response
        response = {
            'job_id': job.id,
            'status': job.status.value if job.status else None,
            'last_step': job.last_step,
            'error_message': job.error_message,
            'exit_code': job.exit_code,
            'confidence_score': job.confidence_score,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'file_info': {
                'original_filename': job.original_filename,
                'file_path': job.file_path,
                'file_size': job.file_size,
                'file_hash': job.file_hash
            }
        }
        
        # Add stderr logs if available
        if job.stderr_logs:
            response['stderr_logs'] = job.stderr_logs
        
        # Parse and add recent debug logs
        if job.debug_logs:
            try:
                debug_logs = json.loads(job.debug_logs)
                # Get last 20 log entries
                response['recent_logs'] = debug_logs[-20:] if len(debug_logs) > 20 else debug_logs
                response['total_log_entries'] = len(debug_logs)
            except json.JSONDecodeError:
                response['recent_logs'] = []
                response['debug_logs_raw'] = job.debug_logs[:1000]  # First 1000 chars
        
        # Add processing metadata if available
        if job.processing_metadata:
            response['processing_metadata'] = job.processing_metadata
        
        # Add processing logs if available
        if job.processing_logs:
            response['processing_logs'] = job.processing_logs[-10:] if isinstance(job.processing_logs, list) else job.processing_logs
        
        # Add extracted data summary
        if job.extracted_data:
            if isinstance(job.extracted_data, list):
                response['extracted_data_count'] = len(job.extracted_data)
                response['extracted_data_sample'] = job.extracted_data[:3] if job.extracted_data else []
            else:
                response['extracted_data_summary'] = str(job.extracted_data)[:500]
        
        # Add validation data summary
        if job.validated_data:
            if isinstance(job.validated_data, list):
                response['validated_data_count'] = len(job.validated_data)
            else:
                response['validated_data_summary'] = str(job.validated_data)[:500]
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error getting debug info for job {job_id}: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to get debug information',
            'details': str(e)
        }), 500