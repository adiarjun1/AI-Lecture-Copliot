"""
Concept extraction and gap detection service
"""
import json
import os
import re
from typing import Dict, List, Set

from openai import OpenAI

from .embedding_service import EmbeddingService
from storage.vector_store import VectorStore


class ConceptDetector:
    """Extract key concepts and detect missing ones."""

    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.client = OpenAI(api_key=api_key)
            self.use_llm = True
        else:
            self.client = None
            self.use_llm = False
    
    def extract_concepts(self, slide_data: List[Dict]) -> Set[str]:
        """
        Extract key concepts from lecture slides using the LLM when available.
        """
        all_concepts: Set[str] = set()

        # Process slides in small chunks to stay under token limits.
        chunk_size = 2
        for i in range(0, len(slide_data), chunk_size):
            chunk = slide_data[i : i + chunk_size]
            chunk_text = "\n\n".join(slide["text"] for slide in chunk if slide.get("text"))
            if not chunk_text.strip():
                continue

            if self.use_llm:
                concepts = self._extract_with_llm(chunk_text)
            else:
                concepts = self._extract_from_text_fallback(chunk_text)

            all_concepts.update(concepts)

        return self._filter_concepts(all_concepts)
    
    def extract_concepts_from_text(self, text: str) -> Set[str]:
        """Extract concepts from arbitrary text (e.g., student notes)."""
        if not text.strip():
            return set()

        if self.use_llm:
            concepts = self._extract_with_llm(text)
        else:
            concepts = self._extract_from_text_fallback(text)
        return self._filter_concepts(concepts)
    
    def _extract_with_llm(self, text: str) -> Set[str]:
        """Extract concepts using the LLM."""
        try:
            prompt = f"""You are extracting concise study notes from lecture slides.

Rules for every concept:
- 6–18 words, written as a clear standalone factual statement.
- Must capture a definition, relationship, numeric range, timeframe, limitation, or condition.
- Include numbers/units/time horizons when present (e.g., "risk score ranges from 1–20", "predicts re-referral within six months").
- DO NOT mention individual people, researchers, universities, dates, slide numbers, or "et al.".
- DO NOT output vague fragments like "system capabilities" or "children data".
- Each concept must be unique and understandable without seeing the slide.

Lecture text (ONLY source of truth):
{text[:2500]}

Return ONLY a valid JSON array of strings, for example:
["AFST assigns families a risk score from 1–20", "The model uses data from 21 administrative sources including child protective services"]"""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You extract clean, factual lecture concepts. Respond with JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=350,
                temperature=0.2,
            )

            result = response.choices[0].message.content.strip()
            # Remove optional Markdown wrappers
            result = re.sub(r"```json\s*", "", result)
            result = re.sub(r"```\s*", "", result)
            result = result.strip()

            concepts = json.loads(result)
            if isinstance(concepts, list):
                return set(filter(lambda x: isinstance(x, str), concepts))
            return set()

        except Exception:
            # Fallback to heuristic extraction
            return self._extract_from_text_fallback(text)
    
    def _extract_from_text_fallback(self, text: str) -> Set[str]:
        """
        Simple regex-based extraction used when LLM is unavailable.
        """
        concepts: Set[str] = set()

        sentences = re.split(r"[.!?]\s+", text)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 12:
                continue

            # Numbered facts
            number_facts = re.findall(
                r"(\b[\w\s]{0,40}(?:ranges?|range|from|between|within)\s+\d+(?:\s*[-–]\s*\d+)?(?:\s+\w+)*)",
                sentence,
                re.IGNORECASE,
            )
            concepts.update(fact.strip() for fact in number_facts)

            # Data sources
            sources = re.findall(
                r"data\s+from\s+(\d+\s+\w+(?:\s+\w+){0,6})", sentence, re.IGNORECASE
            )
            concepts.update(f"data from {src}".strip() for src in sources)

            # Predictions/timeframes
            predictions = re.findall(
                r"predicts?\s+([^,\.]+(?:\([^)]+\))?)", sentence, re.IGNORECASE
            )
            concepts.update(pred.strip() for pred in predictions)

            # Definitions
            definitions = re.findall(
                r"\b([A-Z][A-Z]+)\s+stands?\s+for\s+([^,\.]+)", sentence
            )
            concepts.update(
                f"{abbr} stands for {definition.strip()}"
                for abbr, definition in definitions
            )

            # Capabilities/features
            capabilities = re.findall(
                r"\b(?:uses?|includes?|provides?|offers?|relies\s+on)\s+([^,\.]+)",
                sentence,
                re.IGNORECASE,
            )
            for cap in capabilities[:3]:
                cap = cap.strip()
                if len(cap) > 5 and not cap.lower().startswith(("a ", "an ", "the ")):
                    concepts.add(cap)

        return concepts
    
    def _filter_concepts(self, concepts: Set[str]) -> Set[str]:
        """Filter out noisy or meaningless concepts."""
        filtered: Set[str] = set()
        if not concepts:
            return filtered

        noise_patterns = [
            r"[•▪◦]",
            r"--",
            r"___",
            r"\bslide\b",
            r"\bpage\b",
            r"\bfigure\b",
            r"\btable\b",
            r"\buniversity\b",
            r"\bdepartment\b",
        ]
        stop_words = {
            "the",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
        }

        for concept in concepts:
            if not concept:
                continue

            concept_clean = concept.strip()
            if not concept_clean:
                continue

            # Remove leading bullets/numbering
            concept_clean = re.sub(r"^[\d\.\)\-]+\s*", "", concept_clean)

            # Very short concepts are rarely useful (unless contain numbers/proper nouns)
            if len(concept_clean) < 6:
                if not re.search(r"\d", concept_clean) and not re.search(
                    r"\b[A-Z][a-z]+\b", concept_clean
                ):
                    continue

            # Remove repeated punctuation / bullet artifacts
            if any(re.search(pattern, concept_clean.lower()) for pattern in noise_patterns):
                continue

            # Skip if mostly stopwords (e.g., "the system is")
            words = concept_clean.lower().split()
            if not words:
                continue
            stopword_ratio = sum(1 for w in words if w in stop_words) / len(words)
            if stopword_ratio > 0.65 and len(words) < 5:
                continue

            # Skip if no meaningful nouns or verbs
            if not re.search(r"[A-Za-z]{3,}", concept_clean):
                continue

            filtered.add(concept_clean)

        return filtered
    
    def find_missing_concepts(self, lecture_concepts: Set[str], notes_concepts: Set[str]) -> List[str]:
        """
        Find concepts present in lecture but missing from notes
        
        Args:
            lecture_concepts: Set of clean concepts from covered slides
            notes_concepts: Set of clean concepts from student notes
            
        Returns:
            List of truly missing concept strings
        """
        # Filter both sets first
        lecture_concepts = self._filter_concepts(lecture_concepts)
        notes_concepts = self._filter_concepts(notes_concepts)
        
        # Simple set difference
        missing = lecture_concepts - notes_concepts
        
        if not missing:
            return []
        
        # Use semantic similarity to catch paraphrased concepts
        missing_list = list(missing)
        notes_list = list(notes_concepts)
        
        if not notes_list:
            return missing_list[:10]
        
        # Embed missing concepts and notes concepts
        missing_embeddings = self.embedding_service.embed_batch(missing_list)
        notes_embeddings = self.embedding_service.embed_batch(notes_list)
        
        # Find truly missing concepts (low similarity to any note concept)
        truly_missing = []
        similarity_threshold = 0.75  # High threshold to ensure concepts are actually missing
        
        for i, missing_concept in enumerate(missing_list):
            missing_emb = missing_embeddings[i]
            max_similarity = 0.0
            
            for note_emb in notes_embeddings:
                similarity = self.embedding_service.similarity(missing_emb, note_emb)
                max_similarity = max(max_similarity, similarity)
            
            if max_similarity < similarity_threshold:
                truly_missing.append(missing_concept)
        
        return truly_missing[:10]  # Limit to top 10 missing concepts

    def select_priority_concepts(self, concepts: Set[str], limit: int = 5) -> List[str]:
        """Select the most informative concepts to use as hints."""
        if not concepts:
            return []

        def score(concept: str) -> int:
            s = 0
            if re.search(r"\d", concept):
                s += 3
            if len(concept.split()) >= 4:
                s += 2
            if any(word in concept.lower() for word in ("predict", "risk", "score", "uses", "based", "model")):
                s += 1
            return s

        ranked = sorted(concepts, key=lambda c: (score(c), len(c)), reverse=True)
        return ranked[:limit]

