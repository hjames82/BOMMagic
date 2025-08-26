import subprocess
import xml.etree.ElementTree as ET
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def extract_words(pdf_path: str, page_index: int) -> List[Dict[str, Any]]:
    """
    Extract words with bounding boxes from PDF using pdftohtml XML.
    
    Args:
        pdf_path: Path to PDF file
        page_index: 1-based page index
    
    Returns:
        List of words with bbox: [{'text': str, 'x': float, 'y': float, 'w': float, 'h': float}]
    """
    words = []
    
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
        
        logger.info(f"Extracted {len(words)} words from page {page_index}")
        
    except subprocess.TimeoutExpired:
        logger.error(f"pdftohtml timed out for page {page_index}")
    except ET.ParseError as e:
        logger.error(f"XML parse error: {e}")
    except Exception as e:
        logger.error(f"Error extracting words: {str(e)}")
    
    return words