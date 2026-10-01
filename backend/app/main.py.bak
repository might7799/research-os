import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal
from urllib.parse import quote, urlparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.auth import generate_api_token, hash_password, verify_password
from app.database import get_connection, init_db
from app.security import decode_token, decode_token_value

app = FastAPI(title="Research OS", version="1.4.0")
init_db()


class SearchResult(BaseModel):
    title: str
    source: str
    year: int | None = None
    url: str | None = None
    authors: List[str] = Field(default_factory=list)
    doi: str | None = None
    abstract: str | None = None
    citation_count: int | None = None
    source_id: str | None = None


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    email: str
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserProfile(BaseModel):
    id: int
    username: str
    email: str


class SearchHistoryEntry(BaseModel):
    id: int
    query: str
    results: str
    created_at: str


class ClaimCreate(BaseModel):
    claim_text: str = Field(..., min_length=1)
    status: Literal["draft", "active", "resolved", "disputed"] = "draft"
    workspace_id: int | None = None


class EvidenceCreate(BaseModel):
    source_id: str | None = None
    source_title: str = Field(..., min_length=1)
    authors: List[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    excerpt: str | None = None
    evidence_type: Literal["abstract", "full_text"]
    relation: Literal["supporting", "contradicting", "uncertain"] = "uncertain"
    confidence: float | None = Field(default=None, ge=0, le=1)
    workspace_id: int | None = None


class EvidenceLink(BaseModel):
    evidence_id: int


class ClaimRelationCreate(BaseModel):
    target_claim_id: int
    relation: Literal["supports", "contradicts", "qualifies", "depends_on"]
    workspace_id: int | None = None


class WorkspaceCreate(BaseModel):
    title: str = Field(..., min_length=1)
    research_question: str = Field(..., min_length=1)
    notes: str | None = None


class WorkspaceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    research_question: str | None = Field(default=None, min_length=1)
    notes: str | None = None


class CouncilInputContract(BaseModel):
    workspace: Dict[str, Any]
    search_history: Dict[str, Any]
    claims: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    claim_relations: List[Dict[str, Any]]
    critic: List[Dict[str, Any]]
    summary: Dict[str, int]


class ConflictAnalysis(BaseModel):
    conflict_id: str
    conflict_type: Literal[
        "evidence_conflict",
        "claim_relation_conflict",
        "mixed_conflict",
    ]
    workspace_id: int
    claim_ids: List[int] = Field(default_factory=list)
    evidence_ids: List[int] = Field(default_factory=list)
    relation_ids: List[int] = Field(default_factory=list)
    supporting_evidence_ids: List[int] = Field(default_factory=list)
    contradicting_evidence_ids: List[int] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)
    description_structural: str
    traceability: Dict[str, Any]


class ConflictAnalysisResponse(BaseModel):
    workspace_id: int
    conflicts: List[ConflictAnalysis] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)


class DecisionAnalysis(BaseModel):
    decision_id: str
    workspace_id: int
    claim_id: int
    claim_text: str
    decision_status: Literal[
        "insufficient_evidence",
        "unsupported",
        "conflicting",
        "structurally_supported",
    ]
    reason_code: Literal[
        "no_linked_evidence",
        "no_supporting_evidence",
        "conflict_detected",
        "supporting_evidence_without_conflict",
    ]
    critic_status: str | None = None
    evidence_ids: List[int] = Field(default_factory=list)
    supporting_evidence_ids: List[int] = Field(default_factory=list)
    contradicting_evidence_ids: List[int] = Field(default_factory=list)
    uncertain_evidence_ids: List[int] = Field(default_factory=list)
    conflict_ids: List[str] = Field(default_factory=list)
    relation_ids: List[int] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)
    missing_source_evidence_ids: List[int] = Field(default_factory=list)
    traceability: Dict[str, Any]


class DecisionAnalysisResponse(BaseModel):
    workspace_id: int
    decisions: List[DecisionAnalysis] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)


class SynthesisTraceability(BaseModel):
    claim_ids: List[int] = Field(default_factory=list)
    decision_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[int] = Field(default_factory=list)
    conflict_ids: List[str] = Field(default_factory=list)
    relation_ids: List[int] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)


class ClaimSynthesis(BaseModel):
    claim_id: int
    claim_text: str
    decision_id: str
    decision_status: Literal[
        "insufficient_evidence",
        "unsupported",
        "conflicting",
        "structurally_supported",
    ]
    critic_status: str | None = None
    supporting_evidence_ids: List[int] = Field(default_factory=list)
    contradicting_evidence_ids: List[int] = Field(default_factory=list)
    uncertain_evidence_ids: List[int] = Field(default_factory=list)
    conflict_ids: List[str] = Field(default_factory=list)
    relation_ids: List[int] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)
    synthesis_status: Literal[
        "insufficient_evidence",
        "unsupported",
        "supported_with_conflict",
        "structurally_supported",
        "unresolved",
    ]
    synthesis_statement: str
    limitations: List[str] = Field(default_factory=list)
    traceability: SynthesisTraceability


class SynthesisSummary(BaseModel):
    claim_count: int
    evidence_count: int
    conflict_count: int
    decision_counts: Dict[str, int]
    unlinked_evidence_ids: List[int] = Field(default_factory=list)


class SynthesisAnalysis(BaseModel):
    synthesis_id: str
    workspace_id: int
    research_question: str
    claim_syntheses: List[ClaimSynthesis] = Field(default_factory=list)
    overall_status: Literal[
        "insufficient_evidence",
        "unsupported",
        "supported_with_conflict",
        "structurally_supported",
        "unresolved",
    ]
    summary: SynthesisSummary
    traceability: SynthesisTraceability


class VerificationCheck(BaseModel):
    name: str
    status: Literal["passed", "failed", "not_checked", "not_available"]
    evidence: str
    provenance: List[str] = Field(default_factory=list)
    reference: Dict[str, Any] = Field(default_factory=dict)


class ExternalProvenance(BaseModel):
    provider: str
    provider_record: str
    checked_at: str | None = None
    request_target: str | None = None
    verification_type: str
    status: str
    error: str | None = None


class VerificationFinding(BaseModel):
    finding_type: str
    status: Literal[
        "passed",
        "failed",
        "detected",
        "not_checked",
        "not_available",
    ]
    provider: str
    message: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    provenance: ExternalProvenance


class SourceVerification(BaseModel):
    source_key: str
    source_id: str | None = None
    title: str
    authors: List[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    evidence_ids: List[int] = Field(default_factory=list)
    claim_ids: List[int] = Field(default_factory=list)
    verification_status: Literal[
        "verified",
        "partially_verified",
        "insufficiently_verified",
        "unverified",
    ]
    verification_checks: List[VerificationCheck] = Field(default_factory=list)
    verification_findings: List[VerificationFinding] = Field(default_factory=list)
    external_provenance: List[ExternalProvenance] = Field(default_factory=list)
    verification_flags: List[str] = Field(default_factory=list)
    traceability: Dict[str, Any]


class SourceVerificationResponse(BaseModel):
    workspace_id: int
    sources: List[SourceVerification] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)


class EvidenceQualityFinding(BaseModel):
    dimension: str
    status: Literal["passed", "failed", "not_available", "not_assessed"]
    value: Any = None
    message: str
    provenance: List[str] = Field(default_factory=list)


class EvidenceQualityAssessment(BaseModel):
    evidence_id: int
    claim_ids: List[int] = Field(default_factory=list)
    source_key: str | None = None
    source_verification_status: str | None = None
    source_verification_findings: List[VerificationFinding] = Field(default_factory=list)
    quality_assessment_status: Literal[
        "assessable",
        "partially_assessable",
        "insufficient_information",
        "not_assessed",
    ]
    traceability_status: Literal["strong", "partial", "insufficient"]
    linkage_status: Literal["linked_to_claim", "linked_to_multiple_claims", "unlinked"]
    relation: Literal["supporting", "contradicting", "uncertain"]
    evidence_type: Literal["abstract", "full_text"]
    confidence: float | None = None
    confidence_status: Literal["recorded", "not_provided"]
    findings: List[EvidenceQualityFinding] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    traceability: Dict[str, Any]


class EvidenceQualityResponse(BaseModel):
    workspace_id: int
    assessments: List[EvidenceQualityAssessment] = Field(default_factory=list)
    unlinked_evidence: List[EvidenceQualityAssessment] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)


class ExtractionSourceLocation(BaseModel):
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    paragraph: int | None = Field(default=None, ge=1)
    offset: str | None = None
    locator: str | None = None
    status: Literal["available", "not_available"] = "not_available"


class ExtractionRawInputReference(BaseModel):
    reference_type: Literal["evidence_excerpt", "source_location", "not_available"]
    reference: str | None = None
    status: Literal["available", "not_available"]


class ExtractionProvenance(BaseModel):
    source_type: Literal["evidence", "source_verification", "manual_record"]
    source_id: str | None = None
    evidence_id: int
    source_location: ExtractionSourceLocation
    extraction_method: Literal["manual", "ai"]
    created_at: str


class EvidenceExtraction(BaseModel):
    extraction_id: str
    evidence_id: int
    claim_ids: List[int] = Field(default_factory=list)
    dimension: Literal[
        "study_design",
        "sample_size",
        "population",
        "context",
        "effect_size",
        "limitations",
        "risk_of_bias_information",
    ]
    extracted_value: Any = None
    extraction_method: Literal["manual", "ai"]
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    extraction_confidence_status: Literal["recorded", "not_provided"]
    source_location: ExtractionSourceLocation
    raw_input_reference: ExtractionRawInputReference
    verification_state: Literal["not_verified", "verified", "rejected", "needs_review"]
    human_review_state: Literal["not_reviewed", "approved", "rejected", "needs_review"]
    provenance: ExtractionProvenance


class ClaimAnalysis(BaseModel):
    claim_id: int
    claim_text: str
    critic_status: Literal[
        "unsupported",
        "weakly_supported",
        "supported",
        "conflicting",
        "insufficient_evidence",
    ]
    supporting_evidence_ids: List[int] = Field(default_factory=list)
    contradicting_evidence_ids: List[int] = Field(default_factory=list)
    uncertain_evidence_ids: List[int] = Field(default_factory=list)
    related_claim_ids: List[int] = Field(default_factory=list)
    evidence_count: int = 0
    supporting_count: int = 0
    contradicting_count: int = 0
    uncertain_count: int = 0
    evidence_assessments: List["EvidenceAssessment"] = Field(default_factory=list)
    evidence_completeness_summary: Dict[str, int] = Field(default_factory=dict)
    conflict_count: int = 0
    conflicts: List[ConflictAnalysis] = Field(default_factory=list)
    conflict_types: List[str] = Field(default_factory=list)
    analysis_flags: List[str] = Field(default_factory=list)


class EvidenceAssessment(BaseModel):
    evidence_id: int
    claim_ids: List[int] = Field(default_factory=list)
    source_id: str | None = None
    source_title: str
    evidence_type: Literal["abstract", "full_text"]
    relation: Literal["supporting", "contradicting", "uncertain"]
    confidence: float | None = None
    source_reference: Dict[str, Any]
    excerpt_present: bool
    traceability: Dict[str, Any]
    assessment_flags: List[str] = Field(default_factory=list)
    completeness: Literal["complete", "partial", "insufficient_metadata"]


class EvidenceAssessmentResponse(BaseModel):
    workspace_id: int
    assessments: List[EvidenceAssessment] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)


class CouncilAnalysis(BaseModel):
    claims: List[ClaimAnalysis] = Field(default_factory=list)
    evidence: List[EvidenceAssessment] = Field(default_factory=list)
    conflicts: List[ConflictAnalysis] = Field(default_factory=list)


class CouncilFoundationResponse(BaseModel):
    input: CouncilInputContract
    analysis: CouncilAnalysis


EVIDENCE_CONFIDENCE_HIGH_THRESHOLD = 0.8
EVIDENCE_CONFIDENCE_MEDIUM_THRESHOLD = 0.4
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
DEFAULT_CROSSREF_TIMEOUT = 5.0


@dataclass
class ExternalProviderResult:
    status: str
    provider: str
    provider_record: str
    request_target: str | None
    checked_at: str | None
    metadata: Dict[str, Any]
    error: str | None = None


class CrossrefClient:
    provider = "Crossref"
    base_url = "https://api.crossref.org/works/"

    def __init__(self, timeout: float = DEFAULT_CROSSREF_TIMEOUT):
        self.timeout = timeout

    def fetch(self, doi: str) -> ExternalProviderResult:
        canonical_doi = normalize_doi(doi)
        request_target = f"{self.base_url}{quote(canonical_doi, safe='')}"
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                response = client.get(
                    request_target,
                    headers={"Accept": "application/json", "User-Agent": "Research-OS/0.2"},
                )
            if response.status_code == 404:
                return ExternalProviderResult(
                    status="not_found",
                    provider=self.provider,
                    provider_record="DOI metadata record",
                    request_target=request_target,
                    checked_at=checked_at,
                    metadata={},
                    error="Crossref did not find this DOI.",
                )
            if response.status_code == 429:
                return ExternalProviderResult(
                    status="not_checked",
                    provider=self.provider,
                    provider_record="DOI metadata record",
                    request_target=request_target,
                    checked_at=checked_at,
                    metadata={},
                    error="Crossref rate limit (HTTP 429).",
                )
            if response.status_code >= 500:
                return ExternalProviderResult(
                    status="not_checked",
                    provider=self.provider,
                    provider_record="DOI metadata record",
                    request_target=request_target,
                    checked_at=checked_at,
                    metadata={},
                    error=f"Crossref provider unavailable (HTTP {response.status_code}).",
                )
            response.raise_for_status()
            message = response.json().get("message", {})
            date_parts = (
                message.get("published-print", {}).get("date-parts")
                or message.get("published-online", {}).get("date-parts")
                or message.get("issued", {}).get("date-parts")
                or []
            )
            authors = [
                " ".join(filter(None, [author.get("given"), author.get("family")]))
                for author in message.get("author", [])
            ]
            return ExternalProviderResult(
                status="passed",
                provider=self.provider,
                provider_record="DOI metadata record",
                request_target=request_target,
                checked_at=checked_at,
                metadata={
                    "doi": normalize_doi(message.get("DOI")),
                    "title": (message.get("title") or [None])[0],
                    "authors": [author for author in authors if author],
                    "year": date_parts[0][0] if date_parts and date_parts[0] else None,
                    "container_title": (message.get("container-title") or [None])[0],
                    "publisher": message.get("publisher"),
                },
            )
        except httpx.TimeoutException:
            return ExternalProviderResult(
                status="not_checked", provider=self.provider,
                provider_record="DOI metadata record", request_target=request_target,
                checked_at=checked_at, metadata={}, error="Crossref request timed out.",
            )
        except httpx.HTTPError as error:
            return ExternalProviderResult(
                status="not_checked", provider=self.provider,
                provider_record="DOI metadata record", request_target=request_target,
                checked_at=checked_at, metadata={}, error=f"Crossref request failed: {error}.",
            )
        except (ValueError, KeyError) as error:
            return ExternalProviderResult(
                status="not_checked", provider=self.provider,
                provider_record="DOI metadata record", request_target=request_target,
                checked_at=checked_at, metadata={}, error=f"Crossref response was invalid: {error}.",
            )


class RetractionClient:
    provider = "Retraction registry unavailable"

    def check(self, doi: str) -> ExternalProviderResult:
        return ExternalProviderResult(
            status="not_checked",
            provider=self.provider,
            provider_record="Retraction/correction record",
            request_target=None,
            checked_at=None,
            metadata={},
            error="No reliable retraction or correction provider is configured.",
        )


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", "", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(
        r"^https?://(dx\.)?doi\.org/",
        "",
        value.strip(),
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"^doi:", "", normalized, flags=re.IGNORECASE)
    return normalized.lower()


def deduplicate_results(results: List[SearchResult]) -> List[SearchResult]:
    unique: Dict[str, SearchResult] = {}
    for item in results:
        key = normalize_doi(item.doi) or item.source_id or normalize_title(item.title)
        if not key:
            continue
        if key not in unique:
            unique[key] = item
    return list(unique.values())


def rank_results(results: List[SearchResult], query: str) -> List[SearchResult]:
    query_terms = set(normalize_title(query).split())
    normalized_query = normalize_title(query)

    def score(item: SearchResult) -> tuple[int, int]:
        normalized_title = normalize_title(item.title)
        title_terms = set(normalized_title.split())
        exact_phrase = int(bool(normalized_query and normalized_query in normalized_title))
        return exact_phrase, len(query_terms & title_terms)

    return [item for _, item in sorted(enumerate(results), key=lambda entry: (score(entry[1]), -entry[0]), reverse=True)]


def openalex_abstract(value: Dict[str, Any] | None) -> str | None:
    if not value:
        return None
    words = [word for position, word in sorted((position, word) for word, positions in value.items() for position in positions)]
    return " ".join(words) if words else None


async def fetch_openalex(query: str) -> List[SearchResult]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://api.openalex.org/works",
            params={"search": query, "per_page": 5, "select": "id,title,publication_year,primary_location,authorships,doi,ids,abstract_inverted_index,cited_by_count"},
        )
        response.raise_for_status()
        payload = response.json()

    results: List[SearchResult] = []
    for item in payload.get("results", [])[:5]:
        title = item.get("title") or "Untitled"
        loc = (item.get("primary_location") or {})
        doi = normalize_doi(item.get("doi")) or None
        url = loc.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else item.get("id"))
        year = item.get("publication_year")
        authors = [author.get("author", {}).get("display_name") for author in item.get("authorships", [])]
        results.append(SearchResult(
            title=title,
            source="OpenAlex",
            year=year,
            url=url,
            authors=[author for author in authors if author],
            doi=doi,
            abstract=openalex_abstract(item.get("abstract_inverted_index")),
            citation_count=item.get("cited_by_count"),
            source_id=item.get("id"),
        ))
    return results


async def fetch_semantic_scholar(query: str) -> List[SearchResult]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": 5,
                "fields": "title,year,url,externalIds,authors,abstract,citationCount,paperId",
                "sort": "relevance",
            },
        )
        response.raise_for_status()
        payload = response.json()

    results: List[SearchResult] = []
    for item in payload.get("data", [])[:5]:
        title = item.get("title") or "Untitled"
        year = item.get("year")
        external_ids = item.get("externalIds") or {}
        doi = normalize_doi(external_ids.get("DOI")) or None
        url = item.get("url") or (f"https://doi.org/{doi}" if doi else None)
        results.append(SearchResult(
            title=title,
            source="Semantic Scholar",
            year=year,
            url=url,
            authors=[author.get("name") for author in item.get("authors", []) if author.get("name")],
            doi=doi,
            abstract=item.get("abstract"),
            citation_count=item.get("citationCount"),
            source_id=item.get("paperId"),
        ))
    return results


async def fetch_crossref(query: str) -> List[SearchResult]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://api.crossref.org/works",
            params={"query.title": query, "rows": 5, "select": "title,URL,issued,author,DOI,abstract,is-referenced-by-count"},
        )
        response.raise_for_status()
        payload = response.json()

    results: List[SearchResult] = []
    for item in payload.get("message", {}).get("items", [])[:5]:
        title = item.get("title", ["Untitled"])[0]
        doi = normalize_doi(item.get("DOI")) or None
        url = item.get("URL") or (f"https://doi.org/{doi}" if doi else None)
        issued = item.get("issued", {})
        year = None
        if issued and "date-parts" in issued and issued["date-parts"]:
            year = issued["date-parts"][0][0]
        results.append(SearchResult(
            title=title,
            source="Crossref",
            year=year,
            url=url,
            authors=[" ".join(part for part in (author.get("given"), author.get("family")) if part) for author in item.get("author", []) if author.get("given") or author.get("family")],
            doi=doi,
            abstract=item.get("abstract"),
            citation_count=item.get("is-referenced-by-count"),
            source_id=doi,
        ))
    return results


async def fetch_source_safely(source_name: str, fetcher, query: str) -> tuple[str, List[SearchResult], str | None]:
    try:
        return source_name, await fetcher(query), None
    except Exception:
        return source_name, [], "Source unavailable"


def get_user_by_username(username: str) -> Dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_api_token(token: str) -> Dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE api_token = ?",
            (token,),
        ).fetchone()
    return dict(row) if row else None


def get_current_user(user_token: str = Depends(decode_token)) -> Dict[str, Any]:
    user = get_user_by_username(user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def get_owned_workspace(user_id: int, workspace_id: int) -> Dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM research_workspaces WHERE id = ? AND user_id = ?",
            (workspace_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found or not owned by user")
    return dict(row)


def evidence_from_row(row: Any) -> Dict[str, Any]:
    item = dict(row)
    try:
        item["authors"] = json.loads(item["authors"])
    except (TypeError, json.JSONDecodeError):
        item["authors"] = []
    return item


def claim_response(user_id: int, claim_id: int) -> Dict[str, Any]:
    with get_connection() as conn:
        claim = conn.execute(
            "SELECT id, claim_text, status, workspace_id, created_at FROM claims WHERE id = ? AND user_id = ?",
            (claim_id, user_id),
        ).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        evidence_rows = conn.execute(
            """
            SELECT e.* FROM evidence e
            JOIN claim_evidence ce ON ce.evidence_id = e.id
            WHERE ce.claim_id = ? AND e.user_id = ?
            ORDER BY e.id
            """,
            (claim_id, user_id),
        ).fetchall()

    evidence = [evidence_from_row(row) for row in evidence_rows]
    return {
        **dict(claim),
        "evidence_ids": [item["id"] for item in evidence],
        "evidence": evidence,
    }


def claim_relation_response(relation_row: Any) -> Dict[str, Any]:
    row = dict(relation_row)
    return {
        "id": row["id"],
        "source_claim_id": row["source_claim_id"],
        "target_claim_id": row["target_claim_id"],
        "relation": row["relation"],
        "created_at": row["created_at"],
        "workspace_id": row.get("workspace_id"),
    }


def workspace_response(user_id: int, workspace_id: int) -> Dict[str, Any]:
    workspace = get_owned_workspace(user_id, workspace_id)
    with get_connection() as conn:
        search_rows = conn.execute(
            "SELECT id, query, results, created_at, workspace_id FROM searches WHERE id IS NOT NULL AND user_id = ? AND workspace_id = ? ORDER BY created_at DESC",
            (user_id, workspace_id),
        ).fetchall()
        claim_rows = conn.execute(
            "SELECT id FROM claims WHERE user_id = ? AND workspace_id = ? ORDER BY created_at",
            (user_id, workspace_id),
        ).fetchall()
        evidence_rows = conn.execute(
            "SELECT * FROM evidence WHERE user_id = ? AND workspace_id = ? ORDER BY created_at",
            (user_id, workspace_id),
        ).fetchall()
        relation_rows = conn.execute(
            "SELECT * FROM claim_relations WHERE user_id = ? AND workspace_id = ? ORDER BY created_at",
            (user_id, workspace_id),
        ).fetchall()

    claims = []
    for row in claim_rows:
        claim_id = row["id"]
        claim = claim_response(user_id, claim_id)
        claim["relations"] = [
            claim_relation_response(relation)
            for relation in relation_rows
            if relation["source_claim_id"] == claim_id or relation["target_claim_id"] == claim_id
        ]
        claim["critic"] = claim_critic_response(user_id, claim_id)
        claims.append(claim)

    return {
        **workspace,
        "searches": [dict(row) for row in search_rows],
        "claims": claims,
        "evidence": [evidence_from_row(row) for row in evidence_rows],
        "claim_relations": [claim_relation_response(row) for row in relation_rows],
        "summary": {
            "search_count": len(search_rows),
            "claim_count": len(claims),
            "evidence_count": len(evidence_rows),
            "claim_relation_count": len(relation_rows),
        },
    }


def research_memory_response(user_id: int, workspace_id: int) -> Dict[str, Any]:
    workspace_view = workspace_response(user_id, workspace_id)
    claims = workspace_view["claims"]
    return {
        "workspace": {
            "id": workspace_view["id"],
            "title": workspace_view["title"],
            "research_question": workspace_view["research_question"],
            "notes": workspace_view.get("notes"),
            "created_at": workspace_view["created_at"],
            "updated_at": workspace_view["updated_at"],
        },
        "search_history": {
            "count": len(workspace_view["searches"]),
            "items": workspace_view["searches"],
        },
        "claims": claims,
        "evidence": workspace_view["evidence"],
        "claim_relations": workspace_view["claim_relations"],
        "critic": [
            {
                "claim_id": claim["id"],
                "audit_status": claim["critic"]["audit_status"],
                "issues": claim["critic"]["issues"],
            }
            for claim in claims
        ],
        "summary": workspace_view["summary"],
    }


def council_input_from_memory(memory: Dict[str, Any]) -> CouncilInputContract:
    return CouncilInputContract.model_validate(memory)


def evidence_source_reference(evidence: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_id": evidence.get("source_id"),
        "source_title": evidence.get("source_title"),
        "doi": evidence.get("doi"),
        "url": evidence.get("url"),
    }


def evidence_assessment_from_input(
    evidence: Dict[str, Any], claim_ids: List[int],
) -> EvidenceAssessment:
    source_reference = evidence_source_reference(evidence)
    source_reference_present = bool(
        evidence.get("source_id") or evidence.get("doi") or evidence.get("url")
    )
    excerpt_present = bool(evidence.get("excerpt"))
    flags = [
        evidence["relation"],
        evidence["evidence_type"],
    ]
    if evidence.get("confidence") is not None:
        confidence = float(evidence["confidence"])
        if confidence >= EVIDENCE_CONFIDENCE_HIGH_THRESHOLD:
            flags.append("high_confidence")
        elif confidence >= EVIDENCE_CONFIDENCE_MEDIUM_THRESHOLD:
            flags.append("medium_confidence")
        else:
            flags.append("low_confidence")
    if source_reference_present:
        flags.append("source_reference_present")
    if excerpt_present:
        flags.append("excerpt_present")
    if claim_ids:
        flags.append("linked_to_claim")
    if len(claim_ids) > 1:
        flags.append("linked_to_multiple_claims")

    required_fields_present = all([
        source_reference_present,
        bool(evidence.get("relation")),
        bool(evidence.get("evidence_type")),
        excerpt_present,
    ])
    if required_fields_present:
        completeness = "complete"
    elif not source_reference_present or not evidence.get("relation") or not evidence.get("evidence_type"):
        completeness = "insufficient_metadata"
    else:
        completeness = "partial"

    return EvidenceAssessment(
        evidence_id=evidence["id"],
        claim_ids=sorted(set(claim_ids)),
        source_id=evidence.get("source_id"),
        source_title=evidence.get("source_title", ""),
        evidence_type=evidence["evidence_type"],
        relation=evidence["relation"],
        confidence=evidence.get("confidence"),
        source_reference=source_reference,
        excerpt_present=excerpt_present,
        traceability={
            "evidence_id": evidence["id"],
            "claim_ids": sorted(set(claim_ids)),
            "source_id": evidence.get("source_id"),
        },
        assessment_flags=flags,
        completeness=completeness,
    )


def evidence_assessments_from_input(
    council_input: CouncilInputContract,
) -> List[EvidenceAssessment]:
    claim_ids_by_evidence: Dict[int, List[int]] = {
        evidence["id"]: [] for evidence in council_input.evidence
    }
    for claim in council_input.claims:
        for evidence_id in claim.get("evidence_ids", []):
            if evidence_id in claim_ids_by_evidence:
                claim_ids_by_evidence[evidence_id].append(claim["id"])
    return [
        evidence_assessment_from_input(
            evidence,
            claim_ids_by_evidence[evidence["id"]],
        )
        for evidence in council_input.evidence
    ]


def source_key_for_evidence(evidence: Dict[str, Any]) -> str:
    doi = normalize_doi(evidence.get("doi"))
    if doi:
        return f"doi:{doi}"
    if evidence.get("source_id"):
        return f"source_id:{evidence['source_id']}"
    if evidence.get("url"):
        return f"url:{evidence['url'].strip().rstrip('/').lower()}"
    return f"evidence:{evidence['id']}"


def normalized_url(value: str | None) -> str:
    return value.strip().rstrip("/").lower() if value else ""


def search_result_matches(
    evidence: Dict[str, Any], search_result: Dict[str, Any],
) -> bool:
    evidence_doi = normalize_doi(evidence.get("doi"))
    result_doi = normalize_doi(search_result.get("doi"))
    if evidence_doi and result_doi:
        return evidence_doi == result_doi
    if evidence.get("source_id") and search_result.get("source_id"):
        return evidence["source_id"] == search_result["source_id"]
    if evidence.get("url") and search_result.get("url"):
        return normalized_url(evidence["url"]) == normalized_url(search_result["url"])
    return normalize_title(evidence.get("source_title")) == normalize_title(search_result.get("title"))


def search_candidates_from_input(council_input: CouncilInputContract) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for search in council_input.search_history.get("items", []):
        try:
            results = json.loads(search.get("results", "[]"))
        except (TypeError, json.JSONDecodeError):
            continue
        for result in results:
            candidates.append({
                "search_id": search.get("id"),
                "source": result.get("source"),
                "result": result,
            })
    return candidates


def external_provenance_from_result(
    result: ExternalProviderResult,
    verification_type: str,
) -> ExternalProvenance:
    return ExternalProvenance(
        provider=result.provider,
        provider_record=result.provider_record,
        checked_at=result.checked_at,
        request_target=result.request_target,
        verification_type=verification_type,
        status=result.status,
        error=result.error,
    )


def external_finding(
    result: ExternalProviderResult,
    finding_type: str,
    verification_type: str,
    message: str,
    evidence: Dict[str, Any] | None = None,
) -> VerificationFinding:
    return VerificationFinding(
        finding_type=finding_type,
        status=("failed" if result.status == "not_found" else result.status),
        provider=result.provider,
        message=message,
        evidence=evidence or {},
        provenance=external_provenance_from_result(result, verification_type),
    )


def crossref_bibliographic_finding(
    evidence: Dict[str, Any],
    result: ExternalProviderResult,
) -> VerificationFinding:
    metadata = result.metadata
    fields: Dict[str, str] = {}
    evidence_doi = normalize_doi(evidence.get("doi"))
    fields["doi"] = "matched" if evidence_doi and evidence_doi == metadata.get("doi") else "mismatched"
    if evidence.get("source_title") and metadata.get("title"):
        fields["title"] = (
            "matched"
            if normalize_title(evidence["source_title"]) == normalize_title(metadata["title"])
            else "mismatched"
        )
    else:
        fields["title"] = "not_available"
    evidence_authors = {normalize_title(author) for author in evidence.get("authors", [])}
    metadata_authors = {normalize_title(author) for author in metadata.get("authors", [])}
    if evidence_authors and metadata_authors:
        fields["authors"] = "matched" if evidence_authors == metadata_authors else "mismatched"
    else:
        fields["authors"] = "not_available"
    if evidence.get("year") is not None and metadata.get("year") is not None:
        fields["year"] = "matched" if evidence["year"] == metadata["year"] else "mismatched"
    else:
        fields["year"] = "not_available"
    status = "passed" if result.status == "passed" and all(value != "mismatched" for value in fields.values()) else "failed"
    return external_finding(
        result,
        "bibliographic_match",
        "bibliographic_metadata",
        "Crossref metadata was compared with local source metadata.",
        {"fields": fields, "crossref_metadata": metadata},
    ).model_copy(update={"status": status})


def source_verification_from_group(
    evidence_items: List[Dict[str, Any]],
    claim_ids: List[int],
    search_candidates: List[Dict[str, Any]],
    crossref_client: CrossrefClient | None = None,
    retraction_client: RetractionClient | None = None,
) -> SourceVerification:
    evidence_items = sorted(evidence_items, key=lambda item: item["id"])
    primary = evidence_items[0]
    source_key = source_key_for_evidence(primary)
    evidence_ids = [item["id"] for item in evidence_items]
    source_ids = sorted({item["source_id"] for item in evidence_items if item.get("source_id")})
    matching_candidates = [
        candidate for candidate in search_candidates
        if any(search_result_matches(item, candidate["result"]) for item in evidence_items)
    ]
    checks: List[VerificationCheck] = []

    checks.append(VerificationCheck(
        name="source_record",
        status="passed",
        evidence="A source record is present in workspace evidence metadata.",
        provenance=[f"evidence:{evidence_id}" for evidence_id in evidence_ids],
        reference={"evidence_ids": evidence_ids},
    ))
    title_present = bool(primary.get("source_title"))
    checks.append(VerificationCheck(
        name="title_presence",
        status="passed" if title_present else "failed",
        evidence="Source title is present." if title_present else "Source title is missing.",
        provenance=[f"evidence:{evidence_ids[0]}"],
        reference={"evidence_ids": evidence_ids},
    ))
    reference_present = bool(primary.get("source_id") or primary.get("doi") or primary.get("url"))
    checks.append(VerificationCheck(
        name="source_reference_presence",
        status="passed" if reference_present else "failed",
        evidence="At least one source reference is present." if reference_present else "No source reference is present.",
        provenance=[f"evidence:{evidence_ids[0]}"],
        reference={"source_id": primary.get("source_id"), "doi": primary.get("doi"), "url": primary.get("url")},
    ))

    doi = primary.get("doi")
    doi_present = bool(doi)
    checks.append(VerificationCheck(
        name="doi_presence",
        status="passed" if doi_present else "not_checked",
        evidence="DOI is present in source metadata." if doi_present else "DOI is not available in source metadata.",
        provenance=[f"evidence:{evidence_ids[0]}"],
        reference={"doi": doi},
    ))
    doi_format_valid = bool(doi and DOI_PATTERN.match(normalize_doi(doi)))
    checks.append(VerificationCheck(
        name="doi_format",
        status="passed" if doi_format_valid else ("failed" if doi_present else "not_checked"),
        evidence="DOI has a plausible DOI format." if doi_format_valid else (
            "DOI is present but does not match the local format check." if doi_present
            else "DOI format was not checked because DOI is unavailable."
        ),
        provenance=[f"evidence:{evidence_ids[0]}"],
        reference={"doi": doi},
    ))

    url = primary.get("url")
    parsed_url = urlparse(url) if url else None
    url_valid = bool(parsed_url and parsed_url.scheme in {"http", "https"} and parsed_url.netloc)
    checks.append(VerificationCheck(
        name="url_format",
        status="passed" if url_valid else ("failed" if url else "not_checked"),
        evidence="URL has an HTTP(S) reference format." if url_valid else (
            "URL is present but does not match the local format check." if url
            else "URL was not checked because it is unavailable."
        ),
        provenance=[f"evidence:{evidence_ids[0]}"],
        reference={"url": url},
    ))

    authors_present = bool(primary.get("authors"))
    checks.append(VerificationCheck(
        name="authors_presence",
        status="passed" if authors_present else "not_checked",
        evidence="Au٨thor metadata is present." if authors_present else "Author metadata is unavailable.",
        provenance=[f"evidence:{evidence_ids[0]}"],
        reference={"authors": primary.get("authors", [])},
    ))
    year_present = primary.get("year") is not None
    checks.append(VerificationCheck(
        name="publication_year_presence",
        status="passed" if year_present else "not_checked",
        evidence="Publication year is present." if year_present else "Publication year is unavailable.",
        provenance=[f"evidence:{evidence_ids[0]}"],
        reference={"year": primary.get("year")},
    ))

    metadata_consistent = all(
        normalize_title(item.get("source_title")) == normalize_title(primary.get("source_title"))
        and (
            item.get("year") is None
            or primary.get("year") is None
            or item.get("year") == primary.get("year")
        )
        for item in evidence_items
    )
    if matching_candidates:
        bibliographic_matches = [
            candidate for candidate in matching_candidates
            if normalize_title(candidate["result"].get("title")) == normalize_title(primary.get("source_title"))
            and (
                candidate["result"].get("year") is None
                or primary.get("year") is None
                or candidate["result"].get("year") == primary.get("year")
            )
        ]
        bibliographic_status = "passed" if metadata_consistent and bibliographic_matches else "failed"
        bibliographic_evidence = (
            "Title and available year metadata match indexed search metadata."
            if bibliographic_status == "passed"
            else "Available title or year metadata does not match indexed search metadata."
        )
        bibliographic_provenance = [
            f"search:{candidate['search_id']}:{candidate['source']}"
            for candidate in matching_candidates
        ]
    else:
        bibliographic_status = "not_checked"
        bibliographic_evidence = "No matching local search metadata is available for comparison."
        bibliographic_provenance = []
    checks.append(VerificationCheck(
        name="bibliographic_match",
        status=bibliographic_status,
        evidence=bibliographic_evidence,
        provenance=bibliographic_provenance,
        reference={"evidence_ids": evidence_ids},
    ))
    indexing_status = "passed" if matching_candidates else "not_checked"
    checks.append(VerificationCheck(
        name="indexing_provenance",
        status=indexing_status,
        evidence=(
            "Matching local search provenance is available."
            if matching_candidates
            else "No local indexing provenance is available."
        ),
        provenance=[
            f"search:{candidate['search_id']}:{candidate['source']}"
            for candidate in matching_candidates
        ],
        reference={"providers": sorted({candidate["source"] for candidate in matching_candidates if candidate["source"]})},
    ))
    checks.extend([
        VerificationCheck(
            name="retraction_status",
            status="not_checked",
            evidence="No retraction verification mechanism is available in the current system.",
            provenance=[],
        ),
        VerificationCheck(
            name="correction_status",
            status="not_checked",
            evidence="No correction verification mechanism is available in the current system.",
            provenance=[],
        ),
    ])

    external_findings: List[VerificationFinding] = []
    external_provenance: List[ExternalProvenance] = []
    external_metadata_result: ExternalProviderResult | None = None
    if primary.get("doi") and crossref_client is not None:
        external_metadata_result = crossref_client.fetch(primary["doi"])
        external_findings.append(external_finding(
            external_metadata_result,
            "doi_metadata",
            "doi_metadata",
            (
                "Crossref returned a DOI metadata record."
                if external_metadata_result.status == "passed"
                else external_metadata_result.error or "Crossref did not verify DOI metadata."
            ),
            {"raw_doi": primary.get("doi"), "canonical_doi": normalize_doi(primary.get("doi"))},
        ))
        if external_metadata_result.status == "passed":
            external_findings.append(crossref_bibliographic_finding(primary, external_metadata_result))
        external_findings.append(VerificationFinding(
            finding_type="doi_resolution",
            status="not_checked",
            provider="DOI resolver disabled",
            message="Direct DOI resolution is disabled; only Crossref metadata was requested.",
            evidence={"canonical_doi": normalize_doi(primary.get("doi"))},
            provenance=ExternalProvenance(
                provider="DOI resolver disabled",
                provider_record="DOI landing page",
                checked_at=None,
                request_target=None,
                verification_type="doi_resolution",
                status="not_checked",
                error="Direct URL resolution is disabled to prevent SSRF.",
            ),
        ))
        external_provenance.extend([
            finding.provenance
            for finding in external_findings
            if finding.provenance.provider == "Crossref"
        ])
    if primary.get("doi") and retraction_client is not None:
        retraction_result = retraction_client.check(primary["doi"])
        external_findings.append(external_finding(
            retraction_result,
            "retraction",
            "retraction_status",
            retraction_result.error or "Retraction status was checked.",
            {"canonical_doi": normalize_doi(primary.get("doi"))},
        ))
        external_provenance.append(external_provenance_from_result(retraction_result, "retraction_status"))
        external_findings.append(external_finding(
            retraction_result,
            "correction",
            "correction_status",
            retraction_result.error or "Correction status was checked.",
            {"canonical_doi": normalize_doi(primary.get("doi"))},
        ))

    failed_checks = {check.name for check in checks if check.status == "failed"}
    if not title_present or not reference_present:
        verification_status = "insufficiently_verified"
    elif failed_checks:
        verification_status = "partially_verified"
    elif matching_candidates and bibliographic_status == "passed":
        verification_status = "verified"
    else:
        verification_status = "partially_verified"
    if external_metadata_result is not None:
        if external_metadata_result.status == "not_found":
            verification_status = "unverified"
        elif external_metadata_result.status == "not_checked":
            verification_status = "partially_verified"
        elif any(
            finding.finding_type == "bibliographic_match" and finding.status == "failed"
            for finding in external_findings
        ):
            verification_status = "partially_verified"
        elif any(
            finding.finding_type == "bibliographic_match" and finding.status == "passed"
            for finding in external_findings
        ):
            verification_status = "verified"

    flags = ["source_record_present"]
    if doi_present:
        flags.append("doi_present")
    if doi_format_valid:
        flags.append("doi_format_valid")
    if authors_present:
        flags.append("authors_present")
    if year_present:
        flags.append("year_present")
    if matching_candidates:
        flags.append("indexing_provenance_present")
    if bibliographic_status == "passed":
        flags.append("bibliographic_match")
    if bibliographic_status == "failed":
        flags.append("bibliographic_mismatch")
    if not reference_present:
        flags.append("source_reference_missing")
    if not doi_present:
        flags.append("doi_not_available")
    flags.extend(["retraction_not_checked", "correction_not_checked"])

    return SourceVerification(
        source_key=source_key,
        source_id=primary.get("source_id"),
        title=primary.get("source_title", ""),
        authors=primary.get("authors", []),
        year=primary.get("year"),
        doi=primary.get("doi"),
        url=primary.get("url"),
        evidence_ids=evidence_ids,
        claim_ids=sorted(set(claim_ids)),
        verification_status=verification_status,
        verification_checks=checks,
        verification_findings=external_findings,
        external_provenance=external_provenance,
        verification_flags=flags,
        traceability={
            "source_key": source_key,
            "evidence_ids": evidence_ids,
            "claim_ids": sorted(set(claim_ids)),
            "source_ids": source_ids,
            "search_provenance": [
                f"search:{candidate['search_id']}:{candidate['source']}"
                for candidate in matching_candidates
            ],
        },
    )


def source_verifications_from_input(
    council_input: CouncilInputContract,
    crossref_client: CrossrefClient | None = None,
    retraction_client: RetractionClient | None = None,
) -> List[SourceVerification]:
    assessments = evidence_assessments_from_input(council_input)
    claim_ids_by_evidence = {
        assessment.evidence_id: assessment.claim_ids for assessment in assessments
    }
    evidence_groups: Dict[str, List[Dict[str, Any]]] = {}
    for evidence in council_input.evidence:
        evidence_groups.setdefault(source_key_for_evidence(evidence), []).append(evidence)
    search_candidates = search_candidates_from_input(council_input)
    verifications = [
        source_verification_from_group(
            evidence_items,
            sorted({
                claim_id
                for evidence in evidence_items
                for claim_id in claim_ids_by_evidence.get(evidence["id"], [])
            }),
            search_candidates,
            crossref_client,
            retraction_client,
        )
        for evidence_items in evidence_groups.values()
    ]
    return sorted(verifications, key=lambda item: item.source_key)


def source_verification_response(
    user_id: int, workspace_id: int,
) -> SourceVerificationResponse:
    council_input = council_input_from_memory(research_memory_response(user_id, workspace_id))
    sources = source_verifications_from_input(
        council_input,
        crossref_client=CrossrefClient(),
        retraction_client=RetractionClient(),
    )
    return SourceVerificationResponse(
        workspace_id=workspace_id,
        sources=sources,
        summary={
            "total": len(sources),
            "verified": sum(item.verification_status == "verified" for item in sources),
            "partially_verified": sum(item.verification_status == "partially_verified" for item in sources),
            "insufficiently_verified": sum(
                item.verification_status == "insufficiently_verified" for item in sources
            ),
            "unverified": sum(item.verification_status == "unverified" for item in sources),
        },
    )


def evidence_quality_from_input(
    council_input: CouncilInputContract,
    crossref_client: CrossrefClient | None = None,
    retraction_client: RetractionClient | None = None,
) -> List[EvidenceQualityAssessment]:
    evidence_assessments = evidence_assessments_from_input(council_input)
    source_verifications = source_verifications_from_input(
        council_input,
        crossref_client=crossref_client,
        retraction_client=retraction_client,
    )
    source_by_key = {item.source_key: item for item in source_verifications}
    results: List[EvidenceQualityAssessment] = []

    for evidence, assessment in zip(council_input.evidence, evidence_assessments):
        source_key = source_key_for_evidence(evidence)
        source_verification = source_by_key.get(source_key)
        source_reference_present = bool(
            evidence.get("source_id") or evidence.get("doi") or evidence.get("url")
        )
        title_present = bool(evidence.get("source_title"))
        excerpt_present = bool(evidence.get("excerpt"))
        if (evidence.get("source_id") or evidence.get("doi")) and title_present:
            traceability_status = "strong"
        elif source_reference_present or title_present:
            traceability_status = "partial"
        else:
            traceability_status = "insufficient"

        if not assessment.claim_ids:
            linkage_status = "unlinked"
        elif len(assessment.claim_ids) > 1:
            linkage_status = "linked_to_multiple_claims"
        else:
            linkage_status = "linked_to_claim"

        findings = [
            EvidenceQualityFinding(
                dimension="traceability",
                status="passed" if traceability_status == "strong" else "failed" if traceability_status == "insufficient" else "not_available",
                value=traceability_status,
                message="Evidence has a traceable source reference and title." if traceability_status == "strong" else "Source traceability is partial or insufficient.",
                provenance=[f"evidence:{evidence['id']}", *( [f"source_verification:{source_key}"] if source_verification else [] )],
            ),
            EvidenceQualityFinding(
                dimension="claim_linkage",
                status="passed" if assessment.claim_ids else "not_available",
                value=linkage_status,
                message="Evidence is linked to recorded Claim IDs." if assessment.claim_ids else "Evidence is not linked to a Claim.",
                provenance=[f"claim_evidence:{claim_id}:{evidence['id']}" for claim_id in assessment.claim_ids] or [f"evidence:{evidence['id']}"],
            ),
            EvidenceQualityFinding(
                dimension="relation_explicitness",
                status="passed",
                value=evidence["relation"],
                message="Relation is explicitly recorded in the Evidence model.",
                provenance=[f"evidence:{evidence['id']}:relation"],
            ),
            EvidenceQualityFinding(
                dimension="evidence_type",
                status="passed",
                value=evidence["evidence_type"],
                message="Evidence type is explicitly recorded; it is not treated as a quality ranking.",
                provenance=[f"evidence:{evidence['id']}:evidence_type"],
            ),
            EvidenceQualityFinding(
                dimension="directness",
                status="not_assessed",
                value="not_assessable",
                message="Directness cannot be established from the current metadata without inference.",
                provenance=[f"evidence:{evidence['id']}", *([f"claim_evidence:{claim_id}:{evidence['id']}" for claim_id in assessment.claim_ids])],
            ),
            EvidenceQualityFinding(
                dimension="study_design",
                status="not_available",
                value=None,
                message="Study design is not available in the current Evidence model.",
                provenance=[f"evidence:{evidence['id']}:metadata"],
            ),
            EvidenceQualityFinding(
                dimension="sample_population_context",
                status="not_available",
                value=None,
                message="Sample, population, and context are not available in the current Evidence model.",
                provenance=[f"evidence:{evidence['id']}:metadata"],
            ),
            EvidenceQualityFinding(
                dimension="effect_size",
                status="not_assessed",
                value="not_assessed",
                message="Effect size extraction is outside Evidence Quality v0.1.",
                provenance=[f"evidence:{evidence['id']}:excerpt" if excerpt_present else f"evidence:{evidence['id']}"],
            ),
            EvidenceQualityFinding(
                dimension="bias",
                status="not_assessed",
                value="not_assessed",
                message="Bias is not assessed because structured methodological data is unavailable.",
                provenance=[f"evidence:{evidence['id']}:metadata"],
            ),
            EvidenceQualityFinding(
                dimension="confidence",
                status="passed" if evidence.get("confidence") is not None else "not_available",
                value=evidence.get("confidence"),
                message="Recorded confidence value is reported as metadata only." if evidence.get("confidence") is not None else "Confidence was not provided.",
                provenance=[f"evidence:{evidence['id']}:confidence"],
            ),
        ]
        if source_verification:
            findings.append(EvidenceQualityFinding(
                dimension="source_verification",
                status="passed" if source_verification.verification_status == "verified" else "not_available" if source_verification.verification_status == "partially_verified" else "failed",
                value=source_verification.verification_status,
                message="Source verification status is included as source metadata context, not evidence quality.",
                provenance=[f"source_verification:{source_key}"],
            ))

        missing_information = [
            "study_design",
            "sample_size",
            "population",
            "context",
            "effect_size",
            "bias_assessment",
        ]
        if not source_reference_present:
            missing_information.append("source_reference")
        if not excerpt_present:
            missing_information.append("excerpt")

        if not assessment.claim_ids or traceability_status == "insufficient":
            quality_status = "insufficient_information"
        elif traceability_status == "strong" and excerpt_present:
            quality_status = "assessable"
        else:
            quality_status = "partially_assessable"

        results.append(EvidenceQualityAssessment(
            evidence_id=evidence["id"],
            claim_ids=assessment.claim_ids,
            source_key=source_key,
            source_verification_status=source_verification.verification_status if source_verification else None,
            source_verification_findings=source_verification.verification_findings if source_verification else [],
            quality_assessment_status=quality_status,
            traceability_status=traceability_status,
            linkage_status=linkage_status,
            relation=evidence["relation"],
            evidence_type=evidence["evidence_type"],
            confidence=evidence.get("confidence"),
            confidence_status="recorded" if evidence.get("confidence") is not None else "not_provided",
            findings=findings,
            missing_information=missing_information,
            traceability={
                "evidence_id": evidence["id"],
                "claim_ids": assessment.claim_ids,
                "source_key": source_key,
                "source_ids": [evidence["source_id"]] if evidence.get("source_id") else [],
                "source_verification_key": source_key if source_verification else None,
            },
        ))
    return results


def evidence_quality_response(
    user_id: int, workspace_id: int,
) -> EvidenceQualityResponse:
    council_input = council_input_from_memory(research_memory_response(user_id, workspace_id))
    assessments = evidence_quality_from_input(
        council_input,
        crossref_client=CrossrefClient(),
        retraction_client=RetractionClient(),
    )
    unlinked = [item for item in assessments if item.linkage_status == "unlinked"]
    return EvidenceQualityResponse(
        workspace_id=workspace_id,
        assessments=[item for item in assessments if item.linkage_status != "unlinked"],
        unlinked_evidence=unlinked,
        summary={
            "total": len(assessments),
            "assessable": sum(item.quality_assessment_status == "assessable" for item in assessments),
            "partially_assessable": sum(item.quality_assessment_status == "partially_assessable" for item in assessments),
            "insufficient_information": sum(item.quality_assessment_status == "insufficient_information" for item in assessments),
            "unlinked_evidence": len(unlinked),
        },
    )


def build_evidence_extraction(
    evidence_id: int,
    claim_ids: List[int],
    dimension: str,
    extracted_value: Any = None,
    extraction_method: Literal["manual", "ai"] = "manual",
    extraction_confidence: float | None = None,
    source_location: ExtractionSourceLocation | None = None,
    raw_input_reference: ExtractionRawInputReference | None = None,
    verification_state: Literal["not_verified", "verified", "rejected", "needs_review"] = "not_verified",
    human_review_state: Literal["not_reviewed", "approved", "rejected", "needs_review"] | None = None,
    source_id: str | None = None,
    created_at: str = "not_available",
) -> EvidenceExtraction:
    resolved_review_state = human_review_state or (
        "needs_review" if extraction_method == "ai" else "not_reviewed"
    )
    location = source_location or ExtractionSourceLocation(status="not_available")
    raw_reference = raw_input_reference or ExtractionRawInputReference(
        reference_type="not_available",
        reference=None,
        status="not_available",
    )
    return EvidenceExtraction(
        extraction_id=f"extraction:evidence:{evidence_id}:dimension:{dimension}",
        evidence_id=evidence_id,
        claim_ids=sorted(set(claim_ids)),
        dimension=dimension,
        extracted_value=extracted_value,
        extraction_method=extraction_method,
        extraction_confidence=extraction_confidence,
        extraction_confidence_status=(
            "recorded" if extraction_confidence is not None else "not_provided"
        ),
        source_location=location,
        raw_input_reference=raw_reference,
        verification_state=verification_state,
        human_review_state=resolved_review_state,
        provenance=ExtractionProvenance(
            source_type="evidence",
            source_id=source_id,
            evidence_id=evidence_id,
            source_location=location,
            extraction_method=extraction_method,
            created_at=created_at,
        ),
    )


def council_analysis_from_input(council_input: CouncilInputContract) -> CouncilAnalysis:
    critic_by_claim = {item["claim_id"]: item for item in council_input.critic}
    evidence_assessments = evidence_assessments_from_input(council_input)
    assessments_by_id = {item.evidence_id: item for item in evidence_assessments}
    conflicts = conflict_analysis_from_input(council_input)
    analyses: List[ClaimAnalysis] = []

    for claim in council_input.claims:
        claim_id = claim["id"]
        claim_evidence = claim.get("evidence", [])
        evidence_ids_by_relation = {
            "supporting": [item["id"] for item in claim_evidence if item.get("relation") == "supporting"],
            "contradicting": [item["id"] for item in claim_evidence if item.get("relation") == "contradicting"],
            "uncertain": [item["id"] for item in claim_evidence if item.get("relation") == "uncertain"],
        }
        evidence_types = {item.get("evidence_type") for item in claim_evidence}
        confidence_values = [
            item["confidence"] for item in claim_evidence if item.get("confidence") is not None
        ]
        critic = critic_by_claim.get(claim_id, {"audit_status": "unsupported"})
        flags: List[str] = []
        if not claim_evidence:
            flags.append("no_evidence")
        if evidence_ids_by_relation["supporting"]:
            flags.append("supporting_evidence_present")
        if evidence_ids_by_relation["contradicting"]:
            flags.append("contradicting_evidence_present")
        if evidence_ids_by_relation["uncertain"]:
            flags.append("uncertain_evidence_present")
        if "abstract" in evidence_types and "full_text" not in evidence_types:
            flags.append("abstract_only")
        if "full_text" in evidence_types:
            flags.append("full_text_present")
        if any(float(value) < 0.4 for value in confidence_values):
            flags.append("low_confidence")
        if evidence_ids_by_relation["supporting"] and evidence_ids_by_relation["contradicting"]:
            flags.append("conflicting_evidence")

        related_claim_ids = sorted({
            relation["target_claim_id"] if relation["source_claim_id"] == claim_id else relation["source_claim_id"]
            for relation in claim.get("relations", [])
        })
        if related_claim_ids:
            flags.append("related_claims_present")

        claim_assessments = [
            assessments_by_id[item["id"]]
            for item in claim_evidence
            if item["id"] in assessments_by_id
        ]
        completeness_summary = {
            "complete": sum(item.completeness == "complete" for item in claim_assessments),
            "partial": sum(item.completeness == "partial" for item in claim_assessments),
            "insufficient_metadata": sum(
                item.completeness == "insufficient_metadata" for item in claim_assessments
            ),
        }
        claim_conflicts = [
            conflict for conflict in conflicts if claim_id in conflict.claim_ids
        ]

        analyses.append(ClaimAnalysis(
            claim_id=claim_id,
            claim_text=claim["claim_text"],
            critic_status=critic["audit_status"],
            supporting_evidence_ids=evidence_ids_by_relation["supporting"],
            contradicting_evidence_ids=evidence_ids_by_relation["contradicting"],
            uncertain_evidence_ids=evidence_ids_by_relation["uncertain"],
            related_claim_ids=related_claim_ids,
            evidence_count=len(claim_evidence),
            supporting_count=len(evidence_ids_by_relation["supporting"]),
            contradicting_count=len(evidence_ids_by_relation["contradicting"]),
            uncertain_count=len(evidence_ids_by_relation["uncertain"]),
            evidence_assessments=claim_assessments,
            evidence_completeness_summary=completeness_summary,
            conflict_count=len(claim_conflicts),
            conflicts=claim_conflicts,
            conflict_types=sorted({item.conflict_type for item in claim_conflicts}),
            analysis_flags=flags,
        ))

    return CouncilAnalysis(
        claims=analyses,
        evidence=evidence_assessments,
        conflicts=conflicts,
    )


def evidence_assessment_response(
    user_id: int, workspace_id: int,
) -> EvidenceAssessmentResponse:
    council_input = council_input_from_memory(research_memory_response(user_id, workspace_id))
    assessments = evidence_assessments_from_input(council_input)
    return EvidenceAssessmentResponse(
        workspace_id=workspace_id,
        assessments=assessments,
        summary={
            "evidence_count": len(assessments),
            "complete_count": sum(item.completeness == "complete" for item in assessments),
            "partial_count": sum(item.completeness == "partial" for item in assessments),
            "insufficient_metadata_count": sum(
                item.completeness == "insufficient_metadata" for item in assessments
            ),
        },
    )


def conflict_analysis_from_input(
    council_input: CouncilInputContract,
) -> List[ConflictAnalysis]:
    workspace_id = council_input.workspace["id"]
    evidence_by_id = {item["id"]: item for item in council_input.evidence}
    evidence_conflicts: Dict[int, Dict[str, List[int]]] = {}
    for claim in council_input.claims:
        claim_id = claim["id"]
        supporting_ids = sorted(
            item["id"]
            for item in claim.get("evidence", [])
            if item.get("relation") == "supporting"
        )
        contradicting_ids = sorted(
            item["id"]
            for item in claim.get("evidence", [])
            if item.get("relation") == "contradicting"
        )
        if supporting_ids and contradicting_ids:
            evidence_conflicts[claim_id] = {
                "supporting": supporting_ids,
                "contradicting": contradicting_ids,
            }

    contradicting_relations = [
        relation
        for relation in council_input.claim_relations
        if relation.get("relation") == "contradicts"
    ]
    mixed_relation_ids: set[int] = set()
    mixed_claim_ids: set[int] = set()
    conflicts: List[ConflictAnalysis] = []

    for claim_id, evidence_conflict in evidence_conflicts.items():
        for relation in contradicting_relations:
            relation_claim_ids = {
                relation["source_claim_id"],
                relation["target_claim_id"],
            }
            if claim_id not in relation_claim_ids:
                continue
            relation_id = relation["id"]
            mixed_relation_ids.add(relation_id)
            mixed_claim_ids.add(claim_id)
            evidence_ids = sorted(
                evidence_conflict["supporting"] + evidence_conflict["contradicting"]
            )
            source_ids = sorted({
                evidence_by_id[evidence_id]["source_id"]
                for evidence_id in evidence_ids
                if evidence_by_id[evidence_id].get("source_id")
            })
            conflicts.append(ConflictAnalysis(
                conflict_id=(
                    f"mixed_conflict:claim:{claim_id}:relation:{relation_id}:"
                    f"supporting:{','.join(map(str, evidence_conflict['supporting']))}:"
                    f"contradicting:{','.join(map(str, evidence_conflict['contradicting']))}"
                ),
                conflict_type="mixed_conflict",
                workspace_id=workspace_id,
                claim_ids=sorted(relation_claim_ids),
                evidence_ids=evidence_ids,
                relation_ids=[relation_id],
                supporting_evidence_ids=evidence_conflict["supporting"],
                contradicting_evidence_ids=evidence_conflict["contradicting"],
                source_ids=source_ids,
                description_structural=(
                    "The claim has supporting and contradicting evidence and is part "
                    "of a contradicts claim relation."
                ),
                traceability={
                    "claim_ids": sorted(relation_claim_ids),
                    "evidence_ids": evidence_ids,
                    "relation_ids": [relation_id],
                    "source_ids": source_ids,
                },
            ))

    for claim_id, evidence_conflict in evidence_conflicts.items():
        if claim_id in mixed_claim_ids:
            continue
        evidence_ids = sorted(
            evidence_conflict["supporting"] + evidence_conflict["contradicting"]
        )
        source_ids = sorted({
            evidence_by_id[evidence_id]["source_id"]
            for evidence_id in evidence_ids
            if evidence_by_id[evidence_id].get("source_id")
        })
        conflicts.append(ConflictAnalysis(
            conflict_id=(
                f"evidence_conflict:claim:{claim_id}:"
                f"supporting:{','.join(map(str, evidence_conflict['supporting']))}:"
                f"contradicting:{','.join(map(str, evidence_conflict['contradicting']))}"
            ),
            conflict_type="evidence_conflict",
            workspace_id=workspace_id,
            claim_ids=[claim_id],
            evidence_ids=evidence_ids,
            supporting_evidence_ids=evidence_conflict["supporting"],
            contradicting_evidence_ids=evidence_conflict["contradicting"],
            source_ids=source_ids,
            description_structural=(
                "The claim has both supporting and contradicting evidence."
            ),
            traceability={
                "claim_ids": [claim_id],
                "evidence_ids": evidence_ids,
                "supporting_evidence_ids": evidence_conflict["supporting"],
                "contradicting_evidence_ids": evidence_conflict["contradicting"],
                "source_ids": source_ids,
            },
        ))

    for relation in contradicting_relations:
        if relation["id"] in mixed_relation_ids:
            continue
        conflicts.append(ConflictAnalysis(
            conflict_id=f"claim_relation_conflict:relation:{relation['id']}",
            conflict_type="claim_relation_conflict",
            workspace_id=workspace_id,
            claim_ids=sorted({relation["source_claim_id"], relation["target_claim_id"]}),
            relation_ids=[relation["id"]],
            description_structural="A contradicts relation exists between two claims.",
            traceability={
                "relation_ids": [relation["id"]],
                "source_claim_id": relation["source_claim_id"],
                "target_claim_id": relation["target_claim_id"],
                "relation": relation["relation"],
            },
        ))

    return sorted(conflicts, key=lambda item: item.conflict_id)


def conflict_analysis_response(
    user_id: int, workspace_id: int,
) -> ConflictAnalysisResponse:
    council_input = council_input_from_memory(research_memory_response(user_id, workspace_id))
    conflicts = conflict_analysis_from_input(council_input)
    return ConflictAnalysisResponse(
        workspace_id=workspace_id,
        conflicts=conflicts,
        summary={
            "total": len(conflicts),
            "evidence_conflicts": sum(item.conflict_type == "evidence_conflict" for item in conflicts),
            "claim_relation_conflicts": sum(
                item.conflict_type == "claim_relation_conflict" for item in conflicts
            ),
            "mixed_conflicts": sum(item.conflict_type == "mixed_conflict" for item in conflicts),
        },
    )


def decision_analysis_from_input(
    council_input: CouncilInputContract,
) -> List[DecisionAnalysis]:
    workspace_id = council_input.workspace["id"]
    evidence_assessments = evidence_assessments_from_input(council_input)
    assessments_by_id = {item.evidence_id: item for item in evidence_assessments}
    conflicts = conflict_analysis_from_input(council_input)
    decisions: List[DecisionAnalysis] = []

    for claim in council_input.claims:
        claim_id = claim["id"]
        claim_evidence = claim.get("evidence", [])
        evidence_ids = sorted(item["id"] for item in claim_evidence)
        supporting_ids = sorted(
            item["id"] for item in claim_evidence if item.get("relation") == "supporting"
        )
        contradicting_ids = sorted(
            item["id"] for item in claim_evidence if item.get("relation") == "contradicting"
        )
        uncertain_ids = sorted(
            item["id"] for item in claim_evidence if item.get("relation") == "uncertain"
        )
        claim_conflicts = [
            conflict for conflict in conflicts if claim_id in conflict.claim_ids
        ]
        conflict_ids = sorted(conflict.conflict_id for conflict in claim_conflicts)
        relation_ids = sorted({
            relation_id
            for conflict in claim_conflicts
            for relation_id in conflict.relation_ids
        })
        source_ids = sorted({
            assessments_by_id[evidence_id].source_id
            for evidence_id in evidence_ids
            if evidence_id in assessments_by_id
            and assessments_by_id[evidence_id].source_id
        })
        missing_source_evidence_ids = sorted(
            evidence_id
            for evidence_id in evidence_ids
            if evidence_id in assessments_by_id
            and "source_reference_present" not in assessments_by_id[evidence_id].assessment_flags
        )
        critic = next(
            (item for item in council_input.critic if item["claim_id"] == claim_id),
            None,
        )

        if not evidence_ids:
            decision_status = "insufficient_evidence"
            reason_code = "no_linked_evidence"
        elif claim_conflicts:
            decision_status = "conflicting"
            reason_code = "conflict_detected"
        elif not supporting_ids:
            decision_status = "unsupported"
            reason_code = "no_supporting_evidence"
        else:
            decision_status = "structurally_supported"
            reason_code = "supporting_evidence_without_conflict"

        decisions.append(DecisionAnalysis(
            decision_id=f"decision:workspace:{workspace_id}:claim:{claim_id}",
            workspace_id=workspace_id,
            claim_id=claim_id,
            claim_text=claim["claim_text"],
            decision_status=decision_status,
            reason_code=reason_code,
            critic_status=critic["audit_status"] if critic else None,
            evidence_ids=evidence_ids,
            supporting_evidence_ids=supporting_ids,
            contradicting_evidence_ids=contradicting_ids,
            uncertain_evidence_ids=uncertain_ids,
            conflict_ids=conflict_ids,
            relation_ids=relation_ids,
            source_ids=source_ids,
            missing_source_evidence_ids=missing_source_evidence_ids,
            traceability={
                "workspace_id": workspace_id,
                "claim_id": claim_id,
                "evidence_ids": evidence_ids,
                "conflict_ids": conflict_ids,
                "relation_ids": relation_ids,
                "source_ids": source_ids,
                "missing_source_evidence_ids": missing_source_evidence_ids,
            },
        ))

    return decisions


def decision_analysis_response(
    user_id: int, workspace_id: int,
) -> DecisionAnalysisResponse:
    council_input = council_input_from_memory(research_memory_response(user_id, workspace_id))
    decisions = decision_analysis_from_input(council_input)
    return DecisionAnalysisResponse(
        workspace_id=workspace_id,
        decisions=decisions,
        summary={
            "total": len(decisions),
            "insufficient_evidence": sum(
                item.decision_status == "insufficient_evidence" for item in decisions
            ),
            "unsupported": sum(item.decision_status == "unsupported" for item in decisions),
            "conflicting": sum(item.decision_status == "conflicting" for item in decisions),
            "structurally_supported": sum(
                item.decision_status == "structurally_supported" for item in decisions
            ),
        },
    )


def synthesis_status_for_decision(
    decision: DecisionAnalysis,
) -> tuple[str, str]:
    if decision.decision_status == "insufficient_evidence":
        return "insufficient_evidence", "لا تتوفر أدلة مرتبطة كافية لهذا الادعاء ضمن مساحة البحث الحالية."
    if decision.decision_status == "conflicting":
        if decision.supporting_evidence_ids:
            return (
                "supported_with_conflict",
                "تتضمن الأدلة المرتبطة بالادعاء دعمًا وأدلة متعارضة؛ لذلك يبقى التركيب غير محسوم ضمن البيانات الحالية.",
            )
        return (
            "unresolved",
            "توجد حالة تعارض مرتبطة بالادعاء دون دعم بنيوي كافٍ؛ لذلك يبقى التركيب غير محسوم.",
        )
    if decision.decision_status == "unsupported":
        return (
            "unsupported",
            "توجد أدلة مرتبطة، لكن لا يظهر دعم بنيوي لهذا الادعاء وفق العلاقات المسجلة.",
        )
    return (
        "structurally_supported",
        "تظهر أدلة داعمة مرتبطة بهذا الادعاء دون تعارض مسجل؛ وهذا دعم بنيوي ضمن البيانات الحالية وليس إثباتًا علميًا.",
    )


def claim_synthesis_from_decision(
    decision: DecisionAnalysis,
    conflicts_by_id: Dict[str, ConflictAnalysis],
    unlinked_evidence_ids: List[int],
) -> ClaimSynthesis:
    synthesis_status, synthesis_statement = synthesis_status_for_decision(decision)
    limitations = ["structural_assessment_only"]
    if not decision.evidence_ids:
        limitations.append("no_evidence")
    if decision.uncertain_evidence_ids:
        limitations.append("uncertain_evidence_present")
    if decision.conflict_ids:
        limitations.append("conflicting_evidence")
    if any(
        "claim_relation_conflict" in conflicts_by_id[conflict_id].conflict_type
        for conflict_id in decision.conflict_ids
    ):
        limitations.append("claim_relation_conflict")
    if decision.missing_source_evidence_ids:
        limitations.append("missing_source_reference")
    if unlinked_evidence_ids:
        limitations.append("unlinked_evidence_not_considered")

    return ClaimSynthesis(
        claim_id=decision.claim_id,
        claim_text=decision.claim_text,
        decision_id=decision.decision_id,
        decision_status=decision.decision_status,
        critic_status=decision.critic_status,
        supporting_evidence_ids=decision.supporting_evidence_ids,
        contradicting_evidence_ids=decision.contradicting_evidence_ids,
        uncertain_evidence_ids=decision.uncertain_evidence_ids,
        conflict_ids=decision.conflict_ids,
        relation_ids=decision.relation_ids,
        source_ids=decision.source_ids,
        synthesis_status=synthesis_status,
        synthesis_statement=synthesis_statement,
        limitations=limitations,
        traceability=SynthesisTraceability(
            claim_ids=[decision.claim_id],
            decision_ids=[decision.decision_id],
            evidence_ids=decision.evidence_ids,
            conflict_ids=decision.conflict_ids,
            relation_ids=decision.relation_ids,
            source_ids=decision.source_ids,
        ),
    )


def synthesis_analysis_from_input(
    council_input: CouncilInputContract,
) -> SynthesisAnalysis:
    decisions = decision_analysis_from_input(council_input)
    conflicts = conflict_analysis_from_input(council_input)
    conflicts_by_id = {conflict.conflict_id: conflict for conflict in conflicts}
    assessments = evidence_assessments_from_input(council_input)
    unlinked_evidence_ids = sorted(
        assessment.evidence_id
        for assessment in assessments
        if not assessment.claim_ids
    )
    claim_syntheses = [
        claim_synthesis_from_decision(decision, conflicts_by_id, unlinked_evidence_ids)
        for decision in decisions
    ]
    statuses = [item.synthesis_status for item in claim_syntheses]
    if not statuses or all(status == "insufficient_evidence" for status in statuses):
        overall_status = "insufficient_evidence"
    elif any(status in {"supported_with_conflict", "unresolved"} for status in statuses):
        overall_status = "unresolved"
    elif all(status == "unsupported" for status in statuses):
        overall_status = "unsupported"
    elif all(status == "structurally_supported" for status in statuses):
        overall_status = "structurally_supported"
    else:
        overall_status = "unresolved"

    decision_counts = {
        "insufficient_evidence": sum(
            item.decision_status == "insufficient_evidence" for item in decisions
        ),
        "unsupported": sum(item.decision_status == "unsupported" for item in decisions),
        "conflicting": sum(item.decision_status == "conflicting" for item in decisions),
        "structurally_supported": sum(
            item.decision_status == "structurally_supported" for item in decisions
        ),
    }
    evidence_ids = sorted({
        evidence_id
        for decision in decisions
        for evidence_id in decision.evidence_ids
    })
    conflict_ids = sorted({
        conflict_id
        for decision in decisions
        for conflict_id in decision.conflict_ids
    })
    relation_ids = sorted({
        relation_id
        for decision in decisions
        for relation_id in decision.relation_ids
    })
    source_ids = sorted({
        source_id
        for decision in decisions
        for source_id in decision.source_ids
    })
    claim_ids = [decision.claim_id for decision in decisions]
    decision_ids = [decision.decision_id for decision in decisions]
    return SynthesisAnalysis(
        synthesis_id=f"synthesis:workspace:{council_input.workspace['id']}",
        workspace_id=council_input.workspace["id"],
        research_question=council_input.workspace["research_question"],
        claim_syntheses=claim_syntheses,
        overall_status=overall_status,
        summary=SynthesisSummary(
            claim_count=len(claim_syntheses),
            evidence_count=len(council_input.evidence),
            conflict_count=len(conflicts),
            decision_counts=decision_counts,
            unlinked_evidence_ids=unlinked_evidence_ids,
        ),
        traceability=SynthesisTraceability(
            claim_ids=claim_ids,
            decision_ids=decision_ids,
            evidence_ids=evidence_ids,
            conflict_ids=conflict_ids,
            relation_ids=relation_ids,
            source_ids=source_ids,
        ),
    )


def synthesis_analysis_response(
    user_id: int, workspace_id: int,
) -> SynthesisAnalysis:
    council_input = council_input_from_memory(research_memory_response(user_id, workspace_id))
    return synthesis_analysis_from_input(council_input)


def council_foundation_response(user_id: int, workspace_id: int) -> CouncilFoundationResponse:
    council_input = council_input_from_memory(research_memory_response(user_id, workspace_id))
    return CouncilFoundationResponse(
        input=council_input,
        analysis=council_analysis_from_input(council_input),
    )


def claim_critic_response(user_id: int, claim_id: int) -> Dict[str, Any]:
    with get_connection() as conn:
        claim = conn.execute(
            "SELECT id, claim_text, status, created_at FROM claims WHERE id = ? AND user_id = ?",
            (claim_id, user_id),
        ).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found or not owned by user")

        evidence_rows = conn.execute(
            """
            SELECT e.* FROM evidence e
            JOIN claim_evidence ce ON ce.evidence_id = e.id
            WHERE ce.claim_id = ? AND e.user_id = ?
            ORDER BY e.id
            """,
            (claim_id, user_id),
        ).fetchall()

        relation_rows = conn.execute(
            """
            SELECT * FROM claim_relations
            WHERE user_id = ? AND (source_claim_id = ? OR target_claim_id = ?)
            ORDER BY created_at DESC
            """,
            (user_id, claim_id, claim_id),
        ).fetchall()

    evidence = [evidence_from_row(row) for row in evidence_rows]
    supporting_count = sum(1 for item in evidence if item.get("relation") == "supporting")
    contradicting_count = sum(1 for item in evidence if item.get("relation") == "contradicting")
    uncertain_count = sum(1 for item in evidence if item.get("relation") == "uncertain")
    abstract_count = sum(1 for item in evidence if item.get("evidence_type") == "abstract")
    full_text_count = sum(1 for item in evidence if item.get("evidence_type") == "full_text")
    confidence_values = [float(item["confidence"]) for item in evidence if item.get("confidence") is not None]
    average_confidence = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0
    min_confidence = min(confidence_values) if confidence_values else 0.0
    max_confidence = max(confidence_values) if confidence_values else 0.0

    issues: List[str] = []
    if not evidence:
        issues.append("لا توجد أدلة مرتبطة بهذا الادعاء.")
    if supporting_count == 0 and evidence:
        issues.append("لا توجد أدلة supporting مرتبطة بهذا الادعاء.")
    if contradicting_count > 0:
        issues.append("يوجد دليل متعارض مع هذا الادعاء.")
    if abstract_count and not full_text_count:
        issues.append("الأدلة المتاحة تعتمد على abstract فقط.")
    if len(evidence) == 1:
        issues.append("الادعاء يعتمد على دليل واحد فقط.")
    if not confidence_values:
        issues.append("لا توجد قيم confidence للأدلة المرتبطة بهذا الادعاء.")
    elif average_confidence < 0.4:
        issues.append("متوسط confidence للأدلة منخفض، مما يقلل قوة الدعم.")
    if relation_rows:
        relation_summary = {"supports": 0, "contradicts": 0, "qualifies": 0, "depends_on": 0}
        for row in relation_rows:
            relation_summary[row["relation"]] = relation_summary.get(row["relation"], 0) + 1
        if relation_summary.get("contradicts", 0) > 0:
            issues.append("يوجد علاقة contradicts مع Claims أخرى.")
        if relation_summary.get("depends_on", 0) > 0 and len(evidence) == 0:
            issues.append("هذا الادعاء مرتبط بـ Claims أخرى دون Evidence مباشر.")

    if not evidence and relation_rows:
        issues.append("هذا الادعاء مرتبط بـ Claims أخرى لكنه لا يملك Evidence مباشر.")

    if contradicting_count > 0:
        status = "conflicting"
    elif not evidence:
        status = "unsupported"
    elif supporting_count == 0 and uncertain_count == 0:
        status = "insufficient_evidence"
    elif abstract_count and not full_text_count:
        status = "weakly_supported"
    elif average_confidence < 0.4:
        status = "weakly_supported"
    elif supporting_count > 0 and full_text_count > 0 and average_confidence >= 0.5:
        status = "supported"
    elif len(evidence) == 1 and supporting_count == 1 and average_confidence >= 0.5:
        status = "supported"
    else:
        status = "weakly_supported"

    return {
        "claim": {"id": claim["id"], "claim_text": claim["claim_text"], "status": claim["status"]},
        "evidence_count": len(evidence),
        "supporting_count": supporting_count,
        "contradicting_count": contradicting_count,
        "uncertain_count": uncertain_count,
        "abstract_count": abstract_count,
        "full_text_count": full_text_count,
        "confidence_summary": {
            "average_confidence": average_confidence,
            "min_confidence": min_confidence,
            "max_confidence": max_confidence,
            "count": len(confidence_values),
        },
        "claim_relation_summary": {
            "total_relations": len(relation_rows),
            "supports": sum(1 for row in relation_rows if row["relation"] == "supports"),
            "contradicts": sum(1 for row in relation_rows if row["relation"] == "contradicts"),
            "qualifies": sum(1 for row in relation_rows if row["relation"] == "qualifies"),
            "depends_on": sum(1 for row in relation_rows if row["relation"] == "depends_on"),
        },
        "issues": issues,
        "audit_status": status,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
    <!DOCTYPE html>
    <html lang="ar">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Research OS</title>
        <style>
            :root { --primary: #1d4ed8; --bg: #f5f7fb; --card: #ffffff; --muted: #475569; }
            body { font-family: Arial, sans-serif; background: var(--bg); margin: 0; padding: 40px; }
            .container { max-width: 1000px; margin: 0 auto; background: var(--card); padding: 32px; border-radius: 16px; box-shadow: 0 15px 35px rgba(15, 23, 42, 0.08); }
            h1 { color: var(--primary); margin-bottom: 10px; }
            .pill { display: inline-block; background: #dbeafe; color: #1e3a8a; padding: 6px 12px; border-radius: 999px; font-size: 12px; font-weight: bold; }
            ul { line-height: 2; color: var(--muted); }
            code { background: #eef2ff; padding: 3px 6px; border-radius: 6px; }
        </style>
    </head>
    <body>
        <div class="container">
            <span class="pill">Research OS</span>
            <h1>واجهة البحث الأكاديمي</h1>
            <p>النظام يدعم البحث المتوازي عبر OpenAlex وSemantic Scholar وCrossref مع إزالة التكرار.</p>
            <ul>
                <li><code>/api/health</code> – فحص الخدمة</li>
                <li><code>/api/search?q=AI</code> – استعلام بحث حقيقي</li>
                <li><code>/api/auth/register</code> – تسجيل مستخدم جديد</li>
                <li><code>/api/auth/login</code> – تسجيل دخول</li>
            </ul>
        </div>
    </body>
    </html>
    """


@app.get("/api/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": "research-os"}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterRequest) -> Dict[str, Any]:
    if get_user_by_username(payload.username):
        raise HTTPException(status_code=409, detail="Username already exists")

    token = generate_api_token(payload.username)
    password_hash = hash_password(payload.password)

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, email, password_hash, api_token) VALUES (?, ?, ?, ?)",
            (payload.username, payload.email, password_hash, token),
        )
        user_id = cursor.lastrowid

    return {
        "message": "User registered successfully",
        "token": token,
        "user": {"id": user_id, "username": payload.username, "email": payload.email},
    }


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> Dict[str, Any]:
    user = get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {
        "token": user["api_token"],
        "user": {"id": user["id"], "username": user["username"], "email": user["email"]},
    }


@app.get("/api/search-history")
def search_history(user_token: str = Depends(decode_token)) -> List[Dict[str, Any]]:
    user = get_user_by_username(user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, query, results, created_at FROM searches WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()

    return [dict(row) for row in rows]


@app.post("/api/workspaces", status_code=201)
def create_workspace(payload: WorkspaceCreate, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO research_workspaces (user_id, title, research_question, notes) VALUES (?, ?, ?, ?)",
            (user["id"], payload.title, payload.research_question, payload.notes),
        )
        workspace_id = cursor.lastrowid
    return get_owned_workspace(user["id"], workspace_id)


@app.get("/api/workspaces")
def list_workspaces(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT w.*, COUNT(DISTINCT c.id) AS claim_count,
                   COUNT(DISTINCT e.id) AS evidence_count,
                   COUNT(DISTINCT s.id) AS search_count
            FROM research_workspaces w
            LEFT JOIN claims c ON c.workspace_id = w.id AND c.user_id = w.user_id
            LEFT JOIN evidence e ON e.workspace_id = w.id AND e.user_id = w.user_id
            LEFT JOIN searches s ON s.workspace_id = w.id AND s.user_id = w.user_id
            WHERE w.user_id = ?
            GROUP BY w.id
            ORDER BY w.updated_at DESC, w.id DESC
            """,
            (user["id"],),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/workspaces/{workspace_id}")
def get_workspace(workspace_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return workspace_response(user["id"], workspace_id)


@app.get("/api/workspaces/{workspace_id}/view")
def get_workspace_view(workspace_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return workspace_response(user["id"], workspace_id)


@app.get("/api/workspaces/{workspace_id}/memory")
def get_workspace_memory(workspace_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return research_memory_response(user["id"], workspace_id)


@app.get("/api/workspaces/{workspace_id}/council/input", response_model=CouncilInputContract)
def get_council_input(workspace_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> CouncilInputContract:
    return council_input_from_memory(research_memory_response(user["id"], workspace_id))


@app.get(
    "/api/workspaces/{workspace_id}/council/evidence-assessment",
    response_model=EvidenceAssessmentResponse,
)
def get_evidence_assessment(
    workspace_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> EvidenceAssessmentResponse:
    return evidence_assessment_response(user["id"], workspace_id)


@app.get(
    "/api/workspaces/{workspace_id}/council/conflicts",
    response_model=ConflictAnalysisResponse,
)
def get_council_conflicts(
    workspace_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> ConflictAnalysisResponse:
    return conflict_analysis_response(user["id"], workspace_id)


@app.get(
    "/api/workspaces/{workspace_id}/council/decisions",
    response_model=DecisionAnalysisResponse,
)
def get_council_decisions(
    workspace_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> DecisionAnalysisResponse:
    return decision_analysis_response(user["id"], workspace_id)


@app.get(
    "/api/workspaces/{workspace_id}/council/synthesis",
    response_model=SynthesisAnalysis,
)
def get_council_synthesis(
    workspace_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> SynthesisAnalysis:
    return synthesis_analysis_response(user["id"], workspace_id)


@app.get(
    "/api/workspaces/{workspace_id}/sources/verification",
    response_model=SourceVerificationResponse,
)
def get_source_verification(
    workspace_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> SourceVerificationResponse:
    return source_verification_response(user["id"], workspace_id)


@app.get(
    "/api/workspaces/{workspace_id}/council/evidence-quality",
    response_model=EvidenceQualityResponse,
)
def get_evidence_quality(
    workspace_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> EvidenceQualityResponse:
    return evidence_quality_response(user["id"], workspace_id)


@app.patch("/api/workspaces/{workspace_id}")
def update_workspace(workspace_id: int, payload: WorkspaceUpdate, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    get_owned_workspace(user["id"], workspace_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return get_owned_workspace(user["id"], workspace_id)
    fields = [f"{field} = ?" for field in changes]
    values = list(changes.values()) + [workspace_id, user["id"]]
    with get_connection() as conn:
        conn.execute(
            f"UPDATE research_workspaces SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            values,
        )
    return get_owned_workspace(user["id"], workspace_id)


@app.delete("/api/workspaces/{workspace_id}")
def delete_workspace(workspace_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    get_owned_workspace(user["id"], workspace_id)
    with get_connection() as conn:
        for table in ("searches", "claims", "evidence", "claim_relations"):
            conn.execute(
                f"UPDATE {table} SET workspace_id = NULL WHERE workspace_id = ? AND user_id = ?",
                (workspace_id, user["id"]),
            )
        conn.execute(
            "DELETE FROM research_workspaces WHERE id = ? AND user_id = ?",
            (workspace_id, user["id"]),
        )
    return {"deleted": True, "workspace_id": workspace_id, "data_preserved": True}


@app.post("/api/claims", status_code=201)
def create_claim(payload: ClaimCreate, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if payload.workspace_id is not None:
        get_owned_workspace(user["id"], payload.workspace_id)
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO claims (user_id, claim_text, status, workspace_id) VALUES (?, ?, ?, ?)",
            (user["id"], payload.claim_text, payload.status, payload.workspace_id),
        )
        claim_id = cursor.lastrowid
    return claim_response(user["id"], claim_id)


@app.post("/api/evidence", status_code=201)
def create_evidence(payload: EvidenceCreate, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if payload.workspace_id is not None:
        get_owned_workspace(user["id"], payload.workspace_id)
    if not (payload.source_id or payload.doi or payload.url):
        raise HTTPException(status_code=422, detail="Evidence requires a source reference")
    if not payload.excerpt:
        raise HTTPException(status_code=422, detail="Evidence requires an excerpt or abstract")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO evidence
                (user_id, source_id, source_title, authors, year, doi, url, excerpt, evidence_type, relation, confidence, workspace_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                payload.source_id,
                payload.source_title,
                json.dumps(payload.authors),
                payload.year,
                payload.doi,
                payload.url,
                payload.excerpt,
                payload.evidence_type,
                payload.relation,
                payload.confidence,
                payload.workspace_id,
            ),
        )
        evidence_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM evidence WHERE id = ? AND user_id = ?", (evidence_id, user["id"])).fetchone()
    return evidence_from_row(row)


@app.post("/api/claims/{claim_id}/evidence")
def link_evidence(claim_id: int, payload: EvidenceLink, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with get_connection() as conn:
        claim = conn.execute(
            "SELECT id FROM claims WHERE id = ? AND user_id = ?",
            (claim_id, user["id"]),
        ).fetchone()
        evidence = conn.execute(
            "SELECT id, workspace_id FROM evidence WHERE id = ? AND user_id = ?",
            (payload.evidence_id, user["id"]),
        ).fetchone()
        if not claim or not evidence:
            raise HTTPException(status_code=404, detail="Claim or evidence not found")
        claim_workspace = conn.execute(
            "SELECT workspace_id FROM claims WHERE id = ? AND user_id = ?",
            (claim_id, user["id"]),
        ).fetchone()["workspace_id"]
        if claim_workspace and evidence["workspace_id"] and claim_workspace != evidence["workspace_id"]:
            raise HTTPException(status_code=409, detail="Claim and evidence belong to different workspaces")
        if claim_workspace and evidence["workspace_id"] is None:
            conn.execute(
                "UPDATE evidence SET workspace_id = ? WHERE id = ? AND user_id = ?",
                (claim_workspace, payload.evidence_id, user["id"]),
            )
        existing = conn.execute(
            "SELECT 1 FROM claim_evidence WHERE claim_id = ? AND evidence_id = ?",
            (claim_id, payload.evidence_id),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO claim_evidence (claim_id, evidence_id) VALUES (?, ?)",
                (claim_id, payload.evidence_id),
            )
    return claim_response(user["id"], claim_id)


@app.get("/api/claims/{claim_id}")
def get_claim(claim_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return claim_response(user["id"], claim_id)


@app.get("/api/claims/{claim_id}/critic")
def critic_claim(claim_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return claim_critic_response(user["id"], claim_id)


@app.post("/api/claims/{claim_id}/relations", status_code=201)
def create_claim_relation(claim_id: int, payload: ClaimRelationCreate, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if payload.workspace_id is not None:
        get_owned_workspace(user["id"], payload.workspace_id)
    with get_connection() as conn:
        source_claim = conn.execute(
            "SELECT id, workspace_id FROM claims WHERE id = ? AND user_id = ?",
            (claim_id, user["id"]),
        ).fetchone()
        target_claim = conn.execute(
            "SELECT id, workspace_id FROM claims WHERE id = ? AND user_id = ?",
            (payload.target_claim_id, user["id"]),
        ).fetchone()
        if not source_claim or not target_claim:
            raise HTTPException(status_code=404, detail="Claim not found or not owned by user")
        workspace_id = payload.workspace_id or source_claim["workspace_id"]
        if workspace_id and (
            source_claim["workspace_id"] != workspace_id
            or target_claim["workspace_id"] != workspace_id
        ):
            raise HTTPException(status_code=409, detail="Both claims must belong to the relation workspace")

        duplicate = conn.execute(
            "SELECT id FROM claim_relations WHERE user_id = ? AND source_claim_id = ? AND target_claim_id = ? AND relation = ?",
            (user["id"], claim_id, payload.target_claim_id, payload.relation),
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="Claim relation already exists")

        cursor = conn.execute(
            "INSERT INTO claim_relations (user_id, source_claim_id, target_claim_id, relation, workspace_id) VALUES (?, ?, ?, ?, ?)",
            (user["id"], claim_id, payload.target_claim_id, payload.relation, workspace_id),
        )
        relation_row = conn.execute(
            "SELECT * FROM claim_relations WHERE id = ? AND user_id = ?",
            (cursor.lastrowid, user["id"]),
        ).fetchone()

    return claim_relation_response(relation_row)


@app.get("/api/claims/{claim_id}/relations")
def get_claim_relations(claim_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        claim = conn.execute(
            "SELECT id FROM claims WHERE id = ? AND user_id = ?",
            (claim_id, user["id"]),
        ).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found or not owned by user")
        rows = conn.execute(
            """
            SELECT * FROM claim_relations
            WHERE user_id = ? AND (source_claim_id = ? OR target_claim_id = ?)
            ORDER BY created_at DESC
            """,
            (user["id"], claim_id, claim_id),
        ).fetchall()

    return [claim_relation_response(row) for row in rows]


@app.get("/api/search")
async def search(
    query: str = Query(..., alias="q"),
    workspace_id: int | None = Query(default=None),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Dict[str, Any]:
    authenticated_user = None
    if workspace_id is not None:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Workspace search requires authentication")
        token = authorization.split(" ", 1)[1]
        authenticated_user = get_user_by_username(decode_token_value(token))
        if not authenticated_user:
            raise HTTPException(status_code=401, detail="Invalid token")
        get_owned_workspace(authenticated_user["id"], workspace_id)

    source_results = await asyncio.gather(
        fetch_source_safely("OpenAlex", fetch_openalex, query),
        fetch_source_safely("Semantic Scholar", fetch_semantic_scholar, query),
        fetch_source_safely("Crossref", fetch_crossref, query),
    )
    successful_sources = [name for name, source, error in source_results if source]
    failed_sources = [name for name, source, error in source_results if error]
    flat_results = [item for _, source, _ in source_results for item in source]
    merged = rank_results(deduplicate_results(flat_results), query)
    payload = {
        "query": query,
        "count": len(merged),
        "results": [item.model_dump() for item in merged],
        "sources": successful_sources,
    }
    if failed_sources:
        payload["failed_sources"] = failed_sources
        payload["warning"] = "Some external sources were unavailable."

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            user = authenticated_user or get_user_by_username(decode_token_value(token))
            if user:
                with get_connection() as conn:
                    conn.execute(
                        "INSERT INTO searches (user_id, query, results, workspace_id) VALUES (?, ?, ?, ?)",
                        (user["id"], query, json.dumps(payload["results"]), workspace_id),
                    )
        except Exception:
            pass

    return payload
