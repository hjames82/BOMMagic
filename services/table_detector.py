import logging
import re
import os
from typing import Dict, List, Any, Tuple, Union

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("OpenCV/NumPy not available, image-based table detection will be disabled")

logger = logging.getLogger(__name__)


class TableDetector:
    """Service for detecting and locating BOM tables in documents"""
    
    def __init__(self):
        # BOM-related keywords to look for
        self.bom_keywords = [
            'bill of materials', 'bom', 'material list', 'parts list',
            'item', 'part', 'description', 'qty', 'quantity', 'unit',
            'material', 'supplier', 'cost', 'price', 'drawing', 'spec'
        ]
        
        # Common BOM header patterns
        self.header_patterns = [
            r'item\s*no\.?',
            r'part\s*no\.?',
            r'description',
            r'qty\.?',
            r'quantity',
            r'unit',
            r'material',
            r'supplier',
            r'cost',
            r'price'
        ]
    
    def detect_tables(self, file_path: str, text_data: Dict[str, Any], debug_logger=None) -> Dict[str, Any]:
        """
        Detect BOM tables in the document
        
        Args:
            file_path: Path to the processed document
            text_data: OCR extracted text data
            
        Returns:
            Dictionary containing detected tables and metadata
        """
        result = {
            'success': False,
            'tables': [],
            'metadata': {},
            'error': None
        }
        
        try:
            # Method 1: Text-based table detection
            text_tables = self._detect_tables_from_text(text_data)
            
            if debug_logger:
                debug_logger.log_step("text_table_detection", {
                    "tables_found": len(text_tables),
                    "file_path": file_path
                })
            
            # Method 2: Image-based table detection (if available)
            image_tables = []
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.tif')):
                image_tables = self._detect_tables_from_image(file_path)
                if debug_logger:
                    debug_logger.log_step("image_table_detection", {
                        "tables_found": len(image_tables),
                        "file_path": file_path
                    })
            
            # Combine and rank tables
            all_tables = text_tables + image_tables
            ranked_tables = self._rank_tables_by_bom_likelihood(all_tables, text_data)
            
            # Log detected tables with debug_logger
            if debug_logger:
                for idx, table in enumerate(ranked_tables):
                    if table.get('bbox'):
                        debug_logger.log_detection(
                            page_index=table.get('page_number', 1),
                            bbox=table.get('bbox'),
                            confidence=table.get('confidence', 0),
                            pdf_path=file_path,
                            headers=table.get('detected_headers', [])
                        )
            
            result.update({
                'success': True,
                'tables': ranked_tables,
                'metadata': {
                    'text_tables_found': len(text_tables),
                    'image_tables_found': len(image_tables),
                    'total_tables': len(ranked_tables),
                    'bom_tables_likely': len([t for t in ranked_tables if t.get('bom_likelihood', 0) > 0.5])
                }
            })
            
        except Exception as e:
            logger.error(f"Table detection failed: {str(e)}")
            result['error'] = str(e)
        
        return result
    
    def _detect_tables_from_text(self, text_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect tables based on text patterns"""
        tables = []
        
        for page_data in text_data.get('pages', []):
            page_text = page_data.get('text', '')
            page_number = page_data.get('page_number', 1)
            
            # Split text into lines
            lines = page_text.split('\n')
            
            # Look for table-like structures
            table_regions = self._find_table_regions(lines)
            
            for region in table_regions:
                table = {
                    'type': 'text_based',
                    'page_number': page_number,
                    'start_line': region['start'],
                    'end_line': region['end'],
                    'lines': region['lines'],
                    'confidence': region['confidence'],
                    'bbox': None  # Not available for text-based detection
                }
                tables.append(table)
        
        return tables
    
    def _detect_tables_from_image(self, image_path: str) -> List[Dict[str, Any]]:
        """Detect tables using computer vision techniques"""
        tables = []
        
        try:
            # Read image
            image = cv2.imread(image_path)
            if image is None:
                return tables
            
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Apply thresholding
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
            
            # Detect horizontal and vertical lines
            horizontal_lines = self._detect_horizontal_lines(thresh)
            vertical_lines = self._detect_vertical_lines(thresh)
            
            # Find table candidates based on line intersections
            table_candidates = self._find_table_candidates(horizontal_lines, vertical_lines, image.shape)
            
            for i, candidate in enumerate(table_candidates):
                table = {
                    'type': 'image_based',
                    'page_number': 1,
                    'bbox': candidate['bbox'],
                    'confidence': candidate['confidence'],
                    'lines': None
                }
                tables.append(table)
        
        except Exception as e:
            logger.error(f"Image-based table detection failed: {str(e)}")
        
        return tables
    
    def _find_table_regions(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Find table-like regions in text lines"""
        regions = []
        current_region = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                if current_region and len(current_region['lines']) >= 2:
                    regions.append(current_region)
                current_region = None
                continue
            
            # Check if line looks like a table row
            is_table_row = self._is_table_row(line)
            has_bom_keywords = self._has_bom_keywords(line)
            
            if is_table_row or has_bom_keywords:
                if current_region is None:
                    current_region = {
                        'start': i,
                        'end': i,
                        'lines': [line],
                        'confidence': 0.0
                    }
                else:
                    current_region['end'] = i
                    current_region['lines'].append(line)
            else:
                if current_region and len(current_region['lines']) >= 2:
                    regions.append(current_region)
                current_region = None
        
        # Add final region if exists
        if current_region and len(current_region['lines']) >= 2:
            regions.append(current_region)
        
        # Calculate confidence scores
        for region in regions:
            region['confidence'] = self._calculate_text_table_confidence(region['lines'])
        
        return regions
    
    def _is_table_row(self, line: str) -> bool:
        """Check if a line looks like a table row"""
        # Check for multiple columns separated by whitespace or specific characters
        parts = re.split(r'\s{2,}|\t|[|]', line)
        if len(parts) >= 3:
            return True
        
        # Check for numbered items
        if re.match(r'^\s*\d+[\.\)]\s+', line):
            return True
        
        # Check for part numbers pattern
        if re.search(r'[A-Z0-9]{3,}-[A-Z0-9]{2,}', line):
            return True
        
        return False
    
    def _has_bom_keywords(self, line: str) -> bool:
        """Check if line contains BOM-related keywords"""
        line_lower = line.lower()
        return any(keyword in line_lower for keyword in self.bom_keywords)
    
    def _calculate_text_table_confidence(self, lines: List[str]) -> float:
        """Calculate confidence score for text-based table"""
        score = 0.0
        total_lines = len(lines)
        
        if total_lines == 0:
            return 0.0
        
        # Check for header row
        header_score = 0
        first_line = lines[0].lower()
        for pattern in self.header_patterns:
            if re.search(pattern, first_line):
                header_score += 1
        
        score += min(header_score / len(self.header_patterns), 1.0) * 0.4
        
        # Check consistency of table structure
        consistent_columns = 0
        for line in lines[1:]:  # Skip header
            if self._is_table_row(line):
                consistent_columns += 1
        
        score += (consistent_columns / (total_lines - 1)) * 0.3
        
        # Check for BOM-specific content
        bom_content_score = 0
        for line in lines:
            if self._has_bom_keywords(line):
                bom_content_score += 1
        
        score += min(bom_content_score / total_lines, 1.0) * 0.3
        
        return min(score, 1.0)
    
    def _detect_horizontal_lines(self, thresh_image: Any) -> List[Tuple[int, int, int, int]]:
        """Detect horizontal lines in thresholded image"""
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        detected_lines = cv2.morphologyEx(thresh_image, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        contours, _ = cv2.findContours(detected_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        lines = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 50:  # Minimum line length
                lines.append((x, y, x + w, y + h))
        
        return lines
    
    def _detect_vertical_lines(self, thresh_image: Any) -> List[Tuple[int, int, int, int]]:
        """Detect vertical lines in thresholded image"""
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        detected_lines = cv2.morphologyEx(thresh_image, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        contours, _ = cv2.findContours(detected_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        lines = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if h > 50:  # Minimum line length
                lines.append((x, y, x + w, y + h))
        
        return lines
    
    def _find_table_candidates(self, h_lines: List, v_lines: List, image_shape: Tuple) -> List[Dict[str, Any]]:
        """Find table candidates based on line intersections"""
        candidates = []
        
        # Simple implementation: look for rectangular regions with both horizontal and vertical lines
        for h_line in h_lines:
            for v_line in v_lines:
                # Check if lines intersect
                h_x1, h_y1, h_x2, h_y2 = h_line
                v_x1, v_y1, v_x2, v_y2 = v_line
                
                if (h_x1 <= v_x1 <= h_x2) and (v_y1 <= h_y1 <= v_y2):
                    # Lines intersect, this could be part of a table
                    bbox = (min(h_x1, v_x1), min(h_y1, v_y1), 
                           max(h_x2, v_x2), max(h_y2, v_y2))
                    
                    candidate = {
                        'bbox': bbox,
                        'confidence': 0.7  # Base confidence for line-based detection
                    }
                    candidates.append(candidate)
        
        # Remove duplicate/overlapping candidates
        candidates = self._remove_overlapping_candidates(candidates)
        
        return candidates
    
    def _remove_overlapping_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove overlapping table candidates"""
        if not candidates:
            return candidates
        
        # Sort by confidence score
        candidates.sort(key=lambda x: x['confidence'], reverse=True)
        
        filtered = []
        for candidate in candidates:
            is_overlapping = False
            for existing in filtered:
                if self._calculate_overlap(candidate['bbox'], existing['bbox']) > 0.5:
                    is_overlapping = True
                    break
            
            if not is_overlapping:
                filtered.append(candidate)
        
        return filtered
    
    def _calculate_overlap(self, bbox1: Tuple, bbox2: Tuple) -> float:
        """Calculate overlap ratio between two bounding boxes"""
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # Calculate intersection
        x_left = max(x1_1, x1_2)
        y_top = max(y1_1, y1_2)
        x_right = min(x2_1, x2_2)
        y_bottom = min(y2_1, y2_2)
        
        if x_right < x_left or y_bottom < y_top:
            return 0.0
        
        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        
        # Calculate union
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union_area = area1 + area2 - intersection_area
        
        return intersection_area / union_area if union_area > 0 else 0.0
    
    def _rank_tables_by_bom_likelihood(self, tables: List[Dict[str, Any]], text_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Rank tables by their likelihood of being BOM tables"""
        for table in tables:
            likelihood_score = 0.0
            
            # Base score from table detection confidence
            likelihood_score += table.get('confidence', 0.0) * 0.3
            
            # Check content for BOM indicators
            if table.get('lines'):
                content_score = self._score_bom_content(table['lines'])
                likelihood_score += content_score * 0.7
            
            table['bom_likelihood'] = min(likelihood_score, 1.0)
        
        # Sort by BOM likelihood
        tables.sort(key=lambda x: x.get('bom_likelihood', 0), reverse=True)
        
        return tables
    
    def _score_bom_content(self, lines: List[str]) -> float:
        """Score content for BOM characteristics"""
        if not lines:
            return 0.0
        
        score = 0.0
        
        # Check for typical BOM headers
        header_line = lines[0].lower()
        header_matches = sum(1 for pattern in self.header_patterns if re.search(pattern, header_line))
        score += min(header_matches / len(self.header_patterns), 1.0) * 0.4
        
        # Check for part numbers and quantities
        part_number_count = 0
        quantity_count = 0
        
        for line in lines[1:]:  # Skip header
            if re.search(r'[A-Z0-9]{2,}-[A-Z0-9]{2,}', line):
                part_number_count += 1
            if re.search(r'\b\d+(\.\d+)?\s*(ea|each|pcs?|pieces?|units?|kg|lb|ft|m)?\b', line, re.IGNORECASE):
                quantity_count += 1
        
        total_data_lines = len(lines) - 1
        if total_data_lines > 0:
            score += (part_number_count / total_data_lines) * 0.3
            score += (quantity_count / total_data_lines) * 0.3
        
        return min(score, 1.0)
