import logging
from typing import List, Dict, Any, Tuple
from services.layout_xml import extract_words
import re

logger = logging.getLogger(__name__)


def detect_bom_regions(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Detect BOM regions in a PDF document.
    
    Returns:
        List of candidate BOM regions sorted by confidence desc
        Each candidate: {page, bbox[x0,y0,x1,y1], headers[], confidence}
    """
    # BOM header keywords
    header_keywords = [
        'item', 'part', 'p/n', 'part no', 'qty', 'quantity', 
        'description', 'unit', 'uom', 'price', 'cost', 'material'
    ]
    
    candidates = []
    
    # Get total pages (try up to 50 pages max)
    for page_index in range(1, 51):
        try:
            words = extract_words(pdf_path, page_index)
            if not words:
                break  # No more pages
            
            # Build lines by y-clustering
            lines = cluster_words_into_lines(words)
            
            # Look for header lines
            for line_idx, line in enumerate(lines):
                headers = find_headers_in_line(line, header_keywords)
                
                if len(headers) >= 2:  # Found potential header line
                    # Infer column x-bands
                    col_bands = infer_column_bands(line)
                    
                    if 3 <= len(col_bands) <= 9:
                        # Extract region below header
                        bbox = extract_region_bbox(lines, line_idx, col_bands)
                        
                        # Score the region
                        confidence = score_bom_region(lines, line_idx, headers, col_bands)
                        
                        if confidence >= 0.70:
                            candidates.append({
                                'page': page_index,
                                'bbox': bbox,
                                'headers': [h['text'] for h in headers],
                                'confidence': confidence
                            })
            
            # Keep top 3 candidates per page
            page_candidates = [c for c in candidates if c['page'] == page_index]
            page_candidates.sort(key=lambda x: x['confidence'], reverse=True)
            candidates = [c for c in candidates if c['page'] != page_index] + page_candidates[:3]
            
        except Exception as e:
            logger.error(f"Error processing page {page_index}: {str(e)}")
            continue
    
    # Sort all candidates by confidence
    candidates.sort(key=lambda x: x['confidence'], reverse=True)
    
    return candidates


def cluster_words_into_lines(words: List[Dict[str, Any]], y_threshold: float = 5) -> List[List[Dict[str, Any]]]:
    """Cluster words into lines based on y-coordinate."""
    if not words:
        return []
    
    # Sort by y then x
    words = sorted(words, key=lambda w: (w['y'], w['x']))
    
    lines = []
    current_line = [words[0]]
    current_y = words[0]['y']
    
    for word in words[1:]:
        if abs(word['y'] - current_y) <= y_threshold:
            current_line.append(word)
        else:
            lines.append(sorted(current_line, key=lambda w: w['x']))
            current_line = [word]
            current_y = word['y']
    
    if current_line:
        lines.append(sorted(current_line, key=lambda w: w['x']))
    
    return lines


def find_headers_in_line(line: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
    """Find header keywords in a line."""
    headers = []
    
    for word in line:
        text_lower = word['text'].lower().strip()
        for keyword in keywords:
            if keyword in text_lower or text_lower in keyword:
                headers.append(word)
                break
    
    return headers


def infer_column_bands(line: List[Dict[str, Any]], gap_threshold: float = 20) -> List[Tuple[float, float]]:
    """Infer column x-bands from gaps between words."""
    if not line:
        return []
    
    bands = []
    current_start = line[0]['x']
    current_end = line[0]['x'] + line[0]['w']
    
    for i in range(1, len(line)):
        word = line[i]
        gap = word['x'] - current_end
        
        if gap > gap_threshold:
            # Found column boundary
            bands.append((current_start, current_end))
            current_start = word['x']
            current_end = word['x'] + word['w']
        else:
            current_end = max(current_end, word['x'] + word['w'])
    
    bands.append((current_start, current_end))
    
    return bands


def extract_region_bbox(lines: List[List[Dict[str, Any]]], header_idx: int, 
                        col_bands: List[Tuple[float, float]]) -> List[float]:
    """Extract bounding box for region below header."""
    if not lines or header_idx >= len(lines):
        return [0, 0, 0, 0]
    
    header_line = lines[header_idx]
    if not header_line:
        return [0, 0, 0, 0]
    
    # Start from header line
    x0 = min(col_bands, key=lambda b: b[0])[0] if col_bands else header_line[0]['x']
    y0 = header_line[0]['y']
    x1 = max(col_bands, key=lambda b: b[1])[1] if col_bands else header_line[-1]['x'] + header_line[-1]['w']
    
    # Extend down to include data rows (next 20 lines or until empty line)
    y1 = y0 + header_line[0]['h']
    for i in range(header_idx + 1, min(header_idx + 21, len(lines))):
        if not lines[i]:
            break
        last_word = lines[i][-1]
        y1 = max(y1, last_word['y'] + last_word['h'])
    
    return [x0, y0, x1, y1]


def score_bom_region(lines: List[List[Dict[str, Any]]], header_idx: int,
                     headers: List[Dict[str, Any]], col_bands: List[Tuple[float, float]]) -> float:
    """Score a potential BOM region."""
    # Header score: fraction of header synonyms matched
    expected_headers = ['item', 'part', 'qty', 'description']
    header_texts = [h['text'].lower() for h in headers]
    matched = sum(1 for exp in expected_headers if any(exp in h for h in header_texts))
    header_score = matched / len(expected_headers)
    
    # Column count score
    col_count = len(col_bands)
    if 3 <= col_count <= 9:
        col_count_score = 1.0
    elif col_count < 3:
        col_count_score = col_count / 3.0
    else:
        col_count_score = max(0, 1.0 - (col_count - 9) * 0.1)
    
    # Quantity numeric score - check if presumed qty column has numbers
    qty_numeric_score = 0.5  # Default score
    
    # Try to find qty column
    qty_col_idx = -1
    for i, band in enumerate(col_bands):
        for h in headers:
            if 'qty' in h['text'].lower() or 'quantity' in h['text'].lower():
                if band[0] <= h['x'] <= band[1]:
                    qty_col_idx = i
                    break
    
    if qty_col_idx >= 0 and header_idx + 1 < len(lines):
        # Check next 5 lines for numeric content in qty column
        numeric_count = 0
        total_count = 0
        
        for i in range(header_idx + 1, min(header_idx + 6, len(lines))):
            for word in lines[i]:
                if col_bands[qty_col_idx][0] <= word['x'] <= col_bands[qty_col_idx][1]:
                    total_count += 1
                    if re.search(r'\d+', word['text']):
                        numeric_count += 1
        
        if total_count > 0:
            qty_numeric_score = numeric_count / total_count
    
    # Calculate weighted confidence
    confidence = 0.4 * header_score + 0.3 * col_count_score + 0.3 * qty_numeric_score
    
    return confidence