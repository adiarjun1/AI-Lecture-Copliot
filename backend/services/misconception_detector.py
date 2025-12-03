"""
Misconception detection service
"""
import re
from typing import List, Dict, Tuple
import numpy as np
import os
from openai import OpenAI
from .embedding_service import EmbeddingService
from storage.vector_store import VectorStore


class MisconceptionDetector:
    """Detect misconceptions and conflicting statements"""
    
    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.contradiction_threshold = 0.3  # Threshold for contradiction detection
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.client = OpenAI(api_key=api_key)
            self.use_llm = True
        else:
            self.client = None
            self.use_llm = False
    
    def detect(self, notes_text: str, slide_data: List[Dict]) -> List[Dict]:
        """
        Detect misconceptions in notes by comparing against lecture content
        
        Args:
            notes_text: Student's note text
            slide_data: List of slide dictionaries with 'text' and 'embedding'
            
        Returns:
            List of misconception dictionaries with 'text', 'suggestion', 'position'
        """
        misconceptions = []
        
        # Split notes into sentences
        note_sentences = self._split_into_sentences(notes_text)
        
        # Get lecture text
        lecture_text = ' '.join([slide['text'] for slide in slide_data])
        lecture_sentences = self._split_into_sentences(lecture_text)
        
        # Embed all sentences
        note_embeddings = self.embedding_service.embed_batch(note_sentences)
        lecture_embeddings = self.embedding_service.embed_batch(lecture_sentences)
        
        # Check each note sentence for contradictions
        for i, note_sentence in enumerate(note_sentences):
            note_emb = note_embeddings[i]
            
            # Find most similar lecture sentence
            max_similarity = 0.0
            best_lecture_idx = -1
            
            for j, lecture_emb in enumerate(lecture_embeddings):
                similarity = self.embedding_service.similarity(note_emb, lecture_emb)
                if similarity > max_similarity:
                    max_similarity = similarity
                    best_lecture_idx = j
            
            # If similar enough, check for contradictions
            if max_similarity > 0.5 and best_lecture_idx >= 0:
                # Use LLM for better misconception detection
                if self.use_llm:
                    is_misconception, correction = self._check_with_llm(
                        note_sentence,
                        lecture_sentences[best_lecture_idx],
                        lecture_text
                    )
                    if is_misconception:
                        misconceptions.append({
                            'text': note_sentence,
                            'suggestion': correction,
                            'position': i
                        })
                else:
                    # Fallback to heuristic method
                    contradiction_score = self._check_contradiction(
                        note_sentence,
                        lecture_sentences[best_lecture_idx]
                    )
                    
                    if contradiction_score > self.contradiction_threshold:
                        correction = self._extract_correction(
                            lecture_sentences[best_lecture_idx]
                        )
                        
                        misconceptions.append({
                            'text': note_sentence,
                            'suggestion': correction,
                            'position': i
                        })
        
        return misconceptions
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Simple sentence splitting
        sentences = re.split(r'[.!?]\s+', text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]
    
    def _check_contradiction(self, note_sentence: str, lecture_sentence: str) -> float:
        """
        Check if note sentence contradicts lecture sentence
        
        Returns:
            Contradiction score (0-1, higher = more contradictory)
        """
        # Simple heuristic: check for negation patterns
        note_lower = note_sentence.lower()
        lecture_lower = lecture_sentence.lower()
        
        # Check for explicit contradictions
        contradiction_words = [
            ('not', 'is'), ('no', 'yes'), ('never', 'always'),
            ('cannot', 'can'), ('wrong', 'correct'), ('incorrect', 'correct')
        ]
        
        contradiction_score = 0.0
        
        for neg_word, pos_word in contradiction_words:
            if neg_word in note_lower and pos_word in lecture_lower:
                contradiction_score += 0.3
            elif pos_word in note_lower and neg_word in lecture_lower:
                contradiction_score += 0.3
        
        # Check for conflicting numbers/values
        note_numbers = re.findall(r'\d+\.?\d*', note_sentence)
        lecture_numbers = re.findall(r'\d+\.?\d*', lecture_sentence)
        
        if note_numbers and lecture_numbers:
            # If same concept but different numbers, likely contradiction
            if len(set(note_numbers) & set(lecture_numbers)) == 0:
                # Check semantic similarity to see if same concept
                note_emb = self.embedding_service.embed(note_sentence)
                lecture_emb = self.embedding_service.embed(lecture_sentence)
                similarity = self.embedding_service.similarity(note_emb, lecture_emb)
                
                if similarity > 0.6:  # Same concept but different numbers
                    contradiction_score += 0.4
        
        return min(contradiction_score, 1.0)
    
    def _check_with_llm(self, note_sentence: str, lecture_sentence: str, full_lecture: str) -> Tuple[bool, str]:
        """Use LLM to check if note sentence is a misconception"""
        try:
            prompt = f"""Compare these two statements:

Student's note: "{note_sentence}"
Lecture content: "{lecture_sentence}"

Full lecture context:
{full_lecture[:1000]}

Is the student's note INCORRECT or a MISCONCEPTION compared to the lecture? 
- If the note is CORRECT or just paraphrased differently, respond with: NO
- If the note contains INCORRECT information, respond with: YES

If YES, provide a concise correction (1-2 sentences) explaining what's actually correct.
Format: YES|correction text
If NO, respond with: NO"""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert at detecting misconceptions in student notes by comparing them to lecture content. Only flag actual incorrect information, not paraphrasing."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            result = response.choices[0].message.content.strip()
            
            if result.startswith("YES"):
                parts = result.split("|", 1)
                correction = parts[1].strip() if len(parts) > 1 else lecture_sentence[:150]
                return True, correction
            else:
                return False, ""
        
        except Exception as e:
            # Fallback to heuristic
            contradiction_score = self._check_contradiction(note_sentence, lecture_sentence)
            if contradiction_score > self.contradiction_threshold:
                return True, self._extract_correction(lecture_sentence)
            return False, ""
    
    def _extract_correction(self, lecture_sentence: str) -> str:
        """Extract the correct statement from lecture sentence"""
        # Return the lecture sentence as correction
        return lecture_sentence[:200]  # Limit length

