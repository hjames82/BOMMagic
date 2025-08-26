import os
from typing import Dict, Any


class Config:
    """Application configuration"""
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Session configuration
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'dev-secret-key')
    SESSION_PERMANENT = True
    
    # File upload configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = '/tmp/uploads'
    
    # Processing configuration
    CONFIDENCE_THRESHOLD = float(os.environ.get('CONFIDENCE_THRESHOLD', '0.8'))
    
    # OCR configuration
    OCR_TIMEOUT = int(os.environ.get('OCR_TIMEOUT', '300'))  # 5 minutes
    TESSERACT_CONFIG = '--psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz .,:-()[]'
    
    # Export configuration
    EXPORT_FORMATS = ['csv', 'xlsx']
    
    @staticmethod
    def get_processing_config() -> Dict[str, Any]:
        """Get processing-specific configuration"""
        return {
            'confidence_threshold': Config.CONFIDENCE_THRESHOLD,
            'ocr_timeout': Config.OCR_TIMEOUT,
            'tesseract_config': Config.TESSERACT_CONFIG,
            'max_file_size': Config.MAX_CONTENT_LENGTH,
            'supported_formats': ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif']
        }
    
    @staticmethod
    def get_validation_rules() -> Dict[str, Any]:
        """Get validation rules configuration"""
        return {
            'min_confidence_for_auto_export': 0.8,
            'require_part_number': True,
            'require_description': True,
            'require_quantity': True,
            'max_description_length': 500,
            'quantity_patterns': [r'^\d+(\.\d+)?$'],
            'part_number_patterns': [r'^[A-Z0-9\-_\.]+$']
        }
