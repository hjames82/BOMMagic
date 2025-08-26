"""
OCR Caching Service
Implements page-level caching for OCR results
"""

import hashlib
import logging
from typing import Optional, Tuple
from datetime import datetime
from models import db, OCRCache
import subprocess

logger = logging.getLogger(__name__)


def compute_page_hash(pdf_path: str, page_index: int) -> str:
    """
    Compute SHA256 hash for a specific page.
    Uses page content extracted via pdftotext.
    """
    try:
        # Extract page text to compute hash
        cmd = [
            'pdftotext',
            '-f', str(page_index),
            '-l', str(page_index),
            pdf_path,
            '-'
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        # Use both stdout and return code for hash
        # This ensures different content = different hash
        content = f"{result.stdout}{result.returncode}".encode()
        
        # If no text, try to get page image info
        if len(result.stdout) < 10:
            # Use pdftoppm to get page image dimensions
            cmd_info = ['pdfinfo', '-f', str(page_index), '-l', str(page_index), pdf_path]
            info_result = subprocess.run(cmd_info, capture_output=True, timeout=10)
            content += info_result.stdout
        
        # Compute SHA256
        sha256 = hashlib.sha256()
        sha256.update(content)
        sha256.update(f"page_{page_index}".encode())
        
        return sha256.hexdigest()
        
    except Exception as e:
        logger.error(f"Error computing page hash: {str(e)}")
        # Fallback: use file path and page number
        fallback = f"{pdf_path}_page_{page_index}_{datetime.now().timestamp()}"
        return hashlib.sha256(fallback.encode()).hexdigest()


def get_cached_ocr(page_hash: str) -> Optional[Tuple[str, str]]:
    """
    Check if OCR result exists in cache.
    Returns (text_content, text_xml) if found, None otherwise.
    """
    try:
        cache_entry = OCRCache.query.filter_by(page_hash=page_hash).first()
        
        if cache_entry and cache_entry.ocr_completed:
            # Update usage statistics
            cache_entry.used_count += 1
            cache_entry.last_used = datetime.now()
            db.session.commit()
            
            logger.info(f"OCR cache hit for hash {page_hash[:8]}... (used {cache_entry.used_count} times)")
            return cache_entry.text_content, cache_entry.text_xml
        
        return None
        
    except Exception as e:
        logger.error(f"Error retrieving from OCR cache: {str(e)}")
        return None


def store_ocr_result(page_hash: str, pdf_path: str, page_index: int, 
                    text_content: str, text_xml: str = None):
    """
    Store OCR result in cache.
    """
    try:
        # Check if entry exists
        cache_entry = OCRCache.query.filter_by(page_hash=page_hash).first()
        
        if cache_entry:
            # Update existing entry
            cache_entry.text_content = text_content
            cache_entry.text_xml = text_xml
            cache_entry.ocr_completed = True
            cache_entry.used_count += 1
            cache_entry.last_used = datetime.now()
        else:
            # Create new entry
            cache_entry = OCRCache(
                page_hash=page_hash,
                pdf_path=pdf_path,
                page_index=page_index,
                text_content=text_content,
                text_xml=text_xml,
                ocr_completed=True
            )
            db.session.add(cache_entry)
        
        db.session.commit()
        logger.info(f"Stored OCR result in cache for hash {page_hash[:8]}...")
        
    except Exception as e:
        logger.error(f"Error storing OCR result in cache: {str(e)}")
        db.session.rollback()


def check_ocr_needed(pdf_path: str, page_index: int) -> Tuple[bool, Optional[str]]:
    """
    Check if OCR is needed for a page.
    Returns (needs_ocr, cached_text).
    """
    # Compute hash
    page_hash = compute_page_hash(pdf_path, page_index)
    
    # Check cache
    cached_result = get_cached_ocr(page_hash)
    
    if cached_result:
        text_content, _ = cached_result
        return False, text_content  # OCR not needed, return cached text
    
    # Check if page has text
    try:
        cmd = ['pdftotext', '-f', str(page_index), '-l', str(page_index), pdf_path, '-']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and len(result.stdout.strip()) > 100:
            # Page has text, store in cache
            store_ocr_result(page_hash, pdf_path, page_index, result.stdout)
            return False, result.stdout  # OCR not needed
            
    except Exception as e:
        logger.error(f"Error checking page text: {str(e)}")
    
    return True, None  # OCR needed