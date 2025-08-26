import os
import subprocess
import shutil
import time
import logging

logger = logging.getLogger(__name__)


def ensure_text_layer(src_pdf: str, out_pdf: str, debug_logger=None) -> str:
    """
    Ensure PDF has searchable text layer using OCRmyPDF if needed.
    
    Args:
        src_pdf: Path to source PDF
        out_pdf: Path to output PDF
    
    Returns:
        Path to output PDF with text layer
    """
    start_time = time.time()
    
    try:
        # Check if text exists using pdftotext
        cmd_check = ['pdftotext', '-q', src_pdf, '-']
        import time as timer
        start = timer.time()
        result = subprocess.run(cmd_check, capture_output=True, text=True, timeout=30)
        duration_ms = int((timer.time() - start) * 1000)
        
        if debug_logger:
            debug_logger.log_subprocess(
                cmd_check,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=duration_ms
            )
        
        text_length = len(result.stdout.strip())
        logger.info(f"Text extraction returned {text_length} characters")
        
        if text_length > 500:
            # PDF already has sufficient text, copy unchanged
            shutil.copy2(src_pdf, out_pdf)
            elapsed = time.time() - start_time
            logger.info(f"PDF already has text layer, copied in {elapsed:.2f}s")
            return out_pdf
        else:
            # Need OCR processing
            cmd_ocr = [
                'ocrmypdf',
                '--jobs', '2',
                '--optimize', '1',
                '--skip-text',
                src_pdf,
                out_pdf
            ]
            
            logger.info(f"Running OCR on {src_pdf}")
            start = timer.time()
            result = subprocess.run(cmd_ocr, capture_output=True, text=True, timeout=300)
            duration_ms = int((timer.time() - start) * 1000)
            
            if debug_logger:
                debug_logger.log_subprocess(
                    cmd_ocr,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                    duration_ms=duration_ms
                )
            
            elapsed = time.time() - start_time
            logger.info(f"OCR completed in {elapsed:.2f}s, exit code: {result.returncode}")
            
            if result.returncode != 0:
                logger.error(f"OCR error: {result.stderr}")
                if debug_logger:
                    debug_logger.log_error("ocr_failed", 
                                          f"Exit code {result.returncode}: {result.stderr}")
                # If OCR fails, copy original
                shutil.copy2(src_pdf, out_pdf)
            elif debug_logger:
                debug_logger.log_step("ocr_success", {"output": out_pdf})
            
            return out_pdf
            
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        logger.error(f"Process timed out after {elapsed:.2f}s")
        shutil.copy2(src_pdf, out_pdf)
        return out_pdf
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Error in ensure_text_layer after {elapsed:.2f}s: {str(e)}")
        shutil.copy2(src_pdf, out_pdf)
        return out_pdf