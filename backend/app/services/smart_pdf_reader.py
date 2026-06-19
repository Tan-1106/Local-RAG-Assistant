import fitz
import logging
from pathlib                        import Path
from typing                         import List, Dict, Any, Optional
from llama_index.core.readers.base  import BaseReader
from llama_index.core.schema        import Document

logger = logging.getLogger(__name__)

class SmartPDFReader(BaseReader):
    """
    Smart PDF Reader that detects if a PDF is scanned or digital.
    If it's digital, it uses PyMuPDF for fast and accurate text extraction.
    If it's scanned (average chars per page < threshold), it automatically falls back to Tesseract OCR.
    """
    
    def __init__(self, text_density_threshold: int = 50, dpi_for_ocr: int = 200):
        self.text_density_threshold = text_density_threshold
        self.dpi_for_ocr = dpi_for_ocr
        self.ocr_engine = None
        
    def load_data(
        self, file_path: str | Path, extra_info: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        file_path = str(file_path)
        documents = []
        with fitz.open(file_path) as doc:
            num_pages = len(doc)
            
            if num_pages == 0:
                return []
                
            # 1. Analyze Text Density
            total_text_length = 0
            for page in doc:
                total_text_length += len(page.get_text("text").strip())
                
            avg_chars = total_text_length / num_pages
            is_scanned = avg_chars < self.text_density_threshold
            
            logger.info(f"PDF Analysis for {Path(file_path).name}: Avg {avg_chars:.1f} chars/page. Is Scanned? {is_scanned}")
            
            # Initialize OCR Engine lazily if needed
            if is_scanned and self.ocr_engine is None:
                logger.info("Initializing Tesseract OCR engine...")
                import pytesseract
                self.ocr_engine = pytesseract
                
            for i, page in enumerate(doc):
                text = ""
                
                if is_scanned:
                    # OCR Extraction
                    pix = page.get_pixmap(dpi=self.dpi_for_ocr)
                    img_data = pix.tobytes("png")
                    
                    try:
                        from PIL import Image
                        import io
                        img = Image.open(io.BytesIO(img_data))
                        # Use Vietnamese and English language packs, psm 6 assumes a single uniform block of text
                        text = self.ocr_engine.image_to_string(img, lang="vie+eng")
                    except Exception as e:
                        logger.error(f"OCR failed on page {i+1} of {file_path}: {e}")
                else:
                    # Native Text Extraction
                    text = page.get_text("text")
                    
                metadata = {
                    "file_path": file_path,
                    "file_name": Path(file_path).name,
                    "source": str(i + 1),
                    "total_pages": num_pages,
                }
                if extra_info:
                    metadata.update(extra_info)
                    
                documents.append(Document(text=text.strip(), metadata=metadata))
                
        return documents
