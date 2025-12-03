from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import uuid
from pathlib import Path

from services.pdf_parser import PDFParser
from services.embedding_service import EmbeddingService
from services.alignment_service import AlignmentService
from services.concept_detector import ConceptDetector
from services.misconception_detector import MisconceptionDetector
from services.quiz_generator import QuizGenerator
from storage.vector_store import VectorStore
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="AI Note Scanner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["chrome-extension://*", "http://localhost:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

pdf_parser = PDFParser()
embedding_service = EmbeddingService()
vector_store = VectorStore()
alignment_service = AlignmentService(embedding_service, vector_store)
concept_detector = ConceptDetector(embedding_service, vector_store)
misconception_detector = MisconceptionDetector(embedding_service, vector_store)
quiz_generator = QuizGenerator()


class ScanNotesRequest(BaseModel):
    slide_id: str
    notes_text: str
    doc_id: Optional[str] = None


class RefreshQuestionRequest(BaseModel):
    slide_id: str
    notes_text: str
    previous_questions: Optional[List[dict]] = None


@app.post("/api/upload-slides")
async def upload_slides(file: UploadFile = File(...)):
    try:
        file_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        slides = await pdf_parser.parse(file_path)
        
        slide_embeddings = []
        for i, slide_text in enumerate(slides):
            embedding = embedding_service.embed(slide_text)
            slide_embeddings.append({
                "slide_index": i,
                "text": slide_text,
                "embedding": embedding
            })
        
        vector_store.add_slides(file_id, slide_embeddings)
        
        return {
            "slide_id": file_id,
            "pages": len(slides),
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scan-notes")
async def scan_notes(request: ScanNotesRequest):
    try:
        slide_data = vector_store.get_slides(request.slide_id)
        if not slide_data:
            raise HTTPException(status_code=404, detail="Slides not found")
        
        notes_embedding = embedding_service.embed(request.notes_text)
        covered_slides = alignment_service.find_covered_slides(
            request.slide_id,
            notes_embedding
        )
        
        covered_slide_data = slide_data[:min(covered_slides + 1, len(slide_data))]
        
        misconceptions = misconception_detector.detect(
            request.notes_text,
            covered_slide_data
        )
        
        question = quiz_generator.generate_single(covered_slide_data, previous_questions=None)
        
        return {
            "question": question,
            "misconceptions": misconceptions,
            "covered_slides": len(covered_slide_data),
            "total_slides": len(slide_data)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/refresh-question")
async def refresh_question(request: RefreshQuestionRequest):
    try:
        slide_data = vector_store.get_slides(request.slide_id)
        if not slide_data:
            raise HTTPException(status_code=404, detail="Slides not found")
        
        notes_embedding = embedding_service.embed(request.notes_text)
        covered_slides = alignment_service.find_covered_slides(
            request.slide_id,
            notes_embedding
        )
        
        covered_slide_data = slide_data[:min(covered_slides + 1, len(slide_data))]
        
        question = quiz_generator.generate_single(
            covered_slide_data, 
            previous_questions=request.previous_questions or []
        )
        
        return {
            "question": question,
            "covered_slides": len(covered_slide_data),
            "total_slides": len(slide_data)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
