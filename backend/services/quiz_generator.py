from typing import List, Dict, Any, Optional
import json
import os
import re
from openai import OpenAI


class QuizGenerator:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-3.5-turbo-0125"

    def generate(self, notes_text: str, slide_data: List[Dict[str, Any]]) -> List[Dict]:
        if not slide_data:
            return []

        lecture_text = "\n\n".join(
            s.get("text", "") for s in slide_data if s.get("text")
        ).strip()
        if not lecture_text:
            return []

        try:
            prompt = self._build_prompt(notes_text, lecture_text)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You create clear, grounded multiple-choice questions for students. "
                            "You only use the provided lecture text and never hallucinate."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1100,
                temperature=0.4,
            )
            content = (response.choices[0].message.content or "").strip()

            cleaned = re.sub(r"^```json\s*", "", content)
            cleaned = re.sub(r"^```", "", cleaned)
            cleaned = re.sub(r"```$", "", cleaned).strip()

            try:
                data = json.loads(cleaned)
            except Exception:
                start = cleaned.find("[")
                end = cleaned.rfind("]")
                if start != -1 and end != -1 and end > start:
                    snippet = cleaned[start : end + 1]
                    data = json.loads(snippet)
                else:
                    raise

            return self._normalize_questions(data)
        except Exception as e:
            print(f"[QuizGenerator] Failed to generate quiz: {e}")
            return []

    def generate_single(
        self, 
        slide_data: List[Dict[str, Any]], 
        previous_questions: Optional[List[Dict]] = None
    ) -> Dict:
        if not slide_data:
            return {}

        lecture_text = "\n\n".join(
            s.get("text", "") for s in slide_data if s.get("text")
        ).strip()
        if not lecture_text:
            return {}

        exclude_instruction = ""
        if previous_questions:
            topics_covered = [q.get("topic", "") for q in previous_questions if q.get("topic")]
            questions_asked = [q.get("question", "")[:100] for q in previous_questions if q.get("question")]
            
            if topics_covered:
                exclude_instruction = f"""
IMPORTANT: Do NOT ask about these topics that were already covered:
{', '.join(set(topics_covered))}

Also avoid questions similar to these already asked:
{chr(10).join(f"- {q}" for q in questions_asked[:3])}

Choose a DIFFERENT topic and concept from the lecture that hasn't been asked about yet.
"""

        try:
            prompt = f"""You are an instructor creating a quiz question based on lecture slides.

LECTURE TEXT (only source of truth):
{lecture_text[:3000]}
{exclude_instruction}
TASK:
Write exactly 1 multiple-choice question testing a key concept from this lecture.

CRITICAL REQUIREMENTS:
- Choose a topic/concept that is DIFFERENT from any previous questions
- Cover a different part of the lecture material
- Provide a short topic label (2-4 words) describing what the question tests
- Provide 3-4 answer options
- Exactly ONE option must be correct based on the lecture
- Include a 1-2 sentence explanation

STRICT RULES:
- Use ONLY facts from the lecture text
- No external knowledge, no names, no citations, no dates
- Ensure variety: if previous questions were about technical details, ask about concepts, applications, or relationships instead

Return ONLY valid JSON:
{{
  "topic": "Short Topic Label",
  "question": "...",
  "options": ["...", "...", "..."],
  "correct_index": 0,
  "explanation": "..."
}}
"""
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You create diverse quiz questions grounded in lecture content. You ensure each question covers a different topic."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=400,
                temperature=0.7,
            )
            content = (response.choices[0].message.content or "").strip()
            
            cleaned = re.sub(r"^```json\s*", "", content)
            cleaned = re.sub(r"^```", "", cleaned)
            cleaned = re.sub(r"```$", "", cleaned).strip()
            
            try:
                data = json.loads(cleaned)
            except Exception:
                start = cleaned.find("{")
                end = cleaned.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json.loads(cleaned[start:end+1])
                else:
                    return {}
            
            normalized = self._normalize_questions([data])
            return normalized[0] if normalized else {}
            
        except Exception as e:
            print(f"[QuizGenerator] Failed to generate single question: {e}")
            return {}

    def _build_prompt(self, notes_text: str, lecture_text: str) -> str:
        return f"""You are an instructor creating a short quiz based on lecture slides.

LECTURE TEXT (only source of truth):
{lecture_text[:3500]}

STUDENT NOTES (may be incomplete):
{(notes_text or '')[:800]}

TASK:
Write 4–6 multiple-choice questions that test key concepts from this lecture segment.
Each question should cover a DIFFERENT topic from the lecture.

For each question:
- Provide a SHORT topic label (2-4 words) that describes what concept the question tests (e.g., "Risk Score Range", "Data Sources", "Decision Authority")
- Provide 3–4 answer options
- Exactly ONE option must be clearly correct based only on the lecture text
- Other options must be plausible but incorrect

STRICT RULES:
- Use ONLY facts that appear in the lecture text above
- Do NOT introduce external knowledge
- Do NOT mention researchers, names, universities, or citations
- Avoid slide numbers, dates, or reference codes
- Keep wording simple and clear

Return ONLY valid JSON with this exact structure:
[
  {{
    "topic": "Short Topic Label",
    "question": "...",
    "options": ["...", "...", "..."],
    "correct_index": 1,
    "explanation": "1–2 sentence explanation grounded in the lecture text."
  }},
  ...
]
"""

    def _normalize_questions(self, data: Any) -> List[Dict]:
        questions: List[Dict] = []
        if not isinstance(data, list):
            return questions

        for item in data:
            if not isinstance(item, dict):
                continue

            topic = str(item.get("topic", "")).strip()
            q_text = str(item.get("question", "")).strip()
            options = item.get("options", [])
            correct_idx = item.get("correct_index")
            explanation = str(item.get("explanation", "")).strip()

            if not q_text or not isinstance(options, list) or len(options) < 3:
                continue

            options = [str(opt).strip() for opt in options if str(opt).strip()]
            if not (3 <= len(options) <= 5):
                continue

            if not isinstance(correct_idx, int):
                continue
            if not (0 <= correct_idx < len(options)):
                continue

            def clean_text(text: str) -> str:
                text = re.sub(r"http[s]?://\S+", "", text)
                text = re.sub(r"www\.\S+", "", text)
                text = re.sub(r"\bet\s+al\.?", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\([^)]*\)", "", text)
                text = re.sub(r"\b(?:19|20)\d{2}\b", "", text)
                text = " ".join(text.split())
                return text

            topic = clean_text(topic) if topic else "General"
            q_text = clean_text(q_text)
            options = [clean_text(o) for o in options]
            explanation = clean_text(explanation)

            if not q_text or any(not o for o in options):
                continue

            if len(explanation.split()) > 40:
                explanation = " ".join(explanation.split()[:40]) + "…"

            questions.append(
                {
                    "topic": topic,
                    "question": q_text,
                    "options": options,
                    "correct_index": correct_idx,
                    "explanation": explanation,
                }
            )

        return questions[:6]
