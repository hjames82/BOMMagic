import subprocess
import xml.etree.ElementTree as ET
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def extract_words(pdf_path: str, page_index: int, use_cache: bool = True) -> List[Dict[str, Any]]:
    """
    Extract words with bounding boxes from PDF using pdftohtml XML.
    
    Args:
        pdf_path: Path to PDF file
        page_index: 1-based page index
        use_cache: Whether to use OCR cache
    
    Returns:
        List of words with bbox: [{'text': str, 'x': float, 'y': float, 'w': float, 'h': float}]
    """
    words = []
    
    # Check cache first if enabled
    if use_cache:
        try:
            from services.ocr_cache import compute_page_hash, get_cached_ocr, store_ocr_result
            page_hash = compute_page_hash(pdf_path, page_index)
            cached_result = get_cached_ocr(page_hash)
            
            if cached_result and cached_result[1]:  # Check if XML is cached
                # Parse cached XML
                root = ET.fromstring(cached_result[1])
                return parse_xml_words(root, page_index)
        except Exception as e:
            logger.debug(f"Cache check failed: {e}")
    
    try:
        # Run pdftohtml to extract XML
        cmd = [
            'pdftohtml',
            '-xml',
            '-hidden',
            '-f', str(page_index),
            '-l', str(page_index),
            '-stdout',
            pdf_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            logger.error(f"pdftohtml failed: {result.stderr}")
            return words
        
        # Parse XML
        root = ET.fromstring(result.stdout)
        
        # Cache the XML if caching is enabled
        if use_cache:
            try:
                from services.ocr_cache import compute_page_hash, store_ocr_result
                page_hash = compute_page_hash(pdf_path, page_index)
                # Extract text content for cache
                text_content = subprocess.run(
                    ['pdftotext', '-f', str(page_index), '-l', str(page_index), pdf_path, '-'],
                    capture_output=True, text=True, timeout=30
                ).stdout
                store_ocr_result(page_hash, pdf_path, page_index, text_content, result.stdout)
            except Exception as e:
                logger.debug(f"Failed to cache XML: {e}")
        
        words = parse_xml_words(root, page_index)
        
        logger.info(f"Extracted {len(words)} words from page {page_index}")
        
    except subprocess.TimeoutExpired:
        logger.error(f"pdftohtml timed out for page {page_index}")
    except ET.ParseError as e:
        logger.error(f"XML parse error: {e}")
    except Exception as e:
        logger.error(f"Error extracting words: {str(e)}")
    
    return words


def parse_xml_words(root: ET.Element, page_index: int) -> List[Dict[str, Any]]:
    """Parse words from XML root element."""
    words = []
    
    # Find the page element
    for page in root.findall('.//page'):
        page_num = int(page.get('number', 0))
        if page_num != page_index:
            continue
        
        # Extract text elements
        for text_elem in page.findall('.//text'):
            try:
                x = float(text_elem.get('left', 0))
                y = float(text_elem.get('top', 0))
                w = float(text_elem.get('width', 0))
                h = float(text_elem.get('height', 0))
                
                # Get all text content from child elements
                text_content = ''.join(text_elem.itertext()).strip()
                
                if text_content:
                    words.append({
                        'text': text_content,
                        'x': x,
                        'y': y,
                        'w': w,
                        'h': h
                    })
            except (ValueError, TypeError) as e:
                logger.debug(f"Error parsing text element: {e}")
                continue
    
    return words