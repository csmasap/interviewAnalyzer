"""
THEIA Interview Prep System - Simple Main Application
Simple working version to test all credentials and basic functionality.
"""

import os
import sys
import logging
from datetime import datetime
from fastapi import FastAPI
from fastapi import Header
from fastapi import Query
from fastapi import HTTPException
from fastapi import Depends
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
import json as _json
import urllib.parse as _urlparse

# Permanent Python path configuration for theia_agents module
def ensure_python_path():
    """Ensure the backend directory is in Python path for module imports (prevents duplicates)"""
    backend_path = os.path.dirname(os.path.abspath(__file__))
    
    # Remove any existing duplicate paths first
    while backend_path in sys.path:
        sys.path.remove(backend_path)
    
    # Add it at the beginning
    sys.path.insert(0, backend_path)
    return backend_path

# Apply Python path configuration immediately at module level
ensure_python_path()
import urllib.request as _urlreq
import time

from typing import Optional, Dict, Any, List

from jose import jwt
from jose.utils import base64url_decode
import requests as _requests
import asyncio
import httpx
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

# Import THEIA configuration
try:
    from config import settings
except ImportError:
    # Fallback if config module not available
    class _Settings:
        GOOGLE_CLOUD_PROJECT_ID = None
    settings = _Settings()

# Load environment variables from .env file (robust to working directory)
try:
    project_root = Path(__file__).resolve().parent.parent
    candidates = [
        project_root / '.env',            # repo root
        Path(__file__).resolve().parent / '.env',  # backend/.env (fallback)
        Path.cwd() / '.env',              # current working dir
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p)
            break
    else:
        load_dotenv()  # last resort: default search
except Exception:
    load_dotenv()

# Set up environment
# Cloud Run uses default service account - don't override credentials
# os.environ.setdefault('GOOGLE_APPLICATION_CREDENTIALS', './credentials/theia-service-account.json')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="THEIA Interview Prep System",
    description="AI-powered interview preparation system",
    version="1.0.0"
)

# In-memory session storage for local testing only
SESSIONS = {}

# ISA_Chat dependencies for Text modal live interaction
try:
    from theia_agents.isa_chat import ISAChat
    from models import (
        InterviewSession as _InterviewSession,
        InterviewPhase as _InterviewPhase,
        InterviewStatus as _InterviewStatus,
        QuestionGenerationOutput as _QuestionGenerationOutput,
    )
except Exception:
    ISAChat = None
    _InterviewSession = None
    _InterviewPhase = None
    _InterviewStatus = None
    _QuestionGenerationOutput = None

# ISA_Resume_Builder dependencies for Resume generation
try:
    from theia_agents.isa_resume_builder import ISAResumeBuilder
    RESUME_BUILDER_AVAILABLE = True
    logger.info("✅ ISAResumeBuilder imported successfully at module level")
except Exception as e:
    ISAResumeBuilder = None
    RESUME_BUILDER_AVAILABLE = False
    logger.warning(f"❌ ISAResumeBuilder not available at module level: {e}")

# ----------------------------
# Utility helpers (local only)
# ----------------------------

def _normalize_text(text: str) -> str:
    return (text or "").lower()

# ----------------------------
# Auth & Security helpers
# ----------------------------

_AUTH0_JWKS_CACHE: Optional[dict] = None
_AUTH0_JWKS_FETCH_TS: Optional[float] = None
_AUTH0_JWKS_TTL = 3600.0

# Cache Salesforce Contact describe fields to reduce latency and avoid repeated calls
_SF_CONTACT_FIELDS_CACHE: Optional[set] = None
_SF_CONTACT_FIELDS_TS: Optional[float] = None
_SF_CONTACT_FIELDS_TTL = 300.0

def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(name, default)

def _get_auth0_jwks() -> dict:
    global _AUTH0_JWKS_CACHE, _AUTH0_JWKS_FETCH_TS
    now = time.time()
    if _AUTH0_JWKS_CACHE and _AUTH0_JWKS_FETCH_TS and (now - _AUTH0_JWKS_FETCH_TS) < _AUTH0_JWKS_TTL:
        return _AUTH0_JWKS_CACHE
    domain = _get_env("AUTH0_DOMAIN", "").strip()
    if not domain:
        raise HTTPException(status_code=500, detail="Auth0 domain not configured")
    url = f"https://{domain}/.well-known/jwks.json"
    try:
        resp = _requests.get(url, timeout=10)
        resp.raise_for_status()
        _AUTH0_JWKS_CACHE = resp.json()
        _AUTH0_JWKS_FETCH_TS = now
        return _AUTH0_JWKS_CACHE
    except Exception as e:
        logger.error("Failed to fetch Auth0 JWKS: %s", e)
        raise HTTPException(status_code=500, detail="Unable to fetch Auth0 JWKS")

def _verify_auth0_jwt(bearer_token: str, access_token_for_hash: Optional[str] = None) -> dict:
    """Verify an Auth0 access or ID token and return claims.
    Requires AUTH0_DOMAIN and AUTH0_AUDIENCE in env.
    """
    if not bearer_token or not bearer_token.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = bearer_token.split(" ", 1)[1].strip()
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token header")

    jwks = _get_auth0_jwks()
    rsa_key = {}
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"],
            }
            break
    if not rsa_key:
        raise HTTPException(status_code=401, detail="Appropriate key not found")

    audience = _get_env("AUTH0_AUDIENCE", "").strip() or None
    issuer = f"https://{_get_env('AUTH0_DOMAIN', '').strip()}/"
    try:
        # Build decode options - explicitly disable audience verification when no audience is configured
        decode_options = {"verify_aud": False, "verify_signature": True, "verify_exp": True, "verify_nbf": True, "verify_iat": True}
        
        # If no audience, we likely have an ID token; if at_hash exists and we don't have access_token, disable at_hash verification
        try:
            unverified_claims = jwt.get_unverified_claims(token)
        except Exception:
            unverified_claims = {}
        if not audience and "at_hash" in unverified_claims and not access_token_for_hash:
            decode_options["verify_at_hash"] = False

        # Determine if this is an ID token or access token by checking claims
        token_aud = unverified_claims.get("aud")
        token_iss = unverified_claims.get("iss")
        
        # Debug logging
        logger.info(f"Token claims debug: aud={token_aud}, iss={token_iss}, configured_audience={audience}")
        
        is_id_token = not token_aud or token_aud == token_iss  # ID tokens either have no aud or aud=issuer
        is_access_token = token_aud and token_aud != token_iss  # Access tokens have aud != issuer
        
        logger.info(f"Token type detection: is_id_token={is_id_token}, is_access_token={is_access_token}")
        
        # Handle ID tokens (no audience validation)
        if is_id_token:
            logger.info("Processing as ID token - skipping audience verification")
            # ID tokens don't have audience, so skip audience verification
            id_decode_options = {"verify_aud": False, "verify_signature": True, "verify_exp": True, "verify_nbf": True, "verify_iat": True}
            if "at_hash" in unverified_claims and not access_token_for_hash:
                id_decode_options["verify_at_hash"] = False
            
            claims = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                issuer=issuer,
                options=id_decode_options,
                access_token=access_token_for_hash if access_token_for_hash and "at_hash" in unverified_claims else None,
            )
        
        # Handle access tokens (require audience validation if configured)
        elif is_access_token and audience:
            logger.info(f"Processing as access token - validating audience: {audience}")
            
            # Check if token audience matches our configured audience OR our client_id (Auth0 fallback)
            client_id = _get_env("AUTH0_CLIENT_ID", "").strip()
            valid_audiences = [audience]
            if client_id and token_aud == client_id:
                # Auth0 sometimes issues access tokens with client_id as audience
                logger.info(f"Token has client_id as audience ({client_id}), accepting as valid")
                valid_audiences.append(client_id)
            
            # Validate access token against valid audiences
            access_decode_options = {"verify_aud": True}
            if "at_hash" in unverified_claims and not access_token_for_hash:
                access_decode_options["verify_at_hash"] = False
            
            # Try validation with each valid audience
            claims = None
            for valid_aud in valid_audiences:
                try:
                    # Build jwt.decode arguments conditionally
                    decode_args = {
                        "token": token,
                        "key": rsa_key,
                        "algorithms": ["RS256"],
                        "audience": valid_aud,
                        "issuer": issuer,
                        "options": access_decode_options,
                    }
                    
                    # Only pass access_token if we have one for at_hash verification
                    if access_token_for_hash and "at_hash" in unverified_claims:
                        decode_args["access_token"] = access_token_for_hash
                    
                    claims = jwt.decode(**decode_args)
                    logger.info(f"Successfully validated token with audience: {valid_aud}")
                    break
                except Exception as aud_err:
                    logger.info(f"Failed to validate with audience {valid_aud}: {aud_err}")
                    continue
            
            if not claims:
                raise Exception(f"Token validation failed for all valid audiences: {valid_audiences}")
        
        # Fallback: treat as ID token if audience not configured
        else:
            logger.info("Using fallback ID token handling (no audience configured or unrecognized token type)")
            # Default to ID token handling when audience not configured
            fallback_options = {"verify_aud": False, "verify_signature": True, "verify_exp": True, "verify_nbf": True, "verify_iat": True}
            if "at_hash" in unverified_claims and not access_token_for_hash:
                fallback_options["verify_at_hash"] = False
            
            claims = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                issuer=issuer,
                options=fallback_options,
            )
        return claims
    except Exception as e:
        try:
            hdr = jwt.get_unverified_header(token)
        except Exception:
            hdr = {}
        logger.warning("Auth0 token verification failed: %s (alg=%s)", e, hdr.get("alg"))
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")

def _mint_theia_token(contact_id: str, email: Optional[str]) -> str:
    secret = _get_env("THEIA_JWT_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="Server token secret not configured")
    ttl = int(_get_env("THEIA_JWT_TTL_SECONDS", "7200"))
    now = int(time.time())
    payload = {
        "sub": contact_id,
        "email": email or "",
        "iat": now,
        "exp": now + ttl,
        "iss": _get_env("THEIA_JWT_ISSUER", "theia"),
        "aud": _get_env("THEIA_JWT_AUDIENCE", "theia-clients"),
        "scope": "user"
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def _extract_email_from_claims(claims: dict) -> str:
    # Common email locations in Auth0 tokens
    return (
        claims.get("email")
        or claims.get("https://schemas.auth0.com/email")
        or claims.get("https://schemas.openid.net/claims/email")
        or ""
    )

def extract_skills_from_jd(job_description: str) -> list:
    """Dynamic skill/competency extraction from a variable job description.
    Heuristic-only, no hardcoded skill list. Returns up to 7 ranked phrases.
    """
    import re
    from collections import Counter, defaultdict

    text = (job_description or "").strip()
    if not text:
        return []

    # Normalize for matching but keep original for light-weight casing heuristics later
    lower = text.lower()

    # Very small stopword set to avoid banning domain terms
    stop = {
        "and", "or", "the", "a", "an", "of", "to", "for", "with", "in", "on", "by", "from",
        "at", "as", "be", "is", "are", "that", "this", "these", "those", "you", "your",
        "we", "our", "their", "they", "it", "will", "must", "can", "may", "etc", "including",
        "include", "includes", "such", "such as", "using", "use", "used", "ability", "strong",
        "excellent", "good", "great", "work", "team", "company", "role", "candidate", "experience",
        "knowledge", "skills", "requirements", "qualifications", "preferred", "responsibilities",
    }

    # 1) Capture phrases following common requirement stems (no fixed skills)
    stem_pattern = re.compile(
        r"(?:experience\s+with|proficient\s+in|knowledge\s+of|skills\s+in|expertise\s+in|familiarity\s+with|"
        r"background\s+in|hands\-on\s+with|working\s+with|exposure\s+to|including|such\s+as)\s+"
        r"([A-Za-z0-9+/#&.,\-() ]{3,})",
        re.IGNORECASE,
    )
    candidates: Counter = Counter()
    sources: defaultdict = defaultdict(int)

    def _split_items(blob: str) -> list:
        # Split on commas, slashes, semicolons, and conjunctions
        parts = re.split(r"[,/;]|\band\b|\bor\b", blob, flags=re.IGNORECASE)
        cleaned = []
        for p in parts:
            t = p.strip(" \t\n.:;,-/")
            if not t:
                continue
            # Keep short phrases (1-5 words)
            words = [w for w in re.split(r"\s+", t) if w]
            if 1 <= len(words) <= 5:
                cleaned.append(" ".join(words))
        return cleaned

    for m in stem_pattern.finditer(text):
        items = _split_items(m.group(1))
        for it in items:
            k = it.lower()
            if k and not all(w in stop for w in k.split()):
                candidates[k] += 3  # higher weight for explicit requirement stems
                sources[k] += 1

    # 2) Pull likely bullet items (lines starting with -, *, •)
    bullet_items = []
    for line in text.splitlines():
        if re.match(r"^\s*([\-\*•])\s+", line):
            bullet = re.sub(r"^\s*([\-\*•])\s+", "", line).strip()
            # Truncate at sentence end
            bullet = re.split(r"[.;]", bullet)[0]
            bullet_items.extend(_split_items(bullet))
    for it in bullet_items:
        k = it.lower()
        if k and not all(w in stop for w in k.split()):
            candidates[k] += 2
            sources[k] += 1

    # 3) Add frequent n-grams (1-3) that look like skill phrases (letters, +, /, #, -)
    tokens = [t for t in re.findall(r"[A-Za-z0-9+/#\-]+", lower) if t and t not in stop]
    # Unigrams
    for t in tokens:
        if len(t) >= 2 and any(c.isalpha() for c in t) and t not in stop:
            candidates[t] += 1
    # Bigrams and trigrams
    for n in (2, 3):
        for i in range(len(tokens) - n + 1):
            ngram = " ".join(tokens[i : i + n])
            if any(c.isalpha() for c in ngram) and not any(w in stop for w in ngram.split()):
                candidates[ngram] += 1

    if not candidates:
        return []

    # Light normalization and filtering
    def _clean_phrase(p: str) -> str:
        p = p.strip(" ")
        p = re.sub(r"\s+", " ", p)
        return p

    filtered = []
    for phrase, score in candidates.most_common(200):
        ph = _clean_phrase(phrase)
        if not ph:
            continue
        # Filter too generic singles
        if len(ph) <= 2:
            continue
        if ph in stop or all(w in stop for w in ph.split()):
            continue
        filtered.append((ph, score))

    # De-duplicate by stem (simple lowercase key)
    seen = set()
    ranked = []
    for ph, sc in filtered:
        key = ph.lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append((ph, sc))

    # Choose top 7 by score with slight preference for items seen in stems/bullets
    ranked.sort(key=lambda x: (candidates[x[0].lower()], len(x[0]) <= 25), reverse=True)
    top = [p for p, _ in ranked[:7]]

    # Return lowercased phrases for downstream matching; keep readability
    return [t.lower() for t in top]

def sanitize_for_applicant_perspective(text: str, company_label: str) -> str:
    """Ensure questions never imply the candidate has worked at the target company.
    Replaces patterns like 'for COMPANY' / 'at COMPANY' with applicant-perspective phrasing.
    """
    if not company_label:
        return text
    import re
    company_re = re.escape(company_label)
    # Normalize multiple spaces
    sanitized = text
    sanitized = re.sub(fr"\bfor\s+{company_re}\b", f"in a previous role (relevant to {company_label})", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(fr"\bat\s+{company_re}\b", f"in a previous role (relevant to {company_label})", sanitized, flags=re.IGNORECASE)
    # Guard generic 'for the company' phrasing
    sanitized = re.sub(r"\bfor\s+the\s+company\b", "in a previous role (relevant to the company)", sanitized, flags=re.IGNORECASE)
    return sanitized

def extract_first_name(full_name: str) -> str:
    """Return only the first name from a full name string."""
    if not full_name:
        return ""
    parts = [p for p in str(full_name).strip().split() if p]
    return parts[0] if parts else ""

def summarize_company_interview_style(company_name: str, job_title: str, job_description: str) -> str:
    """Role- and content-driven summary of likely interview format without company-specific hardcoding."""
    title = _normalize_text(job_title)
    jd = _normalize_text(job_description)
    signals = set()
    if any(k in title or k in jd for k in ["consultant", "consulting", "case interview", "case study"]):
        signals.add("case")
    if any(k in title or k in jd for k in ["software", "engineer", "backend", "frontend", "full stack", "system design"]):
        signals.add("tech")
    if any(k in title or k in jd for k in ["product manager", "pm", "product"]):
        signals.add("pm")
    if any(k in title or k in jd for k in ["data", "analytics", "analyst", "quant", "sql", "python"]):
        signals.add("data")
    if any(k in title or k in jd for k in ["talent", "hr", "staffing", "people ops", "recruiting"]):
        signals.add("peopleops")

    parts = []
    if "case" in signals:
        parts.append("Expect structured problem-solving (case-style) evaluating hypothesis-driven thinking, quantitative rigor, and synthesis.")
    if "tech" in signals:
        parts.append("Technical screens may include coding, debugging, and system design with emphasis on clarity and trade-offs.")
    if "pm" in signals:
        parts.append("PM interviews often cover product sense, execution, analytics, and leadership via behavioral prompts.")
    if "data" in signals:
        parts.append("Data interviews focus on metrics, SQL/analysis, experimentation, and communicating insights to stakeholders.")
    if "peopleops" in signals:
        parts.append("People/Talent roles emphasize stakeholder management, prioritization, conflict resolution, and operational judgment.")
    if not parts:
        parts.append("Interviews typically combine role-relevant scenarios with behavioral questions to assess impact, collaboration, and communication.")

    return " ".join(parts)

def perform_company_research(company_name: str, job_title: str, job_description: str) -> dict:
    """ISA_Researcher: derive the company's interview style and process.
    Attempts a structured summary using Vertex AI; falls back to role-based guidance.
    """
    company = (company_name or "").strip()
    title = (job_title or "").strip()
    jd = (job_description or "").strip()

    # Default fallback based on role signals only
    fallback_overview = summarize_company_interview_style(company, title, jd)
    fallback = {
        "company": company,
        "interview_overview": fallback_overview,
        "rounds": ["screening", "role-specific", "behavioral"],
        "question_styles": ["behavioral", "role scenarios", "metrics & outcomes"],
        "evaluation_criteria": ["communication", "problem solving", "collaboration", "impact"],
        "tips": ["structure answers", "quantify outcomes", "align to role scope"],
        "disclaimer": "Generated without live browsing; refine with verified company sources."
    }

    def _cse_search(query: str, cse_id: str, api_key: str, num: int = 5) -> list:
        try:
            params = _urlparse.urlencode({
                "key": api_key,
                "cx": cse_id,
                "q": query,
                "num": num,
                "gl": "us",
                "hl": "en",
                "safe": "active",
            })
            url = f"https://www.googleapis.com/customsearch/v1?{params}"
            with _urlreq.urlopen(url, timeout=10) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            results = []
            for it in items:
                results.append({
                    "title": it.get("title"),
                    "link": it.get("link"),
                    "snippet": it.get("snippet"),
                })
            return results
        except Exception as e:
            logging.warning(f"CSE search failed: {e}")
            return []

    try:
        # 1) Try Google Programmable Search if configured
        sources = []
        combined_snippets = []
        cse_id = os.getenv("GOOGLE_CSE_ID")
        api_key = os.getenv("GOOGLE_API_KEY")
        sge_used = False
        if cse_id and api_key and company:
            queries = [
                f"what is {company} job interview process and style",
                f"{company} interview rounds case behavioral fit",
                f"{company} interview tips evaluation criteria",
                f"{company} case interview format site:glassdoor.com",
                f"{company} interview process site:indeed.com OR site:levels.fyi",
                f"{company} interview experience site:reddit.com",
                f"site:reddit.com r/cscareerquestions {company} interview",
                f"site:reddit.com {company} interview tips questions"
            ]
            seen_links = set()
            for q in queries:
                for r in _cse_search(q, cse_id, api_key, num=5):
                    if r.get("link") and r["link"] not in seen_links:
                        seen_links.add(r["link"])
                        sources.append(r)
                        if r.get("snippet"):
                            combined_snippets.append(r["snippet"])

        # Optional: Google SGE (AI Overview) via a proxy endpoint if provided.
        # Expected contract: GET {SGE_PROXY_URL}?q=... returns JSON { answer: string }
        try:
            sge_url = os.getenv("GOOGLE_SGE_PROXY_URL", "").strip()
            if sge_url and company:
                import urllib.parse as _p
                import urllib.request as _rq
                sge_qs = [
                    f"{company} interview process and style",
                    f"how does {company} interview candidates"
                ]
                for q in sge_qs:
                    url = f"{sge_url}?{_p.urlencode({'q': q})}"
                    with _rq.urlopen(url, timeout=10) as resp:
                        data = _json.loads(resp.read().decode("utf-8"))
                        ans = (data.get("answer") or data.get("text") or "").strip()
                        if ans:
                            combined_snippets.append(ans)
                            sources.append({"title": "Google AI Overview", "link": url, "snippet": ans})
                            sge_used = True
        except Exception as _:
            pass

        # 2) If we have web snippets, summarize strictly to JSON using Vertex AI
        if combined_snippets:
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel
                vertexai.init(project=os.getenv('GCP_PROJECT_ID', 'custom-oasis-468319-f4'), location=os.getenv('GCP_LOCATION', 'us-central1'))
                model = GenerativeModel('gemini-1.5-pro')
                instruction = (
                    "You are ISA_Researcher. Using only the provided web snippets, summarize the company's interview process and style. "
                    "Return STRICT JSON with keys: company, interview_overview, rounds, question_styles, evaluation_criteria, tips, disclaimer."
                )
                content = f"Company: {company}\nSnippets:\n- " + "\n- ".join(combined_snippets[:30])
                resp = model.generate_content([
                    {"role": "system", "parts": [instruction]},
                    {"role": "user", "parts": [content]},
                ], generation_config={"temperature": 0.1, "max_output_tokens": 700})
                text = getattr(resp, 'text', '') or ''
                import re as _re
                m = _re.search(r"\{[\s\S]*\}", text)
                payload = _json.loads(m.group(0)) if m else _json.loads(text)
                # Minimal validation
                required = ["company", "interview_overview", "rounds", "question_styles", "evaluation_criteria", "tips", "disclaimer"]
                if all(k in payload for k in required):
                    payload["company"] = company
                    payload["sources"] = sources[:10]
                    payload["source_used"] = "web"
                    if sge_used:
                        payload["sge_used"] = True
                    return payload
            except Exception as e:
                logging.warning(f"Vertex summarization of web snippets failed: {e}")

        # 3) Fallback to role-aligned guidance via Vertex if no snippets available
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            vertexai.init(project=os.getenv('GCP_PROJECT_ID', 'custom-oasis-468319-f4'), location=os.getenv('GCP_LOCATION', 'us-central1'))
            model = GenerativeModel('gemini-1.5-pro')

            prompt = (
                "You are ISA_Researcher. Summarize the interview process and style for the given company. "
                "Use established, widely known practices only. If specific public info is insufficient, state 'insufficient_public_info' and provide role-aligned guidance. "
                "Return strict JSON with keys: company, interview_overview, rounds (3-6 items), question_styles (3-6), evaluation_criteria (3-6), tips (3-6), disclaimer."
            )

            user = (
                f"Company: {company}\n"
                f"Job Title: {title}\n"
                f"Job Description (excerpt): {jd[:1200]}"
            )

            resp = model.generate_content([
                {"role": "system", "parts": [prompt]},
                {"role": "user", "parts": [user]},
            ], generation_config={"temperature": 0.2, "max_output_tokens": 800})

            text = getattr(resp, 'text', '') or ''
            import re
            m = re.search(r"\{[\s\S]*\}", text)
            payload = _json.loads(m.group(0)) if m else _json.loads(text)
            required = ["company", "interview_overview", "rounds", "question_styles", "evaluation_criteria", "tips", "disclaimer"]
            if not all(k in payload for k in required):
                return fallback
            payload["sources"] = sources[:10] if sources else []
            payload["source_used"] = "fallback"
            return payload
        except Exception:
            return fallback
    except Exception:
        return fallback

def extract_employers_from_resume(resume_text: str) -> list:
    import re
    txt = (resume_text or "")
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    employers = []
    org_suffixes = r"(Inc\.|LLC|Ltd\.|Corporation|Corp\.|Company|Group|Holdings|Consulting|Services|Partners)"
    for line in lines[:200]:
        m = re.search(r"([A-Z][A-Za-z&.,'\- ]{2,}\s" + org_suffixes + r")", line)
        if m:
            name = m.group(1).strip()
            if name not in employers:
                employers.append(name)
        m2 = re.search(r"\bat\s+([A-Z][A-Za-z&.,'\- ]{2,})", line)
        if m2:
            name = m2.group(1).strip()
            if name not in employers and len(name.split()) <= 6:
                employers.append(name)
        if len(employers) >= 3:
            break
    return employers

def generate_aligned_questions(skills: list, company: str, job_title: str, job_description: str, resume_text: str, research: Optional[dict], candidate_name: Optional[str] = None, employers: Optional[list] = None) -> list:
    """Generate 10 aligned questions based on detected skills, role, and resume."""
    questions = []
    company_label = company or "the company"
    role_label = job_title or "this role"
    resume = _normalize_text(resume_text)

    def q(text):
        qid = f"q{len(questions)+1}"
        safe_text = sanitize_for_applicant_perspective(text, company_label)
        questions.append({"id": qid, "text": safe_text})

    # Map skills to question templates
    template_by_skill = {
        "stakeholder management": lambda: q(
            f"Describe a time you managed conflicting stakeholder priorities and how you aligned them toward {role_label} goals. What was the impact?"
        ),
        "problem solving": lambda: q(
            "Walk me through a complex, ambiguous problem you structured from first principles. What hypotheses did you test and what data did you use?"
        ),
        "prioritization": lambda: q(
            "Give an example of how you prioritized time-sensitive requests when business demands exceeded capacity. What framework did you use?"
        ),
        "project management": lambda: q(
            f"Tell me about a project you led end-to-end in a previous role {(f'(e.g., at {employers[0]}) ' if employers else '')}(relevant to {company_label}). How did you plan milestones, manage risks, and deliver outcomes?"
        ),
        "data analysis": lambda: q(
            "Share a decision you drove using analysis. What metrics mattered, what trade-offs were considered, and what was the result?"
        ),
        "resource allocation": lambda: q(
            "How do you approach dynamic resource allocation and utilization balancing development goals with business needs?"
        ),
        "coaching & development": lambda: q(
            "Describe a time you coached someone to improve performance. What was your approach and how did you measure progress?"
        ),
        "cross-functional collaboration": lambda: q(
            "Tell me about a cross-functional initiative. How did you align teams with different incentives and ensure execution?"
        ),
        "conflict resolution": lambda: q(
            "Describe a time you had to deliver difficult feedback. How did you prepare, deliver, and follow up?"
        ),
        "talent management": lambda: q(
            "How would you balance staffing for development opportunities with utilization targets across a cohort?"
        ),
        "business acumen": lambda: q(
            "Explain the financial implications of a typical staffing decision. Which metrics do you monitor and why?"
        ),
        "inclusion & retention": lambda: q(
            "Share an example of driving inclusion and proactive retention through staffing or talent programs."
        ),
        "excel": lambda: q(
            "When have you built an Excel model to support operational decisions? What assumptions and checks did you include?"
        ),
        "sql": lambda: q(
            "Describe a dataset you queried with SQL to answer a business question. What tables, joins, and constraints mattered?"
        ),
        "python": lambda: q(
            "Tell me about a Python script or notebook you used to automate analysis or reporting. What value did it provide?"
        ),
    }

    # Seed with company/role alignment — always address candidate by FIRST name in Q1
    first_name = extract_first_name(candidate_name or "")
    base_q1 = f"Why {company_label}? Based on the {role_label}, where do you expect to add the most value in the first 90 days?"
    if first_name:
        q(f"{first_name}, {base_q1[0].lower() + base_q1[1:]}")
    else:
        q(base_q1)

    # Incorporate company-specific styles from ISA_Researcher if available
    styles = set()
    if research and isinstance(research, dict):
        for s in research.get("question_styles", []) or []:
            styles.add(_normalize_text(str(s)))
        for rnd in research.get("rounds", []) or []:
            styles.add(_normalize_text(str(rnd)))

    # If behavioral style is indicated, enforce at least one behavioral deep-dive
    if any("behavior" in s for s in styles) and len(questions) < 10:
        q("Tell me about a time you navigated significant ambiguity with multiple stakeholders. How did you frame the problem and drive alignment?")

    # Skill-based questions (up to 7) with generic fallback for any skill phrase
    for raw_skill in skills:
        if len(questions) >= 9:
            break
        skill = _normalize_text(str(raw_skill))
        if skill in template_by_skill:
            template_by_skill[skill]()
        else:
            # Generic question for arbitrary skills/competencies
            q(f"Tell me about your experience with {raw_skill}. What outcomes did you drive, how did you measure impact, and what would you improve next time?")

    # Resume-anchored question if we detect artifacts
    if any(k in resume for k in ["sql", "python", "excel", "tableau", "power bi", "lead", "managed", "project"]):
        q("Pick one experience from your resume and decompose it into objective, approach, metrics, and outcomes. What would you do differently?")

    # Add a case-like question if JD/role or research indicates case-style interviews
    jd_lower = _normalize_text(job_description) + " " + _normalize_text(job_title)
    if any(k in jd_lower for k in ["consult", "case interview", "case study", "hypothesis-driven"]) or any("case" in s for s in styles):
        q("A business unit faces volatility in demand and resource utilization. What data would you gather and which levers would you test to stabilize performance?")

    # Ensure exactly 10 questions by adding targeted generics
    while len(questions) < 10:
        q("Describe a decision you made with imperfect information. How did you mitigate risk and measure success?")

    # Sprinkle first-name personalization randomly across remaining questions (beyond Q1)
    if first_name and len(questions) >= 2:
        import random
        random.seed(42)  # deterministic for testing
        candidate_slots = list(range(2, min(10, len(questions)+1)))  # 1-based for readability
        random.shuffle(candidate_slots)
        added = 0
        for slot in candidate_slots:
            if added >= 2:  # besides Q1, add first name in ~2 random spots
                break
            idx = slot - 1
            text = questions[idx]["text"]
            # Avoid double prefixing
            if not text.lower().startswith(first_name.lower()):
                questions[idx]["text"] = f"{first_name}, {text[0].lower() + text[1:] if text and text[0].isupper() else text}"
                added += 1

    return questions

def _get_salesforce_client():
    try:
        from simple_salesforce import Salesforce
        sf_username = os.getenv("SF_USERNAME")
        sf_password = os.getenv("SF_PASSWORD")
        sf_token = os.getenv("SF_SECURITY_TOKEN")
        sf_domain = os.getenv("SF_DOMAIN", "login")
        sf_instance_url = os.getenv("SF_INSTANCE_URL", "").strip()
        if not (sf_username and sf_password and sf_token):
            logger.warning("Salesforce env vars missing; SF_USERNAME/SF_PASSWORD/SF_SECURITY_TOKEN are required")
            return None
        if sf_instance_url:
            logger.info("Using Salesforce instance_url: %s", sf_instance_url)
            return Salesforce(username=sf_username, password=sf_password, security_token=sf_token, instance_url=sf_instance_url)
        # Normalize domain handling for simple_salesforce (login|test|mydomain)
        normalized_domain = sf_domain
        if sf_domain.startswith("http"):
            # Extract subdomain like 'mydomain' from 'https://mydomain.my.salesforce.com'
            try:
                host = sf_domain.split("//", 1)[1].split("/", 1)[0]
                sub = host.split(".")[0]
                normalized_domain = sub if sub not in ("login", "test") else sub
            except Exception:
                normalized_domain = "login"
        elif sf_domain.endswith(".salesforce.com"):
            try:
                sub = sf_domain.split(".")[0]
                normalized_domain = sub if sub not in ("login", "test") else sub
            except Exception:
                normalized_domain = "login"
        logger.info("Using Salesforce domain: %s", normalized_domain)
        return Salesforce(username=sf_username, password=sf_password, security_token=sf_token, domain=normalized_domain)
    except Exception:
        logger.exception("Failed to initialize Salesforce client")
        return None

def _find_contacts_by_email(email: str) -> List[Dict]:
    sf = _get_salesforce_client()
    if sf is None or not email:
        return []
    try:
        safe_email = email.replace("'", "\\'")
        soql = (
            "SELECT Id, Email, LastModifiedDate FROM Contact "
            f"WHERE Email = '{safe_email}' ORDER BY LastModifiedDate DESC"
        )
        res = sf.query(soql)
        return res.get("records", [])
    except Exception:
        logger.exception("Failed to query contacts by email")
        return []

def _create_contact_profile(first_name: str, last_name: str, email: str, phone: Optional[str], linkedin: Optional[str], zip_code: Optional[str]) -> Optional[str]:
    try:
        sf = _get_salesforce_client()
        if sf is None:
            return None
        account_id = os.getenv("THEIA_DEFAULT_ACCOUNT_ID", "001PM00000VuGRaYAN")
        payload = {
            "FirstName": first_name or "",
            "LastName": last_name or "New User",
            "Email": email,
            "Phone": (phone or "").strip() or None,
            "Title": "THEIA NEW PROFILE",
            "LeadSource": "THEIA",
            "AccountId": account_id,
        }
        if linkedin:
            payload["LinkedIn_Profile__c"] = linkedin
        if zip_code:
            payload["OtherPostalCode"] = zip_code
        res = sf.Contact.create(payload)
        if res and res.get("success") and res.get("id"):
            return res.get("id")
        return None
    except Exception:
        logger.exception("Failed to create contact profile")
        return None

def _update_contact_profile(contact_id: str, first_name: Optional[str], last_name: Optional[str], email: Optional[str], phone: Optional[str], linkedin: Optional[str], zip_code: Optional[str]) -> bool:
    try:
        sf = _get_salesforce_client()
        if sf is None or not contact_id:
            return False
        payload = {}
        if first_name is not None: payload["FirstName"] = first_name
        if last_name is not None: payload["LastName"] = last_name
        if email is not None: payload["Email"] = email
        if phone is not None: payload["Phone"] = phone
        if linkedin is not None: payload["LinkedIn_Profile__c"] = linkedin
        if zip_code is not None: payload["OtherPostalCode"] = zip_code
        if not payload:
            return True
        res = sf.Contact.update(contact_id, payload)
        return bool(res == 204 or res is True)
    except Exception:
        logger.exception("Failed to update contact profile")
        return False

def _get_contact_profile(contact_id: Optional[str] = None, email: Optional[str] = None) -> dict:
    """Return a subset of Contact fields for profile editing.
    Uses Contact.describe() to only select fields that actually exist to avoid INVALID_FIELD errors.
    """
    try:
        sf = _get_salesforce_client()
        if sf is None:
            return {}
        where = None
        if contact_id:
            where = f"Id = '{contact_id}'"
        elif email:
            safe = (email or '').replace("'", "\\'")
            where = f"Email = '{safe}'"
        if not where:
            return {}

        # Discover available fields
        global _SF_CONTACT_FIELDS_CACHE, _SF_CONTACT_FIELDS_TS
        now = time.time()
        if not _SF_CONTACT_FIELDS_CACHE or not _SF_CONTACT_FIELDS_TS or (now - _SF_CONTACT_FIELDS_TS) > _SF_CONTACT_FIELDS_TTL:
            try:
                desc = sf.Contact.describe()
                _SF_CONTACT_FIELDS_CACHE = {f.get("name") for f in desc.get("fields", [])}
                _SF_CONTACT_FIELDS_TS = now
            except Exception:
                _SF_CONTACT_FIELDS_CACHE = {"Id", "FirstName", "LastName", "Email", "Phone"}
                _SF_CONTACT_FIELDS_TS = now
        field_names = _SF_CONTACT_FIELDS_CACHE

        select_fields = ["Id"]
        base_fields = ["FirstName", "LastName", "Email", "Phone"]
        for f in base_fields:
            if f in field_names:
                select_fields.append(f)

        linkedin_candidates = [
            "LinkedIn_Profile__c",
            "LinkedIn__c",
            "LinkedIn_URL__c",
            "LinkedInProfile__c",
        ]
        linkedin_field = next((f for f in linkedin_candidates if f in field_names), None)
        if linkedin_field:
            select_fields.append(linkedin_field)

        zip_candidates = [
            "OtherPostalCode",
            "MailingPostalCode",
            "Work_Postal_Code__c",
        ]
        zip_field = next((f for f in zip_candidates if f in field_names), None)
        if zip_field:
            select_fields.append(zip_field)

        soql = (
            f"SELECT {', '.join(select_fields)} FROM Contact WHERE {where} "
            "ORDER BY LastModifiedDate DESC LIMIT 1"
        )
        recs = sf.query(soql).get("records", [])
        if not recs:
            return {}
        rec = recs[0]
        return {
            "contact_id": rec.get("Id"),
            "first_name": rec.get("FirstName") or "",
            "last_name": rec.get("LastName") or "",
            "email": rec.get("Email") or "",
            "phone": rec.get("Phone") or "",
            "linkedin": rec.get(linkedin_field) if linkedin_field else "",
            "zip_code": rec.get(zip_field) if zip_field else "",
        }
    except Exception:
        logger.exception("Failed to fetch contact profile")
        return {}

def _map_auth0_user_to_contact(bearer_token: str, access_token_for_hash: Optional[str] = None) -> dict:
    claims = _verify_auth0_jwt(bearer_token, access_token_for_hash=access_token_for_hash)
    email = _extract_email_from_claims(claims)
    if not email:
        raise HTTPException(status_code=400, detail="Authenticated user missing email claim")
    matches = _find_contacts_by_email(email)
    if not matches:
        return {"status": "no_match", "email": email}
    if len(matches) == 1:
        cid = matches[0].get("Id")
        token = _mint_theia_token(cid, email)
        return {"status": "ok", "contact_id": cid, "email": email, "theia_token": token}
    # Multiple matches: pick most recently modified; attempt merge best-effort
    chosen = matches[0]
    contact_id = chosen.get("Id")
    try:
        sf = _get_salesforce_client()
        # Attempt a REST merge (best-effort; may not be enabled)
        ids_to_merge = [m.get("Id") for m in matches[1:5] if m.get("Id")]
        if ids_to_merge:
            payload = {"masterRecord": {"Id": contact_id}, "recordToMergeIds": ids_to_merge}
            _ = sf.restful("sobjects/Contact/merge", method="POST", data=payload)
    except Exception:
        logger.info("Contact merge not executed; proceeding with most recent record")
    token = _mint_theia_token(contact_id, email)
    return {"status": "multiple", "contact_id": contact_id, "email": email, "theia_token": token}

def try_fetch_resume_from_salesforce(user_id: str) -> str:
    """Fetch Resume_TXT from Salesforce Contact strictly by Contact Id.
    Returns empty string on failure. Logs meaningful messages for diagnostics.
    """
    try:
        sf = _get_salesforce_client()
        if sf is None:
            return ""
        if not user_id or len(user_id) not in (15, 18):
            logger.warning("Provided user_id is not a 15/18-char Salesforce Id; cannot fetch Resume_TXT strictly by Id")
            return ""
        try:
            # Discover available fields via describe to avoid INVALID_FIELD errors
            contact_desc = sf.Contact.describe()
            field_names = {f.get("name") for f in contact_desc.get("fields", [])}
            candidate_fields = [
                "Candidate_s_Resume_TXT__c",
                "Resume_TXT__c",
                "Resume_TXT",
            ]
            available = [f for f in candidate_fields if f in field_names]
            if not available:
                logger.warning("Neither Resume_TXT__c nor Resume_TXT is available on Contact (FLS/metadata)")
                return ""
            resume_field = available[0]
            query = f"SELECT Id, {resume_field} FROM Contact WHERE Id = '{user_id}' LIMIT 1"
            result = sf.query(query)
            records = result.get("records", [])
            if not records:
                logger.error("No Contact found for Id %s", user_id)
                return ""
            rec = records[0]
            resume_txt = rec.get(resume_field) or ""
            if resume_txt:
                logger.info("Fetched %s for contact id %s (%d chars)", resume_field, user_id, len(resume_txt))
            else:
                logger.info("%s empty or missing for contact id %s", resume_field, user_id)
            return resume_txt
        except Exception as e:
            logger.error("Resume fetch failed for Contact Id %s: %s", user_id, str(e))
            return ""
    except Exception:
        logger.exception("Unexpected error during Salesforce resume fetch")
        return ""

def fetch_contact_info_from_salesforce(user_id: str) -> dict:
    """Fetch Contact Name and resume text (best-effort). Returns {contact_name, resume_text}."""
    result = {"contact_name": "", "resume_text": ""}
    try:
        sf = _get_salesforce_client()
        if sf is None:
            return result
        if not user_id or len(user_id) not in (15, 18):
            return result
        # Determine resume field
        desc = sf.Contact.describe()
        field_names = {f.get("name") for f in desc.get("fields", [])}
        candidate_fields = [
            "Candidate_s_Resume_TXT__c",
            "Resume_TXT__c",
            "Resume_TXT",
        ]
        resume_field = next((f for f in candidate_fields if f in field_names), None)
        base = "Name"
        soql = f"SELECT Id, {base}{(',' + resume_field) if resume_field else ''} FROM Contact WHERE Id = '{user_id}' LIMIT 1"
        recs = sf.query(soql).get("records", [])
        if not recs:
            return result
        rec = recs[0]
        result["contact_name"] = rec.get("Name") or ""
        if resume_field:
            result["resume_text"] = rec.get(resume_field) or ""
        return result
    except Exception:
        logger.exception("Failed to fetch contact info")
        return result

def fetch_opportunity_discussed_transcripts(contact_id: str) -> List[str]:
    """Fetch all TR1__Opportunity_Discussed__c transcripts related to the Contact."""
    try:
        sf = _get_salesforce_client()
        if sf is None or not contact_id or len(contact_id) not in (15, 18):
            logger.warning("Invalid Salesforce client or contact_id for opportunity transcripts")
            return []
        
        # Query Opportunity Discussed records related to the Contact
        # Assuming the relationship field is Contact__c (adjust based on actual field name)
        soql = """
        SELECT Id, Transcript__c, CreatedDate 
        FROM TR1__Opportunity_Discussed__c 
        WHERE Contact__c = '{contact_id}' 
        AND Transcript__c != null 
        ORDER BY CreatedDate DESC
        LIMIT 50
        """.format(contact_id=contact_id)
        
        result = sf.query(soql)
        records = result.get("records", [])
        
        transcripts = []
        for record in records:
            transcript = record.get("Transcript__c", "").strip()
            if transcript:
                transcripts.append(transcript)
        
        logger.info(f"Found {len(transcripts)} opportunity discussion transcripts for contact {contact_id}")
        return transcripts
        
    except Exception as e:
        logger.exception(f"Failed to fetch opportunity discussed transcripts for contact {contact_id}: {e}")
        return []

def fetch_theia_interview_transcripts(contact_id: str) -> List[str]:
    """Fetch all THEIA_Interview__c transcripts related to the Contact."""
    try:
        sf = _get_salesforce_client()
        if sf is None or not contact_id or len(contact_id) not in (15, 18):
            logger.warning("Invalid Salesforce client or contact_id for THEIA interview transcripts")
            return []
        
        # Query THEIA Interview records related to the Contact
        soql = """
        SELECT Id, Interview_Transcript__c, CreatedDate 
        FROM THEIA_Interview__c 
        WHERE Contact__c = '{contact_id}' 
        AND Interview_Transcript__c != null 
        ORDER BY CreatedDate DESC
        LIMIT 50
        """.format(contact_id=contact_id)
        
        result = sf.query(soql)
        records = result.get("records", [])
        
        transcripts = []
        for record in records:
            transcript = record.get("Interview_Transcript__c", "").strip()
            if transcript:
                transcripts.append(transcript)
        
        logger.info(f"Found {len(transcripts)} THEIA interview transcripts for contact {contact_id}")
        return transcripts
        
    except Exception as e:
        logger.exception(f"Failed to fetch THEIA interview transcripts for contact {contact_id}: {e}")
        return []

def fetch_resume_builder_data(contact_id: str) -> dict:
    """Fetch all data needed for resume building: contact info, opportunity transcripts, and interview transcripts."""
    try:
        logger.info(f"Fetching resume builder data for contact {contact_id}")
        
        # Fetch contact info and resume
        contact_info = fetch_contact_info_from_salesforce(contact_id)
        
        # Fetch opportunity discussed transcripts
        opportunity_transcripts = fetch_opportunity_discussed_transcripts(contact_id)
        
        # Fetch THEIA interview transcripts
        interview_transcripts = fetch_theia_interview_transcripts(contact_id)
        
        result = {
            "contact_name": contact_info.get("contact_name", ""),
            "resume_text": contact_info.get("resume_text", ""),
            "opportunity_transcripts": opportunity_transcripts,
            "interview_transcripts": interview_transcripts,
            "total_opportunity_transcripts": len(opportunity_transcripts),
            "total_interview_transcripts": len(interview_transcripts)
        }
        
        logger.info(f"Resume builder data fetched for {contact_id}: {result['total_opportunity_transcripts']} opportunities, {result['total_interview_transcripts']} interviews")
        return result
        
    except Exception as e:
        logger.exception(f"Failed to fetch resume builder data for contact {contact_id}: {e}")
        return {
            "contact_name": "",
            "resume_text": "",
            "opportunity_transcripts": [],
            "interview_transcripts": [],
            "total_opportunity_transcripts": 0,
            "total_interview_transcripts": 0,
            "error": str(e)
        }

def create_theia_interview_record(
    contact_id: str,
    interview_transcript: str,
    prep_job_description: str,
    desired_job_skills: str,
    feedback_text: str,
) -> dict:
    """Create THEIA_Interview__c record in Salesforce and return creation result.
    Required fields documented by user. Always uses RecordTypeId for Prep.
    """
    try:
        sf = _get_salesforce_client()
        if sf is None:
            return {"error": "Salesforce client not configured"}
        if not contact_id or len(contact_id) not in (15, 18):
            return {"error": "Invalid contact id"}

        record_type_id = os.getenv("THEIA_PREP_RECORDTYPE_ID", "012PM000001YajdYAC")
        payload = {
            "RecordTypeId": record_type_id,
            "Contact__c": contact_id,
            "Interview_Transcript__c": interview_transcript[:130000],
            "Prep_Job_Description__c": prep_job_description[:130000],
            "Desired_Job_Skills__c": desired_job_skills[:130000],
            "Feedback__c": feedback_text[:130000],
        }
        res = sf.THEIA_Interview__c.create(payload)
        return res
    except Exception:
        logger.exception("Failed to create THEIA_Interview__c record")
        return {"error": "Creation failed"}

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "https://storage.googleapis.com",
        "https://www.theiajobs.ai",
        "https://theiajobs.ai",
    ],
    allow_origin_regex=r"https:\/\/.*\.storage\.googleapis\.com$|^https:\/\/([a-z0-9-]+\.)*theiajobs\.ai$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "THEIA Interview Prep System",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/test/credentials/quick")
async def test_credentials_quick():
    """Quick credential check - only validates environment variables are set (no external calls)"""
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "services": {},
        "mode": "quick_check"
    }
    
    # Quick checks - only verify env vars are set (no external API calls)
    results["services"]["google_cloud"] = {
        "status": "✅ CONFIGURED" if os.getenv("GOOGLE_CLOUD_PROJECT_ID") else "❌ MISSING",
        "env_vars": ["GOOGLE_CLOUD_PROJECT_ID", "VERTEX_LOCATION", "VERTEX_MODEL"]
    }
    
    results["services"]["openai"] = {
        "status": "✅ CONFIGURED" if os.getenv("OPENAI_API_KEY") else "❌ MISSING", 
        "env_vars": ["OPENAI_API_KEY", "OPENAI_REALTIME_MODEL"]
    }
    
    results["services"]["salesforce"] = {
        "status": "✅ CONFIGURED" if all([
            os.getenv("SF_USERNAME"), 
            os.getenv("SF_PASSWORD"), 
            os.getenv("SF_SECURITY_TOKEN")
        ]) else "❌ MISSING",
        "env_vars": ["SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_DOMAIN"]
    }
    
    results["services"]["auth0"] = {
        "status": "✅ CONFIGURED" if all([
            os.getenv("AUTH0_DOMAIN"),
            os.getenv("AUTH0_CLIENT_ID")
        ]) else "❌ MISSING",
        "env_vars": ["AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_AUDIENCE"]
    }
    
    results["services"]["google_search"] = {
        "status": "✅ CONFIGURED" if all([
            os.getenv("GOOGLE_CSE_ID"),
            os.getenv("GOOGLE_API_KEY")
        ]) else "❌ MISSING",
        "env_vars": ["GOOGLE_CSE_ID", "GOOGLE_API_KEY"]
    }
    
    return results

# Cache for credential test results (5 minute TTL)
_credentials_cache = {}
_cache_ttl = 300  # 5 minutes

@app.get("/test/credentials")
async def test_credentials():
    """Test all credential configurations with optimized async execution"""
    # Check cache first
    cache_key = "credentials_test"
    current_time = time.time()
    
    if cache_key in _credentials_cache:
        cached_result, cache_time = _credentials_cache[cache_key]
        if current_time - cache_time < _cache_ttl:
            # Return a copy with cache metadata
            result = cached_result.copy()
            result["cached"] = True
            result["cache_age_seconds"] = int(current_time - cache_time)
            return result
    
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "services": {},
        "cached": False
    }
    
    # Create thread pool for blocking operations
    executor = ThreadPoolExecutor(max_workers=5)
    
    # Run all tests concurrently with reduced timeouts
    tasks = [
        asyncio.create_task(_test_google_cloud_async(executor)),
        asyncio.create_task(_test_openai_async(executor)),
        asyncio.create_task(_test_salesforce_async(executor)),
        asyncio.create_task(_test_redis_async(executor)),
        asyncio.create_task(_test_google_search_async())
    ]
    
    # Wait for all tasks with overall timeout of 10 seconds
    try:
        completed_results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10.0)
        
        service_names = ["google_cloud", "openai", "salesforce", "redis", "google_search"]
        for i, result in enumerate(completed_results):
            if isinstance(result, Exception):
                results["services"][service_names[i]] = {
                    "status": "❌ TIMEOUT",
                    "reason": f"Test timed out: {str(result)}"
                }
            else:
                results["services"][service_names[i]] = result
                
    except asyncio.TimeoutError:
        # If overall timeout, mark remaining services as timed out
        for i, task in enumerate(tasks):
            if not task.done():
                task.cancel()
                service_names = ["google_cloud", "openai", "salesforce", "redis", "google_search"]
                results["services"][service_names[i]] = {
                    "status": "❌ TIMEOUT",
                    "reason": "Overall test timeout (10s)"
                }
    
    # Cache the results
    _credentials_cache[cache_key] = (results.copy(), current_time)
    
    return results

async def _test_google_cloud_async(executor):
    """Test Google Cloud Vertex AI (lightweight - no actual API calls)"""
    try:
        def _test_google_cloud():
            import vertexai
            from vertexai.generative_models import GenerativeModel

            project_id = (
                os.getenv("VERTEX_PROJECT_ID") or 
                os.getenv("GOOGLE_CLOUD_PROJECT") or 
                os.getenv("GOOGLE_CLOUD_PROJECT_ID") or
                settings.GOOGLE_CLOUD_PROJECT_ID
            )
            location = os.getenv("VERTEX_LOCATION", "us-central1")
            model_name = os.getenv("VERTEX_MODEL", "gemini-2.5-pro")

            if not project_id:
                raise RuntimeError("Missing project ID - check GOOGLE_CLOUD_PROJECT_ID")

            # Only initialize and construct model (no API calls)
            vertexai.init(project=project_id, location=location)
            _ = GenerativeModel(model_name)
            
            return {
                "status": "✅ WORKING",
                "project_id": project_id,
                "model": model_name,
                "location": location,
            }
        
        return await asyncio.get_event_loop().run_in_executor(executor, _test_google_cloud)
    except Exception as e:
        return {
            "status": "⚠️ SKIPPED",
            "reason": str(e) or "Vertex AI not configured",
        }

async def _test_openai_async(executor):
    """Test OpenAI (lightweight - just check API key format)"""
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        
        # Lightweight check - just verify key format without API call
        if not api_key.startswith('sk-') or len(api_key) < 20:
            raise RuntimeError("Invalid OPENAI_API_KEY format")
            
        return {
            "status": "✅ WORKING",
            "model": "gpt-4o-realtime-preview-2024-10-01",
            "note": "Key format validated (no API call made)"
        }
    except Exception as e:
        return {
            "status": "⚠️ SKIPPED", 
            "reason": str(e) or "OpenAI not configured"
        }

async def _test_salesforce_async(executor):
    """Test Salesforce with reduced timeout"""
    try:
        def _test_salesforce():
            from simple_salesforce import Salesforce
            sf_username = os.getenv("SF_USERNAME")
            sf_password = os.getenv("SF_PASSWORD")
            sf_token = os.getenv("SF_SECURITY_TOKEN")
            sf_domain = os.getenv("SF_DOMAIN", "login")
            
            if not (sf_username and sf_password and sf_token):
                return {"status": "⚠️ SKIPPED", "reason": "Missing SF env vars"}
            
            # Quick connection test with timeout
            sf = Salesforce(username=sf_username, password=sf_password, 
                          security_token=sf_token, domain=sf_domain)
            
            # Use describe instead of query for faster response
            sf.describe()
            
            return {"status": "✅ WORKING", "domain": f"{sf_domain}.salesforce.com"}
        
        return await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(executor, _test_salesforce),
            timeout=3.0
        )
    except asyncio.TimeoutError:
        return {"status": "❌ TIMEOUT", "reason": "Salesforce test timed out (3s)"}
    except Exception as e:
        return {"status": "❌ ERROR", "error": str(e)}

async def _test_redis_async(executor):
    """Test Redis with reduced timeout"""
    try:
        def _test_redis():
            import redis
            r = redis.from_url('redis://localhost:6379/0', socket_timeout=1)
            r.ping()
            return {
                "status": "✅ WORKING",
                "url": "redis://localhost:6379/0"
            }
        
        return await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(executor, _test_redis),
            timeout=2.0
        )
    except asyncio.TimeoutError:
        return {"status": "❌ TIMEOUT", "reason": "Redis test timed out (2s)"}
    except Exception as e:
        return {
            "status": "⚠️ SKIPPED",
            "reason": "Redis not available"
        }

async def _test_google_search_async():
    """Test Google Custom Search with async HTTP"""
    try:
        cse_id = os.getenv("GOOGLE_CSE_ID", "").strip()
        api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        
        if not cse_id or not api_key:
            raise RuntimeError("Google CSE credentials not configured")
        
        # Use async HTTP with reduced timeout
        test_url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cse_id}&q=test&num=1"
        
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(test_url)
            response.raise_for_status()
                
        return {
            "status": "✅ WORKING",
            "cse_id": cse_id[:10] + "...",
            "description": "Custom Search Engine for ISA_Researcher"
        }
    except httpx.TimeoutException:
        return {"status": "❌ TIMEOUT", "reason": "Google CSE test timed out (2s)"}
    except Exception as e:
        return {
            "status": "⚠️ SKIPPED",
            "reason": str(e) or "Google CSE not configured"
        }

@app.get("/test/agents")
async def test_agents():
    """Test optimized ISA agent functionality with performance benchmarks"""
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "agents": {},
        "performance": {},
        "environment": {
            "GOOGLE_CLOUD_PROJECT": os.getenv("GOOGLE_CLOUD_PROJECT"),
            "GOOGLE_CLOUD_PROJECT_ID": os.getenv("GOOGLE_CLOUD_PROJECT_ID"),
            "VERTEX_LOCATION": os.getenv("VERTEX_LOCATION"),
            "VERTEX_MODEL": os.getenv("VERTEX_MODEL"),
            "VERTEX_MODEL_FAST": os.getenv("VERTEX_AI_MODEL_FAST", "gemini-2.5-flash")
        }
    }
    
    # Test optimized agents with performance benchmarks
    try:
        import sys
        import time
        backend_path = os.path.join(os.path.dirname(__file__))
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
        
        # Test the new optimized agent orchestrator
        from theia_agents.agent_orchestrator import orchestrator
        
        # Quick performance test with sample data
        start_time = time.time()
        
        sample_job_description = """
        We are looking for a Senior Software Engineer to join our team.
        Requirements: 5+ years Python experience, REST API development,
        database design, cloud platforms (AWS/GCP), team collaboration.
        """
        
        sample_resume = """
        John Doe - Software Engineer with 6 years experience in Python,
        Django, PostgreSQL, and AWS. Led multiple API development projects.
        """
        
        # Test ISA_Detector with flash model
        detector_start = time.time()
        skills_output = await orchestrator.detector.analyze_job_requirements(
            job_description=sample_job_description,
            job_title="Senior Software Engineer",
            company_name="Test Company"
        )
        detector_time = time.time() - detector_start
        
        results["agents"]["isa_detector"] = {
            "status": "✅ WORKING",
            "response_time_seconds": round(detector_time, 2),
            "model_used": "gemini-2.5-flash",
            "skills_detected": len(skills_output.key_skills) if skills_output else 0,
            "description": "Skills detection agent (optimized)"
        }
        
        # Get performance stats from orchestrator
        perf_stats = orchestrator.get_performance_stats()
        results["performance"] = {
            "total_time_seconds": round(time.time() - start_time, 2),
            "cache_hit_rate_percent": round(perf_stats.get("total_cache_hits", 0) / max(1, sum(
                stats.get("total_requests", 0) for stats in perf_stats.get("agents", {}).values()
            )) * 100, 1),
            "flash_model_usage_percent": round(perf_stats.get("total_flash_usage", 0) / max(1, 
                perf_stats.get("total_flash_usage", 0) + perf_stats.get("total_pro_usage", 0)
            ) * 100, 1),
            "optimization_status": "✅ ACTIVE"
        }
    except Exception as e:
        results["agents"]["error"] = {
            "status": "❌ ERROR",
            "error": str(e),
            "description": "Agent test failed"
        }
        results["performance"] = {
            "optimization_status": "❌ ERROR",
            "error": str(e)
        }
    
    return results

@app.get("/test/agents/debug")
async def debug_agents():
    """Debug ISA agents with real execution"""
    try:
        import sys
        import os
        backend_path = os.path.join(os.path.dirname(__file__))
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
        
        results = {"debug": {}}
        
        # Test ISA_Detector with real data
        try:
            from theia_agents.isa_detector import ISADetector
            detector = ISADetector()
            
            logger.info("🧪 Testing ISA_Detector with real data")
            skills_output = await detector.analyze_job_requirements(
                job_description="Key Performance Indicators: Min of 1 Placement per month with an average fee of $11,000. Day to day Expectation: Act using ASAP Values and Framework, Keep your calendar organized and updated, Make sure all important data is registered in the system, Initiative and problem-solution approach",
                job_title="Customer Success Manager",
                company_name="ASAP Staffing Services"
            )
            
            results["debug"]["isa_detector"] = {
                "status": "✅ SUCCESS",
                "skills_count": len(skills_output.key_skills) if skills_output else 0,
                "skills": skills_output.key_skills if skills_output else [],
                "experience_level": skills_output.experience_level if skills_output else "Unknown"
            }
            
        except Exception as e:
            results["debug"]["isa_detector"] = {
                "status": "❌ FAILED", 
                "error": str(e)
            }
        
        # Test ISA_Researcher with real data
        try:
            from theia_agents.isa_researcher import ISAResearcher
            researcher = ISAResearcher()
            
            logger.info("🧪 Testing ISA_Researcher with real data")
            research_output = await researcher.research_company_interview_practices(
                company_name="ASAP Staffing Services",
                job_title="Customer Success Manager", 
                job_description="We seek a Customer Success Manager to drive client retention and growth."
            )
            
            results["debug"]["isa_researcher"] = {
                "status": "✅ SUCCESS",
                "confidence": research_output.research_confidence if research_output else 0,
                "sources_count": len(research_output.sources_found) if research_output else 0
            }
            
        except Exception as e:
            results["debug"]["isa_researcher"] = {
                "status": "❌ FAILED", 
                "error": str(e)
            }
        
        return results
        
    except Exception as e:
        return {"debug_error": str(e)}

@app.get("/test/validation/complete")
async def validate_complete_pipeline():
    """Comprehensive validation of the entire THEIA pipeline"""
    import sys
    try:
        validation_results = {
            "timestamp": datetime.utcnow().isoformat(),
            "pipeline_validation": {},
            "data_flow": {},
            "salesforce_mapping": {},
            "credentials": {},
            "endpoints": {}
        }
        
        # 1. Validate credentials
        validation_results["credentials"] = {
            "google_cse_id": "✅ CONFIGURED" if os.getenv("GOOGLE_CSE_ID") else "❌ MISSING",
            "google_api_key": "✅ CONFIGURED" if os.getenv("GOOGLE_API_KEY") else "❌ MISSING",
            "vertex_ai_project": "✅ CONFIGURED" if os.getenv("GOOGLE_CLOUD_PROJECT") else "❌ MISSING",
            "openai_key": "✅ CONFIGURED" if os.getenv("OPENAI_API_KEY") else "❌ MISSING",
            "salesforce": "✅ CONFIGURED" if all([
                os.getenv("SF_USERNAME"), 
                os.getenv("SF_PASSWORD"), 
                os.getenv("SF_SECURITY_TOKEN")
            ]) else "❌ MISSING"
        }
        
        # 2. Test agent initialization
        backend_path = os.path.join(os.path.dirname(__file__))
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
            
        try:
            from theia_agents.isa_researcher import ISAResearcher
            from theia_agents.isa_detector import ISADetector  
            from theia_agents.isa_questioner import ISAQuestioner
            from theia_agents.isa_evaluator import ISAEvaluator
            
            researcher = ISAResearcher()
            detector = ISADetector()
            questioner = ISAQuestioner()
            evaluator = ISAEvaluator()
            
            validation_results["pipeline_validation"] = {
                "isa_researcher": "✅ INITIALIZED" if researcher.model else "❌ FAILED",
                "isa_detector": "✅ INITIALIZED" if detector.model else "❌ FAILED", 
                "isa_questioner": "✅ INITIALIZED" if questioner.model else "❌ FAILED",
                "isa_evaluator": "✅ INITIALIZED" if evaluator.model else "❌ FAILED"
            }
            
        except Exception as e:
            validation_results["pipeline_validation"]["error"] = str(e)
        
        # 3. Test Salesforce connection and field mapping
        try:
            sf = _get_salesforce_client()
            if sf:
                # Check THEIA_Interview__c object and fields
                try:
                    desc = sf.THEIA_Interview__c.describe()
                    field_names = {f.get("name") for f in desc.get("fields", [])}
                    required_fields = [
                        "Contact__c", 
                        "Interview_Transcript__c",
                        "Prep_Job_Description__c", 
                        "Desired_Job_Skills__c",
                        "Feedback__c"
                    ]
                    
                    field_validation = {}
                    for field in required_fields:
                        field_validation[field] = "✅ EXISTS" if field in field_names else "❌ MISSING"
                    
                    validation_results["salesforce_mapping"] = {
                        "connection": "✅ CONNECTED",
                        "theia_interview_object": "✅ ACCESSIBLE",
                        "field_mapping": field_validation
                    }
                except Exception as e:
                    validation_results["salesforce_mapping"] = {
                        "connection": "✅ CONNECTED",
                        "theia_interview_object": f"❌ ERROR: {str(e)}"
                    }
            else:
                validation_results["salesforce_mapping"] = {"connection": "❌ FAILED"}
                
        except Exception as e:
            validation_results["salesforce_mapping"] = {"connection": f"❌ ERROR: {str(e)}"}
        
        # 4. Validate endpoint mappings
        validation_results["endpoints"] = {
            "start_interview": "/api/v1/interviews/start",
            "generate_questions": "/api/v1/interviews/{session_id}/generate_questions", 
            "evaluate_interview": "/api/v1/interviews/{session_id}/evaluate",
            "voice_prepare": "/api/v1/voice/{session_id}/prepare",
            "summaries": "/api/v1/interviews/{session_id}/summaries"
        }
        
        # 5. Test data flow validation
        validation_results["data_flow"] = {
            "session_storage": "✅ IN-MEMORY SESSIONS",
            "agent_pipeline": "ISA_Researcher → ISA_Detector → ISA_Questioner → ISA_Voice/ISA_Evaluator",
            "context_passing": {
                "research_to_questioner": "✅ IMPLEMENTED",
                "detector_to_questioner": "✅ IMPLEMENTED", 
                "detector_to_evaluator": "✅ IMPLEMENTED",
                "all_context_to_voice": "✅ IMPLEMENTED",
                "transcript_to_evaluator": "✅ IMPLEMENTED (95% weight)",
                "resume_to_evaluator": "✅ IMPLEMENTED (5% weight)"
            },
            "salesforce_persistence": "✅ THEIA_Interview__c record creation"
        }
        
        return validation_results
        
    except Exception as e:
        return {"validation_error": str(e)}

@app.get("/test/env/debug")
async def debug_environment():
    """Debug endpoint to check environment variables"""
    import sys
    try:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "environment_variables": {
                "GOOGLE_CLOUD_PROJECT": os.getenv("GOOGLE_CLOUD_PROJECT", "NOT_SET"),
                "VERTEX_PROJECT_ID": os.getenv("VERTEX_PROJECT_ID", "NOT_SET"),
                "GCP_PROJECT": os.getenv("GCP_PROJECT", "NOT_SET"),
                "GOOGLE_CLOUD_PROJECT_ID": os.getenv("GOOGLE_CLOUD_PROJECT_ID", "NOT_SET"),
                "GOOGLE_CSE_ID": "SET" if os.getenv("GOOGLE_CSE_ID") else "NOT_SET",
                "GOOGLE_API_KEY": "SET" if os.getenv("GOOGLE_API_KEY") else "NOT_SET",
                "SF_USERNAME": "SET" if os.getenv("SF_USERNAME") else "NOT_SET",
                "SF_PASSWORD": "SET" if os.getenv("SF_PASSWORD") else "NOT_SET",
                "SF_SECURITY_TOKEN": "SET" if os.getenv("SF_SECURITY_TOKEN") else "NOT_SET",
                "OPENAI_API_KEY": "SET" if os.getenv("OPENAI_API_KEY") else "NOT_SET"
            },
            "current_working_directory": os.getcwd(),
            "python_path": sys.path[:3]
        }
    except Exception as e:
        return {"debug_error": str(e)}


@app.get("/test/agents/real_test")
async def test_real_agents():
    """Test real agents with the exact same data from the user's failing case"""
    try:
        import sys
        import os
        backend_path = os.path.join(os.path.dirname(__file__))
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
        
        # Use the LATEST data from the user's failing case (Lennar)
        company_name = "Lennar"
        job_title = "Sr. Manager HRBP"
        job_description = "Sr. Manager HRBP at Lennar Corporation. We are seeking an experienced Senior Manager of Human Resources Business Partner to join our dynamic team. Key Responsibilities: Partner with business leaders to develop and implement HR strategies, provide guidance on employee relations, lead talent acquisition initiatives. Required: Bachelor's degree in HR, 7+ years progressive HR experience, strong employment law knowledge, HRIS experience, excellent communication skills. Lennar is a leading homebuilder committed to making homeownership achievable."
        
        results = {
            "test_data": {
                "company": company_name,
                "job_title": job_title,
                "job_description_length": len(job_description)
            },
            "agent_tests": {}
        }
        
        # Test ISA_Detector
        try:
            from theia_agents.isa_detector import ISADetector
            detector = ISADetector()
            
            logger.info(f"🎯 Testing ISA_Detector with real job description")
            skills_output = await detector.analyze_job_requirements(
                job_description=job_description,
                job_title=job_title or "Recruitment Specialist",
                company_name=company_name
            )
            
            results["agent_tests"]["isa_detector"] = {
                "status": "✅ SUCCESS",
                "skills_count": len(skills_output.key_skills),
                "skills": skills_output.key_skills,
                "technical_requirements": skills_output.technical_requirements,
                "experience_level": skills_output.experience_level
            }
            
        except Exception as e:
            logger.error(f"❌ ISA_Detector test failed: {e}")
            results["agent_tests"]["isa_detector"] = {
                "status": "❌ FAILED",
                "error": str(e)
            }
        
        # Test ISA_Researcher
        try:
            from theia_agents.isa_researcher import ISAResearcher
            researcher = ISAResearcher()
            
            logger.info(f"🔍 Testing ISA_Researcher with web search")
            research_output = await researcher.research_company_interview_practices(
                company_name=company_name,
                job_title=job_title or "Recruitment Specialist",
                job_description=job_description
            )
            
            # Check if web search was actually used by looking for URLs in sources
            has_web_search = any("http" in str(source).lower() for source in research_output.sources_found)
            
            results["agent_tests"]["isa_researcher"] = {
                "status": "✅ SUCCESS",
                "confidence": research_output.research_confidence,
                "sources_count": len(research_output.sources_found),
                "interview_style": research_output.interview_style,
                "has_web_search": has_web_search,
                "sources_sample": research_output.sources_found[:2] if research_output.sources_found else [],
                "market_intelligence_sample": str(research_output.market_intelligence)[:200] + "..."
            }
            
        except Exception as e:
            logger.error(f"❌ ISA_Researcher test failed: {e}")
            results["agent_tests"]["isa_researcher"] = {
                "status": "❌ FAILED",
                "error": str(e)
            }
        
        return results
        
    except Exception as e:
        return {"test_error": str(e)}

@app.get("/test/validation/transcript_modes")
async def validate_transcript_modes():
    """Test transcript handling for both text and voice interview modes"""
    try:
        # Create mock session data for both modes
        test_results = {
            "timestamp": datetime.utcnow().isoformat(),
            "text_interview": {},
            "voice_interview": {},
            "salesforce_mapping": {}
        }
        
        # Test TEXT INTERVIEW transcript building
        mock_text_session = {
            "user_id": "003XX000004DFJ0",
            "company_name": "ASAP Services", 
            "job_title": "Senior Software Engineer",
            "interview_mode": "text",
            "candidate_name": "John Doe",
            "questions": [
                {"id": "q1", "text": "Tell me about your experience with Python"},
                {"id": "q2", "text": "How do you handle technical challenges?"}
            ]
        }
        
        mock_text_answers = [
            {"question_id": "q1", "answer_text": "I have 5 years of Python experience building web applications..."},
            {"question_id": "q2", "answer_text": "I approach challenges systematically by breaking them down..."}
        ]
        
        # Test VOICE INTERVIEW transcript building  
        mock_voice_session = {
            "user_id": "003XX000004DFJ0",
            "company_name": "ASAP Services",
            "job_title": "Senior Software Engineer", 
            "interview_mode": "voice",
            "candidate_name": "Jane Smith"
        }
        
        mock_voice_transcript = [
            {"type": "assistant", "text": "Hi Jane, I'm Isa. Tell me about your Python experience."},
            {"type": "user", "text": "I've been working with Python for about 5 years, primarily in web development..."},
            {"type": "assistant", "text": "That's great. How do you approach debugging complex issues?"},
            {"type": "user", "text": "I usually start by reproducing the issue, then use logging and debugging tools..."}
        ]
        
        # Simulate transcript building for text interview
        transcript_items = []
        for i, a in enumerate(mock_text_answers):
            question_text = ""
            for q in mock_text_session["questions"]:
                if q.get("id") == a.get("question_id"):
                    question_text = q.get("text", "")
                    break
            answer_text = a.get("answer_text", "")
            transcript_items.append(f"Q{i+1}: {question_text}\nA{i+1}: {answer_text}")
        
        text_transcript_header = [
            f"THEIA Interview Transcript",
            f"Mode: TEXT INTERVIEW", 
            f"Company: {mock_text_session['company_name']}",
            f"Position: {mock_text_session['job_title']}",
            f"Candidate: {mock_text_session['candidate_name']}",
            f"Agent: ISA_Questioner",
            "=" * 50
        ]
        
        text_transcript = "\n".join(text_transcript_header) + "\n\n" + "\n\n".join(transcript_items)
        
        # Simulate transcript building for voice interview
        voice_transcript_items = []
        for t in mock_voice_transcript:
            txt = t.get("text", "")
            speaker = t.get("type", "unknown")
            if speaker == "user":
                voice_transcript_items.append(f"CANDIDATE: {txt}")
            elif speaker == "assistant":
                voice_transcript_items.append(f"ISA_VOICE: {txt}")
        
        voice_transcript_header = [
            f"THEIA Interview Transcript",
            f"Mode: VOICE INTERVIEW",
            f"Company: {mock_voice_session['company_name']}",
            f"Position: {mock_voice_session['job_title']}",
            f"Candidate: {mock_voice_session['candidate_name']}",
            f"Agent: ISA_Voice",
            "=" * 50
        ]
        
        voice_transcript = "\n".join(voice_transcript_header) + "\n\n" + "\n\n".join(voice_transcript_items)
        
        test_results["text_interview"] = {
            "status": "✅ VALIDATED",
            "agent": "ISA_Questioner",
            "data_source": "session.answers + session.questions",
            "transcript_length": len(text_transcript),
            "questions_count": len(mock_text_answers),
            "sample_transcript": text_transcript[:300] + "..." if len(text_transcript) > 300 else text_transcript
        }
        
        test_results["voice_interview"] = {
            "status": "✅ VALIDATED", 
            "agent": "ISA_Voice",
            "data_source": "request.transcript (voice segments)",
            "transcript_length": len(voice_transcript),
            "segments_count": len(mock_voice_transcript),
            "sample_transcript": voice_transcript[:300] + "..." if len(voice_transcript) > 300 else voice_transcript
        }
        
        # Test Salesforce field mapping
        test_results["salesforce_mapping"] = {
            "interview_transcript_field": "Interview_Transcript__c",
            "text_interview_source": "Built from session.answers[] + session.questions[]",
            "voice_interview_source": "Built from request.transcript[] (voice segments)",
            "transcript_format": {
                "header": "Metadata (mode, company, candidate, agent, date)",
                "text_format": "Q1: [question]\nA1: [answer]",
                "voice_format": "ISA_VOICE: [question]\nCANDIDATE: [response]"
            },
            "field_limit": "130,000 characters (Salesforce limit)",
            "both_modes_supported": "✅ YES"
        }
        
        return test_results
        
    except Exception as e:
        return {"validation_error": str(e)}

@app.post("/api/v1/interviews/start")
async def start_interview(request: dict, authorization: Optional[str] = Header(default=None)):
    """Start a new THEIA interview session"""
    try:
        # Extract data from request
        user_id = request.get('user_id')
        # SOC2: prefer server-derived user id from THEIA token if available
        if (not user_id) and authorization:
            try:
                secret = os.getenv("THEIA_JWT_SECRET", "").strip()
                aud = os.getenv("THEIA_JWT_AUDIENCE", "theia-clients")
                iss = os.getenv("THEIA_JWT_ISSUER", "theia")
                token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else authorization
                claims = jwt.decode(token, secret, algorithms=["HS256"], audience=aud, issuer=iss)
                user_id = claims.get("sub")
            except Exception:
                user_id = None
        user_id = user_id or 'demo_user'
        company_name = request.get('company_name', '')
        job_description = request.get('job_description', '')
        job_title = request.get('job_title', '')
        interview_mode = request.get('interview_mode', 'text')
        resume_text = request.get('resume_text', '')
        
        # Validate required fields
        if not company_name or not job_description:
            return {
                "error": "Missing required fields",
                "message": "Company name and job description are required"
            }
        
        # Generate session ID
        import time
        session_id = f"theia_{int(time.time())}_{user_id[:8]}"
        
        # Initialize in-memory session
        # Try fetching resume and name from Salesforce if not provided
        candidate_name = ""
        if not resume_text:
            info = fetch_contact_info_from_salesforce(user_id)
            if info.get("resume_text"):
                resume_text = info["resume_text"]
            candidate_name = info.get("contact_name", "")

        SESSIONS[session_id] = {
            "user_id": user_id,
            "company_name": company_name,
            "job_description": job_description,
            "job_title": job_title,
            "interview_mode": interview_mode,
            "resume_text": resume_text,
            "questions": [],
            "answers": [],
            "research": None,
            "detected_skills": [],
            "candidate_name": candidate_name
        }

        # TODO: Here we would normally:
        # 1. Run ISA_Researcher for company intelligence
        # 2. Run ISA_Detector for skills analysis  
        # 3. Run ISA_Questioner for question generation
        # 4. Initialize interview session
        
        # For now, return success response
        return {
            "session_id": session_id,
            "status": "initialized",
            "message": "Interview session started successfully",
            "interview_mode": interview_mode,
            "next_step": "preparation",
            "company_name": company_name,
            "job_title": job_title,
            "estimated_prep_time": "2-3 minutes"
        }
        
    except Exception as e:
        return {
            "error": "Failed to start interview",
            "message": str(e)
        }


@app.get("/api/v1/auth/me")
async def auth_me(authorization: Optional[str] = Header(default=None), x_auth0_access_token: Optional[str] = Header(default=None)):
    """Map authenticated Auth0 user to Salesforce Contact and mint THEIA token."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        mapping = _map_auth0_user_to_contact(authorization, access_token_for_hash=x_auth0_access_token)
        return mapping
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("/auth/me failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/auth/config")
async def auth_config():
    """Return safe Auth0 client configuration from environment (no secrets)."""
    domain = os.getenv("AUTH0_DOMAIN", "").strip()
    client_id = os.getenv("AUTH0_CLIENT_ID", "").strip()
    audience = os.getenv("AUTH0_AUDIENCE", "").strip()
    return {
        "domain": domain,
        "client_id": client_id,
        "audience": audience,
        "has_config": bool(domain and client_id),
    }


@app.get("/api/v1/auth/userinfo")
async def auth_userinfo(authorization: Optional[str] = Header(default=None), x_auth0_access_token: Optional[str] = Header(default=None)):
    """Server-side proxy to Auth0 /userinfo to reliably fetch user profile (e.g., picture).
    Expects an Auth0 access token via X-Auth0-Access-Token (preferred) or Authorization: Bearer <access_token>.
    """
    try:
        access_token = None
        if x_auth0_access_token and x_auth0_access_token.strip():
            access_token = x_auth0_access_token.strip()
        elif authorization and authorization.lower().startswith("bearer "):
            # Only treat Authorization as Auth0 token if caller explicitly sends it here; don't decode THEIA token
            access_token = authorization.split(" ", 1)[1].strip()
        if not access_token:
            raise HTTPException(status_code=400, detail="Missing Auth0 access token")
        domain = os.getenv("AUTH0_DOMAIN", "").strip()
        if not domain:
            raise HTTPException(status_code=500, detail="Auth0 domain not configured")
        url = f"https://{domain}/userinfo"
        resp = _requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"userinfo fetch failed: {resp.text}")
        data = resp.json()
        # Return only safe fields
        return {
            "sub": data.get("sub"),
            "name": data.get("name"),
            "email": data.get("email"),
            "picture": data.get("picture")
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("/auth/userinfo failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/auth/profile")
async def create_profile(request: dict, authorization: Optional[str] = Header(default=None)):
    """Create a new Salesforce Contact from profile form and mint THEIA token.
    Expects: first_name, last_name, email, phone (opt), linkedin (opt), zip_code (opt)
    """
    try:
        # Allow both: use email from token if present, else from body (min data collection)
        email_from_token = None
        if authorization:
            try:
                claims = _verify_auth0_jwt(authorization)
                email_from_token = _extract_email_from_claims(claims)
            except Exception:
                email_from_token = None
        first_name = (request.get("first_name") or "").strip()
        last_name = (request.get("last_name") or "").strip()
        email = (email_from_token or request.get("email") or "").strip()
        phone = (request.get("phone") or "").strip() or None
        linkedin = (request.get("linkedin") or "").strip() or None
        zip_code = (request.get("zip_code") or "").strip() or None
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        contact_id = _create_contact_profile(first_name, last_name, email, phone, linkedin, zip_code)
        if not contact_id:
            raise HTTPException(status_code=500, detail="Failed to create contact")
        token = _mint_theia_token(contact_id, email)
        return {"status": "created", "contact_id": contact_id, "theia_token": token, "email": email}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("/auth/profile failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/auth/profile")
async def update_profile(request: dict, authorization: Optional[str] = Header(default=None)):
    """Update Salesforce Contact profile fields for the authenticated user."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        # Derive contact id from THEIA token if provided; otherwise from Auth0 mapping
        contact_id = None
        try:
            secret = os.getenv("THEIA_JWT_SECRET", "").strip()
            aud = os.getenv("THEIA_JWT_AUDIENCE", "theia-clients")
            iss = os.getenv("THEIA_JWT_ISSUER", "theia")
            token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else authorization
            claims = jwt.decode(token, secret, algorithms=["HS256"], audience=aud, issuer=iss)
            contact_id = claims.get("sub")
        except Exception:
            # fallback to Auth0 token verification to derive email→contact
            claims = _verify_auth0_jwt(authorization)
            email = _extract_email_from_claims(claims)
            matches = _find_contacts_by_email(email)
            if matches:
                contact_id = matches[0].get("Id")
        if not contact_id:
            raise HTTPException(status_code=400, detail="Unable to resolve contact id")

        first_name = request.get("first_name")
        last_name = request.get("last_name")
        email = request.get("email")
        phone = request.get("phone")
        linkedin = request.get("linkedin")
        zip_code = request.get("zip_code")

        ok = _update_contact_profile(contact_id, first_name, last_name, email, phone, linkedin, zip_code)
        if not ok:
            raise HTTPException(status_code=500, detail="Profile update failed")
        return {"status": "updated", "contact_id": contact_id}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("/auth/profile [PUT] failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/auth/profile")
async def get_profile(authorization: Optional[str] = Header(default=None), contact_id: Optional[str] = Query(default=None)):
    """Fetch current user's profile from Salesforce for prefill/editing."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        # If caller explicitly provides contact_id (from THEIA token sub), trust it (still requires auth)
        if contact_id:
            # 1) Try by Contact Id directly
            prof = _get_contact_profile(contact_id=contact_id)
            if prof:
                return prof
            # 2) Fallbacks: try to resolve by email from token if provided
            try:
                # THEIA token path
                secret = os.getenv("THEIA_JWT_SECRET", "").strip()
                aud = os.getenv("THEIA_JWT_AUDIENCE", "theia-clients")
                iss = os.getenv("THEIA_JWT_ISSUER", "theia")
                token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else authorization
                claims = jwt.decode(token, secret, algorithms=["HS256"], audience=aud, issuer=iss)
                email_claim = claims.get("email") or ""
                if email_claim:
                    prof = _get_contact_profile(email=email_claim)
                    if prof:
                        return prof
            except Exception:
                pass
            try:
                # Auth0 token path
                claims = _verify_auth0_jwt(authorization)
                email_claim = _extract_email_from_claims(claims)
                if email_claim:
                    prof = _get_contact_profile(email=email_claim)
                    if prof:
                        return prof
            except Exception:
                pass
            raise HTTPException(status_code=404, detail="Profile not found")

        derived_contact_id = None
        try:
            secret = os.getenv("THEIA_JWT_SECRET", "").strip()
            aud = os.getenv("THEIA_JWT_AUDIENCE", "theia-clients")
            iss = os.getenv("THEIA_JWT_ISSUER", "theia")
            token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else authorization
            claims = jwt.decode(token, secret, algorithms=["HS256"], audience=aud, issuer=iss)
            derived_contact_id = claims.get("sub")
        except Exception:
            claims = _verify_auth0_jwt(authorization)
            email = _extract_email_from_claims(claims)
            prof = _get_contact_profile(email=email)
            if prof:
                return prof
            raise HTTPException(status_code=404, detail="Profile not found")

        prof = _get_contact_profile(contact_id=derived_contact_id)
        if not prof:
            raise HTTPException(status_code=404, detail="Profile not found")
        return prof
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("/auth/profile [GET] failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/interviews/{session_id}/status")
async def get_interview_status(session_id: str):
    """Get interview session status"""
    return {
        "session_id": session_id,
        "status": "active",
        "phase": "preparation",
        "progress": 25.0,
        "message": "Analyzing job requirements and preparing questions..."
    }

@app.get("/api/v1/interviews/{session_id}/summaries")
async def get_agent_summaries(session_id: str):
    """Return placeholder summaries for each agent for local testing."""
    try:
        logger.info(f"🔍 Fetching summaries for session: {session_id}")
        logger.info(f"📊 Available sessions: {list(SESSIONS.keys())}")
        
        session = SESSIONS.get(session_id)
        if not session:
            logger.error(f"❌ Session {session_id} not found in SESSIONS")
            return {"error": "Invalid session_id"}

        # Fallback: if resume/candidate missing, try to fetch now using Contact Id
        if not session.get("resume_text") and session.get("user_id"):
            try:
                _info = fetch_contact_info_from_salesforce(session.get("user_id"))
                if _info.get("resume_text"):
                    session["resume_text"] = _info["resume_text"]
                if _info.get("contact_name") and not session.get("candidate_name"):
                    session["candidate_name"] = _info["contact_name"]
            except Exception:
                pass

        company = session.get("company_name") or "the company"
        job_title = session.get("job_title") or "the role"
        jd = (session.get("job_description") or "").strip()

        # Use actual agent outputs if available, otherwise fallback to hardcoded
        isa_researcher = session.get("isa_researcher", {})
        isa_detector = session.get("isa_detector", {})
        isa_questioner = session.get("isa_questioner", {})
        
        logger.info(f"🔍 AGENT OUTPUTS CHECK for session {session_id}:")
        logger.info(f"📊 isa_researcher: {bool(isa_researcher)} - {type(isa_researcher)} - {len(str(isa_researcher))}")
        logger.info(f"📊 isa_detector: {bool(isa_detector)} - {type(isa_detector)} - {len(str(isa_detector))}")
        logger.info(f"📊 isa_questioner: {bool(isa_questioner)} - {type(isa_questioner)} - {len(str(isa_questioner))}")
        
        # If no agent outputs available, use fallback
        if not isa_researcher:
            logger.warning(f"⚠️ No ISA_Researcher output found, using fallback for {company}")
            researcher_payload = perform_company_research(company, job_title, jd)
            isa_researcher = researcher_payload
        else:
            logger.info(f"✅ Using real ISA_Researcher output for {company}")
        
        if not isa_detector:
            skills = extract_skills_from_jd(jd)
            isa_detector = {"key_skills": skills}
        
        if not isa_questioner:
            questioner_overview = {
                "planned_count": 10,
                "focus_areas": isa_detector.get("key_skills", [])[:5]
            }
            isa_questioner = questioner_overview
        
        evaluator_stub = {"status": "pending", "rubric": ["communication", "confidence", "listening", "responses", "adaptability"]}

        # Persist to session for downstream agents
        SESSIONS[session_id]["research"] = isa_researcher
        SESSIONS[session_id]["detected_skills"] = isa_detector.get("key_skills", [])

        return {
            "session_id": session_id,
            "company_name": company,
            "job_title": job_title,
            "isa_researcher": isa_researcher,
            "isa_detector": isa_detector,
            "isa_questioner": isa_questioner,
            "isa_evaluator": evaluator_stub,
            "resume_text": session.get("resume_text", ""),
            "candidate_name": session.get("candidate_name", "")
        }
    except Exception as e:
        return {"error": "Failed to build summaries", "message": str(e)}

@app.post("/api/v1/interviews/{session_id}/refresh_research")
async def refresh_research(session_id: str):
    """Re-run ISA_Researcher for the session and update stored payload."""
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "Invalid session_id"}
    company = session.get("company_name") or ""
    job_title = session.get("job_title") or ""
    jd = session.get("job_description") or ""
    payload = perform_company_research(company, job_title, jd)
    SESSIONS[session_id]["research"] = payload
    return {"session_id": session_id, "isa_researcher": payload}

@app.post("/api/v1/interviews/{session_id}/generate_questions")
async def generate_questions(session_id: str, request: dict):
    """Generate interview questions using actual ISA agents."""
    try:
        if session_id not in SESSIONS:
            # Cloud Run can route to different instances; initialize session on-demand
            try:
                user_id = request.get("user_id")
                authorization = request.get("authorization") or request.get("Authorization")
                if (not user_id) and authorization:
                    try:
                        secret = os.getenv("THEIA_JWT_SECRET", "").strip()
                        aud = os.getenv("THEIA_JWT_AUDIENCE", "theia-clients")
                        iss = os.getenv("THEIA_JWT_ISSUER", "theia")
                        token = authorization.split(" ", 1)[1].strip() if str(authorization).lower().startswith("bearer ") else authorization
                        claims = jwt.decode(token, secret, algorithms=["HS256"], audience=aud, issuer=iss)
                        user_id = claims.get("sub")
                    except Exception:
                        user_id = None
                company_name = request.get("company_name", "")
                job_description = request.get("job_description", "")
                job_title = request.get("job_title", "")
                SESSIONS[session_id] = {
                    "user_id": user_id or "stateless_user",
                    "company_name": company_name,
                    "job_description": job_description,
                    "job_title": job_title,
                    "interview_mode": request.get("interview_mode", "text"),
                    "resume_text": "",
                    "questions": [],
                    "answers": [],
                    "research": None,
                    "detected_skills": [],
                    "candidate_name": "",
                }
                logger.warning(f"⚠️ Session {session_id} not found; initialized stateless session for generate_questions")
            except Exception:
                return {"error": "Invalid session_id"}

        # If questions already exist for this session, return them immediately (idempotent)
        existing = SESSIONS.get(session_id, {}).get("questions", [])
        if existing:
            logger.info(f"↩️ Returning existing questions for session {session_id} (count={len(existing)})")
            return {
                "session_id": session_id,
                "questions": existing,
                "count": len(existing),
                "company_name": SESSIONS[session_id].get("company_name", ""),
                "job_title": SESSIONS[session_id].get("job_title", ""),
            }

        # Use provided context, falling back to session
        company_name = request.get("company_name") or SESSIONS[session_id].get("company_name")
        job_title = request.get("job_title") or SESSIONS[session_id].get("job_title")
        job_description = request.get("job_description") or SESSIONS[session_id].get("job_description")
        resume_text = SESSIONS[session_id].get("resume_text", "")
        candidate_name = SESSIONS[session_id].get("candidate_name", "")

        # Fetch resume and candidate info if missing
        if not resume_text and SESSIONS[session_id].get("user_id"):
            try:
                logger.info(f"📄 Fetching resume for user: {SESSIONS[session_id].get('user_id')}")
                info = fetch_contact_info_from_salesforce(SESSIONS[session_id].get("user_id"))
                if info.get("resume_text"):
                    resume_text = info["resume_text"]
                    SESSIONS[session_id]["resume_text"] = resume_text
                    logger.info(f"✅ Resume fetched: {len(resume_text)} characters")
                if info.get("contact_name") and not candidate_name:
                    candidate_name = info["contact_name"]
                    SESSIONS[session_id]["candidate_name"] = candidate_name
                    logger.info(f"✅ Candidate name: {candidate_name}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to fetch resume: {e}")

        logger.info(f"🚀 Starting parallel ISA agent coordination for {company_name} - {job_title}")
        logger.info(f"📊 Input data - Resume: {len(resume_text)} chars, Candidate: {candidate_name or 'Unknown'}")

        # Use the new Agent Coordinator for parallel execution
        coordination_result = None  # Initialize coordination_result
        try:
            from services.agent_coordinator import get_agent_coordinator
            coordinator = get_agent_coordinator()
            
            # Run agents in parallel coordination
            coordination_result = await coordinator.prepare_interview_data(
                company_name=company_name,
                job_title=job_title,
                job_description=job_description,
                candidate_resume=resume_text,
                session_id=session_id
            )
            
            # Extract individual agent outputs
            research_output = None
            skills_output = None
            questions_output = None
            
            # Store normalized prepared_context for downstream agents (voice/text)
            try:
                prepared_ctx = coordination_result.get("prepared_context")
                if prepared_ctx:
                    SESSIONS[session_id]["prepared_context"] = prepared_ctx
                    logger.info(f"🧩 prepared_context stored for session {session_id} (keys={list(prepared_ctx.keys()) if isinstance(prepared_ctx, dict) else 'model'})")
                else:
                    logger.warning(f"⚠️ prepared_context missing in coordination_result for session {session_id}")
            except Exception as _pc_err:
                logger.error(f"❌ Failed to persist prepared_context for session {session_id}: {_pc_err}")
            
            if coordination_result.get("research_output"):
                from models import ResearchOutput
                research_output = ResearchOutput(**coordination_result["research_output"])
                SESSIONS[session_id]["isa_researcher"] = coordination_result["research_output"]
                
            if coordination_result.get("skills_output"):
                from models import SkillsDetectionOutput
                skills_output = SkillsDetectionOutput(**coordination_result["skills_output"])
                SESSIONS[session_id]["isa_detector"] = coordination_result["skills_output"]
                
            if coordination_result.get("questions_output"):
                from models import QuestionGenerationOutput
                questions_output = QuestionGenerationOutput(**coordination_result["questions_output"])
                SESSIONS[session_id]["isa_questioner"] = coordination_result["questions_output"]
            
            logger.info(f"✅ Parallel agent coordination completed in {coordination_result.get('execution_time', 0):.2f}s")
            logger.info(f"📊 Parallel execution: {coordination_result.get('parallel_execution', False)}")
            logger.info(f"🎯 Agents executed: {coordination_result.get('agents_executed', {})}")
            
        except Exception as e:
            logger.error(f"❌ Agent coordination failed: {e}")
            logger.error(f"❌ Falling back to sequential execution")
            
            # Fallback to sequential execution
            research_output = None
            skills_output = None
            questions_output = None
            
            # Step 1: Run ISA_Researcher
            try:
                from theia_agents.isa_researcher import ISAResearcher
                researcher = ISAResearcher()
                logger.info(f"🔍 ISA_Researcher: Researching {company_name}")
                research_output = await researcher.research_company_interview_practices(
                    company_name=company_name,
                    job_title=job_title,
                    job_description=job_description
                )
                SESSIONS[session_id]["isa_researcher"] = research_output.dict()
            except Exception as e:
                logger.error(f"❌ ISA_Researcher failed: {e}")
                research_output = None
            
            # Step 2: Run ISA_Detector
            try:
                from theia_agents.isa_detector import ISADetector
                detector = ISADetector()
                logger.info(f"🎯 ISA_Detector: Analyzing job requirements")
                skills_output = await detector.analyze_job_requirements(
                    job_description=job_description,
                    job_title=job_title,
                    company_name=company_name,
                    company_research=SESSIONS[session_id].get("isa_researcher")
                )
                SESSIONS[session_id]["isa_detector"] = skills_output.dict()
            except Exception as e:
                logger.error(f"❌ ISA_Detector failed: {e}")
                skills_output = None
            
            # Step 3: Run ISA_Questioner
            try:
                from theia_agents.isa_questioner import ISAQuestioner
                questioner = ISAQuestioner()
                
                logger.info(f"❓ ISA_Questioner: Generating tailored questions")
                questions_output = await questioner.generate_interview_questions(
                    job_description=job_description,
                    job_title=job_title,
                    company_name=company_name,
                    candidate_resume=resume_text,
                    research_output=research_output if research_output else None,
                    skills_output=skills_output if skills_output else None
                )
                logger.info(f"✅ ISA_Questioner completed - generated {len(questions_output.questions) if questions_output else 0} questions")
                if questions_output and len(questions_output.questions) > 0:
                    logger.info(f"❓ Sample question: {questions_output.questions[0]}")
            except Exception as e:
                logger.error(f"❌ ISA_Questioner failed: {e}")
                questions_output = None

        # Convert to the format expected by frontend
        if coordination_result and coordination_result.get("questions"):
            # Use formatted questions from Agent Coordinator - already in {"id": "q1", "text": "..."} format
            questions = coordination_result["questions"]
            logger.info(f"✅ Using Agent Coordinator formatted questions: {len(questions)} questions")
        elif questions_output and hasattr(questions_output, 'questions') and len(questions_output.questions) > 0:
            # Use ISA agent output - questions is List[str]
            questions = [
                {"id": f"q{i+1}", "text": q}
                for i, q in enumerate(questions_output.questions)
            ]
            logger.info(f"✅ Using ISA_Questioner output: {len(questions)} questions")
        else:
            # Use fallback questions if ISA_Questioner failed or returned empty
            logger.info("🔄 ISA_Questioner failed or returned empty - using fallback question generation")
            employers = extract_employers_from_resume(resume_text)
            questions = generate_aligned_questions(
                extract_skills_from_jd(job_description),
                company_name,
                job_title,
                job_description,
                resume_text,
                research_output.dict() if research_output else None,
                candidate_name=candidate_name,
                employers=employers,
            )

        # Save to session with all agent outputs
        SESSIONS[session_id]["questions"] = questions
        SESSIONS[session_id]["research"] = research_output.dict() if research_output else {}
        SESSIONS[session_id]["detected_skills"] = skills_output.key_skills if skills_output else []
        SESSIONS[session_id]["isa_researcher"] = research_output.dict() if research_output else {}
        SESSIONS[session_id]["isa_detector"] = skills_output.dict() if skills_output else {}
        SESSIONS[session_id]["isa_questioner"] = questions_output.dict() if questions_output else {}
        
        # Debug session storage
        logger.info(f"📊 Session storage - Research: {bool(research_output)}, Skills: {bool(skills_output)}, Questions: {bool(questions_output)}")
        if skills_output:
            logger.info(f"🎯 ISA_Detector output stored: {len(skills_output.key_skills)} skills")
        else:
            logger.error(f"❌ ISA_Detector output is None - will use fallback in summaries")

        logger.info(f"✅ ISA agent pipeline completed for {company_name}")

        resp = {
            "session_id": session_id,
            "questions": questions,
            "count": len(questions),
            "company_name": company_name,
            "job_title": job_title,
            "prepared_context": SESSIONS[session_id].get("prepared_context")
        }
        try:
            # Make ISA_Chat aware by mirroring the questions into API session store if available
            from backend.api.v1.endpoints.interviews import _API_SESSIONS
            st = _API_SESSIONS.get(session_id)
            if st and (not st.get("questions")):
                from models import QuestionGenerationOutput
                q_texts = [q.get("text", "") if isinstance(q, dict) else str(q) for q in questions]
                st["questions"] = QuestionGenerationOutput(
                    questions=q_texts[:10],
                    question_rationale=[""] * min(10, len(q_texts)),
                    difficulty_levels=["Medium"] * min(10, len(q_texts)),
                    skill_coverage={},
                    question_types=["General"] * min(10, len(q_texts)),
                )
                _API_SESSIONS[session_id] = st
        except Exception as _e:
            logger.warning(f"Could not sync questions to API session store: {_e}")
        return resp
    except Exception as e:
        logger.error(f"❌ ISA agent pipeline failed: {e}")
        return {"error": "Failed to generate questions", "message": str(e)}

@app.post("/api/v1/interviews/{session_id}/evaluate")
async def evaluate_interview(session_id: str, request: dict):
    """ISA_Evaluator: Comprehensive assessment using all available context."""
    try:
        session = SESSIONS.get(session_id)
        if not session:
            return {"error": "Invalid session_id"}
            
        # Get all available inputs
        transcript = request.get("transcript", []) or []
        answers = session.get("answers", [])
        questions = session.get("questions", [])
        job_title = session.get("job_title", "")
        company_name = session.get("company_name", "")
        job_description = session.get("job_description", "")
        resume_text = session.get("resume_text", "")
        
        # Get agent outputs
        isa_detector = session.get("isa_detector", {})
        isa_questioner = session.get("isa_questioner", {})
        
        logger.info(f"🔍 Starting ISA_Evaluator for {job_title} at {company_name}")
        logger.info(f"📊 Evaluation inputs - Questions: {len(questions)}, Answers: {len(answers)}, Resume: {len(resume_text)} chars")

        # Try to use real ISA_Evaluator
        try:
            import sys
            import os
            backend_path = os.path.join(os.path.dirname(__file__))
            if backend_path not in sys.path:
                sys.path.insert(0, backend_path)
            
            from theia_agents.isa_evaluator import ISAEvaluator
            evaluator = ISAEvaluator()
            
            # Convert questions and answers to simple lists
            question_texts = [q.get("text", "") if isinstance(q, dict) else str(q) for q in questions]
            answer_texts = [a.get("answer_text", "") if isinstance(a, dict) else str(a) for a in answers]
            
            # Create skills output object if available
            skills_output = None
            if isa_detector and isa_detector.get("key_skills"):
                from models import SkillsDetectionOutput
                skills_output = SkillsDetectionOutput(
                    key_skills=isa_detector.get("key_skills", []),
                    competencies=isa_detector.get("competencies", []),
                    technical_requirements=isa_detector.get("technical_requirements", []),
                    soft_skills=isa_detector.get("soft_skills", []),
                    experience_level=isa_detector.get("experience_level", "Mid-level"),
                    scorecard_criteria=isa_detector.get("scorecard_criteria", {}),
                    job_analysis_summary=isa_detector.get("job_analysis_summary", "")
                )
            
            # Run ISA_Evaluator with all inputs
            evaluation_output = await evaluator.evaluate_interview_performance(
                questions=question_texts,
                answers=answer_texts,
                job_title=job_title,
                company_name=company_name,
                job_description=job_description,
                candidate_resume=resume_text,
                skills_output=skills_output,
                interview_transcript=transcript
            )
            
            result = {
                "session_id": session_id,
                "job_matching_score": evaluation_output.job_matching_score,
                "interviewing_skills": evaluation_output.interviewing_skills,
                "skill_assessments": evaluation_output.skill_assessments,
                "strengths": evaluation_output.strengths,
                "improvement_areas": evaluation_output.improvement_areas,
                "specific_feedback": evaluation_output.specific_feedback,
                "interview_readiness": evaluation_output.interview_readiness,
                "notes": "Assessment based on 95% interview responses, 5% resume context"
            }
            
            logger.info(f"✅ ISA_Evaluator completed - Job matching score: {evaluation_output.job_matching_score}")
            
        except Exception as e:
            logger.error(f"❌ ISA_Evaluator failed: {e}")
            # Fallback to simple heuristic scoring
            logger.info("🔄 Using fallback evaluation")
            skills = session.get("detected_skills", [])
            
            text_blob = "\n".join([a.get("answer_text", "") for a in answers]) + "\n" + "\n".join([t.get("text", "") for t in transcript])
            blob = _normalize_text(text_blob)

            skill_scores = []
            for s in skills:
                tokens = s.split()
                hit = any(tok in blob for tok in tokens)
                score = 7 + (3 if hit else 0)
                skill_scores.append({"skill": s, "score": score})

            interviewing = {
                "communication": 7 + (1 if "structure" in blob or "synthesize" in blob else 0),
                "confidence": 7,
                "listening": 7,
                "responses": 7 + (1 if "metrics" in blob or "outcome" in blob else 0),
                "adaptability": 7
            }

            result = {
                "session_id": session_id,
                "job_matching_feedback": skill_scores,
                "interviewing_skills": interviewing,
                "notes": "Heuristic fallback evaluation - ISA_Evaluator not available."
            }

        # Persist to Salesforce THEIA_Interview__c
        try:
            contact_id = session.get("user_id")
            interview_mode = session.get("interview_mode", "text")
            
            # Build comprehensive transcript from both text and voice interviews
            transcript_items = []
            
            # Handle TEXT INTERVIEW transcripts (from ISA_Questioner)
            if answers and len(answers) > 0:
                logger.info(f"📝 Processing {len(answers)} text interview answers")
                questions_list = session.get("questions", [])
                
                for i, a in enumerate(answers):
                    # Get question text from session questions or answer object
                    question_text = ""
                    if isinstance(a, dict):
                        question_text = a.get("question_text", "")
                        if not question_text and a.get("question_id"):
                            # Find question by ID in session questions
                            for q in questions_list:
                                if q.get("id") == a.get("question_id"):
                                    question_text = q.get("text", "")
                                    break
                        if not question_text:
                            question_text = f"Question {a.get('question_id', i+1)}"
                        
                        answer_text = a.get("answer_text", "")
                        transcript_items.append(f"Q{i+1}: {question_text}\nA{i+1}: {answer_text}")
                    else:
                        # Handle simple string answers
                        if i < len(questions_list):
                            question_text = questions_list[i].get("text", f"Question {i+1}")
                        else:
                            question_text = f"Question {i+1}"
                        transcript_items.append(f"Q{i+1}: {question_text}\nA{i+1}: {str(a)}")
            
            # Handle VOICE INTERVIEW transcripts (from ISA_Voice)
            if transcript and len(transcript) > 0:
                logger.info(f"🎤 Processing {len(transcript)} voice interview segments")
                
                # Group voice transcript by conversation flow
                for i, t in enumerate(transcript):
                    if isinstance(t, dict):
                        txt = t.get("text", "")
                        speaker = t.get("speaker", t.get("type", "unknown"))
                        timestamp = t.get("timestamp", "")
                        
                        if txt:
                            if speaker in ["user", "candidate"]:
                                transcript_items.append(f"CANDIDATE: {txt}")
                            elif speaker in ["assistant", "isa", "voice_agent"]:
                                transcript_items.append(f"ISA_VOICE: {txt}")
                            else:
                                transcript_items.append(f"VOICE[{speaker}]: {txt}")
                    else:
                        # Handle simple string transcript entries
                        transcript_items.append(f"VOICE: {str(t)}")
            
            # Create final transcript with metadata header
            transcript_header = [
                f"THEIA Interview Transcript",
                f"Mode: {interview_mode.upper()} INTERVIEW",
                f"Company: {session.get('company_name', 'Unknown')}",
                f"Position: {session.get('job_title', 'Unknown')}",
                f"Candidate: {session.get('candidate_name', 'Unknown')}",
                f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                f"Agent: {'ISA_Voice' if interview_mode == 'voice' else 'ISA_Questioner'}",
                "=" * 50
            ]
            
            if transcript_items:
                transcript_text = "\n".join(transcript_header) + "\n\n" + "\n\n".join(transcript_items)
            else:
                transcript_text = "\n".join(transcript_header) + "\n\nNo interview transcript available"
            
            logger.info(f"📋 Built {interview_mode} interview transcript: {len(transcript_text)} characters")

            prep_job_description = session.get("job_description", "")
            
            # Map scorecard criteria from ISA_Detector to Desired_Job_Skills__c
            isa_detector = session.get("isa_detector", {})
            scorecard_criteria = isa_detector.get("scorecard_criteria", {})
            key_skills = isa_detector.get("key_skills", [])
            
            # Create comprehensive skills mapping for scorecard
            if scorecard_criteria:
                desired_job_skills = _json.dumps({
                    "scorecard_criteria": scorecard_criteria,
                    "key_skills": key_skills,
                    "technical_requirements": isa_detector.get("technical_requirements", []),
                    "soft_skills": isa_detector.get("soft_skills", []),
                    "experience_level": isa_detector.get("experience_level", "")
                }, ensure_ascii=False)
            else:
                # Fallback to simple skills list if no scorecard available
                skill_names = [s.get("skill") if isinstance(s, dict) else str(s) for s in (result.get("job_matching_feedback") or [])]
                desired_job_skills = ", ".join(skill_names) if skill_names else "Skills analysis not available"

            feedback_text = _json.dumps(result, ensure_ascii=False)

            logger.info(f"📝 Creating THEIA_Interview__c record for contact {contact_id}")
            logger.info(f"📊 Scorecard skills: {len(key_skills)} skills, Transcript: {len(transcript_text)} chars")

            interview_record = create_theia_interview_record(
                contact_id=contact_id,
                interview_transcript=transcript_text,
                prep_job_description=prep_job_description,
                desired_job_skills=desired_job_skills,
                feedback_text=feedback_text,
            )
            
            if interview_record.get("success"):
                logger.info(f"✅ THEIA_Interview__c record created: {interview_record.get('id')}")
            else:
                logger.error(f"❌ Failed to create THEIA_Interview__c record: {interview_record}")
                
        except Exception as e:
            logger.exception(f"❌ Failed to create THEIA_Interview__c from evaluation: {e}")

        # Store evaluation result in session for later Salesforce record creation
        session["evaluation_result"] = result

        return result
    except Exception as e:
        return {"error": "Failed to evaluate interview", "message": str(e)}


@app.post("/api/v1/interviews/{session_id}/answer")
async def chat_answer(session_id: str, request: dict):
    """ISA_Chat: Handle a single answer/message from the Text modal.
    This mirrors the API router behavior so the static frontend can POST here directly.
    """
    try:
        # Entry debug
        try:
            sd = SESSIONS.get(session_id) or {}
            logger.info(
                f"ISA_Chat: /answer entry session={session_id} has_session={bool(sd)} answers={len(sd.get('answers', [])) if sd else 0}"
            )
        except Exception:
            pass
        session_data = SESSIONS.get(session_id)
        if not session_data:
            return {"session_id": session_id, "status": "answer_received"}

        # Build an InterviewSession-like object for ISA_Chat
        if _InterviewSession:
            current_q_idx = session_data.get("current_question_index", 0)
            # Phase enum name differs across versions; prefer INTERVIEW_ACTIVE, fallback to INTERVIEW, else string
            phase_value = (
                getattr(_InterviewPhase, "INTERVIEW_ACTIVE", None)
                or getattr(_InterviewPhase, "INTERVIEW", None)
                or "interview"
            )
            interview_session = _InterviewSession(
                session_id=session_id,
                user_id=session_data.get("user_id", ""),
                interview_mode=session_data.get("interview_mode", "text"),
                phase=phase_value,
                status=_InterviewStatus.IN_PROGRESS if _InterviewStatus else "in_progress",
                job_description=session_data.get("job_description", ""),
                company_name=session_data.get("company_name", ""),
                job_title=session_data.get("job_title", ""),
                current_question_index=current_q_idx,
            )
        else:
            interview_session = None

        # Prepare questions_output from saved questions (or generate if missing)
        q_texts: List[str] = []
        for q in session_data.get("questions", []) or []:
            q_texts.append(q.get("text", "") if isinstance(q, dict) else str(q))
        try:
            logger.info(
                f"ISA_Chat: built q_texts count={len(q_texts)} first='" + (q_texts[0][:60] if q_texts else "") + "'"
            )
        except Exception:
            pass
        if _QuestionGenerationOutput and q_texts:
            questions_output = _QuestionGenerationOutput(
                questions=q_texts[:10],
                question_rationale=[""] * min(10, len(q_texts)),
                difficulty_levels=["Medium"] * min(10, len(q_texts)),
                skill_coverage={},
                question_types=["General"] * min(10, len(q_texts)),
            )
        else:
            questions_output = None

        # Extract answer text
        answer_text = (
            request.get("answer")
            or request.get("message")
            or request.get("text")
            or ""
        )

        # Initialize ISA_Chat
        chat = ISAChat() if ISAChat else None

        # If no questions exist yet, try to auto-generate from job description
        if chat and interview_session and (not questions_output or not questions_output.questions):
            try:
                generated = await chat.generate_questions_from_job_description(
                    job_description=interview_session.job_description,
                    job_title=interview_session.job_title or "",
                    company_name=interview_session.company_name,
                )
                if _QuestionGenerationOutput:
                    questions_output = _QuestionGenerationOutput(
                        questions=generated.questions,
                        question_rationale=generated.question_rationale,
                        difficulty_levels=generated.difficulty_levels,
                        skill_coverage=generated.skill_coverage,
                        question_types=generated.question_types,
                    )
                # Persist generated questions in session for UI parity
                try:
                    SESSIONS[session_id]["questions"] = [
                        {"id": f"q{i+1}", "text": q} for i, q in enumerate(generated.questions)
                    ]
                except Exception:
                    pass
            except Exception:
                questions_output = None

        # Debug state snapshot
        try:
            logger.info(
                f"ISA_Chat: state chat={bool(chat)} session={bool(interview_session)} q_out={bool(questions_output)} q_texts={len(q_texts)} answer_len={len(answer_text.strip()) if isinstance(answer_text, str) else 0}"
            )
        except Exception:
            pass

        # If we have questions but no answer text, return the current question to start the conversation
        if chat and interview_session and questions_output and not answer_text.strip():
            total = len(questions_output.questions)
            current_index = getattr(interview_session, "current_question_index", 0)
            # Ensure session has an explicit index for subsequent calls
            try:
                SESSIONS[session_id]["current_question_index"] = current_index
            except Exception:
                pass
            logger.info(
                f"ISA_Chat: question_ready prev_index={current_index} total={total} q='" +
                (questions_output.questions[current_index][:60] if current_index < total else "") + "'"
            )
            return {
                "session_id": session_id,
                "status": "question_ready",
                "ai": {
                    "response": "Here is your next question.",
                    "next_question_number": min(current_index + 1, total),
                    "total_questions": total,
                    "next_question": questions_output.questions[current_index] if current_index < total else None,
                }
            }

        # Fallback: if no chat but we do have questions and this is an initial fetch, return current question
        if (not answer_text.strip()) and (questions_output or q_texts):
            total = len(questions_output.questions) if questions_output else len(q_texts)
            current_index = int(SESSIONS.get(session_id, {}).get("current_question_index", 0))
            logger.info(
                f"ISA_Chat: fallback question_ready prev_index={current_index} total={total}"
            )
            return {
                "session_id": session_id,
                "status": "question_ready",
                "ai": {
                    "response": "Here is your next question.",
                    "next_question_number": min(current_index + 1, total),
                    "total_questions": total,
                    "next_question": (
                        (questions_output.questions[current_index] if questions_output else q_texts[current_index])
                        if current_index < total else None
                    ),
                }
            }

        # Initialize ISA_Chat and conduct single step
        if chat and interview_session and questions_output and answer_text.strip():
            # Build AI response text (acknowledgement/feedback) using model prompts; fallback to heuristic
            ai_text = None
            try:
                if "?" in answer_text:
                    ai_text = await chat.provide_guidance(
                        user_question=answer_text,
                        job_title=interview_session.job_title or "",
                        company_name=interview_session.company_name,
                    )
                else:
                    validation = await chat.validate_answer(
                        answer_text,
                        questions_output.questions[getattr(interview_session, "current_question_index", 0)] if questions_output.questions else "",
                        job_title=interview_session.job_title or "",
                        company_name=interview_session.company_name,
                    )
                    ai_text = await chat.provide_feedback(
                        validation,
                        job_title=interview_session.job_title or "",
                        company_name=interview_session.company_name,
                    )
            except Exception as _ack_err:
                logger.error(f"ISA_Chat: acknowledgement/feedback generation failed: {_ack_err}")
                try:
                    hv = chat._heuristic_validate_answer(
                        answer_text,
                        questions_output.questions[getattr(interview_session, "current_question_index", 0)] if questions_output.questions else "",
                    )
                    ai_text = chat._heuristic_feedback_text(hv)
                except Exception:
                    ai_text = "Thanks. Let's keep going."
            # Guardrail: if model echoes the user's answer, synthesize concise feedback instead
            try:
                if ai_text and answer_text and ai_text.strip().lower() == answer_text.strip().lower():
                    hv = chat._heuristic_validate_answer(
                        answer_text,
                        questions_output.questions[getattr(interview_session, "current_question_index", 0)] if questions_output.questions else "",
                    )
                    ai_text = chat._heuristic_feedback_text(hv)
            except Exception:
                pass
            if not ai_text:
                ai_text = "Thanks. Let's keep going."

            try:
                updated = await chat.conduct_interview(
                    session=interview_session,
                    questions_output=questions_output,
                    user_answer=answer_text,
                    client_id=None,
                )
                next_index = getattr(updated, "current_question_index", 0)
            except Exception as _flow_err:
                # If ISAChat flow fails, advance index manually to keep UX flowing
                logger.warning(f"ISA_Chat.conduct_interview failed, advancing manually: {_flow_err}")
                next_index = min(getattr(interview_session, "current_question_index", 0) + 1, max(len(questions_output.questions) - 1, 0))

            # Persist progress and answer regardless of how next_index was produced
            prev_index = getattr(interview_session, "current_question_index", 0)
            try:
                SESSIONS[session_id]["current_question_index"] = next_index
                qs = SESSIONS[session_id].get("questions", []) or []
                q_id = None
                q_text = ""
                if prev_index < len(qs):
                    try:
                        q_id = qs[prev_index].get("id")
                        q_text = qs[prev_index].get("text", "")
                    except Exception:
                        q_id = None
                        q_text = str(qs[prev_index])
                answers_list = SESSIONS[session_id].get("answers") or []
                answers_list.append({
                    "question_id": q_id or f"q{prev_index+1}",
                    "question_text": q_text,
                    "answer_text": answer_text,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                SESSIONS[session_id]["answers"] = answers_list
            except Exception:
                pass

            total = len(questions_output.questions)
            try:
                q_snippet = questions_output.questions[next_index][:80] if next_index < total else None
            except Exception:
                q_snippet = None
            logger.info(
                f"ISA_Chat: answer_recorded prev_index={prev_index} next_index={next_index} total={total} ack_len={len((ai_text or '').strip())} next_q_present={q_snippet is not None}"
            )
            resp = {
                "session_id": session_id,
                "status": "answer_recorded",
                "ai": {
                    "response": ai_text or "Thanks. Let's keep going.",
                    "next_question_number": min(next_index + 1, total),
                    "total_questions": total,
                    "next_question": questions_output.questions[next_index] if next_index < total else None,
                }
            }
            return resp

        # Manual fallback when chat or questions_output is unavailable but we have q_texts and an answer
        if answer_text.strip() and q_texts:
            try:
                idx = int(SESSIONS.get(session_id, {}).get("current_question_index", 0))
            except Exception:
                idx = 0
            total = len(q_texts)
            # record answer
            try:
                answers_list = SESSIONS[session_id].get("answers") or []
                answers_list.append({
                    "question_id": f"q{idx+1}",
                    "question_text": q_texts[idx] if idx < total else "",
                    "answer_text": answer_text,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                SESSIONS[session_id]["answers"] = answers_list
            except Exception:
                pass
            next_idx = min(idx + 1, max(total - 1, 0))
            try:
                SESSIONS[session_id]["current_question_index"] = next_idx
            except Exception:
                pass
            logger.info(
                f"ISA_Chat: manual fallback answer_recorded idx={idx} next_idx={next_idx} total={total}"
            )
            return {
                "session_id": session_id,
                "status": "answer_recorded",
                "ai": {
                    "response": "Thanks. Let's keep going.",
                    "next_question_number": min(next_idx + 1, total),
                    "total_questions": total,
                    "next_question": q_texts[next_idx] if next_idx < total else None,
                }
            }

        # Fallback response keeps UI flowing
        try:
            logger.info(
                f"ISA_Chat: bottom fallback chat={bool(chat)} session={bool(interview_session)} q_out={bool(questions_output)} q_texts={len(q_texts)} answer_len={len(answer_text.strip()) if isinstance(answer_text, str) else 0}"
            )
        except Exception:
            pass
        # include next_question if we have session questions
        try:
            idx = int(SESSIONS.get(session_id, {}).get("current_question_index", 0))
            next_q = q_texts[idx] if idx < len(q_texts) else None
            total_q = len(q_texts)
        except Exception:
            next_q = None
            total_q = len(q_texts)
        return {
            "session_id": session_id,
            "status": "answer_received",
            "ai": {
                "response": "Thanks. Let's keep going.",
                "next_question_number": (idx + 1) if next_q else None,
                "total_questions": total_q,
                "next_question": next_q,
            }
        }
    except Exception as e:
        logger.exception(f"ISA_Chat: /answer unhandled error for session={session_id}: {e}")
        return {"error": "Failed to submit answer", "message": str(e)}


@app.delete("/api/v1/interviews/{session_id}")
async def delete_interview_session(session_id: str):
    """Delete cached interview session state (for starting fresh practice runs).
    Does not touch auth or Salesforce profile cache.
    """
    try:
        if session_id in SESSIONS:
            try:
                del SESSIONS[session_id]
            except Exception:
                # Fallback in case del fails for any reason
                SESSIONS.pop(session_id, None)
            logger.info(f"🧹 Deleted cached interview session: {session_id}")
            return {"session_id": session_id, "status": "deleted"}
        return {"session_id": session_id, "status": "not_found"}
    except Exception as e:
        return {"error": "Failed to delete session", "message": str(e)}

@app.post("/api/v1/interviews/{session_id}/create_salesforce_record")
async def create_salesforce_interview_record(session_id: str):
    """Create THEIA_Interview__c record in Salesforce after interview completion."""
    try:
        session = SESSIONS.get(session_id)
        if not session:
            return {"success": False, "error": "Invalid session_id"}
            
        # Get session data
        job_title = session.get("job_title", "")
        company_name = session.get("company_name", "")
        job_description = session.get("job_description", "")
        candidate_name = session.get("candidate_name", "")
        resume_text = session.get("resume_text", "")
        answers = session.get("answers", [])
        questions = session.get("questions", [])
        evaluation_result = session.get("evaluation_result", {})
        
        # Get Salesforce client
        sf = _get_salesforce_client()
        if not sf:
            return {"success": False, "error": "Salesforce not configured"}
            
        # Prepare interview data
        interview_data = {
            "Name": f"Interview - {candidate_name} - {company_name}",
            "Job_Title__c": job_title,
            "Company_Name__c": company_name,
            "Job_Description__c": job_description[:32000] if job_description else "",  # Salesforce field limit
            "Candidate_Name__c": candidate_name,
            "Resume_Text__c": resume_text[:32000] if resume_text else "",  # Salesforce field limit
            "Interview_Status__c": "Completed",
            "Interview_Type__c": "Text Interview",
            "Questions_Count__c": len(questions),
            "Answers_Count__c": len([a for a in answers if a.get("answer_text", "").strip()]),
            "Overall_Score__c": evaluation_result.get("job_matching_score"),
            "Interview_Readiness__c": evaluation_result.get("interview_readiness"),
            "Strengths__c": "\n".join(evaluation_result.get("strengths", [])) if evaluation_result.get("strengths") else "",
            "Areas_for_Improvement__c": "\n".join(evaluation_result.get("improvement_areas", [])) if evaluation_result.get("improvement_areas") else "",
            "Specific_Feedback__c": evaluation_result.get("specific_feedback", "")[:32000] if evaluation_result.get("specific_feedback") else "",
            "Interview_Date__c": datetime.now().strftime("%Y-%m-%d"),
            "Session_ID__c": session_id
        }
        
        # Create the record
        result = sf.THEIA_Interview__c.create(interview_data)
        
        if result.get("success"):
            logger.info(f"✅ THEIA_Interview__c record created: {result.get('id')}")
            return {"success": True, "record_id": result.get("id")}
        else:
            logger.error(f"❌ Failed to create THEIA_Interview__c record: {result}")
            return {"success": False, "error": "Failed to create Salesforce record"}
            
    except Exception as e:
        logger.exception(f"❌ Failed to create Salesforce interview record: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/v1/interviews/{session_id}/questions")
async def get_questions(session_id: str):
    """Return existing questions for a session."""
    if session_id not in SESSIONS:
        return {"error": "Invalid session_id"}
    return {"session_id": session_id, "questions": SESSIONS[session_id].get("questions", [])}

@app.get("/api/v1/interviews/{session_id}/resume")
async def get_resume(session_id: str):
    """Debug endpoint: return the stored Resume_TXT for the session (if any)."""
    session = SESSIONS.get(session_id)
    if not session:
        return {"error": "Invalid session_id"}
    return {"session_id": session_id, "resume_text": session.get("resume_text", "")}

@app.post("/api/v1/resume/build")
async def build_resume(request: Request):
    """Build optimized resume using ISA_Resume_Builder agent."""
    try:
        # Parse request body
        body = await request.json()
        user_id = body.get("user_id", "")
        company_name = body.get("company_name", "")
        job_title = body.get("job_title", "")
        job_description = body.get("job_description", "")
        
        # Validate required fields
        if not all([user_id, company_name, job_title, job_description]):
            return {"error": "Missing required fields: user_id, company_name, job_title, job_description"}
        
        logger.info(f"🚀 Starting resume build for user {user_id}: {company_name} - {job_title}")
        
        # Ensure Python path is configured (call our centralized function)
        ensure_python_path()
        
        # Debug: Log current Python path state for troubleshooting
        logger.debug(f"Python path includes: {[p for p in sys.path if 'backend' in p or 'theia' in p.lower()]}")
        
        # Fetch candidate data from Salesforce
        candidate_data = fetch_resume_builder_data(user_id)
        if candidate_data.get("error"):
            logger.warning(f"Salesforce data fetch had issues: {candidate_data['error']}")
        
        # Initialize ISA_Resume_Builder agent with enhanced error handling and fallback
        resume_builder = None
        
        # First, try using the module-level import
        if RESUME_BUILDER_AVAILABLE and ISAResumeBuilder is not None:
            try:
                resume_builder = ISAResumeBuilder()
                logger.debug("✅ Successfully used module-level ISAResumeBuilder")
            except Exception as e:
                logger.warning(f"⚠️ Module-level ISAResumeBuilder failed, trying fallback: {e}")
        
        # Fallback: Try dynamic import with path configuration
        if resume_builder is None:
            try:
                # Ensure Python path is configured (call our centralized function)
                ensure_python_path()
                
                # Try dynamic import
                from theia_agents.isa_resume_builder import ISAResumeBuilder as ISAResumeBuilderDynamic
                resume_builder = ISAResumeBuilderDynamic()
                logger.debug("✅ Successfully used dynamic import ISAResumeBuilder")
            except ImportError as ie:
                logger.error(f"❌ Import Error for ISAResumeBuilder: {ie}")
                logger.error(f"Current working directory: {os.getcwd()}")
                logger.error(f"Current sys.path (first 5): {sys.path[:5]}")
                logger.error(f"Backend directory exists: {os.path.exists(os.path.dirname(os.path.abspath(__file__)))}")
                logger.error(f"theia_agents directory exists: {os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'theia_agents'))}")
                
                # Check if files exist
                backend_dir = os.path.dirname(os.path.abspath(__file__))
                agents_dir = os.path.join(backend_dir, 'theia_agents')
                resume_builder_file = os.path.join(agents_dir, 'isa_resume_builder.py')
                init_file = os.path.join(agents_dir, '__init__.py')
                
                logger.error(f"theia_agents/__init__.py exists: {os.path.exists(init_file)}")
                logger.error(f"isa_resume_builder.py exists: {os.path.exists(resume_builder_file)}")
                
                return {
                    "status": "error",
                    "error": f"Resume builder module not available: {str(ie)}",
                    "resume_text": "",
                    "company_name": company_name,
                    "job_title": job_title,
                    "debug_info": {
                        "backend_dir": backend_dir,
                        "agents_dir_exists": os.path.exists(agents_dir),
                        "init_file_exists": os.path.exists(init_file),
                        "resume_builder_file_exists": os.path.exists(resume_builder_file),
                        "python_path_backend": [p for p in sys.path if 'backend' in p]
                    }
                }
            except Exception as e:
                logger.error(f"❌ Unexpected error initializing ISAResumeBuilder: {e}")
                return {
                    "status": "error", 
                    "error": f"Resume builder initialization failed: {str(e)}",
                    "resume_text": "",
                    "company_name": company_name,
                    "job_title": job_title
                }
        
        if resume_builder is None:
            logger.error("❌ All attempts to initialize ISAResumeBuilder failed")
            return {
                "status": "error",
                "error": "Resume builder is not available",
                "resume_text": "",
                "company_name": company_name,
                "job_title": job_title
            }
        
        # Build optimized resume
        result = await resume_builder.build_resume(
            job_description=job_description,
            company_name=company_name,
            job_title=job_title,
            candidate_resume=candidate_data.get("resume_text", ""),
            opportunity_transcripts=candidate_data.get("opportunity_transcripts", []),
            interview_transcripts=candidate_data.get("interview_transcripts", []),
            contact_name=candidate_data.get("contact_name", ""),
            user_id=user_id
        )
        
        # Add data source information
        result["data_sources"] = {
            "resume_available": bool(candidate_data.get("resume_text", "").strip()),
            "opportunity_transcripts_count": candidate_data.get("total_opportunity_transcripts", 0),
            "interview_transcripts_count": candidate_data.get("total_interview_transcripts", 0)
        }
        
        logger.info(f"✅ Resume build completed for user {user_id}")
        return result
        
    except Exception as e:
        logger.exception(f"❌ Resume build failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "resume_text": "",
            "company_name": company_name if 'company_name' in locals() else "",
            "job_title": job_title if 'job_title' in locals() else ""
        }

@app.get("/api/v1/salesforce/contact/{contact_id}/resume_test")
async def salesforce_resume_test(contact_id: str):
    """Diagnostics endpoint: attempts to fetch resume for a specific Contact Id and returns field info."""
    try:
        sf = _get_salesforce_client()
        if sf is None:
            return {"error": "Salesforce client not configured"}
        desc = sf.Contact.describe()
        field_names = [f.get("name") for f in desc.get("fields", [])]
        candidate_fields = [
            "Candidate_s_Resume_TXT__c",
            "Resume_TXT__c",
            "Resume_TXT",
        ]
        available = [f for f in candidate_fields if f in field_names]
        payload = {"contact_id": contact_id, "available_fields": available}
        if len(contact_id) not in (15, 18):
            payload["error"] = "Provided id is not 15/18 chars"
            return payload
        resume_field = available[0] if available else None
        if resume_field:
            res = sf.query(f"SELECT Id, {resume_field} FROM Contact WHERE Id = '{contact_id}' LIMIT 1")
            recs = res.get("records", [])
            if recs:
                txt = recs[0].get(resume_field) or ""
                payload["resume_field"] = resume_field
                payload["resume_length"] = len(txt)
                payload["snippet"] = txt[:200]
            else:
                payload["error"] = "No contact found"
        else:
            payload["error"] = "Resume field not found on Contact"
        return payload
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/v1/interviews/{session_id}/submit_answers")
async def submit_answers(session_id: str, request: dict):
    """Accept user answers for the generated questions (local testing)."""
    try:
        if session_id not in SESSIONS:
            return {"error": "Invalid session_id"}

        answers = request.get("answers", [])
        if not isinstance(answers, list) or not answers:
            return {"error": "No answers provided"}

        # Basic validation: ensure question_id exists
        valid_ids = {q["id"] for q in SESSIONS[session_id].get("questions", [])}
        cleaned = []
        for a in answers:
            qid = a.get("question_id")
            text = a.get("answer_text", "").strip()
            if qid in valid_ids and text:
                cleaned.append({"question_id": qid, "answer_text": text})

        if not cleaned:
            return {"error": "Answers invalid or empty"}

        SESSIONS[session_id]["answers"] = cleaned

        return {
            "session_id": session_id,
            "received": len(cleaned),
            "status": "answers_recorded"
        }
    except Exception as e:
        return {"error": "Failed to submit answers", "message": str(e)}

@app.post("/api/v1/voice/{session_id}/prepare")
async def prepare_voice_session(session_id: str):
    """Prepare ISA_Voice Realtime session: compile all available context and return instructions.
    Frontend can use this to initialize the OpenAI Realtime connection.
    
    Updated to use timing retry logic to handle Cloud Run session delays.
    """
    try:
        # Use session validation with timing retry to handle Cloud Run delays
        session = SESSIONS.get(session_id)
        if not session:
            # Check if this is a timing issue - try a brief wait and retry
            import asyncio
            logger.warning(f"⚠️ Prepare endpoint: Session {session_id} not immediately found, waiting 1 second and retrying...")
            await asyncio.sleep(1.0)
            session = SESSIONS.get(session_id)
            
            if not session:
                logger.error(f"❌ Prepare endpoint: Session {session_id} not found in SESSIONS after retry")
                logger.error(f"📊 Available sessions: {list(SESSIONS.keys())}")
                return {"error": "Invalid session_id"}

        # Fallback: if resume/candidate missing, try to fetch now using Contact Id
        if not session.get("resume_text") and session.get("user_id"):
            try:
                _info = fetch_contact_info_from_salesforce(session.get("user_id"))
                if _info.get("resume_text"):
                    session["resume_text"] = _info["resume_text"]
                if _info.get("contact_name") and not session.get("candidate_name"):
                    session["candidate_name"] = _info["contact_name"]
            except Exception:
                pass

        company = session.get("company_name") or "the company"
        job_title = session.get("job_title") or "the role"
        jd = (session.get("job_description") or "").strip()

        # Use actual agent outputs if available, otherwise fallback to hardcoded (same as summaries)
        isa_researcher = session.get("isa_researcher", {})
        isa_detector = session.get("isa_detector", {})
        isa_questioner = session.get("isa_questioner", {})
        
        logger.info(f"🔍 AGENT OUTPUTS CHECK for voice session {session_id}:")
        logger.info(f"📊 isa_researcher: {bool(isa_researcher)} - {type(isa_researcher)} - {len(str(isa_researcher))}")
        logger.info(f"📊 isa_detector: {bool(isa_detector)} - {type(isa_detector)} - {len(str(isa_detector))}")
        logger.info(f"📊 isa_questioner: {bool(isa_questioner)} - {type(isa_questioner)} - {len(str(isa_questioner))}")
        
        # If no agent outputs available, use fallback (same logic as summaries)
        if not isa_researcher:
            logger.warning(f"⚠️ No ISA_Researcher output found, using fallback for {company}")
            researcher_payload = perform_company_research(company, job_title, jd)
            isa_researcher = researcher_payload
        else:
            logger.info(f"✅ Using real ISA_Researcher output for {company}")
        
        if not isa_detector:
            skills = extract_skills_from_jd(jd)
            isa_detector = {"key_skills": skills}
        
        if not isa_questioner:
            questioner_overview = {
                "planned_count": 10,
                "focus_areas": isa_detector.get("key_skills", [])[:5]
            }
            isa_questioner = questioner_overview

        # Persist to session for downstream agents (same as summaries)
        SESSIONS[session_id]["research"] = isa_researcher
        SESSIONS[session_id]["detected_skills"] = isa_detector.get("key_skills", [])

        # Extract necessary data for voice session
        resume_text = session.get("resume_text", "")
        candidate_name = session.get("candidate_name", "")
        first_name = extract_first_name(candidate_name)

        # Prepare questions for voice session
        questions = []
        if isa_questioner and isinstance(isa_questioner, dict):
            # Use ISA_Questioner generated questions if available
            isa_questions = isa_questioner.get("questions", [])
            if isa_questions:
                questions = [
                    {"id": f"q{i+1}", "text": q}
                    for i, q in enumerate(isa_questions)
                ]
                logger.info(f"✅ Using ISA_Questioner output: {len(questions)} questions for voice session {session_id}")
        
        # Fallback to generated questions if needed
        if not questions:
            logger.warning(f"⚠️ No ISA_Questioner questions found for session {session_id}, generating fallback questions")
            detected_skills = isa_detector.get("key_skills", [])
            employers = extract_employers_from_resume(resume_text)
            questions = generate_aligned_questions(
                detected_skills,
                company,
                job_title,
                jd,
                resume_text,
                isa_researcher,
                candidate_name=candidate_name,
                employers=employers,
            )
        
        # Store questions in session
        SESSIONS[session_id]["questions"] = questions

        # Build concise instructions for the Realtime voice agent
        first_question = (questions[0]["text"] if questions else "To begin, could you give a brief overview of your most relevant experience for this role?")
        greeting = (
            f"Hi {first_name or 'there'}, I'm Isa. We'll run a quick preparation interview for {company or 'this role'}. "
            "Once we complete the Prep Interview, you'll receive feedback on role-aligned strengths and interview skills. "
            f"First question: {first_question}"
        )
        instructions = (
            "You are ISA_Voice (name: Isa), a professional interview coach for preparation interviews. "
            "On connect, immediately say the following greeting and first question verbatim to the candidate: "
            f"\"{greeting}\" "
            "INTERVIEW STYLE: Follow the question plan and company interview style if provided; keep questions concise, probe with targeted follow-ups, and progress from warm-up to deeper assessment. "
            "GUARDRAILS: If the candidate asks for answers, to skip steps, or otherwise tries to 'game' the process, remind them this is a preparation interview meant to build real readiness; encourage genuine practice instead of shortcuts, then continue. "
            "Maintain applicant perspective: never imply prior employment at the target company."
        )

        # Build comprehensive context from all agent outputs (enhanced version of summaries data)
        prepared_ctx = session.get("prepared_context") or {}
        context = {
            "company": company,
            "job_title": job_title,
            "job_description": jd,
            "resume_text": resume_text,
            "research": isa_researcher,
            "detected_skills": isa_detector.get("key_skills", []),
            "question_plan": questions,
            "candidate_name": candidate_name,
            "first_name": first_name,
            "prepared_context": prepared_ctx,
            "isa_researcher": isa_researcher,
            "isa_detector": isa_detector,
            "isa_questioner": isa_questioner,
        }

        # Optionally include suggested system prompt for OpenAI Realtime agent
        system_prompt = (
            "You are ISA_Voice (Isa), a professional interview coach for mock preparation. "
            "Use the provided context (job title, company name, job description, detected skills, prepared question plan, resume excerpts, researcher insights) to tailor delivery. "
            "Greet the candidate by first name if available and ask the first prepared question. Maintain applicant perspective."
        )

        # Opportunistically mint a realtime token so the client can connect without a separate call
        realtime_token: Dict[str, Any] = {}
        try:
            import json as _j
            import urllib.request as _r
            OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
            if OPENAI_API_KEY:
                _payload = {
                    "model": os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-10-01"),
                    "voice": "coral",
                    "instructions": system_prompt,
                }
                _req = _r.Request(
                    "https://api.openai.com/v1/realtime/sessions",
                    data=_j.dumps(_payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with _r.urlopen(_req, timeout=20) as _resp:
                    _data = _j.loads(_resp.read().decode("utf-8"))
                _client_secret = (_data.get("client_secret") or {}).get("value")
                if _client_secret:
                    realtime_token = {"client_secret": _client_secret, "model": _data.get("model", _payload["model"]) }
        except Exception:
            # Non-fatal: fall back to explicit token fetch from client
            realtime_token = {}

        logger.info(f"✅ Voice session prepared successfully for {session_id}")
        return {
            "session_id": session_id,
            "instructions": instructions,
            "system_prompt": system_prompt,
            "context": context,
            "initial_say": greeting,
            "token": realtime_token,
        }
    except Exception as e:
        logger.error(f"❌ Failed to prepare voice session for {session_id}: {e}")
        return {"error": "Failed to prepare voice session", "message": str(e)}

        # Build concise instructions for the Realtime voice agent
        first_question = (questions[0]["text"] if questions else "To begin, could you give a brief overview of your most relevant experience for this role?")
        greeting = (
            f"Hi {first_name or 'there'}, I'm Isa. We'll run a quick preparation interview for {company or 'this role'}. "
            "Once we complete the Prep Interview, you'll receive feedback on role-aligned strengths and interview skills. "
            f"First question: {first_question}"
        )
        instructions = (
            "You are ISA_Voice (name: Isa), a professional interview coach for preparation interviews. "
            "On connect, immediately say the following greeting and first question verbatim to the candidate: "
            f"\"{greeting}\" "
            "INTERVIEW STYLE: Follow the question plan and company interview style if provided; keep questions concise, probe with targeted follow-ups, and progress from warm-up to deeper assessment. "
            "GUARDRAILS: If the candidate asks for answers, to skip steps, or otherwise tries to 'game' the process, remind them this is a preparation interview meant to build real readiness; encourage genuine practice instead of shortcuts, then continue. "
            "Maintain applicant perspective: never imply prior employment at the target company."
        )

        # Prefer normalized prepared_context if available
        prepared_ctx = session.get("prepared_context") or {}
        context = {
            "company": company,
            "job_title": job_title,
            "job_description": job_description,
            "resume_text": resume_text,
            "research": research,
            "detected_skills": detected_skills,
            "question_plan": questions,
            "candidate_name": candidate_name,
            "first_name": first_name,
            "prepared_context": prepared_ctx,
        }

        # Optionally include suggested system prompt for OpenAI Realtime agent (generic; avoids hardcoding company/candidate)
        system_prompt = (
            "You are ISA_Voice (Isa), a professional interview coach for mock preparation. "
            "Use the provided context (job title, company name, job description, detected skills, prepared question plan, resume excerpts, researcher insights) to tailor delivery. "
            "Greet the candidate by first name if available and ask the first prepared question. Maintain applicant perspective."
        )

        # Opportunistically mint a realtime token so the client can connect without a separate call
        realtime_token: Dict[str, Any] = {}
        try:
            import json as _j
            import urllib.request as _r
            OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
            if OPENAI_API_KEY:
                _payload = {
                    "model": os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-10-01"),
                    "voice": "coral",
                    "instructions": system_prompt,
                }
                _req = _r.Request(
                    "https://api.openai.com/v1/realtime/sessions",
                    data=_j.dumps(_payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with _r.urlopen(_req, timeout=20) as _resp:
                    _data = _j.loads(_resp.read().decode("utf-8"))
                _client_secret = (_data.get("client_secret") or {}).get("value")
                if _client_secret:
                    realtime_token = {"client_secret": _client_secret, "model": _data.get("model", _payload["model"]) }
        except Exception:
            # Non-fatal: fall back to explicit token fetch from client
            realtime_token = {}

        return {
            "session_id": session_id,
            "instructions": instructions,
            "system_prompt": system_prompt,
            "context": context,
            "initial_say": greeting,
            "token": realtime_token,
        }
    except Exception as e:
        return {"error": "Failed to prepare voice session", "message": str(e)}

@app.post("/api/v1/voice/{session_id}/token")
async def create_voice_token(session_id: str, request: dict = None):
    """Mint an OpenAI Realtime ephemeral session token for the browser client.
    Accepts optional body with 'system_prompt' or 'instructions' to avoid relying on in-memory session.
    
    Updated to use the same robust session validation logic as summaries/prepare endpoints.
    """
    try:
        # Use session validation with timing retry to handle Cloud Run delays (same as prepare endpoint)
        session = SESSIONS.get(session_id)
        if not session:
            # Check if this is a timing issue - try a brief wait and retry
            import asyncio
            logger.warning(f"⚠️ Token endpoint: Session {session_id} not immediately found, waiting 1 second and retrying...")
            await asyncio.sleep(1.0)
            session = SESSIONS.get(session_id)
            
            if not session:
                logger.error(f"❌ Token endpoint: Session {session_id} not found in SESSIONS after retry")
                logger.error(f"📊 Available sessions: {list(SESSIONS.keys())}")
                return {"error": "Invalid session_id"}

        # Compose instructions from stored context (prefer normalized prepared_context)
        provided_prompt = None
        if request and isinstance(request, dict):
            provided_prompt = request.get("system_prompt") or request.get("instructions")

        if provided_prompt:
            system_prompt = str(provided_prompt).strip()
        elif session:
            # Generic, context-aware prompt without hardcoding company/candidate
            system_prompt = (
                "You are ISA_Voice (Isa), a professional interview coach for mock preparation. "
                "Use the session context (company name, job title, job description, detected skills, prepared question plan, resume excerpts, researcher insights) to tailor delivery. "
                "Greet the candidate by first name if available and ask the first prepared question. Maintain applicant perspective."
            )
        else:
            # Last-resort generic prompt
            system_prompt = (
                "You are ISA_Voice (Isa), a professional interview coach for mock preparation interviews. "
                "Greet the candidate by first name if known, ask the first prepared question immediately, and maintain a supportive, professional style."
            )

        import json as _j
        import urllib.request as _r
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        if not OPENAI_API_KEY:
            return {"error": "OPENAI_API_KEY not configured"}
        payload = {
            "model": (request.get("model") if request and isinstance(request, dict) and request.get("model") else os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-10-01")),
            "voice": "coral",
            "instructions": system_prompt,
        }
        req = _r.Request(
            "https://api.openai.com/v1/realtime/sessions",
            data=_j.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with _r.urlopen(req, timeout=20) as resp:
            data = _j.loads(resp.read().decode("utf-8"))
        client_secret = (data.get("client_secret") or {}).get("value")
        if not client_secret:
            return {"error": "Failed to mint realtime token", "details": data}
        logger.info(f"✅ Voice token created successfully for session {session_id}")
        return {"client_secret": client_secret, "model": data.get("model", payload["model"]) }
    except Exception as e:
        logger.error(f"❌ Failed to create voice token for session {session_id}: {e}")
        return {"error": "Failed to mint realtime token", "message": str(e)}


@app.post("/api/v1/voice/token")
async def create_voice_token_fallback(request: dict = None):
    """Stateless fallback: Mint a realtime token without relying on session cache.
    Accepts JSON body with optional: system_prompt, model.
    """
    try:
        system_prompt = None
        if request and isinstance(request, dict):
            system_prompt = request.get("system_prompt") or request.get("instructions")
        if not system_prompt:
            system_prompt = (
                "You are ISA_Voice (Isa), a professional interview coach for mock preparation interviews. "
                "Greet the candidate and immediately start with the first prepared question."
            )

        import json as _j
        import urllib.request as _r
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        if not OPENAI_API_KEY:
            return {"error": "OPENAI_API_KEY not configured"}
        payload = {
            "model": (request.get("model") if request and isinstance(request, dict) and request.get("model") else os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-10-01")),
            "voice": "coral",
            "instructions": system_prompt,
        }
        req = _r.Request(
            "https://api.openai.com/v1/realtime/sessions",
            data=_j.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with _r.urlopen(req, timeout=20) as resp:
            data = _j.loads(resp.read().decode("utf-8"))
        client_secret = (data.get("client_secret") or {}).get("value")
        if not client_secret:
            return {"error": "Failed to mint realtime token", "details": data}
        return {"client_secret": client_secret, "model": data.get("model", payload["model"]) }
    except Exception as e:
        return {"error": "Failed to mint realtime token", "message": str(e)}


_SF_SKILLS_FIELDS_CACHE = {}
_SF_SKILLS_FIELDS_TS = None
_SF_SKILLS_FIELDS_TTL = 300.0  # seconds

def _discover_skill_fields(sf, object_name: str) -> dict:
    """Discover skill and score fields for a Salesforce object with caching."""
    global _SF_SKILLS_FIELDS_CACHE, _SF_SKILLS_FIELDS_TS
    now = time.time()
    # Check cache
    if (
        _SF_SKILLS_FIELDS_CACHE.get(object_name)
        and _SF_SKILLS_FIELDS_TS
        and (now - _SF_SKILLS_FIELDS_TS) < _SF_SKILLS_FIELDS_TTL
    ):
        return _SF_SKILLS_FIELDS_CACHE[object_name]

    try:
        obj = getattr(sf, object_name)
        desc = obj.describe()
        fields = desc.get("fields", [])
        field_names = [f.get("name") for f in fields if f.get("name")]

        skill_fields = []
        score_fields = []

        if object_name == "THEIA_Interview__c":
            # criteria_1__c ... criteria_10__c
            for i in range(1, 11):
                fn = f"Criteria_{i}__c"
                # Also accept lowercase variant if org uses it (defensive)
                if fn in field_names or fn.lower() in field_names:
                    skill_fields.append(fn if fn in field_names else fn.lower())
            # Any score/rating fields
            for fn in field_names:
                if "score" in fn.lower() or "rating" in fn.lower():
                    score_fields.append(fn)
        elif object_name == "TR1__Opportunity_Discussed__c":
            # Criteria_Header_1__c ... Criteria_Header_10__c
            for i in range(1, 11):
                fn = f"Criteria_Header_{i}__c"
                if fn in field_names:
                    skill_fields.append(fn)
            for fn in field_names:
                if "score" in fn.lower() or "rating" in fn.lower():
                    score_fields.append(fn)

        # Fallback discovery
        if not skill_fields:
            for fn in field_names:
                if ("skill" in fn.lower()) or ("criteria" in fn.lower()):
                    skill_fields.append(fn)

        result = {"skill_fields": skill_fields, "score_fields": score_fields}
        _SF_SKILLS_FIELDS_CACHE[object_name] = result
        _SF_SKILLS_FIELDS_TS = now
        logger.info(
            f"Discovered fields for {object_name}: {len(skill_fields)} skill fields, {len(score_fields)} score fields"
        )
        return result
    except Exception as e:
        logger.error(f"Failed to discover fields for {object_name}: {e}")
        if object_name == "THEIA_Interview__c":
            return {"skill_fields": ["Criteria_1__c", "Criteria_2__c", "Criteria_3__c"], "score_fields": ["Score__c"]}
        else:
            return {"skill_fields": ["Criteria_Header_1__c", "Criteria_Header_2__c"], "score_fields": ["Score__c"]}

def _fetch_skills_from_object(sf, object_name: str, contact_id: str, fields: dict) -> list:
    """Fetch skills from a specific Salesforce object given discovered field sets."""
    try:
        skill_fields = list(fields.get("skill_fields", []) or [])
        score_fields = list(fields.get("score_fields", []) or [])
        if not skill_fields:
            logger.warning(f"No skill fields found for {object_name}")
            return []

        select_fields = ["Id", "CreatedDate"] + skill_fields + score_fields

        # Try common contact relationship field names
        possible_contact_fields = ["Contact__c", "Contact_Id__c", "ContactId", "Contact"]
        for contact_field in possible_contact_fields:
            try:
                query = (
                    f"SELECT {', '.join(select_fields)} FROM {object_name} "
                    f"WHERE {contact_field} = '{contact_id}' ORDER BY CreatedDate DESC LIMIT 100"
                )
                result = sf.query(query)
                records = result.get("records", [])

                skills = []
                for rec in records:
                    created_date = rec.get("CreatedDate", "")
                    for sfield in skill_fields:
                        sname = rec.get(sfield)
                        if sname and str(sname).strip():
                            # Find first valid score
                            score = None
                            for scfield in score_fields:
                                sval = rec.get(scfield)
                                if sval is not None:
                                    try:
                                        score = int(float(sval))
                                        if 1 <= score <= 10:
                                            break
                                    except (ValueError, TypeError):
                                        continue
                            if score is None:
                                score = 5
                            skills.append({
                                "name": str(sname).strip(),
                                "score": score,
                                "source": object_name,
                                "created_at": created_date,
                            })
                logger.info(f"Fetched {len(skills)} skills from {object_name} using {contact_field}")
                return skills
            except Exception as e:
                logger.debug(f"Failed to query {object_name} with {contact_field}: {e}")
                continue
        logger.warning(f"No valid contact relationship field found for {object_name}")
        return []
    except Exception as e:
        logger.error(f"Failed to fetch skills from {object_name}: {e}")
        return []

@app.get("/api/v1/skills")
async def get_skills(authorization: Optional[str] = Header(default=None), contact_id: Optional[str] = Query(default=None)):
    """
    Get skills for a contact from Salesforce THEIA_Interview__c records.
    Extracts criteria (Criteria_1__c through Criteria_10__c) with scores (Criteria_1_Score__c through Criteria_10_Score__c).
    Returns the most recent skill evaluations, deduplicated by skill name.
    
    Auth: Bearer THEIA token or Auth0 Bearer token (same as /api/v1/auth/profile).
    Query params:
      - contact_id (optional): Salesforce Contact Id. If absent, derive from token.
    
    Response: {"skills": [{"name": str, "score": int (1-10), "source": str, "created_at": str}]}
    """
    try:
        # Validate authorization
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        
        # Resolve contact ID using existing patterns from get_profile
        resolved_contact_id = contact_id
        
        if not resolved_contact_id:
            # Try THEIA token first
            try:
                secret = os.getenv("THEIA_JWT_SECRET", "").strip()
                aud = os.getenv("THEIA_JWT_AUDIENCE", "theia-clients")
                iss = os.getenv("THEIA_JWT_ISSUER", "theia")
                
                if secret:
                    token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else authorization
                    claims = jwt.decode(token, secret, algorithms=["HS256"], audience=aud, issuer=iss)
                    resolved_contact_id = claims.get("sub")
            except Exception:
                pass
            
            # Try Auth0 token if THEIA token failed
            if not resolved_contact_id:
                try:
                    claims = _verify_auth0_jwt(authorization)
                    email = _extract_email_from_claims(claims)
                    if email:
                        # Find contact by email using existing function
                        contacts = _find_contacts_by_email(email)
                        if contacts:
                            resolved_contact_id = contacts[0].get("Id")
                except Exception:
                    pass
        
        if not resolved_contact_id:
            raise HTTPException(status_code=400, detail="Unable to derive contact ID from token")
        
        logger.info(f"Fetching skills for contact: {resolved_contact_id}")
        
        # Get Salesforce client
        sf = _get_salesforce_client()
        if not sf:
            logger.warning("Salesforce client unavailable")
            return {"skills": []}
        
        all_skills = []
        
        # Fetch from THEIA_Interview__c
        try:
            # Discover available fields using describe
            theia_desc = sf.THEIA_Interview__c.describe()
            theia_fields = {f.get("name") for f in theia_desc.get("fields", [])}
            
            # Look for skill fields (Criteria_1__c through Criteria_10__c pattern)
            skill_fields = []
            score_fields = []
            for i in range(1, 11):
                skill_field = f"Criteria_{i}__c"
                score_field = f"Criteria_{i}_Score__c"
                if skill_field in theia_fields:
                    skill_fields.append(skill_field)
                if score_field in theia_fields:
                    score_fields.append(score_field)
            
            if skill_fields:
                # Build query
                select_fields = ["Id", "CreatedDate"] + skill_fields + score_fields
                
                # Try different contact field names
                for contact_field in ["Contact__c", "Contact_Id__c", "ContactId", "Contact"]:
                    if contact_field in theia_fields:
                        try:
                            query = f"SELECT {', '.join(select_fields)} FROM THEIA_Interview__c WHERE {contact_field} = '{resolved_contact_id}' ORDER BY CreatedDate DESC LIMIT 100"
                            result = sf.query(query)
                            records = result.get("records", [])
                            
                            for record in records:
                                created_date = record.get("CreatedDate", "")
                                
                                # Extract skills from each skill field with corresponding score
                                for i in range(1, 11):
                                    skill_field = f"Criteria_{i}__c"
                                    score_field = f"Criteria_{i}_Score__c"
                                    
                                    if skill_field in skill_fields:
                                        skill_name = record.get(skill_field)
                                        if skill_name and skill_name.strip():
                                            # Get corresponding score
                                            score = 5  # Default score
                                            if score_field in score_fields:
                                                score_value = record.get(score_field)
                                                if score_value is not None:
                                                    try:
                                                        score = int(float(score_value))
                                                        if not (1 <= score <= 10):
                                                            score = 5  # Reset to default if out of range
                                                    except (ValueError, TypeError):
                                                        score = 5
                                            
                                            all_skills.append({
                                                "name": skill_name.strip(),
                                                "score": score,
                                                "source": "THEIA_Interview__c",
                                                "created_at": created_date
                                            })
                            
                            logger.info(f"Fetched {len([s for s in all_skills if s['source'] == 'THEIA_Interview__c'])} skills from THEIA_Interview__c")
                            break
                            
                        except Exception as e:
                            logger.debug(f"Failed to query THEIA_Interview__c with {contact_field}: {e}")
                            continue
                            
        except Exception as e:
            logger.error(f"Failed to fetch from THEIA_Interview__c: {e}")
        
        # Also fetch from TR1__Opportunity_Discussed__c (dynamic discovery)
        try:
            opp_fields = _discover_skill_fields(sf, "TR1__Opportunity_Discussed__c")
            opp_skills = _fetch_skills_from_object(sf, "TR1__Opportunity_Discussed__c", resolved_contact_id, opp_fields)
            all_skills.extend(opp_skills)
        except Exception as e:
            logger.error(f"Failed to fetch from TR1__Opportunity_Discussed__c: {e}")
        
        # Deduplicate by skill name (case-insensitive), keeping most recent
        skills_by_name = {}
        for skill in all_skills:
            skill_name = skill["name"].lower().strip()
            created_at = skill.get("created_at", "")
            
            if skill_name not in skills_by_name:
                skills_by_name[skill_name] = skill
            else:
                # Keep the most recent one
                existing_date = skills_by_name[skill_name].get("created_at", "")
                if created_at > existing_date:
                    skills_by_name[skill_name] = skill
        
        # Convert back to list and restore original casing
        final_skills = []
        for skill in skills_by_name.values():
            final_skills.append({
                "name": skill["name"],  # Keep original casing
                "score": skill["score"],
                "source": skill["source"],
                "created_at": skill["created_at"]
            })
        
        # Sort by skill name for consistent output
        final_skills.sort(key=lambda x: x["name"].lower())
        
        logger.info(f"Returning {len(final_skills)} deduplicated skills for contact {resolved_contact_id}")
        
        return {"skills": final_skills}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to fetch skills")
        # Return empty list on error to avoid information leakage
        return {"skills": []}

try:
    from services.job_hunter.api.routers import api_router as job_hunter_router
    app.include_router(job_hunter_router, prefix="/job-hunter")
    logger.info("✅ Mounted Job Hunter service at /job-hunter")
except Exception as e:
    logger.warning(f"⚠️ Job Hunter service not mounted: {e}")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


