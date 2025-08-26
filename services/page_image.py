import subprocess
import os
import tempfile
import logging

logger = logging.getLogger(__name__)


def render_page_png(pdf_path: str, page_index: int) -> str:
    """
    Render a PDF page as PNG for UI overlays.
    
    Args:
        pdf_path: Path to PDF file
        page_index: 1-based page index
    
    Returns:
        Path to generated PNG file
    """
    # Create output path
    temp_dir = tempfile.gettempdir()
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_path = os.path.join(temp_dir, f"{base_name}_page_{page_index}")
    
    try:
        cmd = [
            'pdftoppm',
            '-f', str(page_index),
            '-l', str(page_index),
            '-png',
            '-singlefile',
            '-scale-to', '2000',
            pdf_path,
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            logger.error(f"pdftoppm failed: {result.stderr}")
            return ""
        
        # pdftoppm adds .png extension
        png_path = f"{output_path}.png"
        
        if os.path.exists(png_path):
            logger.info(f"Rendered page {page_index} to {png_path}")
            return png_path
        else:
            logger.error(f"PNG file not found at {png_path}")
            return ""
            
    except subprocess.TimeoutExpired:
        logger.error(f"pdftoppm timed out for page {page_index}")
        return ""
    except Exception as e:
        logger.error(f"Error rendering page: {str(e)}")
        return ""