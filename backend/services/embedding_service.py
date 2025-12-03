"""
Embedding service for generating sentence/document embeddings
"""
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Union


class EmbeddingService:
    """Generate embeddings using sentence transformers"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize embedding model
        Using MiniLM for fast, lightweight embeddings
        """
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = 384  # MiniLM dimension
    
    def embed(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        Generate embedding(s) for text
        
        Args:
            text: Single string or list of strings
            
        Returns:
            numpy array of embeddings (shape: (n, 384) for list, (384,) for single)
        """
        if isinstance(text, str):
            text = [text]
        
        embeddings = self.model.encode(text, convert_to_numpy=True)
        
        # If single text, return 1D array
        if len(embeddings.shape) == 2 and embeddings.shape[0] == 1:
            return embeddings[0]
        
        return embeddings
    
    def embed_batch(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """Generate embeddings for a batch of texts"""
        return self.model.encode(texts, batch_size=batch_size, convert_to_numpy=True)
    
    def similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings"""
        # Normalize embeddings
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return np.dot(embedding1, embedding2) / (norm1 * norm2)

