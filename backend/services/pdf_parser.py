"""
PDF parsing service for extracting text from lecture slides
"""
from pathlib import Path
from typing import List
import PyPDF2
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import io


class PDFParser:
    """Parse PDF files and extract text per slide/page"""
    
    def __init__(self):
        self.supported_formats = ['.pdf', '.png', '.jpg', '.jpeg']
    
    async def parse(self, file_path: Path) -> List[str]:
        """
        Parse PDF and return list of text chunks (one per slide)
        """
        file_path = Path(file_path)
        
        if file_path.suffix.lower() == '.pdf':
            return await self._parse_pdf(file_path)
        elif file_path.suffix.lower() in ['.png', '.jpg', '.jpeg']:
            return await self._parse_image(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
    
    async def _parse_pdf(self, pdf_path: Path) -> List[str]:
        """Extract text from PDF pages"""
        slides = []
        
        try:
            # Try text extraction first (doesn't require poppler)
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                for page_num, page in enumerate(pdf_reader.pages):
                    text = page.extract_text()
                    
                    # If text extraction yields little content, try OCR (requires poppler)
                    if len(text.strip()) < 50:
                        try:
                            # Convert page to image and OCR (requires poppler)
                            images = convert_from_path(pdf_path, first_page=page_num+1, last_page=page_num+1)
                            if images:
                                text = pytesseract.image_to_string(images[0])
                        except Exception as ocr_error:
                            # OCR failed (likely poppler not installed), use extracted text as-is
                            pass
                    
                    slides.append(text.strip())
        
        except Exception as e:
            # If PyPDF2 fails, try OCR fallback (requires poppler)
            try:
                images = convert_from_path(pdf_path)
                for image in images:
                    text = pytesseract.image_to_string(image)
                    slides.append(text.strip())
            except Exception as fallback_error:
                # Check if error is about poppler
                error_msg = str(fallback_error).lower()
                if 'poppler' in error_msg or 'page count' in error_msg:
                    raise Exception(
                        "Failed to parse PDF: Poppler is not installed. "
                        "Install it with: macOS: 'brew install poppler', "
                        "Linux: 'sudo apt-get install poppler-utils', "
                        "or use a PDF with extractable text."
                    )
                else:
                    raise Exception(f"Failed to parse PDF: {str(e)}, {str(fallback_error)}")
        
        return slides
    
    async def _parse_image(self, image_path: Path) -> List[str]:
        """Extract text from image using OCR"""
        try:
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image)
            return [text.strip()]
        except Exception as e:
            raise Exception(f"Failed to parse image: {str(e)}")

