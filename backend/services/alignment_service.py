"""
Semantic alignment service to determine lecture progress
"""
import numpy as np
from typing import List, Dict
from .embedding_service import EmbeddingService
from storage.vector_store import VectorStore


class AlignmentService:
    """Determine which slides have been covered based on note content"""
    
    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.similarity_threshold = 0.3  # Minimum similarity to consider slide "covered"
    
    def find_covered_slides(self, slide_id: str, notes_embedding: np.ndarray) -> int:
        """
        Find the highest slide index that has been covered
        
        Returns:
            Index of last covered slide (0-indexed)
        """
        slide_data = self.vector_store.get_slides(slide_id)
        if not slide_data:
            return 0
        
        # Compute similarity between notes and each slide
        similarities = []
        for slide in slide_data:
            slide_embedding = slide['embedding']
            similarity = self.embedding_service.similarity(notes_embedding, slide_embedding)
            similarities.append(similarity)
        
        # Find the highest cumulative similarity region
        # Use a sliding window approach
        max_cumulative = 0
        best_index = 0
        
        # Check cumulative similarity up to each slide
        for i in range(len(similarities)):
            cumulative = sum(similarities[:i+1])
            if cumulative > max_cumulative:
                max_cumulative = cumulative
                best_index = i
        
        # Also check if individual slides exceed threshold
        for i, sim in enumerate(similarities):
            if sim > self.similarity_threshold:
                best_index = max(best_index, i)
        
        return best_index
    
    def compute_similarity_matrix(self, slide_id: str, notes_chunks: List[str]) -> np.ndarray:
        """
        Compute similarity matrix between lecture slides and note chunks
        
        Returns:
            Matrix of shape (num_slides, num_note_chunks)
        """
        slide_data = self.vector_store.get_slides(slide_id)
        if not slide_data:
            return np.array([])
        
        # Embed note chunks
        note_embeddings = self.embedding_service.embed_batch(notes_chunks)
        
        # Compute similarity matrix
        similarity_matrix = np.zeros((len(slide_data), len(notes_chunks)))
        
        for i, slide in enumerate(slide_data):
            slide_embedding = slide['embedding']
            for j, note_embedding in enumerate(note_embeddings):
                similarity = self.embedding_service.similarity(slide_embedding, note_embedding)
                similarity_matrix[i, j] = similarity
        
        return similarity_matrix

