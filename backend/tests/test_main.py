import json
import uuid

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import (
    CouncilInputContract,
    CrossrefClient,
    EvidenceExtraction,
    ExtractionRawInputReference,
    ExtractionSourceLocation,
    ExternalProviderResult,
    RetractionClient,
    SearchResult,
    app,
    council_analysis_from_input,
    conflict_analysis_from_input,
    decision_analysis_from_input,
    evidence_quality_from_input,
    evidence_assessment_from_input,
    evidence_assessments_from_input,
    build_evidence_extraction,
    source_verifications_from_input,
    synthesis_analysis_from_input,
)

client = TestClient(app)


def unique_identity(prefix: str):
    token = uuid.uuid4().hex[:8]
    return f"{prefix}_{token}", f"{token}@example.com"


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_search_endpoint():
    response = client.get("/api/search", params={"q": "AI"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "AI"
    assert "results" in body


def test_auth_flow_register_login():
    username, email = unique_identity("demo_user_1")
    password = "StrongPass123!"

    register = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert register.status_code == 201

    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    payload = login.json()
    assert "token" in payload
    assert payload["user"]["username"] == username


def test_history_is_saved_for_authenticated_user():
    username, email = unique_identity("demo_user_2")
    password = "StrongPass123!"

    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    token = login.json()["token"]

    response = client.get("/api/search-history", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_authenticated_search_integration(monkeypatch):
    username, email = unique_identity("integration_user")
    password = "StrongPass123"

    async def fake_openalex(query):
        return [SearchResult(title="Shared Research Result", source="OpenAlex", year=2024, url="https://openalex.org/work")]

    async def fake_semantic_scholar(query):
        return [SearchResult(title="Shared Research Result", source="Semantic Scholar", year=2024, url="https://semanticscholar.org/paper")]

    async def fake_crossref(query):
        return [SearchResult(title="Crossref Result", source="Crossref", year=2023, url="https://doi.org/example")]

    monkeypatch.setattr(main_module, "fetch_openalex", fake_openalex)
    monkeypatch.setattr(main_module, "fetch_semantic_scholar", fake_semantic_scholar)
    monkeypatch.setattr(main_module, "fetch_crossref", fake_crossref)

    register = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert register.status_code == 201
    token = register.json()["token"]

    search = client.get(
        "/api/search",
        params={"q": "quantum computing"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search.status_code == 200
    assert search.json()["count"] == 2
    assert len(search.json()["results"]) == 2

    history = client.get(
        "/api/search-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history.status_code == 200
    assert history.json()[0]["query"] == "quantum computing"

    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    assert login.json()["user"]["username"] == username


def test_search_continues_when_one_source_fails(monkeypatch):
    username, email = unique_identity("partial_source_user")
    password = "StrongPass123"

    async def working_source(query):
        return [SearchResult(title="Working Source Result", source="OpenAlex", year=2024, url="https://example.com/result")]

    async def failed_source(query):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(main_module, "fetch_openalex", working_source)
    monkeypatch.setattr(main_module, "fetch_semantic_scholar", working_source)
    monkeypatch.setattr(main_module, "fetch_crossref", failed_source)

    register = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    token = register.json()["token"]
    search = client.get(
        "/api/search",
        params={"q": "partial availability"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert search.status_code == 200
    assert search.json()["count"] == 1
    assert search.json()["sources"] == ["OpenAlex", "Semantic Scholar"]
    assert search.json()["failed_sources"] == ["Crossref"]

    history = client.get(
        "/api/search-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history.status_code == 200
    assert history.json()[0]["query"] == "partial availability"


def test_search_result_keeps_legacy_shape_and_supports_new_fields():
    legacy = SearchResult(title="Legacy result", source="OpenAlex", url="https://example.com")
    enriched = SearchResult(
        title="Enriched result",
        source="Crossref",
        url="https://doi.org/10.1234/example",
        authors=["Ada Lovelace"],
        year=2024,
        doi="10.1234/example",
        abstract="A real abstract.",
        citation_count=12,
    )

    assert legacy.year is None
    assert legacy.authors == []
    assert enriched.model_dump()["citation_count"] == 12


def test_deduplication_prefers_doi_then_source_id_then_title():
    results = [
        SearchResult(title="First DOI", source="OpenAlex", url="https://example.com/1", doi="10.1000/Test"),
        SearchResult(title="Second DOI", source="Crossref", url="https://example.com/2", doi="https://doi.org/10.1000/test"),
        SearchResult(title="First source id", source="OpenAlex", url="https://example.com/3", source_id="A-1"),
        SearchResult(title="Second source id", source="Semantic Scholar", url="https://example.com/4", source_id="A-1"),
        SearchResult(title="Same Title", source="OpenAlex", url="https://example.com/5"),
        SearchResult(title=" same   title ", source="Crossref", url="https://example.com/6"),
    ]

    unique = main_module.deduplicate_results(results)

    assert [item.title for item in unique] == ["First DOI", "First source id", "Same Title"]


def test_evidence_engine_claim_lifecycle_and_user_isolation():
    username, email = unique_identity("evidence_owner")
    other_username, other_email = unique_identity("evidence_other")
    password = "StrongPass123"

    owner_register = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other_register = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_token = owner_register.json()["token"]
    other_token = other_register.json()["token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    claim = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "Quantum methods can reduce simulation cost.", "status": "active"},
    )
    assert claim.status_code == 201
    claim_id = claim.json()["id"]
    assert claim.json()["evidence_ids"] == []

    evidence = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "openalex:W123",
            "source_title": "Quantum simulation methods",
            "authors": ["Ada Lovelace"],
            "year": 2024,
            "doi": "10.1234/example",
            "url": "https://doi.org/10.1234/example",
            "excerpt": "The reported method reduced simulation cost in the evaluated setting.",
            "evidence_type": "abstract",
            "relation": "supporting",
            "confidence": 0.8,
        },
    )
    assert evidence.status_code == 201
    evidence_id = evidence.json()["id"]

    linked = client.post(
        f"/api/claims/{claim_id}/evidence",
        headers=owner_headers,
        json={"evidence_id": evidence_id},
    )
    assert linked.status_code == 200
    assert linked.json()["evidence_ids"] == [evidence_id]
    assert linked.json()["evidence"][0]["evidence_type"] == "abstract"
    assert linked.json()["evidence"][0]["relation"] == "supporting"
    assert linked.json()["evidence"][0]["confidence"] == 0.8

    fetched = client.get(f"/api/claims/{claim_id}", headers=owner_headers)
    assert fetched.status_code == 200
    assert fetched.json()["claim_text"] == "Quantum methods can reduce simulation cost."
    assert fetched.json()["evidence"][0]["excerpt"].startswith("The reported method")

    assert client.get(f"/api/claims/{claim_id}", headers=other_headers).status_code == 404
    assert client.post(
        "/api/evidence",
        headers=owner_headers,
        json={"source_title": "Untraceable", "evidence_type": "full_text"},
    ).status_code == 422


def test_claim_argument_relations_work_and_respect_user_ownership():
    username, email = unique_identity("graph_owner")
    other_username, other_email = unique_identity("graph_other")
    password = "StrongPass123"

    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_token = owner.json()["token"]
    other_token = other.json()["token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    claim_a = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "Quantum systems are increasingly practical.", "status": "active"},
    )
    claim_b = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "Quantum computing can reduce simulation cost.", "status": "active"},
    )
    claim_a_id = claim_a.json()["id"]
    claim_b_id = claim_b.json()["id"]

    evidence = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "claim-graph-evidence",
            "source_title": "Quantum methods review",
            "authors": ["Ada Lovelace"],
            "year": 2024,
            "doi": "10.1234/graph-evidence",
            "url": "https://doi.org/10.1234/graph-evidence",
            "excerpt": "The method shows measurable improvement in simulation cost.",
            "evidence_type": "abstract",
            "relation": "supporting",
            "confidence": 0.9,
        },
    )
    assert evidence.status_code == 201
    evidence_id = evidence.json()["id"]
    assert client.post(
        f"/api/claims/{claim_a_id}/evidence",
        headers=owner_headers,
        json={"evidence_id": evidence_id},
    ).status_code == 200

    relation = client.post(
        f"/api/claims/{claim_a_id}/relations",
        headers=owner_headers,
        json={"target_claim_id": claim_b_id, "relation": "supports"},
    )
    assert relation.status_code == 201
    payload = relation.json()
    assert payload["relation"] == "supports"
    assert payload["source_claim_id"] == claim_a_id
    assert payload["target_claim_id"] == claim_b_id

    graph = client.get(f"/api/claims/{claim_a_id}/relations", headers=owner_headers)
    assert graph.status_code == 200
    assert graph.json()[0]["relation"] == "supports"

    other_claim = client.post(
        "/api/claims",
        headers=other_headers,
        json={"claim_text": "Only the other user owns this claim.", "status": "draft"},
    )
    assert client.post(
        f"/api/claims/{claim_a_id}/relations",
        headers=other_headers,
        json={"target_claim_id": other_claim.json()["id"], "relation": "supports"},
    ).status_code == 404

    bad_relation = client.post(
        f"/api/claims/{claim_a_id}/relations",
        headers=owner_headers,
        json={"target_claim_id": claim_b_id, "relation": "unsupported"},
    )
    assert bad_relation.status_code == 422

    claim_view = client.get(f"/api/claims/{claim_a_id}", headers=owner_headers)
    assert claim_view.status_code == 200
    assert claim_view.json()["evidence"][0]["source_title"] == "Quantum methods review"


def test_claim_critic_rule_based_audit_and_user_isolation():
    username, email = unique_identity("critic_owner")
    other_username, other_email = unique_identity("critic_other")
    password = "StrongPass123"

    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}

    empty_claim = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "No evidence claim.", "status": "active"},
    )
    empty_claim_id = empty_claim.json()["id"]

    support_claim = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "Supporting claim.", "status": "active"},
    )
    support_claim_id = support_claim.json()["id"]
    support_evidence = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "support-1",
            "source_title": "Support source",
            "authors": ["Alpha Author"],
            "excerpt": "The evidence strongly supports this claim.",
            "evidence_type": "full_text",
            "relation": "supporting",
            "confidence": 0.95,
        },
    )
    client.post(
        f"/api/claims/{support_claim_id}/evidence",
        headers=owner_headers,
        json={"evidence_id": support_evidence.json()["id"]},
    )

    conflict_claim = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "Conflicting claim.", "status": "active"},
    )
    conflict_claim_id = conflict_claim.json()["id"]
    for payload in [
        {
            "source_id": "conflict-support",
            "source_title": "Support source",
            "authors": ["Support Author"],
            "excerpt": "This supports the claim.",
            "evidence_type": "abstract",
            "relation": "supporting",
            "confidence": 0.7,
        },
        {
            "source_id": "conflict-contradict",
            "source_title": "Contradict source",
            "authors": ["Contradict Author"],
            "excerpt": "This contradicts the claim.",
            "evidence_type": "full_text",
            "relation": "contradicting",
            "confidence": 0.6,
        },
    ]:
        evidence = client.post("/api/evidence", headers=owner_headers, json=payload)
        client.post(
            f"/api/claims/{conflict_claim_id}/evidence",
            headers=owner_headers,
            json={"evidence_id": evidence.json()["id"]},
        )

    abstract_only_claim = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "Abstract-only claim.", "status": "active"},
    )
    abstract_only_id = abstract_only_claim.json()["id"]
    abstract_evidence = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "abstract-only",
            "source_title": "Abstract evidence",
            "authors": ["Abstract Author"],
            "excerpt": "Only an abstract is available here.",
            "evidence_type": "abstract",
            "relation": "supporting",
            "confidence": 0.7,
        },
    )
    client.post(
        f"/api/claims/{abstract_only_id}/evidence",
        headers=owner_headers,
        json={"evidence_id": abstract_evidence.json()["id"]},
    )

    low_confidence_claim = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "Low confidence claim.", "status": "active"},
    )
    low_confidence_id = low_confidence_claim.json()["id"]
    low_confidence_evidence = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "low-conf",
            "source_title": "Low confidence evidence",
            "authors": ["Low Author"],
            "excerpt": "The evidence is weakly phrased.",
            "evidence_type": "abstract",
            "relation": "uncertain",
            "confidence": 0.2,
        },
    )
    client.post(
        f"/api/claims/{low_confidence_id}/evidence",
        headers=owner_headers,
        json={"evidence_id": low_confidence_evidence.json()["id"]},
    )

    empty_response = client.get(f"/api/claims/{empty_claim_id}/critic", headers=owner_headers)
    assert empty_response.status_code == 200
    assert empty_response.json()["audit_status"] == "unsupported"
    assert any("لا توجد أدلة" in issue for issue in empty_response.json()["issues"])

    support_response = client.get(f"/api/claims/{support_claim_id}/critic", headers=owner_headers)
    assert support_response.status_code == 200
    assert support_response.json()["audit_status"] == "supported"
    assert support_response.json()["supporting_count"] == 1

    conflict_response = client.get(f"/api/claims/{conflict_claim_id}/critic", headers=owner_headers)
    assert conflict_response.status_code == 200
    assert conflict_response.json()["audit_status"] == "conflicting"
    assert conflict_response.json()["contradicting_count"] == 1

    abstract_response = client.get(f"/api/claims/{abstract_only_id}/critic", headers=owner_headers)
    assert abstract_response.status_code == 200
    assert abstract_response.json()["audit_status"] == "weakly_supported"
    assert abstract_response.json()["abstract_count"] == 1
    assert any("abstract" in issue.lower() for issue in abstract_response.json()["issues"])

    low_response = client.get(f"/api/claims/{low_confidence_id}/critic", headers=owner_headers)
    assert low_response.status_code == 200
    assert low_response.json()["audit_status"] == "weakly_supported"
    assert low_response.json()["confidence_summary"]["average_confidence"] == 0.2

    assert client.get(f"/api/claims/{empty_claim_id}/critic", headers=other_headers).status_code == 404


def test_root_page_contains_title():
    response = client.get("/")
    assert response.status_code == 200
    assert "Research OS" in response.text


def test_research_workspace_unifies_research_data_and_isolates_users(monkeypatch):
    username, email = unique_identity("workspace_owner")
    other_username, other_email = unique_identity("workspace_other")
    password = "StrongPass123"

    async def workspace_source(query):
        return [SearchResult(title="Workspace source", source="OpenAlex", source_id="workspace-source")]

    monkeypatch.setattr(main_module, "fetch_openalex", workspace_source)
    monkeypatch.setattr(main_module, "fetch_semantic_scholar", workspace_source)
    monkeypatch.setattr(main_module, "fetch_crossref", workspace_source)

    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}

    workspace = client.post(
        "/api/workspaces",
        headers=owner_headers,
        json={
            "title": "Quantum methods study",
            "research_question": "Can quantum methods reduce simulation cost?",
            "notes": "Initial evidence map",
        },
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["id"]

    assert client.get(f"/api/workspaces/{workspace_id}", headers=other_headers).status_code == 404
    assert client.get(f"/api/workspaces/{workspace_id}/view", headers=other_headers).status_code == 404
    assert client.get(
        "/api/search",
        params={"q": "private workspace search", "workspace_id": workspace_id},
        headers=other_headers,
    ).status_code == 404
    assert client.get(
        "/api/search",
        params={"q": "anonymous workspace search", "workspace_id": workspace_id},
    ).status_code == 401

    search = client.get(
        "/api/search",
        params={"q": "quantum methods", "workspace_id": workspace_id},
        headers=owner_headers,
    )
    assert search.status_code == 200

    claim_a = client.post(
        "/api/claims",
        headers=owner_headers,
        json={
            "claim_text": "Quantum methods reduce simulation cost.",
            "status": "active",
            "workspace_id": workspace_id,
        },
    )
    claim_b = client.post(
        "/api/claims",
        headers=owner_headers,
        json={
            "claim_text": "The reduction depends on the evaluated setting.",
            "status": "draft",
            "workspace_id": workspace_id,
        },
    )
    assert claim_a.status_code == 201
    assert claim_b.status_code == 201
    claim_a_id = claim_a.json()["id"]
    claim_b_id = claim_b.json()["id"]

    evidence = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "workspace-evidence",
            "source_title": "Quantum methods review",
            "authors": ["Ada Lovelace"],
            "excerpt": "The evaluated method reduced simulation cost.",
            "evidence_type": "full_text",
            "relation": "supporting",
            "confidence": 0.9,
            "workspace_id": workspace_id,
        },
    )
    assert evidence.status_code == 201
    evidence_id = evidence.json()["id"]
    linked = client.post(
        f"/api/claims/{claim_a_id}/evidence",
        headers=owner_headers,
        json={"evidence_id": evidence_id},
    )
    assert linked.status_code == 200

    relation = client.post(
        f"/api/claims/{claim_a_id}/relations",
        headers=owner_headers,
        json={"target_claim_id": claim_b_id, "relation": "supports", "workspace_id": workspace_id},
    )
    assert relation.status_code == 201

    critic = client.get(f"/api/claims/{claim_a_id}/critic", headers=owner_headers)
    assert critic.status_code == 200
    assert critic.json()["audit_status"] == "supported"

    view = client.get(f"/api/workspaces/{workspace_id}/view", headers=owner_headers)
    assert view.status_code == 200
    body = view.json()
    assert body["research_question"] == "Can quantum methods reduce simulation cost?"
    assert body["summary"] == {
        "search_count": 1,
        "claim_count": 2,
        "evidence_count": 1,
        "claim_relation_count": 1,
    }
    assert body["claims"][0]["evidence"][0]["id"] == evidence_id
    assert body["claims"][0]["relations"][0]["relation"] == "supports"
    assert body["claims"][0]["critic"]["audit_status"] == "supported"

    listed = client.get("/api/workspaces", headers=owner_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["claim_count"] == 2

    updated = client.patch(
        f"/api/workspaces/{workspace_id}",
        headers=owner_headers,
        json={"title": "Updated quantum study"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated quantum study"

    assert client.get("/api/workspaces", headers=other_headers).json() == []
    assert client.post(
        "/api/claims",
        headers=other_headers,
        json={"claim_text": "Cross-user claim", "workspace_id": workspace_id},
    ).status_code == 404

    deleted = client.delete(f"/api/workspaces/{workspace_id}", headers=owner_headers)
    assert deleted.status_code == 200
    assert deleted.json()["data_preserved"] is True
    assert client.get(f"/api/workspaces/{workspace_id}", headers=owner_headers).status_code == 404
    preserved_claim = client.get(f"/api/claims/{claim_a_id}", headers=owner_headers)
    assert preserved_claim.status_code == 200
    assert preserved_claim.json()["workspace_id"] is None


def test_research_memory_snapshot_for_empty_workspace():
    username, email = unique_identity("memory_empty")
    register = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "StrongPass123"},
    )
    headers = {"Authorization": f"Bearer {register.json()['token']}"}
    workspace = client.post(
        "/api/workspaces",
        headers=headers,
        json={"title": "Empty memory", "research_question": "What remains unknown?"},
    )

    response = client.get(f"/api/workspaces/{workspace.json()['id']}/memory", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["workspace"]["research_question"] == "What remains unknown?"
    assert body["search_history"] == {"count": 0, "items": []}
    assert body["claims"] == []
    assert body["evidence"] == []
    assert body["claim_relations"] == []
    assert body["critic"] == []
    assert body["summary"] == {
        "search_count": 0,
        "claim_count": 0,
        "evidence_count": 0,
        "claim_relation_count": 0,
    }


def test_research_memory_snapshot_contains_structured_history_and_isolates_users(monkeypatch):
    username, email = unique_identity("memory_owner")
    other_username, other_email = unique_identity("memory_other")

    async def memory_source(query):
        return [SearchResult(title="Memory source", source="OpenAlex", source_id="memory-source")]

    monkeypatch.setattr(main_module, "fetch_openalex", memory_source)
    monkeypatch.setattr(main_module, "fetch_semantic_scholar", memory_source)
    monkeypatch.setattr(main_module, "fetch_crossref", memory_source)

    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "StrongPass123"},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": "StrongPass123"},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    workspace = client.post(
        "/api/workspaces",
        headers=owner_headers,
        json={
            "title": "Memory study",
            "research_question": "Does the method improve outcomes?",
            "notes": "Structured memory test",
        },
    )
    workspace_id = workspace.json()["id"]

    search = client.get(
        "/api/search",
        params={"q": "method outcomes", "workspace_id": workspace_id},
        headers=owner_headers,
    )
    assert search.status_code == 200

    source_claim = client.post(
        "/api/claims",
        headers=owner_headers,
        json={
            "claim_text": "The method improves outcomes.",
            "status": "active",
            "workspace_id": workspace_id,
        },
    )
    target_claim = client.post(
        "/api/claims",
        headers=owner_headers,
        json={
            "claim_text": "The improvement depends on context.",
            "status": "draft",
            "workspace_id": workspace_id,
        },
    )
    source_claim_id = source_claim.json()["id"]
    target_claim_id = target_claim.json()["id"]
    evidence = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "memory-evidence",
            "source_title": "Memory evidence source",
            "excerpt": "The observed results support the improvement.",
            "evidence_type": "full_text",
            "relation": "supporting",
            "confidence": 0.9,
            "workspace_id": workspace_id,
        },
    )
    evidence_id = evidence.json()["id"]
    assert client.post(
        f"/api/claims/{source_claim_id}/evidence",
        headers=owner_headers,
        json={"evidence_id": evidence_id},
    ).status_code == 200
    relation = client.post(
        f"/api/claims/{source_claim_id}/relations",
        headers=owner_headers,
        json={
            "target_claim_id": target_claim_id,
            "relation": "qualifies",
            "workspace_id": workspace_id,
        },
    )
    assert relation.status_code == 201
    assert client.get(f"/api/claims/{source_claim_id}/critic", headers=owner_headers).json()["audit_status"] == "supported"

    response = client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["workspace"]["id"] == workspace_id
    assert body["workspace"]["created_at"]
    assert body["workspace"]["updated_at"]
    assert body["search_history"]["count"] == 1
    assert body["search_history"]["items"][0]["query"] == "method outcomes"
    assert body["summary"] == {
        "search_count": 1,
        "claim_count": 2,
        "evidence_count": 1,
        "claim_relation_count": 1,
    }
    assert body["evidence"][0]["id"] == evidence_id
    assert body["claim_relations"][0]["relation"] == "qualifies"
    assert body["critic"] == [
        {
            "claim_id": source_claim_id,
            "audit_status": "supported",
            "issues": ["الادعاء يعتمد على دليل واحد فقط."],
        },
        {
            "claim_id": target_claim_id,
            "audit_status": "unsupported",
            "issues": [
                "لا توجد أدلة مرتبطة بهذا الادعاء.",
                    "لا توجد قيم confidence للأدلة المرتبطة بهذا الادعاء.",
                "هذا الادعاء مرتبط بـ Claims أخرى لكنه لا يملك Evidence مباشر.",
            ],
        },
    ]
    assert client.get(f"/api/workspaces/{workspace_id}/memory", headers=other_headers).status_code == 404


def test_council_input_contract_and_analysis_are_traceable(monkeypatch):
    username, email = unique_identity("council_owner")
    other_username, other_email = unique_identity("council_other")
    password = "StrongPass123"

    async def council_source(query):
        return [SearchResult(title="Council source", source="OpenAlex", source_id="council-search-source")]

    monkeypatch.setattr(main_module, "fetch_openalex", council_source)
    monkeypatch.setattr(main_module, "fetch_semantic_scholar", council_source)
    monkeypatch.setattr(main_module, "fetch_crossref", council_source)

    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}

    workspace = client.post(
        "/api/workspaces",
        headers=owner_headers,
        json={
            "title": "Council foundation",
            "research_question": "Do the observed methods improve outcomes?",
        },
    )
    workspace_id = workspace.json()["id"]
    assert client.get(f"/api/workspaces/{workspace_id}/council/input", headers=owner_headers).json()["claims"] == []

    search = client.get(
        "/api/search",
        params={"q": "observed methods", "workspace_id": workspace_id},
        headers=owner_headers,
    )
    assert search.status_code == 200

    empty_claim = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "There is not enough evidence yet.", "workspace_id": workspace_id},
    )
    claim_a = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "The method improves outcomes.", "status": "active", "workspace_id": workspace_id},
    )
    claim_b = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "The effect depends on context.", "status": "draft", "workspace_id": workspace_id},
    )
    empty_claim_id = empty_claim.json()["id"]
    claim_a_id = claim_a.json()["id"]
    claim_b_id = claim_b.json()["id"]

    evidence_payloads = [
        {
            "source_id": "council-support",
            "source_title": "Supporting source",
            "doi": "10.1234/support",
            "url": "https://doi.org/10.1234/support",
            "excerpt": "The evaluated method improved outcomes.",
            "evidence_type": "full_text",
            "relation": "supporting",
            "confidence": 0.9,
            "workspace_id": workspace_id,
        },
        {
            "source_id": "council-contradiction",
            "source_title": "Contradicting source",
            "url": "https://example.com/contradiction",
            "excerpt": "The method did not improve outcomes in another setting.",
            "evidence_type": "abstract",
            "relation": "contradicting",
            "confidence": 0.7,
            "workspace_id": workspace_id,
        },
        {
            "source_id": "council-uncertain",
            "source_title": "Uncertain source",
            "url": "https://example.com/uncertain",
            "excerpt": "The context may affect the observed effect.",
            "evidence_type": "abstract",
            "relation": "uncertain",
            "confidence": 0.2,
            "workspace_id": workspace_id,
        },
    ]
    evidence_ids = []
    for payload in evidence_payloads:
        evidence = client.post("/api/evidence", headers=owner_headers, json=payload)
        assert evidence.status_code == 201
        evidence_ids.append(evidence.json()["id"])

    assert client.post(
        f"/api/claims/{claim_a_id}/evidence",
        headers=owner_headers,
        json={"evidence_id": evidence_ids[0]},
    ).status_code == 200
    assert client.post(
        f"/api/claims/{claim_a_id}/evidence",
        headers=owner_headers,
        json={"evidence_id": evidence_ids[1]},
    ).status_code == 200
    assert client.post(
        f"/api/claims/{claim_b_id}/evidence",
        headers=owner_headers,
        json={"evidence_id": evidence_ids[2]},
    ).status_code == 200
    relation = client.post(
        f"/api/claims/{claim_a_id}/relations",
        headers=owner_headers,
        json={"target_claim_id": claim_b_id, "relation": "qualifies", "workspace_id": workspace_id},
    )
    relation_id = relation.json()["id"]

    before = client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json()
    council_response = client.get(f"/api/workspaces/{workspace_id}/council/input", headers=owner_headers)
    assert council_response.status_code == 200
    council_input = council_response.json()
    assert "analysis" not in council_input
    assert council_input["workspace"]["id"] == workspace_id
    assert council_input["workspace"]["research_question"] == "Do the observed methods improve outcomes?"
    assert council_input["search_history"]["count"] == 1
    assert {claim["id"] for claim in council_input["claims"]} == {empty_claim_id, claim_a_id, claim_b_id}
    assert {evidence["id"] for evidence in council_input["evidence"]} == set(evidence_ids)
    assert council_input["claim_relations"][0]["id"] == relation_id
    assert {item["claim_id"] for item in council_input["critic"]} == {empty_claim_id, claim_a_id, claim_b_id}

    analysis = council_analysis_from_input(CouncilInputContract.model_validate(council_input))
    analyses = {item.claim_id: item for item in analysis.claims}
    assert analyses[empty_claim_id].critic_status == "unsupported"
    assert "no_evidence" in analyses[empty_claim_id].analysis_flags
    assert analyses[claim_a_id].critic_status == "conflicting"
    assert analyses[claim_a_id].supporting_evidence_ids == [evidence_ids[0]]
    assert analyses[claim_a_id].contradicting_evidence_ids == [evidence_ids[1]]
    assert analyses[claim_a_id].evidence_count == 2
    assert {
        "supporting_evidence_present",
        "contradicting_evidence_present",
        "full_text_present",
        "conflicting_evidence",
        "related_claims_present",
    }.issubset(set(analyses[claim_a_id].analysis_flags))
    assert analyses[claim_b_id].critic_status == "weakly_supported"
    assert "uncertain_evidence_present" in analyses[claim_b_id].analysis_flags
    assert "abstract_only" in analyses[claim_b_id].analysis_flags
    assert "low_confidence" in analyses[claim_b_id].analysis_flags
    evidence_assessment = {item.evidence_id: item for item in analysis.evidence}
    assert evidence_assessment[evidence_ids[0]].claim_ids == [claim_a_id]
    assert evidence_assessment[evidence_ids[0]].source_reference["doi"] == "10.1234/support"
    assert evidence_assessment[evidence_ids[1]].source_reference["url"] == "https://example.com/contradiction"
    assert before == client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json()
    assert client.get(f"/api/workspaces/{workspace_id}/council/input", headers=other_headers).status_code == 404


def test_evidence_assessment_is_structural_traceable_and_isolated():
    username, email = unique_identity("assessment_owner")
    other_username, other_email = unique_identity("assessment_other")
    password = "StrongPass123"
    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    workspace = client.post(
        "/api/workspaces",
        headers=owner_headers,
        json={"title": "Evidence assessment", "research_question": "What does the evidence show?"},
    )
    workspace_id = workspace.json()["id"]
    empty = client.get(
        f"/api/workspaces/{workspace_id}/council/evidence-assessment",
        headers=owner_headers,
    )
    assert empty.status_code == 200
    assert empty.json() == {
        "workspace_id": workspace_id,
        "assessments": [],
        "summary": {
            "evidence_count": 0,
            "complete_count": 0,
            "partial_count": 0,
            "insufficient_metadata_count": 0,
        },
    }

    claim_a = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "The intervention improves outcomes.", "workspace_id": workspace_id},
    )
    claim_b = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "The effect depends on context.", "workspace_id": workspace_id},
    )
    claim_a_id = claim_a.json()["id"]
    claim_b_id = claim_b.json()["id"]
    evidence_payloads = [
        {
            "source_id": "assessment-support",
            "source_title": "Supporting source",
            "url": "https://example.com/support",
            "excerpt": "The intervention improved outcomes.",
            "evidence_type": "full_text",
            "relation": "supporting",
            "confidence": 0.9,
            "workspace_id": workspace_id,
        },
        {
            "source_id": "assessment-contradiction",
            "source_title": "Contradicting source",
            "url": "https://example.com/contradiction",
            "excerpt": "The intervention did not improve outcomes in this setting.",
            "evidence_type": "abstract",
            "relation": "contradicting",
            "confidence": 0.6,
            "workspace_id": workspace_id,
        },
        {
            "source_id": "assessment-uncertain",
            "source_title": "Uncertain source",
            "url": "https://example.com/uncertain",
            "excerpt": "The context may influence the effect.",
            "evidence_type": "abstract",
            "relation": "uncertain",
            "confidence": 0.2,
            "workspace_id": workspace_id,
        },
    ]
    evidence_ids = []
    for payload in evidence_payloads:
        response = client.post("/api/evidence", headers=owner_headers, json=payload)
        assert response.status_code == 201
        evidence_ids.append(response.json()["id"])

    for evidence_id, claim_id in [
        (evidence_ids[0], claim_a_id),
        (evidence_ids[0], claim_b_id),
        (evidence_ids[1], claim_a_id),
        (evidence_ids[2], claim_b_id),
    ]:
        assert client.post(
            f"/api/claims/{claim_id}/evidence",
            headers=owner_headers,
            json={"evidence_id": evidence_id},
        ).status_code == 200

    memory_before = client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json()
    assessment_response = client.get(
        f"/api/workspaces/{workspace_id}/council/evidence-assessment",
        headers=owner_headers,
    )
    assert assessment_response.status_code == 200
    body = assessment_response.json()
    assessments = {item["evidence_id"]: item for item in body["assessments"]}
    assert body["summary"] == {
        "evidence_count": 3,
        "complete_count": 3,
        "partial_count": 0,
        "insufficient_metadata_count": 0,
    }
    assert assessments[evidence_ids[0]]["claim_ids"] == [claim_a_id, claim_b_id]
    assert "linked_to_multiple_claims" in assessments[evidence_ids[0]]["assessment_flags"]
    assert "high_confidence" in assessments[evidence_ids[0]]["assessment_flags"]
    assert assessments[evidence_ids[0]]["completeness"] == "complete"
    assert "contradicting" in assessments[evidence_ids[1]]["assessment_flags"]
    assert "medium_confidence" in assessments[evidence_ids[1]]["assessment_flags"]
    assert "abstract" in assessments[evidence_ids[1]]["assessment_flags"]
    assert "uncertain" in assessments[evidence_ids[2]]["assessment_flags"]
    assert "low_confidence" in assessments[evidence_ids[2]]["assessment_flags"]
    assert assessments[evidence_ids[0]]["traceability"] == {
        "evidence_id": evidence_ids[0],
        "claim_ids": [claim_a_id, claim_b_id],
        "source_id": "assessment-support",
    }
    assert assessments[evidence_ids[0]]["source_reference"]["source_id"] == "assessment-support"
    assert client.get(f"/api/claims/{claim_a_id}/critic", headers=owner_headers).json()["audit_status"] == "conflicting"
    council = client.get(f"/api/workspaces/{workspace_id}/council/input", headers=owner_headers).json()
    analysis = council_analysis_from_input(CouncilInputContract.model_validate(council))
    claim_analysis = {item.claim_id: item for item in analysis.claims}[claim_a_id]
    assert claim_analysis.supporting_count == 1
    assert claim_analysis.contradicting_count == 1
    assert claim_analysis.uncertain_count == 0
    assert claim_analysis.evidence_completeness_summary == {
        "complete": 2,
        "partial": 0,
        "insufficient_metadata": 0,
    }
    assert memory_before == client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json()
    assert client.get(
        f"/api/workspaces/{workspace_id}/council/evidence-assessment",
        headers=other_headers,
    ).status_code == 404

    partial = evidence_assessment_from_input(
        {
            "id": 9001,
            "source_id": "partial-source",
            "source_title": "Partial source",
            "doi": None,
            "url": None,
            "excerpt": None,
            "evidence_type": "abstract",
            "relation": "uncertain",
            "confidence": 0.4,
        },
        [claim_a_id],
    )
    assert partial.completeness == "partial"
    assert partial.excerpt_present is False
    assert "medium_confidence" in partial.assessment_flags
    missing_source = evidence_assessment_from_input(
        {
            "id": 9002,
            "source_id": None,
            "source_title": "Unreferenced source",
            "doi": None,
            "url": None,
            "excerpt": "An excerpt exists.",
            "evidence_type": "full_text",
            "relation": "supporting",
            "confidence": None,
        },
        [],
    )
    assert missing_source.completeness == "insufficient_metadata"
    assert "source_reference_present" not in missing_source.assessment_flags
    assert "excerpt_present" in missing_source.assessment_flags


def test_conflict_analysis_is_deterministic_traceable_and_non_mutating():
    username, email = unique_identity("conflict_owner")
    other_username, other_email = unique_identity("conflict_other")
    password = "StrongPass123"
    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    workspace = client.post(
        "/api/workspaces",
        headers=owner_headers,
        json={"title": "Conflict analysis", "research_question": "Where is the evidence conflict?"},
    )
    workspace_id = workspace.json()["id"]
    empty = client.get(
        f"/api/workspaces/{workspace_id}/council/conflicts",
        headers=owner_headers,
    )
    assert empty.status_code == 200
    assert empty.json() == {
        "workspace_id": workspace_id,
        "conflicts": [],
        "summary": {
            "total": 0,
            "evidence_conflicts": 0,
            "claim_relation_conflicts": 0,
            "mixed_conflicts": 0,
        },
    }

    claim_a = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "The intervention improves outcomes.", "workspace_id": workspace_id},
    )
    claim_b = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "The intervention does not improve outcomes.", "workspace_id": workspace_id},
    )
    claim_a_id = claim_a.json()["id"]
    claim_b_id = claim_b.json()["id"]
    evidence_ids = []
    for relation, source_id, excerpt in [
        ("supporting", "conflict-support", "The intervention improves outcomes."),
        ("contradicting", "conflict-contradict", "The intervention does not improve outcomes."),
    ]:
        evidence = client.post(
            "/api/evidence",
            headers=owner_headers,
            json={
                "source_id": source_id,
                "source_title": source_id,
                "url": f"https://example.com/{source_id}",
                "excerpt": excerpt,
                "evidence_type": "full_text",
                "relation": relation,
                "confidence": 0.9 if relation == "supporting" else 0.2,
                "workspace_id": workspace_id,
            },
        )
        assert evidence.status_code == 201
        evidence_ids.append(evidence.json()["id"])
        assert client.post(
            f"/api/claims/{claim_a_id}/evidence",
            headers=owner_headers,
            json={"evidence_id": evidence.json()["id"]},
        ).status_code == 200

    relation = client.post(
        f"/api/claims/{claim_a_id}/relations",
        headers=owner_headers,
        json={
            "target_claim_id": claim_b_id,
            "relation": "contradicts",
            "workspace_id": workspace_id,
        },
    )
    assert relation.status_code == 201
    relation_id = relation.json()["id"]
    memory_before = client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json()
    critic_before = client.get(f"/api/claims/{claim_a_id}/critic", headers=owner_headers).json()

    conflicts_response = client.get(
        f"/api/workspaces/{workspace_id}/council/conflicts",
        headers=owner_headers,
    )
    assert conflicts_response.status_code == 200
    body = conflicts_response.json()
    assert body["summary"] == {
        "total": 1,
        "evidence_conflicts": 0,
        "claim_relation_conflicts": 0,
        "mixed_conflicts": 1,
    }
    conflict = body["conflicts"][0]
    assert conflict["conflict_type"] == "mixed_conflict"
    assert conflict["claim_ids"] == [claim_a_id, claim_b_id]
    assert conflict["evidence_ids"] == sorted(evidence_ids)
    assert conflict["supporting_evidence_ids"] == [evidence_ids[0]]
    assert conflict["contradicting_evidence_ids"] == [evidence_ids[1]]
    assert conflict["relation_ids"] == [relation_id]
    assert conflict["source_ids"] == ["conflict-contradict", "conflict-support"]
    assert conflict["traceability"] == {
        "claim_ids": [claim_a_id, claim_b_id],
        "evidence_ids": sorted(evidence_ids),
        "relation_ids": [relation_id],
        "source_ids": ["conflict-contradict", "conflict-support"],
    }
    assert conflict["conflict_id"].startswith(
        f"mixed_conflict:claim:{claim_a_id}:relation:{relation_id}:"
    )
    again = client.get(
        f"/api/workspaces/{workspace_id}/council/conflicts",
        headers=owner_headers,
    ).json()
    assert again == body
    assert client.get(f"/api/claims/{claim_a_id}/critic", headers=owner_headers).json() == critic_before
    assert client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json() == memory_before

    council = client.get(f"/api/workspaces/{workspace_id}/council/input", headers=owner_headers).json()
    analysis = council_analysis_from_input(CouncilInputContract.model_validate(council))
    analyses = {item.claim_id: item for item in analysis.claims}
    assert analyses[claim_a_id].critic_status == "conflicting"
    assert analyses[claim_a_id].conflict_count == 1
    assert analyses[claim_a_id].conflict_types == ["mixed_conflict"]
    assert analyses[claim_b_id].conflict_count == 1
    assert analysis.conflicts[0].conflict_id == conflict["conflict_id"]
    assert client.get(
        f"/api/workspaces/{workspace_id}/council/conflicts",
        headers=other_headers,
    ).status_code == 404

    def snapshot(claim_relation: str, evidence_relation: str | list[str] | None) -> CouncilInputContract:
        evidence = []
        claim_evidence = []
        if evidence_relation:
            relations = [evidence_relation] if isinstance(evidence_relation, str) else evidence_relation
            evidence = [{
                "id": 501 + index,
                "source_id": f"snapshot-source-{index}",
                "source_title": "Snapshot source",
                "doi": None,
                "url": f"https://example.com/snapshot-{index}",
                "excerpt": "Snapshot excerpt",
                "evidence_type": "abstract",
                "relation": relation,
                "confidence": 0.5,
            } for index, relation in enumerate(relations)]
            claim_evidence = evidence
        return CouncilInputContract.model_validate({
            "workspace": {"id": 77},
            "search_history": {"count": 0, "items": []},
            "claims": [{"id": 11, "claim_text": "Snapshot claim", "evidence_ids": [item["id"] for item in evidence], "evidence": claim_evidence, "relations": []}],
            "evidence": evidence,
            "claim_relations": ([{"id": 601, "source_claim_id": 11, "target_claim_id": 12, "relation": claim_relation}] if claim_relation else []),
            "critic": [],
            "summary": {"search_count": 0, "claim_count": 1, "evidence_count": len(evidence), "claim_relation_count": 1 if claim_relation else 0},
        })

    assert conflict_analysis_from_input(snapshot("supports", "supporting")) == []
    assert conflict_analysis_from_input(snapshot("supports", "contradicting")) == []
    assert conflict_analysis_from_input(snapshot("supports", None)) == []
    evidence_only = conflict_analysis_from_input(snapshot("", ["supporting", "contradicting"]))
    assert len(evidence_only) == 1
    assert evidence_only[0].conflict_type == "evidence_conflict"
    assert evidence_only[0].supporting_evidence_ids == [501]
    assert evidence_only[0].contradicting_evidence_ids == [502]
    relation_only = conflict_analysis_from_input(snapshot("contradicts", None))
    assert relation_only[0].conflict_type == "claim_relation_conflict"
    assert relation_only[0].relation_ids == [601]


def test_decision_analysis_is_read_only_deterministic_and_does_not_resolve_conflicts():
    username, email = unique_identity("decision_owner")
    other_username, other_email = unique_identity("decision_other")
    password = "StrongPass123"
    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    workspace = client.post(
        "/api/workspaces",
        headers=owner_headers,
        json={"title": "Decision analysis", "research_question": "What can be decided structurally?"},
    )
    workspace_id = workspace.json()["id"]
    empty = client.get(f"/api/workspaces/{workspace_id}/council/decisions", headers=owner_headers)
    assert empty.status_code == 200
    assert empty.json() == {
        "workspace_id": workspace_id,
        "decisions": [],
        "summary": {
            "total": 0,
            "insufficient_evidence": 0,
            "unsupported": 0,
            "conflicting": 0,
            "structurally_supported": 0,
        },
    }

    claim_payloads = [
        "No evidence claim.",
        "Supporting-only claim.",
        "Contradicting-only claim.",
        "Uncertain-only claim.",
        "Evidence conflict claim.",
        "Relation source claim.",
        "Relation target claim.",
    ]
    claim_ids = []
    for claim_text in claim_payloads:
        response = client.post(
            "/api/claims",
            headers=owner_headers,
            json={"claim_text": claim_text, "workspace_id": workspace_id},
        )
        assert response.status_code == 201
        claim_ids.append(response.json()["id"])
    empty_id, support_id, contradict_id, uncertain_id, conflict_id, relation_source_id, relation_target_id = claim_ids

    evidence_specs = [
        ("supporting", "decision-support", 0.95, support_id),
        ("contradicting", "decision-contradict", 0.2, contradict_id),
        ("uncertain", "decision-uncertain", 0.5, uncertain_id),
        ("supporting", "decision-conflict-support", 0.95, conflict_id),
        ("contradicting", "decision-conflict-contradict", 0.2, conflict_id),
        ("supporting", "decision-relation-support", 0.95, relation_source_id),
        ("supporting", "decision-relation-target", 0.2, relation_target_id),
    ]
    evidence_ids = []
    for relation, source_id, confidence, claim_id in evidence_specs:
        response = client.post(
            "/api/evidence",
            headers=owner_headers,
            json={
                "source_id": source_id,
                "source_title": source_id,
                "url": f"https://example.com/{source_id}",
                "excerpt": source_id,
                "evidence_type": "full_text",
                "relation": relation,
                "confidence": confidence,
                "workspace_id": workspace_id,
            },
        )
        assert response.status_code == 201
        evidence_id = response.json()["id"]
        evidence_ids.append(evidence_id)
        assert client.post(
            f"/api/claims/{claim_id}/evidence",
            headers=owner_headers,
            json={"evidence_id": evidence_id},
        ).status_code == 200

    unlinked = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "unlinked-source",
            "source_title": "Unlinked evidence",
            "url": "https://example.com/unlinked-source",
            "excerpt": "This evidence is not linked to a claim.",
            "evidence_type": "abstract",
            "relation": "supporting",
            "confidence": 0.99,
            "workspace_id": workspace_id,
        },
    )
    assert unlinked.status_code == 201
    unlinked_id = unlinked.json()["id"]

    relation = client.post(
        f"/api/claims/{relation_source_id}/relations",
        headers=owner_headers,
        json={
            "target_claim_id": relation_target_id,
            "relation": "contradicts",
            "workspace_id": workspace_id,
        },
    )
    assert relation.status_code == 201
    relation_id = relation.json()["id"]
    memory_before = client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json()
    critic_before = client.get(f"/api/claims/{conflict_id}/critic", headers=owner_headers).json()

    decisions_response = client.get(
        f"/api/workspaces/{workspace_id}/council/decisions",
        headers=owner_headers,
    )
    assert decisions_response.status_code == 200
    body = decisions_response.json()
    decisions = {item["claim_id"]: item for item in body["decisions"]}
    assert body["summary"] == {
        "total": 7,
        "insufficient_evidence": 1,
            "unsupported": 2,
            "conflicting": 3,
        "structurally_supported": 1,
    }
    assert decisions[empty_id]["decision_status"] == "insufficient_evidence"
    assert decisions[empty_id]["reason_code"] == "no_linked_evidence"
    assert decisions[support_id]["decision_status"] == "structurally_supported"
    assert decisions[contradict_id]["decision_status"] == "unsupported"
    assert decisions[uncertain_id]["decision_status"] == "unsupported"
    assert decisions[conflict_id]["decision_status"] == "conflicting"
    assert decisions[conflict_id]["reason_code"] == "conflict_detected"
    assert decisions[relation_source_id]["decision_status"] == "conflicting"
    assert decisions[relation_target_id]["decision_status"] == "conflicting"
    assert decisions[relation_source_id]["relation_ids"] == [relation_id]
    assert decisions[relation_target_id]["relation_ids"] == [relation_id]
    assert decisions[conflict_id]["supporting_evidence_ids"] == [evidence_ids[3]]
    assert decisions[conflict_id]["contradicting_evidence_ids"] == [evidence_ids[4]]
    assert decisions[conflict_id]["source_ids"] == [
        "decision-conflict-contradict",
        "decision-conflict-support",
    ]
    assert unlinked_id not in decisions[conflict_id]["evidence_ids"]
    assert decisions[conflict_id]["critic_status"] == critic_before["audit_status"]
    assert decisions[conflict_id]["traceability"] == {
        "workspace_id": workspace_id,
        "claim_id": conflict_id,
        "evidence_ids": [evidence_ids[3], evidence_ids[4]],
        "conflict_ids": decisions[conflict_id]["conflict_ids"],
        "relation_ids": [],
        "source_ids": [
            "decision-conflict-contradict",
            "decision-conflict-support",
        ],
        "missing_source_evidence_ids": [],
    }
    assert decisions[conflict_id]["decision_id"] == f"decision:workspace:{workspace_id}:claim:{conflict_id}"

    repeated = client.get(
        f"/api/workspaces/{workspace_id}/council/decisions",
        headers=owner_headers,
    ).json()
    assert repeated == body
    assert client.get(f"/api/claims/{conflict_id}/critic", headers=owner_headers).json() == critic_before
    assert client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json() == memory_before
    assert client.get(
        f"/api/workspaces/{workspace_id}/council/decisions",
        headers=other_headers,
    ).status_code == 404

    missing_source_input = CouncilInputContract.model_validate({
        "workspace": {"id": 55},
        "search_history": {"count": 0, "items": []},
        "claims": [{
            "id": 900,
            "claim_text": "Missing source claim.",
            "evidence_ids": [901],
            "evidence": [{
                "id": 901,
                "source_id": None,
                "source_title": "Unknown source",
                "doi": None,
                "url": None,
                "excerpt": "An excerpt without a source reference.",
                "evidence_type": "full_text",
                "relation": "supporting",
                "confidence": 0.95,
            }],
            "relations": [],
        }],
        "evidence": [{
            "id": 901,
            "source_id": None,
            "source_title": "Unknown source",
            "doi": None,
            "url": None,
            "excerpt": "An excerpt without a source reference.",
            "evidence_type": "full_text",
            "relation": "supporting",
            "confidence": 0.95,
        }],
        "claim_relations": [],
        "critic": [{"claim_id": 900, "audit_status": "supported", "issues": []}],
        "summary": {"search_count": 0, "claim_count": 1, "evidence_count": 1, "claim_relation_count": 0},
    })
    missing_source_decision = decision_analysis_from_input(missing_source_input)[0]
    assert missing_source_decision.decision_status == "structurally_supported"
    assert missing_source_decision.source_ids == []
    assert missing_source_decision.missing_source_evidence_ids == [901]


def test_decision_engine_adversarial_combinations_and_traceability():
    def evidence(evidence_id, relation, source_id=None, confidence=0.5):
        return {
            "id": evidence_id,
            "source_id": source_id,
            "source_title": source_id or "Unknown source",
            "doi": None,
            "url": f"https://example.com/{source_id}" if source_id else None,
            "excerpt": f"Evidence {evidence_id}",
            "evidence_type": "abstract",
            "relation": relation,
            "confidence": confidence,
        }

    def council_input(claim_specs, evidence_items, relation_items=None):
        relation_items = relation_items or []
        claims = []
        for claim_id, evidence_items_for_claim in claim_specs:
            claims.append({
                "id": claim_id,
                "claim_text": f"Claim {claim_id}",
                "evidence_ids": [item["id"] for item in evidence_items_for_claim],
                "evidence": evidence_items_for_claim,
                "relations": [
                    relation for relation in relation_items
                    if relation["source_claim_id"] == claim_id
                    or relation["target_claim_id"] == claim_id
                ],
            })
        return CouncilInputContract.model_validate({
            "workspace": {"id": 500},
            "search_history": {"count": 0, "items": []},
            "claims": claims,
            "evidence": evidence_items,
            "claim_relations": relation_items,
            "critic": [],
            "summary": {
                "search_count": 0,
                "claim_count": len(claims),
                "evidence_count": len(evidence_items),
                "claim_relation_count": len(relation_items),
            },
        })

    scenarios = [
        ("supporting_only", [evidence(1, "supporting", "support-only", 0.01)], "structurally_supported"),
        ("uncertain_only", [evidence(2, "uncertain", "uncertain-only", 0.99)], "unsupported"),
        ("contradicting_only", [evidence(3, "contradicting", "contradict-only", 0.99)], "unsupported"),
        ("supporting_uncertain", [evidence(4, "supporting", "support-uncertain", 0.01), evidence(5, "uncertain", "support-uncertain-2", 0.99)], "structurally_supported"),
        ("contradicting_uncertain", [evidence(6, "contradicting", "contradict-uncertain", 0.99), evidence(7, "uncertain", "contradict-uncertain-2", 0.01)], "unsupported"),
        ("all_relations", [evidence(8, "supporting", "all-support", 0.01), evidence(9, "contradicting", "all-contradict", 0.99), evidence(10, "uncertain", "all-uncertain", 0.5)], "conflicting"),
    ]
    for index, (_, evidence_items, expected_status) in enumerate(scenarios, start=1):
        analysis = decision_analysis_from_input(council_input([(index, evidence_items)], evidence_items))
        decision = analysis[0]
        assert decision.decision_status == expected_status
        assert decision.evidence_ids == [item["id"] for item in evidence_items]
        assert decision.traceability["claim_id"] == index
        assert decision.decision_id == f"decision:workspace:500:claim:{index}"

    support_low = decision_analysis_from_input(
        council_input([(50, [evidence(50, "supporting", "low-confidence", 0.01)])], [evidence(50, "supporting", "low-confidence", 0.01)])
    )[0]
    support_high = decision_analysis_from_input(
        council_input([(51, [evidence(51, "supporting", "high-confidence", 0.99)])], [evidence(51, "supporting", "high-confidence", 0.99)])
    )[0]
    assert support_low.decision_status == support_high.decision_status == "structurally_supported"

    shared = evidence(60, "supporting", "shared-source", 0.5)
    shared_input = council_input([(60, [shared]), (61, [shared])], [shared])
    shared_decisions = decision_analysis_from_input(shared_input)
    assert [item.evidence_ids for item in shared_decisions] == [[60], [60]]
    assert [item.source_ids for item in shared_decisions] == [["shared-source"], ["shared-source"]]
    shared_assessment = evidence_assessments_from_input(shared_input)[0]
    assert shared_assessment.claim_ids == [60, 61]

    unlinked = evidence(70, "supporting", "unlinked-source", 0.99)
    linked = evidence(71, "supporting", "linked-source", 0.01)
    unlinked_input = council_input([(70, [linked])], [linked, unlinked])
    unlinked_decision = decision_analysis_from_input(unlinked_input)[0]
    assert unlinked_decision.evidence_ids == [71]
    assert 70 not in unlinked_decision.evidence_ids
    assert [item.evidence_id for item in evidence_assessments_from_input(unlinked_input)] == [71, 70]

    relation = {"id": 80, "source_claim_id": 80, "target_claim_id": 81, "relation": "contradicts"}
    relation_input = council_input(
        [(80, [evidence(80, "supporting", "relation-a")]), (81, [evidence(81, "supporting", "relation-b")])],
        [evidence(80, "supporting", "relation-a"), evidence(81, "supporting", "relation-b")],
        [relation],
    )
    relation_decisions = decision_analysis_from_input(relation_input)
    assert [item.decision_status for item in relation_decisions] == ["conflicting", "conflicting"]
    assert all(item.relation_ids == [80] for item in relation_decisions)
    assert relation_decisions[0].source_ids == ["relation-a"]
    assert relation_decisions[1].source_ids == ["relation-b"]

    relation_without_evidence = council_input(
        [(90, [evidence(90, "supporting", "relation-only")]), (91, [])],
        [evidence(90, "supporting", "relation-only")],
        [{"id": 90, "source_claim_id": 90, "target_claim_id": 91, "relation": "contradicts"}],
    )
    relation_without_evidence_decisions = decision_analysis_from_input(relation_without_evidence)
    assert [item.decision_status for item in relation_without_evidence_decisions] == [
        "conflicting",
        "insufficient_evidence",
    ]
    assert relation_without_evidence_decisions[1].relation_ids == [90]

    evidence_conflict_claim = [evidence(100, "supporting", "evidence-only-support"), evidence(101, "contradicting", "evidence-only-contradict")]
    relation_conflict = {"id": 102, "source_claim_id": 103, "target_claim_id": 104, "relation": "contradicts"}
    mixed_claim = [evidence(103, "supporting", "mixed-support"), evidence(104, "contradicting", "mixed-contradict")]
    multi_conflict_input = council_input(
        [
            (100, evidence_conflict_claim),
            (103, mixed_claim),
            (104, []),
        ],
        evidence_conflict_claim + mixed_claim,
        [relation_conflict],
    )
    multi_conflicts = conflict_analysis_from_input(multi_conflict_input)
    assert [item.conflict_type for item in multi_conflicts] == [
        "evidence_conflict",
        "mixed_conflict",
    ]
    assert len({item.conflict_id for item in multi_conflicts}) == 2
    multi_decisions = decision_analysis_from_input(multi_conflict_input)
    assert multi_decisions[0].conflict_ids == [multi_conflicts[0].conflict_id]
    assert multi_decisions[1].conflict_ids == [multi_conflicts[1].conflict_id]
    assert multi_decisions[2].decision_status == "insufficient_evidence"
    assert multi_decisions[2].relation_ids == [102]

    missing_source = evidence(110, "supporting", None, 0.99)
    missing_source_input = council_input([(110, [missing_source])], [missing_source])
    missing_source_decision = decision_analysis_from_input(missing_source_input)[0]
    assert missing_source_decision.source_ids == []
    assert missing_source_decision.missing_source_evidence_ids == [110]
    assert missing_source_decision.traceability["source_ids"] == []


def test_synthesis_is_deterministic_conservative_traceable_and_isolated():
    username, email = unique_identity("synthesis_owner")
    other_username, other_email = unique_identity("synthesis_other")
    password = "StrongPass123"
    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    workspace = client.post(
        "/api/workspaces",
        headers=owner_headers,
        json={
            "title": "Synthesis baseline",
            "research_question": "What can the recorded evidence support structurally?",
        },
    )
    workspace_id = workspace.json()["id"]
    empty = client.get(f"/api/workspaces/{workspace_id}/council/synthesis", headers=owner_headers)
    assert empty.status_code == 200
    assert empty.json()["overall_status"] == "insufficient_evidence"
    assert empty.json()["claim_syntheses"] == []
    assert empty.json()["summary"] == {
        "claim_count": 0,
        "evidence_count": 0,
        "conflict_count": 0,
        "decision_counts": {
            "insufficient_evidence": 0,
            "unsupported": 0,
            "conflicting": 0,
            "structurally_supported": 0,
        },
        "unlinked_evidence_ids": [],
    }

    claim_texts = [
        "No evidence claim.",
        "Supporting claim.",
        "Uncertain claim.",
        "Conflicting claim.",
        "Relation source claim.",
        "Relation target claim.",
    ]
    claims = []
    for claim_text in claim_texts:
        response = client.post(
            "/api/claims",
            headers=owner_headers,
            json={"claim_text": claim_text, "workspace_id": workspace_id},
        )
        assert response.status_code == 201
        claims.append(response.json())
    empty_id, support_id, uncertain_id, conflict_id, relation_source_id, relation_target_id = [
        claim["id"] for claim in claims
    ]

    def create_evidence(relation, source_id, confidence=0.5):
        response = client.post(
            "/api/evidence",
            headers=owner_headers,
            json={
                "source_id": source_id,
                "source_title": source_id,
                "url": f"https://example.com/{source_id}",
                "excerpt": f"{source_id} excerpt",
                "evidence_type": "abstract",
                "relation": relation,
                "confidence": confidence,
                "workspace_id": workspace_id,
            },
        )
        assert response.status_code == 201
        return response.json()

    support = create_evidence("supporting", "synthesis-support", 0.01)
    uncertain = create_evidence("uncertain", "synthesis-uncertain", 0.99)
    conflict_support = create_evidence("supporting", "synthesis-conflict-support", 0.99)
    conflict_contradict = create_evidence("contradicting", "synthesis-conflict-contradict", 0.01)
    relation_support = create_evidence("supporting", "synthesis-relation-support", 0.5)
    unlinked = create_evidence("supporting", "synthesis-unlinked", 0.99)
    for claim_id, evidence_id in [
        (support_id, support["id"]),
        (uncertain_id, uncertain["id"]),
        (conflict_id, conflict_support["id"]),
        (conflict_id, conflict_contradict["id"]),
        (relation_source_id, relation_support["id"]),
    ]:
        assert client.post(
            f"/api/claims/{claim_id}/evidence",
            headers=owner_headers,
            json={"evidence_id": evidence_id},
        ).status_code == 200
    relation = client.post(
        f"/api/claims/{relation_source_id}/relations",
        headers=owner_headers,
        json={
            "target_claim_id": relation_target_id,
            "relation": "contradicts",
            "workspace_id": workspace_id,
        },
    )
    assert relation.status_code == 201
    relation_id = relation.json()["id"]

    memory_before = client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json()
    critic_before = client.get(f"/api/claims/{conflict_id}/critic", headers=owner_headers).json()
    synthesis_response = client.get(
        f"/api/workspaces/{workspace_id}/council/synthesis",
        headers=owner_headers,
    )
    assert synthesis_response.status_code == 200
    body = synthesis_response.json()
    syntheses = {item["claim_id"]: item for item in body["claim_syntheses"]}
    assert body["synthesis_id"] == f"synthesis:workspace:{workspace_id}"
    assert body["research_question"] == "What can the recorded evidence support structurally?"
    assert body["overall_status"] == "unresolved"
    assert body["summary"]["claim_count"] == 6
    assert body["summary"]["evidence_count"] == 6
    assert body["summary"]["conflict_count"] == 2
    assert body["summary"]["unlinked_evidence_ids"] == [unlinked["id"]]
    assert body["summary"]["decision_counts"] == {
        "insufficient_evidence": 2,
        "unsupported": 1,
        "conflicting": 2,
        "structurally_supported": 1,
    }

    assert syntheses[empty_id]["synthesis_status"] == "insufficient_evidence"
    assert "no_evidence" in syntheses[empty_id]["limitations"]
    assert "structural_assessment_only" in syntheses[empty_id]["limitations"]
    assert "لا تتوفر أدلة مرتبطة" in syntheses[empty_id]["synthesis_statement"]
    assert syntheses[support_id]["synthesis_status"] == "structurally_supported"
    assert "ليس إثباتًا علميًا" in syntheses[support_id]["synthesis_statement"]
    assert syntheses[uncertain_id]["synthesis_status"] == "unsupported"
    assert "uncertain_evidence_present" in syntheses[uncertain_id]["limitations"]
    assert syntheses[conflict_id]["synthesis_status"] == "supported_with_conflict"
    assert "conflicting_evidence" in syntheses[conflict_id]["limitations"]
    assert syntheses[conflict_id]["supporting_evidence_ids"] == [conflict_support["id"]]
    assert syntheses[conflict_id]["contradicting_evidence_ids"] == [conflict_contradict["id"]]
    assert syntheses[relation_source_id]["synthesis_status"] == "supported_with_conflict"
    assert syntheses[relation_source_id]["relation_ids"] == [relation_id]
    assert syntheses[relation_target_id]["synthesis_status"] == "insufficient_evidence"
    assert syntheses[relation_target_id]["relation_ids"] == [relation_id]
    assert syntheses[relation_target_id]["conflict_ids"] == [
        syntheses[relation_source_id]["conflict_ids"][0]
    ]
    assert syntheses[support_id]["traceability"] == {
        "claim_ids": [support_id],
        "decision_ids": [f"decision:workspace:{workspace_id}:claim:{support_id}"],
        "evidence_ids": [support["id"]],
        "conflict_ids": [],
        "relation_ids": [],
        "source_ids": ["synthesis-support"],
    }
    assert syntheses[conflict_id]["traceability"]["conflict_ids"]
    assert syntheses[conflict_id]["traceability"]["evidence_ids"] == sorted([
        conflict_support["id"], conflict_contradict["id"],
    ])
    assert syntheses[conflict_id]["traceability"]["source_ids"] == [
        "synthesis-conflict-contradict",
        "synthesis-conflict-support",
    ]
    assert syntheses[conflict_id]["critic_status"] == critic_before["audit_status"]
    assert unlinked["id"] not in syntheses[support_id]["traceability"]["evidence_ids"]
    assert "unlinked_evidence_not_considered" in syntheses[support_id]["limitations"]

    repeated = client.get(
        f"/api/workspaces/{workspace_id}/council/synthesis",
        headers=owner_headers,
    ).json()
    assert repeated == body
    assert client.get(f"/api/claims/{conflict_id}/critic", headers=owner_headers).json() == critic_before
    assert client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json() == memory_before
    assert client.get(
        f"/api/workspaces/{workspace_id}/council/synthesis",
        headers=other_headers,
    ).status_code == 404

    missing_source_input = CouncilInputContract.model_validate({
        "workspace": {"id": 900, "research_question": "Missing source question"},
        "search_history": {"count": 0, "items": []},
        "claims": [{
            "id": 901,
            "claim_text": "Missing source claim",
            "evidence_ids": [902],
            "evidence": [{
                "id": 902,
                "source_id": None,
                "source_title": "Unknown",
                "doi": None,
                "url": None,
                "excerpt": "Recorded excerpt",
                "evidence_type": "abstract",
                "relation": "supporting",
                "confidence": 0.9,
            }],
            "relations": [],
        }],
        "evidence": [{
            "id": 902,
            "source_id": None,
            "source_title": "Unknown",
            "doi": None,
            "url": None,
            "excerpt": "Recorded excerpt",
            "evidence_type": "abstract",
            "relation": "supporting",
            "confidence": 0.9,
        }],
        "claim_relations": [],
        "critic": [],
        "summary": {"search_count": 0, "claim_count": 1, "evidence_count": 1, "claim_relation_count": 0},
    })
    missing_source_synthesis = synthesis_analysis_from_input(missing_source_input).claim_syntheses[0]
    assert missing_source_synthesis.source_ids == []
    assert "missing_source_reference" in missing_source_synthesis.limitations


def test_source_verification_is_deterministic_provenance_aware_and_non_mutating():
    def source_evidence(evidence_id, source_id, title, doi=None, url=None, authors=None, year=None):
        return {
            "id": evidence_id,
            "source_id": source_id,
            "source_title": title,
            "authors": authors or [],
            "year": year,
            "doi": doi,
            "url": url,
            "excerpt": f"Excerpt {evidence_id}",
            "evidence_type": "abstract",
            "relation": "supporting",
            "confidence": 0.5,
        }

    openalex = source_evidence(
        1,
        "https://openalex.org/W1",
        "Shared source",
        "10.1000/shared",
        "https://doi.org/10.1000/shared",
        ["Ada Lovelace"],
        2024,
    )
    crossref = source_evidence(
        2,
        "crossref:10.1000/shared",
        "Shared source",
        "https://doi.org/10.1000/shared",
        "https://doi.org/10.1000/shared",
        ["Ada Lovelace"],
        2024,
    )
    semantic = source_evidence(
        3,
        "Semantic Scholar:paper-1",
        "Shared source",
        "10.1000/shared",
        "https://example.com/paper-1",
        ["Ada Lovelace"],
        2024,
    )
    url_only = source_evidence(
        4,
        "url-only",
        "URL only source",
        url="https://example.com/url-only",
        year=2023,
    )
    mismatch = source_evidence(
        5,
        "https://openalex.org/W5",
        "Local title",
        "10.1000/mismatch",
        "https://doi.org/10.1000/mismatch",
        year=2020,
    )
    missing = source_evidence(6, None, "", authors=None, year=None)
    search_items = [{
        "id": 10,
        "query": "shared",
        "results": json.dumps([
            {
                "title": "Shared source",
                "source": "OpenAlex",
                "year": 2024,
                "url": "https://doi.org/10.1000/shared",
                "doi": "10.1000/shared",
                "source_id": "https://openalex.org/W1",
            },
            {
                "title": "Shared source",
                "source": "Crossref",
                "year": 2024,
                "url": "https://doi.org/10.1000/shared",
                "doi": "10.1000/shared",
                "source_id": "crossref:10.1000/shared",
            },
            {
                "title": "Shared source",
                "source": "Semantic Scholar",
                "year": 2024,
                "url": "https://example.com/paper-1",
                "doi": "10.1000/shared",
                "source_id": "Semantic Scholar:paper-1",
            },
            {
                "title": "Different indexed title",
                "source": "Crossref",
                "year": 2021,
                "url": "https://doi.org/10.1000/mismatch",
                "doi": "10.1000/mismatch",
                "source_id": "https://openalex.org/W5",
            },
        ]),
        "created_at": "2026-09-15 00:00:00",
        "workspace_id": 700,
    }]
    input_data = CouncilInputContract.model_validate({
        "workspace": {"id": 700, "research_question": "Verify sources"},
        "search_history": {"count": 1, "items": search_items},
        "claims": [
            {
                "id": 701,
                "claim_text": "Source claim",
                "evidence_ids": [1, 2, 3, 4, 5, 6],
                "evidence": [openalex, crossref, semantic, url_only, mismatch, missing],
                "relations": [],
            },
        ],
        "evidence": [openalex, crossref, semantic, url_only, mismatch, missing],
        "claim_relations": [],
        "critic": [],
        "summary": {"search_count": 1, "claim_count": 1, "evidence_count": 6, "claim_relation_count": 0},
    })
    before = input_data.model_dump()
    verifications = source_verifications_from_input(input_data)
    after = input_data.model_dump()
    assert before == after
    by_key = {item.source_key: item for item in verifications}
    shared = by_key["doi:10.1000/shared"]
    assert shared.verification_status == "verified"
    assert shared.evidence_ids == [1, 2, 3]
    assert shared.claim_ids == [701]
    assert shared.traceability["source_ids"] == [
        "Semantic Scholar:paper-1",
        "crossref:10.1000/shared",
        "https://openalex.org/W1",
    ]
    providers = {
        provenance.rsplit(":", 1)[-1]
        for provenance in shared.traceability["search_provenance"]
    }
    assert {"OpenAlex", "Crossref", "Semantic Scholar"}.issubset(providers)
    shared_check_names = {check.name for check in shared.verification_checks}
    assert {
        "source_record",
        "doi_presence",
        "doi_format",
        "bibliographic_match",
        "indexing_provenance",
        "retraction_status",
        "correction_status",
    }.issubset(shared_check_names)
    assert next(check for check in shared.verification_checks if check.name == "retraction_status").status == "not_checked"
    assert "doi_format_valid" in shared.verification_flags
    assert by_key["source_id:url-only"].verification_status == "partially_verified"
    mismatch_result = by_key["doi:10.1000/mismatch"]
    assert mismatch_result.verification_status == "partially_verified"
    assert "bibliographic_mismatch" in mismatch_result.verification_flags
    assert by_key["evidence:6"].verification_status == "insufficiently_verified"
    assert "source_reference_missing" in by_key["evidence:6"].verification_flags
    assert all(item.traceability["evidence_ids"] for item in verifications)


def test_source_verification_endpoint_isolated_and_read_only():
    username, email = unique_identity("source_verify_owner")
    other_username, other_email = unique_identity("source_verify_other")
    password = "StrongPass123"
    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    workspace = client.post(
        "/api/workspaces",
        headers=owner_headers,
        json={"title": "Source verification", "research_question": "Can sources be traced?"},
    )
    workspace_id = workspace.json()["id"]
    evidence = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "endpoint-source",
            "source_title": "Endpoint source",
            "url": "https://example.com/endpoint-source",
            "excerpt": "Endpoint evidence",
            "evidence_type": "abstract",
            "relation": "supporting",
            "confidence": 0.5,
            "workspace_id": workspace_id,
        },
    )
    evidence_id = evidence.json()["id"]
    before = client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json()
    first = client.get(f"/api/workspaces/{workspace_id}/sources/verification", headers=owner_headers)
    assert first.status_code == 200
    body = first.json()
    assert body["workspace_id"] == workspace_id
    assert body["summary"]["total"] == 1
    assert body["sources"][0]["evidence_ids"] == [evidence_id]
    assert body["sources"][0]["verification_status"] == "partially_verified"
    assert all(check["provenance"] or check["status"] == "not_checked" for check in body["sources"][0]["verification_checks"])
    second = client.get(f"/api/workspaces/{workspace_id}/sources/verification", headers=owner_headers)
    assert second.json() == body
    assert client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json() == before
    assert client.get(
        f"/api/workspaces/{workspace_id}/sources/verification",
        headers=other_headers,
    ).status_code == 404


def test_external_source_adapters_are_traceable_and_handle_provider_results():
    evidence = {
        "id": 1200,
        "source_id": "crossref-source",
        "source_title": "Verified article",
        "authors": ["Ada Lovelace"],
        "year": 2024,
        "doi": "doi:10.1234/example",
        "url": "https://doi.org/10.1234/example",
        "excerpt": "Recorded excerpt",
        "evidence_type": "abstract",
        "relation": "supporting",
        "confidence": 0.5,
    }
    input_data = CouncilInputContract.model_validate({
        "workspace": {"id": 1201, "research_question": "Verify metadata"},
        "search_history": {"count": 0, "items": []},
        "claims": [{"id": 1202, "claim_text": "Verified article claim.", "evidence_ids": [1200], "evidence": [evidence], "relations": []}],
        "evidence": [evidence],
        "claim_relations": [],
        "critic": [],
        "summary": {"search_count": 0, "claim_count": 1, "evidence_count": 1, "claim_relation_count": 0},
    })

    class FakeCrossref:
        def fetch(self, doi):
            assert doi == "doi:10.1234/example"
            return ExternalProviderResult(
                status="passed",
                provider="Crossref",
                provider_record="DOI metadata record",
                request_target="https://api.crossref.org/works/10.1234%2Fexample",
                checked_at="2026-09-15T00:00:00+00:00",
                metadata={
                    "doi": "10.1234/example",
                    "title": "Verified article",
                    "authors": ["Ada Lovelace"],
                    "year": 2024,
                    "container_title": "Journal",
                    "publisher": "Publisher",
                },
            )

    class FakeRetraction:
        def check(self, doi):
            return ExternalProviderResult(
                status="detected",
                provider="Trusted registry",
                provider_record="Retraction/correction record",
                request_target="https://registry.example/10.1234/example",
                checked_at="2026-09-15T00:00:00+00:00",
                metadata={"finding": "retraction"},
            )

    verifications = source_verifications_from_input(input_data, FakeCrossref(), FakeRetraction())
    result = verifications[0]
    assert result.verification_status == "verified"
    assert result.doi == "doi:10.1234/example"
    findings = {finding.finding_type: finding for finding in result.verification_findings}
    assert findings["doi_metadata"].status == "passed"
    assert findings["doi_metadata"].provenance.provider == "Crossref"
    assert findings["doi_metadata"].provenance.checked_at == "2026-09-15T00:00:00+00:00"
    assert findings["doi_metadata"].provenance.request_target.startswith("https://api.crossref.org/")
    assert findings["bibliographic_match"].status == "passed"
    assert findings["bibliographic_match"].evidence["fields"] == {
        "doi": "matched",
        "title": "matched",
        "authors": "matched",
        "year": "matched",
    }
    assert findings["retraction"].status == "detected"
    assert findings["correction"].status == "detected"
    assert result.traceability["evidence_ids"] == [1200]
    assert result.external_provenance[0].provider == "Crossref"

    class FakeMismatch(FakeCrossref):
        def fetch(self, doi):
            result = super().fetch(doi)
            result.metadata["title"] = "Different article"
            result.metadata["authors"] = ["Different Author"]
            result.metadata["year"] = 2020
            return result

    mismatch = source_verifications_from_input(input_data, FakeMismatch(), RetractionClient())[0]
    mismatch_finding = next(
        finding for finding in mismatch.verification_findings
        if finding.finding_type == "bibliographic_match"
    )
    assert mismatch.verification_status == "partially_verified"
    assert mismatch_finding.status == "failed"
    assert mismatch_finding.evidence["fields"] == {
        "doi": "matched",
        "title": "mismatched",
        "authors": "mismatched",
        "year": "mismatched",
    }


def test_crossref_adapter_network_failures_are_not_source_invalid(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

        def json(self):
            return {"message": {}}

        def raise_for_status(self):
            raise main_module.httpx.HTTPStatusError(
                "provider error",
                request=main_module.httpx.Request("GET", "https://api.crossref.org"),
                response=main_module.httpx.Response(self.status_code),
            )

    class FakeHttpClient:
        status_code = 500

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse(self.status_code)

    for status_code in (429, 500):
        FakeHttpClient.status_code = status_code
        monkeypatch.setattr(main_module.httpx, "Client", FakeHttpClient)
        result = CrossrefClient().fetch("10.1234/network")
        assert result.status == "not_checked"
        assert str(status_code) in (result.error or "")

    class TimeoutClient(FakeHttpClient):
        def get(self, *args, **kwargs):
            raise main_module.httpx.TimeoutException("timeout")

    monkeypatch.setattr(main_module.httpx, "Client", TimeoutClient)
    timeout_result = CrossrefClient().fetch("10.1234/timeout")
    assert timeout_result.status == "not_checked"
    assert "timed out" in (timeout_result.error or "")
    assert RetractionClient().check("10.1234/example").status == "not_checked"


def test_evidence_quality_is_conservative_traceable_and_relation_specific():
    def evidence(evidence_id, source_id, relation, claim_ids, excerpt="Recorded excerpt", confidence=None, evidence_type="abstract"):
        return {
            "id": evidence_id,
            "source_id": source_id,
            "source_title": f"Source {source_id}",
            "authors": ["Ada Lovelace"],
            "year": 2024,
            "doi": None,
            "url": f"https://example.com/{source_id}" if source_id else None,
            "excerpt": excerpt,
            "evidence_type": evidence_type,
            "relation": relation,
            "confidence": confidence,
            "claim_ids": claim_ids,
        }

    items = [
        evidence(1301, "complete-source", "supporting", [130]),
        evidence(1302, "no-doi-source", "contradicting", [130], confidence=0.2, evidence_type="full_text"),
        evidence(1303, "uncertain-source", "uncertain", [131], excerpt="", confidence=None),
        evidence(1304, "shared-source", "supporting", [130, 131], confidence=0.8),
        evidence(1305, "unlinked-source", "supporting", []),
        evidence(1306, None, "supporting", [132]),
    ]
    claims = [
        {
            "id": 130,
            "claim_text": "Claim 130",
            "evidence_ids": [1301, 1302, 1304],
            "evidence": [items[0], items[1], items[3]],
            "relations": [],
        },
        {
            "id": 131,
            "claim_text": "Claim 131",
            "evidence_ids": [1303, 1304],
            "evidence": [items[2], items[3]],
            "relations": [],
        },
        {
            "id": 132,
            "claim_text": "Claim 132",
            "evidence_ids": [1306],
            "evidence": [items[5]],
            "relations": [],
        },
    ]
    input_data = CouncilInputContract.model_validate({
        "workspace": {"id": 133, "research_question": "Assess evidence information"},
        "search_history": {"count": 0, "items": []},
        "claims": claims,
        "evidence": items,
        "claim_relations": [],
        "critic": [],
        "summary": {"search_count": 0, "claim_count": 3, "evidence_count": 6, "claim_relation_count": 0},
    })

    class VerifiedSource:
        source_key = "source_id:complete-source"
        verification_status = "verified"
        verification_findings = []

    class FakeSourceVerification:
        def __init__(self, source_key, verification_status, verification_findings=None):
            self.source_key = source_key
            self.verification_status = verification_status
            self.verification_findings = verification_findings or []

    class FakeCrossref:
        def fetch(self, doi):
            raise AssertionError("No DOI should invoke Crossref in this fixture")

    assessments = evidence_quality_from_input(input_data, FakeCrossref(), RetractionClient())
    by_id = {item.evidence_id: item for item in assessments}
    assert len(assessments) == 6
    assert by_id[1301].quality_assessment_status == "assessable"
    assert by_id[1301].traceability_status == "strong"
    assert by_id[1301].linkage_status == "linked_to_claim"
    assert by_id[1301].source_verification_status == "partially_verified"
    assert by_id[1301].relation == "supporting"
    assert by_id[1302].evidence_type == "full_text"
    assert by_id[1302].quality_assessment_status == "assessable"
    assert by_id[1302].confidence_status == "recorded"
    assert by_id[1303].relation == "uncertain"
    assert by_id[1303].quality_assessment_status == "partially_assessable"
    assert "excerpt" in by_id[1303].missing_information
    assert by_id[1304].claim_ids == [130, 131]
    assert by_id[1304].linkage_status == "linked_to_multiple_claims"
    assert by_id[1305].linkage_status == "unlinked"
    assert by_id[1305].quality_assessment_status == "insufficient_information"
    assert by_id[1306].traceability_status == "partial"
    assert "source_reference" in by_id[1306].missing_information
    finding_by_dimension = {item.dimension: item for item in by_id[1301].findings}
    assert finding_by_dimension["study_design"].status == "not_available"
    assert finding_by_dimension["sample_population_context"].status == "not_available"
    assert finding_by_dimension["effect_size"].status == "not_assessed"
    assert finding_by_dimension["bias"].status == "not_assessed"
    assert finding_by_dimension["directness"].status == "not_assessed"
    assert "structural_assessment_only" not in by_id[1301].missing_information


def test_evidence_quality_endpoint_preserves_previous_layers_and_isolates_users():
    username, email = unique_identity("quality_owner")
    other_username, other_email = unique_identity("quality_other")
    password = "StrongPass123"
    owner = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    other = client.post(
        "/api/auth/register",
        json={"username": other_username, "email": other_email, "password": password},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    workspace_id = client.post(
        "/api/workspaces",
        headers=owner_headers,
        json={"title": "Quality endpoint", "research_question": "What information is available?"},
    ).json()["id"]
    claim = client.post(
        "/api/claims",
        headers=owner_headers,
        json={"claim_text": "Quality claim", "workspace_id": workspace_id},
    ).json()
    evidence = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "quality-endpoint-source",
            "source_title": "Quality endpoint source",
            "url": "https://example.com/quality-endpoint-source",
            "excerpt": "Recorded evidence",
            "evidence_type": "abstract",
            "relation": "supporting",
            "confidence": 0.5,
            "workspace_id": workspace_id,
        },
    ).json()
    assert client.post(
        f"/api/claims/{claim['id']}/evidence",
        headers=owner_headers,
        json={"evidence_id": evidence["id"]},
    ).status_code == 200
    unlinked = client.post(
        "/api/evidence",
        headers=owner_headers,
        json={
            "source_id": "quality-unlinked-source",
            "source_title": "Unlinked quality source",
            "url": "https://example.com/quality-unlinked-source",
            "excerpt": "Unlinked evidence",
            "evidence_type": "full_text",
            "relation": "uncertain",
            "workspace_id": workspace_id,
        },
    ).json()
    memory_before = client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json()
    decision_before = client.get(f"/api/workspaces/{workspace_id}/council/decisions", headers=owner_headers).json()
    synthesis_before = client.get(f"/api/workspaces/{workspace_id}/council/synthesis", headers=owner_headers).json()
    response = client.get(f"/api/workspaces/{workspace_id}/council/evidence-quality", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total"] == 2
    assert len(body["assessments"]) == 1
    assert body["assessments"][0]["evidence_id"] == evidence["id"]
    assert body["unlinked_evidence"][0]["evidence_id"] == unlinked["id"]
    assert body["unlinked_evidence"][0]["linkage_status"] == "unlinked"
    assert client.get(f"/api/workspaces/{workspace_id}/council/evidence-quality", headers=owner_headers).json() == body
    assert client.get(f"/api/workspaces/{workspace_id}/memory", headers=owner_headers).json() == memory_before
    assert client.get(f"/api/workspaces/{workspace_id}/council/decisions", headers=owner_headers).json() == decision_before
    assert client.get(f"/api/workspaces/{workspace_id}/council/synthesis", headers=owner_headers).json() == synthesis_before
    assert client.get(
        f"/api/workspaces/{workspace_id}/council/evidence-quality",
        headers=other_headers,
    ).status_code == 404


def test_evidence_extraction_contract_is_typed_provenance_safe_and_non_mutating():
    dimensions = [
        "study_design",
        "sample_size",
        "population",
        "context",
        "effect_size",
        "limitations",
        "risk_of_bias_information",
    ]
    location = ExtractionSourceLocation(
        page=4,
        section="Methods",
        paragraph=2,
        offset="p4:p2",
        locator="source://paper#methods",
        status="available",
    )
    raw_reference = ExtractionRawInputReference(
        reference_type="evidence_excerpt",
        reference="Evidence excerpt 1400",
        status="available",
    )
    extractions = [
        build_evidence_extraction(
            evidence_id=1400,
            claim_ids=[140, 141],
            dimension=dimension,
            extracted_value={"value": dimension},
            extraction_method="manual",
            extraction_confidence=0.8,
            source_location=location,
            raw_input_reference=raw_reference,
            verification_state="verified",
            human_review_state="approved",
            source_id="source-1400",
            created_at="2026-09-15T00:00:00+00:00",
        )
        for dimension in dimensions
    ]
    assert all(isinstance(item, EvidenceExtraction) for item in extractions)
    assert [item.dimension for item in extractions] == dimensions
    assert all(item.evidence_id == 1400 for item in extractions)
    assert all(item.claim_ids == [140, 141] for item in extractions)
    assert all(item.extraction_confidence_status == "recorded" for item in extractions)
    assert all(item.provenance.source_type == "evidence" for item in extractions)
    assert all(item.provenance.source_id == "source-1400" for item in extractions)
    assert all(item.provenance.source_location.page == 4 for item in extractions)
    assert all(item.raw_input_reference.status == "available" for item in extractions)
    assert all(item.human_review_state == "approved" for item in extractions)

    ai_extraction = build_evidence_extraction(
        evidence_id=1400,
        claim_ids=[140],
        dimension="study_design",
        extracted_value="observational",
        extraction_method="ai",
        created_at="2026-09-15T00:00:00+00:00",
    )
    assert ai_extraction.extraction_confidence is None
    assert ai_extraction.extraction_confidence_status == "not_provided"
    assert ai_extraction.source_location.status == "not_available"
    assert ai_extraction.raw_input_reference.status == "not_available"
    assert ai_extraction.verification_state == "not_verified"
    assert ai_extraction.human_review_state == "needs_review"
    assert ai_extraction.provenance.created_at == "2026-09-15T00:00:00+00:00"
    assert ai_extraction.extraction_id == "extraction:evidence:1400:dimension:study_design"

    for verification_state in ["not_verified", "verified", "rejected", "needs_review"]:
        item = build_evidence_extraction(
            evidence_id=1401,
            claim_ids=[],
            dimension="limitations",
            extraction_method="manual",
            verification_state=verification_state,
            created_at="2026-09-15T00:00:00+00:00",
        )
        assert item.verification_state == verification_state
    for review_state in ["not_reviewed", "approved", "rejected", "needs_review"]:
        item = build_evidence_extraction(
            evidence_id=1402,
            claim_ids=[142],
            dimension="context",
            extraction_method="manual",
            human_review_state=review_state,
            created_at="2026-09-15T00:00:00+00:00",
        )
        assert item.human_review_state == review_state

    snapshot = CouncilInputContract.model_validate({
        "workspace": {"id": 1403, "research_question": "Extraction safety"},
        "search_history": {"count": 0, "items": []},
        "claims": [{
            "id": 1404,
            "claim_text": "Recorded claim",
            "evidence_ids": [1405],
            "evidence": [{
                "id": 1405,
                "source_id": "source-1405",
                "source_title": "Recorded source",
                "authors": [],
                "year": 2024,
                "doi": None,
                "url": "https://example.com/source-1405",
                "excerpt": "Recorded excerpt",
                "evidence_type": "abstract",
                "relation": "supporting",
                "confidence": 0.5,
            }],
            "relations": [],
        }],
        "evidence": [{
            "id": 1405,
            "source_id": "source-1405",
            "source_title": "Recorded source",
            "authors": [],
            "year": 2024,
            "doi": None,
            "url": "https://example.com/source-1405",
            "excerpt": "Recorded excerpt",
            "evidence_type": "abstract",
            "relation": "supporting",
            "confidence": 0.5,
        }],
        "claim_relations": [],
        "critic": [],
        "summary": {"search_count": 0, "claim_count": 1, "evidence_count": 1, "claim_relation_count": 0},
    })
    before = (
        evidence_assessments_from_input(snapshot),
        conflict_analysis_from_input(snapshot),
        decision_analysis_from_input(snapshot),
        synthesis_analysis_from_input(snapshot),
    )
    build_evidence_extraction(
        evidence_id=1405,
        claim_ids=[1404],
        dimension="sample_size",
        extracted_value=42,
        extraction_method="ai",
        created_at="2026-09-15T00:00:00+00:00",
    )
    after = (
        evidence_assessments_from_input(snapshot),
        conflict_analysis_from_input(snapshot),
        decision_analysis_from_input(snapshot),
        synthesis_analysis_from_input(snapshot),
    )
    assert before == after
    assert snapshot.evidence[0]["source_id"] == "source-1405"
    assert snapshot.claims[0]["evidence_ids"] == [1405]
