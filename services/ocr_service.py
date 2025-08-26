import os
import subprocess
import tempfile
import logging
import io
from typing import Dict, Any, Optional
import PyPDF2
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError as e:
    PIL_AVAILABLE = False
    print(f"PIL/Pillow not available, image processing will be disabled: {e}")

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError as e:
    PYTESSERACT_AVAILABLE = False
    print(f"Pytesseract not available: {e}")

try:
    import ocrmypdf
    OCRMYPDF_AVAILABLE = True
except ImportError:
    OCRMYPDF_AVAILABLE = False
    print("OCRmyPDF not available, PDF OCR will use fallback method")

logger = logging.getLogger(__name__)


class OCRService:
    """Service for OCR processing using OCRmyPDF and Tesseract"""
    
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
    
    def process_document(self, file_path: str, debug_logger=None) -> Dict[str, Any]:
        """
        Process document with OCR to extract text
        
        Args:
            file_path: Path to the input document
            
        Returns:
            Dictionary containing OCR results and metadata
        """
        result = {
            'success': False,
            'processed_file_path': None,
            'text_data': {},
            'metadata': {},
            'error': None
        }
        
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.pdf':
                return self._process_pdf(file_path, debug_logger)
            elif file_ext in ['.png', '.jpg', '.jpeg', '.tiff', '.tif']:
                return self._process_image(file_path, debug_logger)
            else:
                result['error'] = f"Unsupported file format: {file_ext}"
                return result
                
        except Exception as e:
            logger.error(f"OCR processing failed: {str(e)}")
            result['error'] = str(e)
            return result
    
    def _process_pdf(self, pdf_path: str, debug_logger=None) -> Dict[str, Any]:
        """Process PDF file using OCRmyPDF"""
        result = {
            'success': False,
            'processed_file_path': None,
            'text_data': {},
            'metadata': {},
            'error': None
        }
        
        try:
            # Create output path for OCR processed PDF
            output_path = os.path.join(
                self.temp_dir,
                f"ocr_{os.path.basename(pdf_path)}"
            )
            
            # Check if PDF already has text
            has_text = self._pdf_has_text(pdf_path)
            
            if has_text:
                logger.info("PDF already contains text, extracting directly")
                processed_path = pdf_path
            else:
                logger.info("PDF requires OCR processing - using system OCRmyPDF")
                # Run OCRmyPDF to add text layer
                # OCRmyPDF is available as a system command
                cmd = [
                    'ocrmypdf',
                    '--language', 'eng',
                    '--output-type', 'pdf',
                    '--optimize', '1',
                    '--jpeg-quality', '85',
                    '--png-quality', '85',
                    '--max-image-mpixels', '50',
                    pdf_path,
                    output_path
                ]
                
                logger.info(f"Running OCRmyPDF command: {' '.join(cmd[:2])}")
                import time
                start_time = time.time()
                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Log subprocess execution
                if debug_logger:
                    debug_logger.log_subprocess(
                        cmd,
                        stdout=process.stdout,
                        stderr=process.stderr,
                        exit_code=process.returncode,
                        duration_ms=duration_ms
                    )
                
                if process.returncode != 0:
                    logger.error(f"OCRmyPDF failed: {process.stderr}")
                    if debug_logger:
                        debug_logger.log_error("ocrmypdf_failed",
                                              f"Exit code {process.returncode}: {process.stderr}")
                    # Try without optimization flags for simpler processing
                    cmd_simple = ['ocrmypdf', pdf_path, output_path]
                    start_time = time.time()
                    process_simple = subprocess.run(cmd_simple, capture_output=True, text=True, timeout=300)
                    duration_ms = int((time.time() - start_time) * 1000)
                    
                    if debug_logger:
                        debug_logger.log_subprocess(
                            cmd_simple,
                            stdout=process_simple.stdout,
                            stderr=process_simple.stderr,
                            exit_code=process_simple.returncode,
                            duration_ms=duration_ms
                        )
                    if process_simple.returncode != 0:
                        if debug_logger:
                            debug_logger.log_error("ocrmypdf_simple_failed",
                                                  f"Exit code {process_simple.returncode}: {process_simple.stderr}")
                        return self._fallback_pdf_ocr(pdf_path, debug_logger)
                
                processed_path = output_path
            
            # Extract text from processed PDF
            text_data = self._extract_pdf_text(processed_path)
            
            result.update({
                'success': True,
                'processed_file_path': processed_path,
                'text_data': text_data,
                'metadata': {
                    'had_text_layer': has_text,
                    'total_pages': len(text_data.get('pages', [])),
                    'total_characters': sum(len(page.get('text', '')) for page in text_data.get('pages', []))
                }
            })
            
        except subprocess.TimeoutExpired:
            result['error'] = "OCR processing timed out"
        except Exception as e:
            logger.error(f"PDF OCR processing failed: {str(e)}")
            result['error'] = str(e)
        
        return result
    
    def _process_image(self, image_path: str, debug_logger=None) -> Dict[str, Any]:
        """Process image file using Tesseract OCR"""
        result = {
            'success': False,
            'processed_file_path': image_path,
            'text_data': {},
            'metadata': {},
            'error': None
        }
        
        if not PIL_AVAILABLE:
            result['error'] = "PIL/Pillow not available for image processing"
            return result
        
        try:
            # Open and preprocess image
            image = Image.open(image_path)
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Extract text using Tesseract
            text = pytesseract.image_to_string(
                image,
                config='--psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz .,:-()[]'
            )
            
            # Get additional OCR data
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            # Calculate confidence scores
            confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            result.update({
                'success': True,
                'text_data': {
                    'pages': [{
                        'page_number': 1,
                        'text': text,
                        'confidence': avg_confidence
                    }],
                    'full_text': text
                },
                'metadata': {
                    'image_dimensions': image.size,
                    'average_confidence': avg_confidence,
                    'total_characters': len(text),
                    'detected_words': len([w for w in data['text'] if w.strip()])
                }
            })
            
        except Exception as e:
            logger.error(f"Image OCR processing failed: {str(e)}")
            result['error'] = str(e)
        
        return result
    
    def _pdf_has_text(self, pdf_path: str) -> bool:
        """Check if PDF already contains text"""
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages[:3]:  # Check first 3 pages
                    text = page.extract_text().strip()
                    if text and len(text) > 50:  # Has substantial text
                        return True
            return False
        except Exception:
            return False
    
    def _extract_pdf_text(self, pdf_path: str) -> Dict[str, Any]:
        """Extract text from PDF file"""
        text_data = {
            'pages': [],
            'full_text': ''
        }
        
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                full_text = []
                
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    text_data['pages'].append({
                        'page_number': i + 1,
                        'text': page_text,
                        'confidence': 95  # Assume high confidence for existing text
                    })
                    full_text.append(page_text)
                
                text_data['full_text'] = '\n'.join(full_text)
        
        except Exception as e:
            logger.error(f"Text extraction failed: {str(e)}")
        
        return text_data
    
    def _fallback_pdf_ocr(self, pdf_path: str) -> Dict[str, Any]:
        """Fallback OCR method for PDFs by converting to images"""
        result = {
            'success': False,
            'processed_file_path': pdf_path,
            'text_data': {},
            'metadata': {},
            'error': None
        }
        
        try:
            # Convert PDF pages to images and OCR each
            import fitz  # PyMuPDF
            
            doc = fitz.open(pdf_path)
            pages_data = []
            full_text = []
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap()
                img_data = pix.tobytes("ppm")
                
                # Create PIL image from bytes
                image = Image.open(io.BytesIO(img_data))
                
                # OCR the image
                text = pytesseract.image_to_string(image)
                data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
                
                confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                
                pages_data.append({
                    'page_number': page_num + 1,
                    'text': text,
                    'confidence': avg_confidence
                })
                full_text.append(text)
            
            doc.close()
            
            result.update({
                'success': True,
                'text_data': {
                    'pages': pages_data,
                    'full_text': '\n'.join(full_text)
                },
                'metadata': {
                    'total_pages': len(pages_data),
                    'fallback_method': True,
                    'average_confidence': sum(p['confidence'] for p in pages_data) / len(pages_data) if pages_data else 0
                }
            })
            
        except Exception as e:
            logger.error(f"Fallback PDF OCR failed: {str(e)}")
            result['error'] = str(e)
        
        return result
