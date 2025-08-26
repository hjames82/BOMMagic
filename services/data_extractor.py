import re
import logging
import tempfile
import os
from typing import Dict, List, Any, Optional, Tuple, Union

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("Pandas not available, data processing will be limited")

try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False
    print("Camelot not available, table extraction will be limited")

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    print("pdfplumber not available, PDF processing will be limited")

logger = logging.getLogger(__name__)


class DataExtractor:
    """Service for extracting structured BOM data from detected tables"""
    
    def __init__(self):
        self.standard_columns = [
            'item_number', 'part_number', 'description', 'quantity',
            'unit', 'material', 'supplier', 'cost'
        ]
        
        # Column mapping patterns
        self.column_mappings = {
            'item_number': [
                r'item\s*no\.?', r'item\s*#', r'#', r'no\.?', r'line\s*no\.?'
            ],
            'part_number': [
                r'part\s*no\.?', r'part\s*#', r'p/n', r'drawing\s*no\.?', r'dwg\s*no\.?'
            ],
            'description': [
                r'description', r'desc\.?', r'title', r'name', r'component'
            ],
            'quantity': [
                r'qty\.?', r'quantity', r'qnty', r'req\'?d', r'required'
            ],
            'unit': [
                r'unit', r'u/m', r'uom', r'ea\.?', r'each'
            ],
            'material': [
                r'material', r'mat\'?l', r'spec\.?', r'specification'
            ],
            'supplier': [
                r'supplier', r'vendor', r'mfg', r'manufacturer'
            ],
            'cost': [
                r'cost', r'price', r'rate', r'amount', r'\$'
            ]
        }
    
    def extract_bom_data(self, file_path: str, tables: List[Dict[str, Any]], 
                         debug_logger=None, document_id: str = None) -> Dict[str, Any]:
        """
        Extract structured BOM data from detected tables
        
        Args:
            file_path: Path to the document
            tables: List of detected tables
            
        Returns:
            Dictionary containing extracted BOM data and metadata
        """
        result = {
            'success': False,
            'bom_data': [],
            'metadata': {},
            'error': None
        }
        
        try:
            if not tables:
                result['error'] = "No tables detected for data extraction"
                return result
            
            # Try different extraction methods
            all_extractions = []
            
            # Method 1: Use Camelot for PDF tables
            if file_path.lower().endswith('.pdf'):
                if debug_logger:
                    debug_logger.log_step("camelot_extraction", {"file_path": file_path})
                camelot_data = self._extract_with_camelot(file_path, tables)
                if camelot_data:
                    all_extractions.extend(camelot_data)
            
            # Method 2: Use pdfplumber for PDF tables
            if file_path.lower().endswith('.pdf'):
                if debug_logger:
                    debug_logger.log_step("pdfplumber_extraction", {"file_path": file_path})
                pdfplumber_data = self._extract_with_pdfplumber(file_path, tables)
                if pdfplumber_data:
                    all_extractions.extend(pdfplumber_data)
            
            # Method 3: Text-based extraction for all files
            if debug_logger:
                debug_logger.log_step("text_extraction", {"table_count": len(tables)})
            text_data = self._extract_from_text_tables(tables)
            if text_data:
                all_extractions.extend(text_data)
            
            if not all_extractions:
                result['error'] = "No data could be extracted from detected tables"
                return result
            
            # Select best extraction
            best_extraction = self._select_best_extraction(all_extractions)
            
            # Normalize and clean data
            normalized_data = self._normalize_bom_data(best_extraction['data'])
            
            # Log extraction results
            if debug_logger and document_id:
                for idx, table in enumerate(tables):
                    debug_logger.log_extraction(
                        document_id=document_id,
                        page_index=table.get('page_number', 1),
                        table_region=table,
                        items_extracted=len(normalized_data) if idx == 0 else 0
                    )
            
            result.update({
                'success': True,
                'bom_data': normalized_data,
                'metadata': {
                    'extraction_method': best_extraction['method'],
                    'total_items': len(normalized_data),
                    'confidence': best_extraction['confidence'],
                    'columns_found': best_extraction.get('columns', [])
                }
            })
            
        except Exception as e:
            logger.error(f"Data extraction failed: {str(e)}")
            result['error'] = str(e)
        
        return result
    
    def _extract_with_camelot(self, pdf_path: str, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract data using Camelot library"""
        extractions = []
        
        try:
            # Extract all tables from PDF
            camelot_tables = camelot.read_pdf(pdf_path, pages='all')
            
            for i, table in enumerate(camelot_tables):
                df = table.df
                
                if df.empty:
                    continue
                
                # Convert DataFrame to structured data
                structured_data = self._dataframe_to_bom_structure(df)
                
                extraction = {
                    'method': 'camelot',
                    'table_index': i,
                    'data': structured_data,
                    'confidence': table.accuracy / 100.0,  # Camelot provides accuracy score
                    'raw_table': df
                }
                extractions.append(extraction)
        
        except Exception as e:
            logger.warning(f"Camelot extraction failed: {str(e)}")
        
        return extractions
    
    def _extract_with_pdfplumber(self, pdf_path: str, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract data using pdfplumber library"""
        extractions = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_tables = page.extract_tables()
                    
                    for i, table_data in enumerate(page_tables):
                        if not table_data:
                            continue
                        
                        # Convert to DataFrame
                        df = pd.DataFrame(table_data[1:], columns=table_data[0])
                        
                        # Convert DataFrame to structured data
                        structured_data = self._dataframe_to_bom_structure(df)
                        
                        extraction = {
                            'method': 'pdfplumber',
                            'page_number': page_num + 1,
                            'table_index': i,
                            'data': structured_data,
                            'confidence': 0.8,  # Default confidence for pdfplumber
                            'raw_table': df
                        }
                        extractions.append(extraction)
        
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {str(e)}")
        
        return extractions
    
    def _extract_from_text_tables(self, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract data from text-based table detection"""
        extractions = []
        
        for table in tables:
            if table['type'] != 'text_based' or not table.get('lines'):
                continue
            
            try:
                # Parse lines into structured data
                structured_data = self._parse_text_lines(table['lines'])
                
                extraction = {
                    'method': 'text_parsing',
                    'data': structured_data,
                    'confidence': table.get('confidence', 0.5),
                    'source_lines': table['lines']
                }
                extractions.append(extraction)
            
            except Exception as e:
                logger.warning(f"Text table extraction failed: {str(e)}")
        
        return extractions
    
    def _dataframe_to_bom_structure(self, df: Any) -> List[Dict[str, Any]]:
        """Convert DataFrame to standardized BOM structure"""
        if df.empty:
            return []
        
        # Clean column names
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Map columns to standard BOM fields
        column_mapping = self._map_columns(df.columns)
        
        bom_items = []
        for index, row in df.iterrows():
            item = {}
            
            # Map each column to BOM field
            for bom_field, df_column in column_mapping.items():
                if df_column is not None and df_column in df.columns:
                    value = str(row[df_column]).strip()
                    if value and value.lower() not in ['nan', 'none', '']:
                        item[bom_field] = value
            
            # Add row metadata
            item['row_index'] = index
            item['confidence_score'] = 0.8  # Default confidence
            
            # Only add if item has some meaningful data
            if len(item) > 2:  # More than just row_index and confidence
                bom_items.append(item)
        
        return bom_items
    
    def _parse_text_lines(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Parse text lines into BOM structure"""
        if not lines:
            return []
        
        # Assume first line is header
        header_line = lines[0]
        data_lines = lines[1:]
        
        # Try to identify column boundaries
        column_positions = self._identify_column_positions(lines)
        
        # Parse header to identify columns
        header_fields = self._parse_header_line(header_line, column_positions)
        
        bom_items = []
        for i, line in enumerate(data_lines):
            if not line.strip():
                continue
            
            # Parse data line based on column positions
            values = self._parse_data_line(line, column_positions)
            
            item = {}
            for j, value in enumerate(values):
                if j < len(header_fields) and header_fields[j]:
                    item[header_fields[j]] = value.strip()
            
            item['row_index'] = i
            item['confidence_score'] = 0.7  # Default confidence for text parsing
            
            if len(item) > 2:
                bom_items.append(item)
        
        return bom_items
    
    def _map_columns(self, column_names: List[str]) -> Dict[str, Optional[str]]:
        """Map DataFrame columns to standard BOM fields"""
        mapping = {}
        
        for bom_field in self.standard_columns:
            mapping[bom_field] = None
            
            # Find best matching column
            for col_name in column_names:
                col_clean = re.sub(r'[^\w\s]', '', col_name.lower())
                
                for pattern in self.column_mappings.get(bom_field, []):
                    if re.search(pattern, col_clean, re.IGNORECASE):
                        mapping[bom_field] = col_name
                        break
                
                if mapping[bom_field]:
                    break
        
        return mapping
    
    def _identify_column_positions(self, lines: List[str]) -> List[int]:
        """Identify column boundary positions in text"""
        if not lines:
            return []
        
        # Analyze whitespace patterns to find column boundaries
        max_length = max(len(line) for line in lines)
        whitespace_counts = [0] * max_length
        
        for line in lines:
            for i, char in enumerate(line):
                if char.isspace():
                    whitespace_counts[i] += 1
        
        # Find positions with consistent whitespace
        threshold = len(lines) * 0.7  # 70% of lines have whitespace at this position
        column_positions = [0]  # Start position
        
        for i, count in enumerate(whitespace_counts):
            if count >= threshold and (not column_positions or i - column_positions[-1] > 3):
                column_positions.append(i)
        
        return column_positions
    
    def _parse_header_line(self, header_line: str, column_positions: List[int]) -> List[str]:
        """Parse header line to identify field names"""
        if not column_positions:
            # Fallback: split by multiple spaces
            return re.split(r'\s{2,}', header_line.strip())
        
        fields = []
        for i in range(len(column_positions)):
            start = column_positions[i]
            end = column_positions[i + 1] if i + 1 < len(column_positions) else len(header_line)
            
            field = header_line[start:end].strip()
            
            # Map to standard BOM field
            mapped_field = self._map_header_field(field)
            fields.append(mapped_field)
        
        return fields
    
    def _parse_data_line(self, line: str, column_positions: List[int]) -> List[str]:
        """Parse data line based on column positions"""
        if not column_positions:
            # Fallback: split by multiple spaces or tabs
            return re.split(r'\s{2,}|\t', line)
        
        values = []
        for i in range(len(column_positions)):
            start = column_positions[i]
            end = column_positions[i + 1] if i + 1 < len(column_positions) else len(line)
            
            value = line[start:end].strip()
            values.append(value)
        
        return values
    
    def _map_header_field(self, field: str) -> str:
        """Map header field to standard BOM field name"""
        field_clean = re.sub(r'[^\w\s]', '', field.lower())
        
        for bom_field, patterns in self.column_mappings.items():
            for pattern in patterns:
                if re.search(pattern, field_clean, re.IGNORECASE):
                    return bom_field
        
        # Return original if no mapping found
        return field.lower().replace(' ', '_')
    
    def _select_best_extraction(self, extractions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Select the best extraction from multiple methods"""
        if not extractions:
            return {'method': 'none', 'data': [], 'confidence': 0.0}
        
        # Score each extraction
        for extraction in extractions:
            score = extraction['confidence']
            
            # Bonus for more data items
            data_count = len(extraction['data'])
            score += min(data_count / 20.0, 0.2)  # Up to 20% bonus for item count
            
            # Bonus for better structured data
            if extraction['data']:
                avg_fields = sum(len(item) for item in extraction['data']) / len(extraction['data'])
                score += min(avg_fields / 8.0, 0.2)  # Up to 20% bonus for field completeness
            
            extraction['total_score'] = score
        
        # Return extraction with highest score
        best_extraction = max(extractions, key=lambda x: x['total_score'])
        return best_extraction
    
    def _normalize_bom_data(self, bom_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize and clean BOM data"""
        normalized_data = []
        
        for item in bom_data:
            normalized_item = {}
            
            # Ensure all standard fields exist
            for field in self.standard_columns:
                normalized_item[field] = item.get(field, '')
            
            # Copy metadata
            normalized_item['row_index'] = item.get('row_index', 0)
            normalized_item['confidence_score'] = item.get('confidence_score', 0.5)
            
            # Clean and format specific fields
            normalized_item = self._clean_bom_item(normalized_item)
            
            normalized_data.append(normalized_item)
        
        return normalized_data
    
    def _clean_bom_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and format individual BOM item"""
        # Clean quantity field
        if item.get('quantity'):
            quantity = re.sub(r'[^\d.,]', '', str(item['quantity']))
            item['quantity'] = quantity
        
        # Clean part number
        if item.get('part_number'):
            part_no = str(item['part_number']).strip().upper()
            item['part_number'] = part_no
        
        # Clean cost field
        if item.get('cost'):
            cost = re.sub(r'[^\d.,\$]', '', str(item['cost']))
            item['cost'] = cost
        
        # Trim all string fields
        for key, value in item.items():
            if isinstance(value, str):
                item[key] = value.strip()
        
        return item
