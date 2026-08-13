"""
services/llm.py — LLM client: Gemma 4 2B (local, via transformers) PRIMARY
                               Gemini API (google-generativeai)      FALLBACK

All 5 LLM use-cases in the MVP flow through this module:
  1. generate_queries()   — Module 1: expand seed niches to Maps search queries
  2. score_rag()          — Module 3: 0-100 RAG-fit score + rationale
  3. summarize_persona()  — Module 5: 3-5 sentence company summary
  4. draft_email()        — Module 6: HTML outreach email
  5. classify_reply()     — Module 9: classify inbound reply into 4 buckets

Design constraints (from spec §2):
  - Never invent facts not present in the evidence passed in.
  - Return JSON for structured calls; retry once on parse failure.
  - A bad model response must never block the pipeline — callers get None / fallback.

LLM priority:
  1. Gemma 4 2B loaded locally via HuggingFace transformers (GEMMA_LOCAL_MODEL_ID).
  2. If Gemma fails (OOM, model not found, etc.), the call falls back to the
     Gemini API (GEMINI_API_KEY + GEMMA_MODEL).  Set GEMINI_API_KEY="" to
     disable the fallback entirely.
"""
import json
import logging
import re
import threading
from typing import Optional

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Gemma 4 2B local model (primary) ─────────────────────────────────────────

_gemma_processor = None
_gemma_model = None
_gemma_load_lock = threading.Lock()
_gemma_load_failed = False   # set to True if the model fails to load so we skip retries

GEMMA_LOCAL_MODEL_ID = settings.GEMMA_LOCAL_MODEL_ID  # e.g. "google/gemma-4-2b-it"


def _load_gemma():
    """
    Lazy-load the Gemma model + processor on first use.
    Thread-safe via a lock so concurrent callers don't double-load.
    Returns (processor, model) or (None, None) on failure.
    """
    global _gemma_processor, _gemma_model, _gemma_load_failed
    if _gemma_load_failed:
        return None, None
    if _gemma_processor is not None:
        return _gemma_processor, _gemma_model

    with _gemma_load_lock:
        # Double-checked locking
        if _gemma_processor is not None:
            return _gemma_processor, _gemma_model
        if _gemma_load_failed:
            return None, None
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch
            logger.info("Loading Gemma model '%s' (this may take a while to download) …", GEMMA_LOCAL_MODEL_ID)
            tokenizer = AutoTokenizer.from_pretrained(GEMMA_LOCAL_MODEL_ID)
            
            # device_map="auto" works if accelerate is installed.
            model = AutoModelForCausalLM.from_pretrained(
                GEMMA_LOCAL_MODEL_ID,
                torch_dtype="auto",
                device_map="auto",
            )
            _gemma_processor = tokenizer
            _gemma_model = model
            logger.info("Gemma model loaded successfully.")
            return _gemma_processor, _gemma_model
        except Exception as exc:
            logger.error(
                "Failed to load Gemma local model '%s': %s. "
                "Will fall back to Gemini API for all LLM calls.",
                GEMMA_LOCAL_MODEL_ID, exc,
            )
            _gemma_load_failed = True
            return None, None


def _call_gemma(prompt: str) -> Optional[str]:
    """
    Run inference with the local Gemma model.
    Returns the generated text string, or None on any error.
    """
    processor, model = _load_gemma()
    if processor is None or model is None:
        return None

    try:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ]
        inputs = processor.apply_chat_template(
            messages,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            add_generation_prompt=True,
        ).to(model.device)
        input_len = inputs["input_ids"].shape[-1]
        
        logger.info("Starting Gemma inference (prompt length: %s tokens)...", input_len)
        outputs = model.generate(**inputs, max_new_tokens=1024)
        logger.info("Gemma inference complete.")
        
        raw = processor.decode(outputs[0][input_len:], skip_special_tokens=True)
        return raw.strip()
    except Exception as exc:
        logger.error("Gemma inference error: %s", exc)
        return None


# ── Gemini API fallback ───────────────────────────────────────────────────────

_gemini_model = None


def _get_gemini_model():
    """Lazy-init the Gemini API client (only when actually needed)."""
    global _gemini_model
    if _gemini_model is not None:
        return _gemini_model
    if not settings.GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel(model_name=settings.GEMMA_MODEL)
        logger.info("Gemini API fallback client initialised (model: %s).", settings.GEMMA_MODEL)
        return _gemini_model
    except Exception as exc:
        logger.error("Failed to initialise Gemini API client: %s", exc)
        return None


def _call_gemini(prompt: str) -> Optional[str]:
    """Call the Gemini API. Returns text or None."""
    model = _get_gemini_model()
    if model is None:
        return None
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as exc:
        logger.error("Gemini API fallback error: %s", exc)
        return None


# ── Unified call helpers ──────────────────────────────────────────────────────

def _call(prompt: str) -> str:
    """
    Run the prompt through Gemma (primary) → Gemini (fallback).
    Raises RuntimeError only when BOTH providers fail, so callers can catch.
    """
    result = _call_gemma(prompt)
    if result is not None:
        return result

    logger.warning("Gemma unavailable — falling back to Gemini API.")
    result = _call_gemini(prompt)
    if result is not None:
        return result

    raise RuntimeError("Both Gemma local model and Gemini API fallback failed.")


def _parse_json(text: str) -> Optional[dict]:
    """Extract JSON from model output, tolerating markdown fences."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _call_json(prompt: str) -> Optional[dict]:
    """Call model and parse JSON; retry once on parse failure."""
    for attempt in range(2):
        try:
            raw = _call(prompt)
            result = _parse_json(raw)
            if result is not None:
                return result
            logger.warning("JSON parse failed (attempt %d). Raw: %s", attempt + 1, raw[:200])
        except Exception as exc:
            logger.error("LLM call error (attempt %d): %s", attempt + 1, exc)
    return None


# ── 1. Query generation (Module 1) ────────────────────────────────────────────

def generate_queries(seed_niches: list[str], seed_locations: list[str], n: int = 5) -> list[str]:
    """
    Expand seed niches × locations into natural Google Maps search queries.
    Falls back to simple `niche + location` combinations on parse failure.
    """
    prompt = f"""You are helping build search queries for a local business lead-generation
tool that searches Google Maps.

Business niches: {', '.join(seed_niches)}
Target locations: {', '.join(seed_locations)}

For EACH niche, write {n} distinct, natural-sounding Google Maps search queries that
combine that niche with one or more of the target locations.
Vary the phrasing the way a real person types into Google Maps search.
Do not repeat the same query twice.

Return ONLY a JSON array of strings. No markdown, no commentary, no keys."""

    try:
        raw = _call(prompt)
        result = _parse_json(raw)
        if isinstance(result, list) and result:
            return [str(q) for q in result]
    except Exception as exc:
        logger.error("Query generation failed: %s", exc)

    # Fallback: simple cross-product
    fallback = [f"{niche} in {loc}" for niche in seed_niches for loc in seed_locations]
    logger.warning("Using fallback queries (%d total).", len(fallback))
    return fallback


# ── Unified Extraction, Scoring, Persona (Module 2/3/5) ──────────────────────

def extract_and_score_and_persona(combined_text: str) -> Optional[dict]:
    """
    Unified LLM call to extract fields, score RAG opportunity, and generate a persona.
    Returns a dict with keys: industry, employees_estimate, summary, tech_stack_hints,
    rag_score, rag_rationale, persona_summary.
    """
    prompt = f"""You are a B2B research analyst. Extract information and score the
company based ONLY on the website text below. Do not invent facts.

Website text:
{combined_text[:3000]}

Return ONLY a valid JSON object with EXACTLY these keys:
- "industry": primary industry or sector (string or null)
- "employees_estimate": rough headcount band e.g. "1-10", "11-50", "51-200", "201-500", "500+" (string or null)
- "summary": 2-3 sentences describing what the company does (string or null)
- "tech_stack_hints": comma-separated list of technologies/tools mentioned (string or null)
- "rag_score": integer (0-100) scoring how likely they would benefit from a RAG system (consider knowledge base size, AI initiatives, compliance)
- "rag_rationale": 1 sentence explaining the rag_score (string)
- "persona_summary": 3-5 sentences summarizing the company for a sales rep, using only confirmed facts (string)
"""
    return _call_json(prompt)


# ── 4. Email draft (Module 6) ─────────────────────────────────────────────────

def draft_email(
    persona_summary: str,
    company_name: str,
    contact_name: str,
    sender_name: str,
    sender_company: str,
    meeting_link: str,
    website: str,
) -> Optional[str]:
    """
    Returns a valid HTML string (120-160 words) or None on failure.
    """
    prompt = f"""You are a professional B2B sales writer. Write a short, genuine-sounding
outreach email (120-160 words).

Rules:
- Use ONLY facts present in the persona summary below. Never invent news, numbers,
  or claims about the recipient's company.
- Reference exactly one specific, verifiable detail about them.
- Name exactly one plausible pain point and how a RAG solution helps.
- End with a call to action to schedule a 10-minute chat using this meeting link: {meeting_link}
- Output CLEAN and VALID HTML only. DO NOT wrap your output in markdown ```html code blocks. Just output the raw HTML tags.
- Use simple, clean HTML styling (e.g. <p style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333;">).
- Format the CTA as a highly visible, clickable HTML button or link.
- In the signature footer, include the sender name, company, and this website link: {website}
- No superlatives, no fake urgency, no "I noticed you're the perfect fit" filler.

Persona summary:
{persona_summary}

Company: {company_name}
Contact name: {contact_name}
Sender: {sender_name}, {sender_company}"""

    try:
        html = _call(prompt)
        
        # Strip markdown fences if the model still outputs them
        html = html.replace('```html', '').replace('```', '').strip()
        
        return html
    except Exception as exc:
        logger.error("Email draft failed: %s", exc)
        return None


# ── 5. Reply classification (Module 9) ────────────────────────────────────────

def classify_reply(reply_text: str) -> Optional[dict]:
    """
    Returns {"classification": str, "sentiment": str} or None on failure.
    Classification buckets: interested | not_interested | needs_info | auto_reply_or_oof
    """
    prompt = f"""Classify this email reply into exactly one category:
interested | not_interested | needs_info | auto_reply_or_oof

Return JSON only:
{{"classification": "<category>", "sentiment": "positive|neutral|negative"}}

Reply text:
{reply_text[:4000]}"""   # cap at 4k chars to avoid token blowout

    return _call_json(prompt)
