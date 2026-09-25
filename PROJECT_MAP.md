# PROJECT_MAP.md — SkillSprint AI Central Architecture Map

> **Company**: NovaCart — a mid-size e-commerce and logistics company operating
> an online marketplace with warehousing, payment processing, customer support,
> and engineering divisions.
>
> **Last Updated**: 2026-09-25 (Phase 2 integrated into `main`) | **Updated By**: Phase 2 GenAI Pipeline Engineer (A'LAA MADYAN)

---

## [TECH_STACK]

### Language & Runtime
| Component | Version | Notes |
|---|---|---|
| Python | 3.12.3 | System-installed; all code targets 3.12+ |

### Backend Framework
| Package | Pinned Version | Purpose |
|---|---|---|
| fastapi | ==0.141.1 | REST API framework — async, typed, OpenAPI auto-docs |
| uvicorn[standard] | ==0.53.0 | ASGI server for FastAPI |
| jinja2 | ==3.1.6 | Server-side HTML templating for dashboard views |

### Data & ORM
| Package | Pinned Version | Purpose |
|---|---|---|
| sqlalchemy | ==2.0.54 | ORM + Repository pattern; SQLite in dev, Postgres-ready |
| pydantic | ==2.13.5 | Schema validation for all GenAI JSON boundaries |
| pandas | ==3.0.6 | CSV/matrix loading, report generation, data analysis |
| numpy | ==2.5.3 | Numerical operations (similarity scores, statistics) |

### Document Processing
| Package | Pinned Version | Purpose |
|---|---|---|
| pdfplumber | ==0.11.10 | PDF text + layout extraction with page/bbox metadata |
| python-docx | ==1.2.0 | DOCX paragraph/section extraction |

### GenAI
| Package | Pinned Version | Purpose |
|---|---|---|
| google-genai | ==2.23.0 | Gemini API (replaces deprecated google-generativeai) |

### Semantic Analysis
| Package | Pinned Version | Purpose |
|---|---|---|
| sentence-transformers | ==6.1.0 | Embeddings for duplicate/contradiction detection |

### Visualization & Export
| Package | Pinned Version | Purpose |
|---|---|---|
| plotly | ==7.0.0 | Interactive dashboard charts |
| openpyxl | ==3.1.5 | Excel export |
| reportlab | ==4.2.5 | PDF report generation |

### Testing & Logging
| Package | Pinned Version | Purpose |
|---|---|---|
| pytest | ==8.3.4 | Test framework |
| pytest-asyncio | ==0.24.0 | Async test support |
| httpx | ==0.28.1 | Async HTTP client for API testing |

### Frontend
- HTML5 / CSS3 / JavaScript (vanilla + Bootstrap 5.3)
- Jinja2 templates served by FastAPI
- Plotly.js for client-side interactive charts

### Database
- **Development**: SQLite (zero-config, single-file)
- **Production-ready**: PostgreSQL (same SQLAlchemy models, connection string swap)

### Deployment
- Render / Railway / PythonAnywhere (any supports FastAPI + SQLite/Postgres)

---

## [SYSTEM_FLOW]

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE LAYER                            │
│  Employee Dashboard │ Admin Dashboard │ Role Dashboard │ Review Queue   │
│  (Jinja2 + Plotly.js + Bootstrap 5.3)                                  │
└──────────────┬──────────────────────────────────────────────────────────┘
               │ HTTP (FastAPI Routes)
               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        API / CONTROLLER LAYER                          │
│  AuthController │ DocumentController │ EmployeeController │            │
│  PlanController │ ValidationController │ ReviewController │            │
│  DashboardController │ ReportController │ SearchController             │
└──────┬───────────┬───────────┬──────────┬───────────────────────────────┘
       │           │           │          │
       ▼           ▼           ▼          ▼
┌────────────┐ ┌──────────┐ ┌──────────────────┐ ┌──────────────────────┐
│  Document  │ │ Employee │ │   PIPELINE 1     │ │   PIPELINE 2         │
│ Processing │ │ & Role   │ │  (GenAI + Python) │ │  (Pure Python ONLY)  │
│   Service  │ │ Service  │ │                  │ │                      │
│            │ │          │ │ PromptManager    │ │ ValidationPipeline   │
│ Upload     │ │ Profile  │ │ GeminiProvider   │ │  ├─CoverageValidator │
│ Validate   │ │ CRUD     │ │ PlanGenerator    │ │  ├─TraceValidator    │
│ Parse      │ │ Matrix   │ │ ModuleGenerator  │ │  ├─DuplicateValidator│
│ Chunk      │ │ Loader   │ │ QuizGenerator    │ │  ├─ContradictValidator│
│ Version    │ │          │ │ AssessmentGen    │ │  ├─RoleRelevanceVal  │
│ Control    │ │          │ │ SchemaValidator  │ │  ├─HallucinationDet  │
│            │ │          │ │ RetryManager     │ │  ├─SequenceValidator │
│            │ │          │ │ InjectionGuard   │ │  └─SchemaValidator   │
│            │ │          │ │                  │ │                      │
│            │ │          │ │ → Structured JSON │ │ ComparisonEngine     │
│            │ │          │ │   output ONLY    │ │ ConsistencyTester    │
└─────┬──────┘ └────┬─────┘ └────────┬─────────┘ └──────────┬───────────┘
      │             │                │                       │
      ▼             ▼                ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     REPOSITORY / DATA ACCESS LAYER                     │
│  DocumentRepository │ ChunkRepository │ EmployeeRepository │           │
│  RoleMatrixRepository │ PlanRepository │ ValidationRepository │        │
│  ReviewRepository │ AuditRepository │ PromptTemplateRepository         │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ SQLAlchemy ORM
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATABASE (SQLite / PostgreSQL)                  │
│  documents │ document_chunks │ employees │ roles │ role_requirements │  │
│  onboarding_plans │ learning_modules │ checklists │ tasks │ quizzes │  │
│  assessments │ validation_reports │ review_decisions │ audit_log │     │
│  prompt_templates │ generation_metadata                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Summary
1. **Ingest**: Documents uploaded → validated (type/size/dup/version) → parsed (retain doc_id, title, section, heading, page, version, effective_date) → chunked with traceability metadata → stored
2. **Matrix Load**: `load_matrix.py` reads `role_requirement_matrix_seed.csv` → validates (reject malformed IDs, missing columns, duplicates) → populates `role_requirements` table
3. **Generate (Pipeline 1)**: Employee profile + role + matrix + parsed chunks → PromptManager selects versioned template → GeminiProvider generates structured JSON (plan, modules, checklists, tasks, quizzes, assessments) → SchemaValidator validates JSON structure → RetryManager handles failures → stored with generation metadata (prompt version, model, timestamp, source doc versions)
4. **Validate (Pipeline 2)**: Structured JSON from Pipeline 1 → ValidationPipeline runs all validators independently (coverage, traceability, hallucination, contradiction, duplicate, role-relevance, sequence, schema) → produces ValidationReport with scores and per-item verification status
5. **Compare**: ComparisonEngine aligns Pipeline 1 output vs Pipeline 2 expectations on STRUCTURED ATTRIBUTES ONLY (IDs, booleans, enums — never exact NL text matching) → produces comparison report
6. **Review**: Items with status ≠ "Verified" enter ManualReviewQueue → Reviewer approves/rejects/edits/regenerates → both original + reviewer decision stored in audit trail
7. **Present**: Dashboards (Employee/Admin/Role) render from validated, reviewed data → progress tracking, adaptive recommendations, weak-area identification → reports exportable as CSV/PDF/Excel

---

## [ARCHITECTURE]

### Core Domain Classes (OOP — Mandatory)

All classes follow Single Responsibility Principle. Every class and public method has a docstring.

#### Entity / Model Layer

| Class | Layer | Base | Responsibility |
|---|---|---|---|
| `Document` | SQLAlchemy Model | `Base` | Uploaded document metadata: id, name, type, version, effective_date, expiry_date, department, category, status (active/obsolete), file_hash |
| `DocumentChunk` | SQLAlchemy Model | `Base` | Parsed chunk with traceability: id, document_id (FK), section_id, heading, content, page_number, paragraph_ref, chunk_index, embedding_vector |
| `Employee` | SQLAlchemy Model | `Base` | Profile: id, name, role_id (FK), department, experience_level, location, joining_date, reporting_manager, training_status |
| `Role` | SQLAlchemy Model | `Base` | Role definition: id, title, department, description |
| `RequirementMatrixEntry` | SQLAlchemy Model | `Base` | One row of the matrix: requirement_id, role, department, requirement_text, mandatory, priority, due_stage, source_document_id, source_section_id, competency, assessment_requirement |
| `OnboardingPlan` | SQLAlchemy Model | `Base` | Generated plan: id, employee_id (FK), role_id (FK), generation_timestamp, prompt_version, model_used, source_doc_versions (JSON), status, verification_status |
| `LearningModule` | Pydantic + SQLAlchemy | `BaseModel` | title, purpose, objectives, key_concepts, source_docs, duration, activities, assessment_method, completion_criteria, stage, difficulty |
| `ChecklistItem` | Pydantic + SQLAlchemy | `BaseModel` | activity, required_or_optional, due_stage, completion_status, source_doc_id, source_section_id, responsible_person |
| `Task` | Pydantic + SQLAlchemy | `BaseModel` | description, expected_outcome, source_requirement_id, completion_criteria, difficulty, due_stage, role_id |
| `QuizQuestion` | Pydantic + SQLAlchemy | `BaseModel` | question_text, question_type (MCQ/MR/TF/Scenario), options, correct_answer, explanation, source_doc_id, source_section_id, difficulty, distractor_validation_status |
| `Assessment` | Pydantic + SQLAlchemy | `BaseModel` | type (knowledge/practical/scenario/role-specific), rubric (criteria, weights, expected_performance, pass_condition), difficulty |
| `ValidationReport` | Pydantic | `BaseModel` | plan_id, coverage_score, traceability_score, consistency_score, missing_count, unsupported_count, contradiction_count, per_item_results: list[ItemValidationResult], overall_status |
| `ItemValidationResult` | Pydantic | `BaseModel` | item_id, item_type, verification_status (enum: Verified/VerifiedWithWarning/PartiallyVerified/SourceSupportMissing/RequirementMissing/UnsupportedRequirement/OutdatedSource/ContradictionDetected/ManualReviewRequired), details, source_references |
| `ReviewDecision` | SQLAlchemy Model | `Base` | id, item_id, item_type, reviewer_id, action (approve/reject/edit/regenerate), comment, original_result (JSON), reviewer_override (JSON), timestamp |
| `AuditEntry` | SQLAlchemy Model | `Base` | id, timestamp, actor, action, entity_type, entity_id, details (JSON), log_level |
| `PromptTemplate` | SQLAlchemy Model | `Base` | id, name, version, template_text, variables, created_at, is_active |
| `GenerationMetadata` | SQLAlchemy Model | `Base` | id, plan_id (FK), prompt_template_id (FK), model_name, api_version, generation_timestamp, source_doc_versions (JSON), retry_count, response_time_ms |

#### GenAI Abstraction Layer

```python
class BaseGenAIProvider(ABC):
    """Abstract base for all GenAI API providers.
    Every LLM call in the codebase goes through this interface."""

    @abstractmethod
    def generate(self, prompt: str, schema: type[BaseModel] | None = None,
                 config: GenerationConfig | None = None) -> GenAIResponse:
        """Generate structured output from the LLM.
        Args:
            prompt: The fully rendered prompt string.
            schema: Optional Pydantic model class for structured JSON output.
            config: Optional generation parameters (temperature, max_tokens, etc.).
        Returns:
            GenAIResponse with parsed content, raw response, and metadata.
        """
        ...

    @abstractmethod
    def generate_with_retry(self, prompt: str, schema: type[BaseModel] | None,
                            max_retries: int = 3) -> GenAIResponse:
        """Generate with automatic retry on invalid/incomplete output."""
        ...

class GeminiProvider(BaseGenAIProvider):
    """Concrete implementation using google-genai SDK (Gemini API).
    Wraps client = genai.Client(api_key=...) pattern."""
    ...
```

#### Validation Pipeline (Pure Python — ZERO GenAI)

```python
class BaseValidator(ABC):
    """Abstract base for all validation rules.
    Adding a new validation rule = adding one new class."""

    @abstractmethod
    def validate(self, plan: OnboardingPlan, matrix: list[RequirementMatrixEntry],
                 documents: list[Document], chunks: list[DocumentChunk]) -> ValidationResult:
        """Run this specific validation check.
        Returns:
            ValidationResult with status, score, and detailed findings.
        """
        ...

class CoverageValidator(BaseValidator):
    """Checks: all mandatory requirements in the matrix are covered by the plan."""

class TraceabilityValidator(BaseValidator):
    """Checks: every generated item has a valid source_document_id + source_section_id
    that actually exists in the parsed document corpus."""

class DuplicateValidator(BaseValidator):
    """Checks: no duplicate modules, tasks, checklist items, or quiz questions
    (uses semantic similarity via sentence-transformers embeddings)."""

class ContradictionValidator(BaseValidator):
    """Checks: no contradictory instructions in the plan; applies policy precedence rules.
    Policy Precedence (configurable):
      Latest Approved Policy > Department SOP > Compliance Procedures > FAQ > Informal Guidance"""

class RoleRelevanceValidator(BaseValidator):
    """Checks: every generated item is relevant to the employee's actual role,
    not just valid in general."""

class HallucinationDetector(BaseValidator):
    """Checks: no unsupported factual claims. Distinguishes:
    - Source-supported content (OK)
    - Reasonable instructional wording (OK)
    - Unsupported factual claims about company policy/process (REJECT/REVIEW)"""

class SequenceValidator(BaseValidator):
    """Checks: prerequisite ordering — no advanced task before required prerequisite,
    no assessment before content delivery, correct stage sequencing."""

class SchemaValidator(BaseValidator):
    """Checks: JSON structural correctness — missing fields, invalid types,
    invalid source IDs, invalid role, duplicate IDs, missing mandatory status."""

class ValidationPipeline:
    """Composes and runs all validators in sequence.
    To add a new validation rule: create a new BaseValidator subclass,
    register it in this pipeline's validator list."""

    def __init__(self, validators: list[BaseValidator] | None = None):
        self.validators = validators or [
            CoverageValidator(),
            TraceabilityValidator(),
            DuplicateValidator(),
            ContradictionValidator(),
            RoleRelevanceValidator(),
            HallucinationDetector(),
            SequenceValidator(),
            SchemaValidator(),
        ]

    def run(self, plan, matrix, documents, chunks) -> ValidationReport:
        """Execute all validators and aggregate into a ValidationReport."""
        ...
```

#### Repository Layer

```python
class BaseRepository(Generic[T]):
    """Generic repository with common CRUD operations.
    No raw SQL queries outside repository classes — ever."""

class DocumentRepository(BaseRepository[Document]): ...
class ChunkRepository(BaseRepository[DocumentChunk]): ...
class EmployeeRepository(BaseRepository[Employee]): ...
class RoleMatrixRepository(BaseRepository[RequirementMatrixEntry]):
    """Also provides: get_by_role(), get_mandatory(), get_by_source_doc()"""

class PlanRepository(BaseRepository[OnboardingPlan]): ...
class ValidationRepository(BaseRepository[ValidationReport]): ...
class ReviewRepository(BaseRepository[ReviewDecision]): ...
class AuditRepository(BaseRepository[AuditEntry]): ...
class PromptTemplateRepository(BaseRepository[PromptTemplate]): ...
```

#### Service Layer

| Service | Responsibility |
|---|---|
| `DocumentService` | Orchestrates upload → validate → parse → chunk → version control |
| `EmployeeService` | CRUD for employees + role assignment |
| `RoleMatrixService` | Matrix loading, querying, validation against parsed docs |
| `PlanGenerationService` | Orchestrates Pipeline 1: template selection → prompt rendering → GenAI call → schema validation → retry → storage |
| `ValidationService` | Orchestrates Pipeline 2: runs ValidationPipeline → stores report → determines verification status |
| `ComparisonService` | Aligns Pipeline 1 vs Pipeline 2 on structured attributes → produces comparison report |
| `ConsistencyService` | Repeats generation, compares structured outputs, calculates consistency score |
| `ReviewService` | Manual review queue management, reviewer actions, audit trail |
| `ProgressService` | Progress tracking, assessment, weak-area detection, adaptive recommendations |
| `PolicyUpdateService` | Detects doc changes → identifies affected items → triggers selective regeneration |
| `SearchService` | Cross-entity search and filtering |
| `ReportService` | Report generation + export (CSV/PDF/Excel) |
| `AuthService` | Authentication + RBAC (5 roles: Employee, Admin, Training Manager, Reviewer, Manager) |

---

## [PHASE OWNERSHIP]

### Phase 1 — Foundation Engineer
**Scope**: Data layer, document pipeline, employee/role management, auth skeleton

#### Development Steps Owned
| Step | Description | Status |
|---|---|---|
| 1 | Fictional company creation | ✅ DONE (Prompt A0 — NovaCart) |
| 2 | 10 job roles (all 10 now have dedicated ROLE-xx documents) | ✅ DONE (Prompt A0 + Addendum) |
| 3 | 24 company documents (20 original + ROLE-07 to ROLE-10 addendum) with all required variation | ✅ DONE (Prompt A0 + Addendum) |
| 4 | Document upload (PDF/DOCX mandatory; TXT/MD/CSV optional) — process all 24 documents (38 files on disk: 24 DOCX + 14 PDF) end-to-end | ✅ DONE (Phase 1 — `DocumentService.ingest_directory`) |
| 5 | Document validation: file type, size, duplicate, empty, version, effective/expiry date, department, category | ✅ DONE |
| 6 | Document parsing: retain doc_id, title, section, heading, page/location ref, version, effective_date | ✅ DONE |
| 7 | Content chunking with full traceability metadata | ✅ DONE |
| 8 | Document version control (active vs obsolete) | ✅ DONE (`DocumentRevision`; POL-02 v1 obsolete / v2 active) |
| 9 | Employee profile creation (ID, role, department, experience, location, joining_date, reporting_manager, competencies, prior_experience, training_status) | ✅ DONE |
| 10 | Role Requirement Matrix — write `load_matrix.py` to load CSV, validate (reject malformed IDs, missing columns, duplicates), populate DB. NOT authoring content. | ✅ DONE (178 rows loaded; malformed/duplicate IDs rejected) |

#### Functional Requirements Owned (from Section C)
- User Authentication — ✅
- Role-Based Access Control (skeleton — route guards + role decorators) — ✅
- Employee Profile Management — ✅
- Role Management — ✅
- Document Upload — ✅
- Document Validation — ✅
- Document Parsing — ✅
- Document Chunking — ✅
- Source Metadata Management — ✅
- Document Version Control — ✅
- Role Requirement Matrix — ✅
- Responsive Web Interface (layout skeleton + base templates) — ✅
- API Error Handling (base error handler middleware) — ✅

#### Deliverables Touched
- requirements.txt (create, pin all versions)
- Database schema (all tables)
- Mandatory GitHub folder structure (scaffold all directories)
- README.md (initial version)
- Sample data loaded end-to-end

#### Key Verification Goals
- [x] VG-1.1: All 24 documents (38 files) in sample_documents/ successfully uploaded, validated, parsed, chunked, and stored with full metadata
- [x] VG-1.2: `load_matrix.py` loads all 178 CSV rows; rejects any row with malformed requirement_id, missing mandatory columns, or duplicate requirement_id
- [x] VG-1.3: Parsed counts verified: ≥24 docs, ≥102 mandatory sections, ≥28 optional sections, ≥65 role-specific sections, ≥10 conflict pairs, ≥10 version changes, ≥11 adversarial cases
- [x] VG-1.4: Document version control distinguishes POL-02 v1/v2 (both .docx and .pdf) correctly; obsolete versions marked accordingly
- [x] VG-1.5: Employee CRUD works for all 10 roles (each with a dedicated ROLE-xx document) with proper RBAC guards
- [x] VG-1.6: Database schema supports all entities from the Architecture section
- [x] VG-1.7: Auth skeleton: 5 user roles (Employee, Admin, Training Manager, Reviewer, Manager) with route-level access control

---

### Phase 2 — GenAI Pipeline Engineer
**Scope**: Pipeline 1 — all GenAI-powered generation, prompt management, structured output, injection defense

#### Development Steps Owned
| Step | Description | Status |
|---|---|---|
| 11 | Requirement extraction (Must Know/Complete/Demonstrate/Acknowledge/Recommended/Optional/N/A) | ✅ DONE (`RequirementExtractor`) |
| 12 | Personalized onboarding plan generation per role/department/experience/timeline | ✅ DONE (`PlanGenerationService.generate_for_employee`) |
| 13 | Multi-stage plan (Day 1, Week 1, Week 2, First 30/60/90 Days) | ✅ DONE (`OutputSchemaValidator` rejects single-stage dumps) |
| 14 | Learning module generation (title, purpose, objectives, key concepts, source docs, duration, activities, assessment, completion criteria) | ✅ DONE (`ModuleGenerator` + `PlanAssembler`) |
| 15 | Source-grounded generation — unsupported content flagged/removed/manual review | ✅ DONE (`GroundingFlag` / `grounding_status` on items) |
| 16 | Role-specific learning (genuinely different content per role) | ✅ DONE (VG-2.1: ten live plans differ by role) |
| 17 | Checklist generation (activity, required/optional, due date/stage, status, source, responsible) | ✅ DONE |
| 18 | Role-specific task generation (description, outcome, source req, completion criteria, difficulty, due stage) | ✅ DONE |
| 19 | Scenario-based task generation from approved processes | ✅ DONE (`ScenarioTaskGenerator`; SOP-preferred scenario task) |
| 20 | Quiz generation (MCQ, multiple response, True/False, scenario-based) | ✅ DONE |
| 21 | Quiz traceability (source doc/section, correct answer, explanation, difficulty) | ✅ DONE |
| 22 | Distractor validation — plausible but not misleadingly contradictory; correct answer validated by Python against source | ✅ DONE (`DistractorValidator`) |
| 23 | Assessment generation (knowledge, practical, scenario, role-specific) | ✅ DONE |
| 24 | Assessment rubric (criterion, weight, expected performance, pass condition) | ✅ DONE |
| 25 | Difficulty levels (Beginner/Intermediate/Advanced reflecting role+experience) | ✅ DONE (`RequirementExtractor.difficulty_for`) |
| 26 | Prerequisite management (no advanced task before required prerequisite) | ✅ DONE (`PrerequisiteEnforcer`) |
| 37 | GenAI structured JSON output per defined schema; free-form never sole output | ✅ DONE (`GeneratedPlan` is the plan of record) |
| 38 | Schema validation in Python (missing fields, invalid types, invalid source IDs, invalid role, duplicate IDs, missing mandatory status) | ✅ DONE (`OutputSchemaValidator`) |
| 39 | GenAI retry & recovery on invalid/incomplete output, with logging + cap | ✅ DONE (`RetryManager` cap 3; assembler recovery on 502) |
| 40 | Prompt template management — versioned template files, not hard-coded | ✅ DONE (`prompt_templates/*_v1.json` + `PromptManager`) |
| 41 | Prompt version tracking — every plan records prompt version, model, timestamp, source doc versions | ✅ DONE (`OnboardingPlan` + `GenerationMetadata`) |
| 42 | Prompt injection defense — uploaded text treated strictly as data | ✅ DONE (`InjectionGuard` fences `UNTRUSTED_DOCUMENT_DATA`) |
| 43 | Adversarial document testing — demonstrate protection against injection docs | ✅ DONE (11 corpus cases in `tests/test_injection.py`) |

#### Functional Requirements Owned (from Section C)
- Requirement Extraction — ✅
- GenAI API Integration — ✅
- Structured Prompt Templates — ✅
- Structured JSON Output — ✅
- JSON Schema Validation — ✅
- Personalized Onboarding Plan — ✅
- Multi-Stage Onboarding — ✅
- Learning Module Generation — ✅
- Learning Objective Generation — ✅
- Checklist Generation — ✅
- Task Generation — ✅
- Scenario Generation — ✅
- Quiz Generation — ✅
- Quiz Answer Validation — ✅
- Assessment Generation — ✅
- Assessment Rubric Generation — ✅
- Prerequisite Detection — ✅
- Source Citation — ✅
- Prompt Injection Protection — ✅
- Adversarial Document Detection — ✅
- Retry Management — ✅
- Model and Prompt Logging — ✅

#### Deliverables Touched
- GenAI Pipeline Evidence (D4)
- prompt_templates/ (versioned files)
- schemas/ (Pydantic models for all JSON outputs)
- genai_pipeline/ (GeminiProvider, generators)
- security/ (InjectionGuard)

#### Key Verification Goals
- [x] VG-2.1: Onboarding plans generated for all 10 roles (each with dedicated role description document + matrix entries) with genuinely different content per role
- [x] VG-2.2: Multi-stage plans never dump everything into Day 1
- [x] VG-2.3: All generated JSON passes Pydantic schema validation with zero missing required fields
- [x] VG-2.4: Every generated module/task/quiz/assessment includes valid source_document_id + source_section_id
- [x] VG-2.5: Prompt injection defense demonstrated against all 11 adversarial cases in the corpus
- [x] VG-2.6: Retry logic capped (max 3), logged, recovers gracefully from invalid GenAI output
- [x] VG-2.7: Prompt templates versioned in files; generation metadata records version + model + timestamp
- [x] VG-2.8: Prerequisite ordering enforced in generated plans (no advanced before basic)
- [x] VG-2.9: Distractor validation: incorrect quiz options plausible but not contradictory to source

---

### Phase 3 — Validation & Trust Engineer
**Scope**: Pipeline 2 — the entire independent pure-Python validation pipeline, comparison engine, consistency testing

#### Development Steps Owned
| Step | Description | Status |
|---|---|---|
| 27 | Learning sequence validation (missing prerequisites, incorrect sequence, advanced-before-basic, assessment-before-content) | PENDING |
| 28 | Python Requirement Validation Engine (required vs covered vs missing vs unsupported vs duplicate) | PENDING |
| 29 | Coverage Score = Covered Mandatory / Total Mandatory × 100, target 100% | PENDING |
| 30 | Traceability Score — target 100% for mandatory content | PENDING |
| 31 | Hallucination detection — unsupported statements flagged, never silently accepted | PENDING |
| 32 | Unsupported content detection (source-supported vs instructional wording vs unsupported factual claims) | PENDING |
| 33 | Contradiction detection (old vs new policy, FAQ vs official, role desc vs SOP, generated task violating rule) | PENDING |
| 34 | Policy precedence rules — configurable hierarchy: Latest Approved Policy > Department SOP > Compliance Procedures > FAQ > Informal Guidance | PENDING |
| 35 | Duplicate learning detection (modules, tasks, checklist items, quiz questions) | PENDING |
| 36 | Role relevance validation (valid but irrelevant content flagged) | PENDING |
| 44 | GenAI consistency check — repeat same task, compare structured outputs, flag major differences | PENDING |
| 45 | Generation Consistency Score (structured business requirements, not exact wording) | PENDING |
| 46 | Python/GenAI result comparison (Requirement ID, Python expected, GenAI result, Match/Mismatch, Source, Status) | PENDING |
| 47 | Final verification status per item (Verified/Verified with Warning/Incomplete/Unsupported/Contradictory/Manual Review Required) | PENDING |

#### Functional Requirements Owned (from Section C)
- Learning Sequence Validation
- Python Validation Pipeline
- Mandatory Requirement Coverage
- Coverage Score
- Traceability Score
- Hallucination Detection
- Contradiction Detection
- Policy Precedence
- Duplicate Detection
- Role-Relevance Check
- GenAI Consistency Testing
- Consistency Score
- GenAI/Python Comparison
- Verification Status

#### Deliverables Touched
- Python Validation Pipeline Evidence (D5)
- GenAI/Python Comparison Report — ≥100 requirement-level comparisons (D6)
- Validation Report (D8)
- python_validation/ (all validator classes)
- comparison_engine/
- hallucination_checks/
- contradiction_checks/

#### Key Verification Goals
- [ ] VG-3.1: CoverageValidator correctly computes score; 100% mandatory coverage required for "Verified" status
- [ ] VG-3.2: TraceabilityValidator rejects any item with source_document_id or source_section_id not found in parsed corpus
- [ ] VG-3.3: HallucinationDetector flags all 10 adversarial injection cases as unsupported
- [ ] VG-3.4: ContradictionValidator identifies all 10 known conflict pairs from the dataset
- [ ] VG-3.5: Policy precedence correctly resolves contradictions (e.g., POL-02 v2 > FAQ-01 §2.2)
- [ ] VG-3.6: DuplicateValidator detects semantically similar content using embeddings
- [ ] VG-3.7: ComparisonEngine produces ≥100 requirement-level comparisons with explanations
- [ ] VG-3.8: ConsistencyTester runs ≥2 generation passes, compares on structured attributes only
- [ ] VG-3.9: Verification statuses correctly assigned per the 9-status enum
- [ ] VG-3.10: Zero GenAI calls in any Pipeline 2 code path (hard constraint)

---

### Phase 4 — Workflow, Dashboards & Delivery Engineer
**Scope**: Human review, dashboards, progress tracking, policy updates, search, reports, export, security testing, final packaging

#### Development Steps Owned
| Step | Description | Status |
|---|---|---|
| 48 | Human review workflow (Approve, Reject, Edit, Regenerate, Add Comment) | PENDING |
| 49 | Reviewer override — original + reviewer decision both in audit trail | PENDING |
| 50 | Employee dashboard (progress, assigned/completed modules, tasks, quiz scores, upcoming, milestones) | PENDING |
| 51 | Administrator dashboard (employees, roles, plans, completion, scores, coverage, flagged content, reviews) | PENDING |
| 52 | Role dashboard (onboarding requirements & completion stats by role) | PENDING |
| 53 | Progress tracking (module/checklist/task completion, quiz score, assessment score, overall) | PENDING |
| 54 | Progress assessment (On Track/Requires Attention/Behind Schedule/Assessment Required/Completed) | PENDING |
| 55 | Adaptive recommendation (revision, additional quiz/task, advanced module, manager review) based on real performance | PENDING |
| 56 | Weak-area identification from quiz performance, assessment results, incomplete tasks, repeated errors | PENDING |
| 57 | Policy update detection — identify all affected items when a policy changes | PENDING |
| 58 | Impact analysis of source-document update on existing plans | PENDING |
| 59 | Selective regeneration — only affected modules regenerate, not entire plan | PENDING |
| 60 | Training plan comparison across roles/departments/levels/doc versions | PENDING |
| 61 | Search and filtering (employee, role, department, module, policy, status, progress, verification result) | PENDING |
| 62 | Reports (employee progress, role coverage, mandatory training, assessment results, source traceability, hallucination flags, policy coverage, GenAI/Python comparison) | PENDING |
| 63 | Export to CSV, PDF, and Excel-compatible format | PENDING |

#### Functional Requirements Owned (from Section C)
- Manual Review Queue
- Reviewer Decision
- Reviewer Override
- Audit Trail
- Employee Dashboard
- Administrator Dashboard
- Role Dashboard
- Progress Tracking
- Progress Assessment
- Weak-Area Detection
- Adaptive Recommendations
- Policy Update Detection
- Impact Analysis
- Selective Regeneration
- Search and Filtering
- Reports
- Export

#### Deliverables Touched
- Onboarding Plan Evidence for ≥10 roles (D7)
- Security Testing Report (D9)
- Test Cases (D10)
- Installation Instructions (D11)
- Execution Instructions (D12)
- Deployed Application (D14)
- Demonstration Video (D15)
- Technical Blog (D16)
- Final Submission Checklist (D18)
- hidden_test_ready/
- screenshots/
- reports/
- templates/ (dashboard HTML)

#### Key Verification Goals
- [ ] VG-4.1: Review workflow: items with status ≠ Verified enter queue; approve/reject/edit/regenerate all functional
- [ ] VG-4.2: Reviewer override preserves BOTH original result AND reviewer decision in audit trail
- [ ] VG-4.3: Employee dashboard shows real progress data, not placeholders
- [ ] VG-4.4: Admin dashboard shows compliance coverage, flagged content, pending reviews
- [ ] VG-4.5: Role dashboard shows per-role requirement completion stats
- [ ] VG-4.6: Progress assessment correctly categorizes (On Track/Attention/Behind/etc.)
- [ ] VG-4.7: Policy update → system identifies affected modules/quizzes/employees automatically
- [ ] VG-4.8: Selective regeneration only regenerates affected items, not entire plan
- [ ] VG-4.9: Search works across all entities with combined filters
- [ ] VG-4.10: Export produces valid CSV, PDF, and Excel files
- [ ] VG-4.11: hidden_test_ready/ contains working demo data + evaluator logins
- [ ] VG-4.12: Security testing suite covers: injection, malicious doc, unsupported topic, invalid file, unauthorized access, invalid API response

---

## [ORPHANS & PENDING]

### 18 Project Deliverables Tracker
| # | Deliverable | Owner Phase | Status |
|---|---|---|---|
| D1 | Project Report (problem definition, diagrams: DFD, Use Case, Activity, Sequence) | Phase 4 | PENDING |
| D2 | Source Code in mandatory GitHub folder structure | Phase 1 (scaffold) + all | IN PROGRESS — Phase 1 foundation + Phase 2 `genai_pipeline/`, `prompt_templates/`, `schemas/`, `security/injection_guard.py`, `/api/plans*` **merged into `main`**; Phase 3–4 remaining (all four Phase 3 packages are still `__init__.py`-only) |
| D3 | Company Document Dataset — 24 documents, 38 files (profile, scenario, policies, role descriptions, etc.) | ✅ DONE (Prompt A0 + Addendum) | COMPLETE |
| D4 | GenAI Pipeline Evidence (API/model, prompts, config, samples, failures, retries) | Phase 2 | PARTIAL — `reports/d4_genai_pipeline_evidence.md` documents API/model, prompts, config, retry, injection; `scripts/live_genai_run.py` records real runs; **still needs one valid `GEMINI_API_KEY` run** to supply the live sample + `reports/d4_live_genai_run.json` |
| D5 | Python Validation Pipeline Evidence | Phase 3 | PENDING |
| D6 | GenAI/Python Comparison Report (≥100 comparisons) | Phase 3 | PENDING |
| D7 | Onboarding Plan Evidence for ≥10 roles | Phase 4 (assembly) | PENDING |
| D8 | Validation Report | Phase 3 | PENDING |
| D9 | Security Testing Report | Phase 4 | PENDING |
| D10 | Test Cases (all categories) | Phase 4 (integration) + all phases (unit) | IN PROGRESS — Phase 1 (15) + Phase 2 (`tests/test_genai_pipeline.py`, `tests/test_injection.py`); suite 27 passing |
| D11 | Installation Instructions | Phase 4 | PENDING |
| D12 | Execution Instructions (full walkthrough) | Phase 4 | PENDING |
| D13 | Public GitHub Repository (daily commits from all members) | All phases | PENDING |
| D14 | Deployed Application (public URL + evaluator logins) | Phase 4 | PENDING |
| D15 | Demonstration Video (.mp4) | Phase 4 | PENDING |
| D16 | Technical Blog (2,000+ words) | Phase 4 | PENDING |
| D17 | AI Tool Usage Declaration (AI_USAGE.md) | All phases (human-filled) | IN PROGRESS — Phase 1 + Phase 2 entries present; remaining members/days still required |
| D18 | Final Submission Checklist | Phase 4 | PENDING |

### Unresolved Architectural Questions
- **Q1**: ~~4 roles had no dedicated ROLE-XX documents.~~ **RESOLVED (Addendum v1.1, 2026-09-25)**: ROLE-07 (Recruiter), ROLE-08 (Financial Analyst), ROLE-09 (Accounts Payable Clerk), ROLE-10 (Warehouse Operations Coordinator) added. All 10 roles now have dedicated role description documents with both DOCX and PDF. Matrix expanded to 178 rows (R155–R178).
- **Q2**: The fictional company name "NovaCart" is confirmed from document inspection. Ensure consistency across all deliverables.

### Known Input Data Gaps (for Phase 1 to flag)
- ~~No dedicated role description documents for 4 roles.~~ **Resolved** — all 10 roles now have ROLE-xx documents.
- **Live GenAI evidence gap (Phase 2, found 2026-09-25 14:09)**: Pipeline 1 code was complete and 27 tests green, but **no call to the real Gemini API had ever been made**. `GEMINI_API_KEY` unset; every test injects `ScriptedProvider`; the only `GeminiProvider` test asserts the 503 fail-closed branch; `d4_sample_software_engineer_plan.json` lacks `model_used`/`prompt_version`/`generation_timestamp`, so it is `PlanAssembler` output, not model output. Remediation in progress: `google-genai==2.23.0` installed into `.venv`, and `scripts/live_genai_run.py` added to record a real run. **A valid `GEMINI_API_KEY` is still required to close D4.**
- **Seeded DB was empty (Phase 2, found 2026-09-25 14:09)**: `data/skillsprint.db` had 18 tables and 0 rows, so `python -m database.seed` had never been run in this working copy. Re-seeded (178 matrix rows, 38 files, 24 documents). Anyone running the live harness must seed first.
- PDF versions exist for 14 of 24 documents (POL-02 through POL-05, ROLE-01 through ROLE-10). The remaining 10 documents (HANDBOOK-01, POL-01, SOP-01 through SOP-05, FAQ-01, FAQ-02, COMP-01) are DOCX-only. Both formats are ingested where present.
- **Metrics note (Phase 1)**: Some documents repeat the same `section_id` in body text (e.g. a later sentence citing `1.1`). `CorpusMetricsService` ORs `[M]/[O]` flags across those duplicates so VG-1.3 counts the tagged section, not the last write. Phase 2 `PlanAssembler.excerpts_from_chunks` prefers the longest tagged chunk per `(document_id, section_id)`.

---

## [NON-FUNCTIONAL REQUIREMENTS MAPPING]

| NFR | Target | Implementation Approach | Verification |
|---|---|---|---|
| Performance | Plan generation + validation ≤30s | Async GenAI calls; validators run in sequence (fast); chunked retrieval | Time the end-to-end flow for a standard role |
| Scalability | ≥1000 employees, ≥100 roles, ≥1000 docs | Repository pattern + indexed DB queries; no in-memory full-corpus loads | Load test with synthetic profiles |
| Usability | Intuitive for 5 user types | Bootstrap 5.3 responsive layout; role-specific dashboards; clear navigation | Manual UX walkthrough per role |
| Accuracy | 100% mandatory coverage before approval | ValidationPipeline enforces; "Verified" status requires 100% coverage + valid sources + zero contradictions | VG-3.1 through VG-3.10 |
| Availability | ≥99% uptime (excl. GenAI API outages) | Stateless API; SQLite resilient; graceful GenAI timeout handling | Uptime monitoring during eval |

---

## [COMPLIANCE CHECKLIST] (Section F — Anti-Shortcut Requirements)

| # | Requirement | Relevant Phase(s) | Status |
|---|---|---|---|
| F1 | Unique company pack (NovaCart) | Prompt A0 | ✅ DONE |
| F2 | Correctly ingest hidden unseen documents without code modification | Phase 1 (upload pipeline must be generic) | PHASE 1 READY — ingest is filename/content-driven, not a hardcoded 24-doc list; hidden-eval proof still requires live upload of unseen files |
| F3 | Correctly onboard a hidden new role without code modification | Phase 1 (role CRUD) + Phase 2 (generic prompts) + Phase 3 (generic validators) | PHASE 1+2 READY — CRUD plus generic templates/`PlanGenerationService` (new role needs matrix rows + ingested docs); Phase 3 validators still pending |
| F4 | Policy Update Challenge readiness | Phase 4 (steps 57-59) | PENDING |
| F5 | Prompt Injection Challenge readiness | Phase 2 (step 42-43) + Phase 3 (hallucination detection) | PHASE 2 READY — `InjectionGuard` fences uploaded text as data; 11 corpus cases covered in `tests/test_injection.py`; Phase 3 hallucination still pending |
| F6 | Contradiction Challenge readiness | Phase 3 (steps 33-34) | PENDING |
| F7 | Source Traceability Challenge readiness | Phase 1 (metadata) + Phase 2 (citations) + Phase 3 (traceability score) | PHASE 1+2 READY — chunks store doc/section/page; generated items carry `source_document_id` + `source_section_id` checked by `OutputSchemaValidator`; Phase 3 traceability score still pending |
| F8 | Hallucination Challenge readiness | Phase 2 (source grounding) + Phase 3 (hallucination detection) | PHASE 2 READY for `grounding_status` / `GroundingFlag`; Phase 3 `HallucinationDetector` still pending |
| F9 | Live Code Modification readiness | All phases (OOP design enables single-class changes) | PENDING |
| F10 | Deliberate Defect readiness (debug planted errors) | All phases (clean code, docstrings, SRP) | PENDING |
| F11 | Meaningful GitHub commits across all 5 days from all members | All phases | IN PROGRESS — 13 Phase 2 commits (A'LAA MADYAN) fast-forwarded into `main`; Phase 1 split commits by Azhar Raji AL-Herwi; remaining members/days still required |
| F12 | ABSOLUTE PROHIBITION on hard-coded plans/answers/scores/fakes | Phase 2 + Phase 3 (everything computed live) | PHASE 2 SATISFIED for generation — live `PlanAssembler` from matrix+chunks, fail-closed Gemini, no per-role hard-coded plans; Phase 3 scores still pending |
| F14 | GenAI never replaces Python validation/business rules/security | Phase 2 + Phase 3 (strict pipeline separation) | PHASE 2 SATISFIED — schema/retry/injection/distractors are Python; Pipeline 2 remains Phase 3 with zero GenAI. Note: no live Gemini call yet (see ORPHANS), so the *separation* is proven but the *GenAI half* is proven only by wiring |
| F15 | AI-assisted code must be reviewed/understood/explainable by team | All phases | PENDING |
| F16 | AI_USAGE.md maintained by every team member | All phases (human responsibility) | PENDING |

---

## [MANDATORY FOLDER STRUCTURE]

```
SkillSprint_AI/
├── README.md
├── AI_USAGE.md
├── requirements.txt
├── LICENSE
├── agent_history.md
├── app_explanation.md
├── PROJECT_MAP.md
├── config/
│   ├── settings.py              # Environment config, API keys, DB URL
│   ├── logging_config.py        # Async logging setup
│   └── policy_precedence.yaml   # Configurable precedence hierarchy
├── src/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── models.py            # User, Role SQLAlchemy models
│   │   ├── service.py           # AuthService
│   │   ├── routes.py            # Login/logout/RBAC routes
│   │   └── dependencies.py      # get_current_user, require_role decorators
│   ├── documents/
│   │   ├── __init__.py
│   │   ├── models.py            # Document, DocumentChunk
│   │   ├── service.py           # DocumentService
│   │   ├── repository.py        # DocumentRepository, ChunkRepository
│   │   └── routes.py            # Upload/list/version endpoints
│   ├── employees/
│   │   ├── __init__.py
│   │   ├── models.py            # Employee, Role
│   │   ├── service.py           # EmployeeService
│   │   ├── repository.py        # EmployeeRepository
│   │   └── routes.py            # CRUD endpoints
│   ├── plans/
│   │   ├── __init__.py
│   │   ├── models.py            # OnboardingPlan, LearningModule, etc.
│   │   ├── service.py           # PlanGenerationService
│   │   └── routes.py            # Generation/retrieval endpoints
│   ├── reviews/
│   │   ├── __init__.py
│   │   ├── models.py            # ReviewDecision, AuditEntry
│   │   ├── service.py           # ReviewService
│   │   ├── repository.py        # ReviewRepository, AuditRepository
│   │   └── routes.py            # Review queue/action endpoints
│   ├── dashboards/
│   │   ├── __init__.py
│   │   ├── service.py           # Dashboard data aggregation
│   │   └── routes.py            # Employee/Admin/Role dashboard routes
│   ├── search/
│   │   ├── __init__.py
│   │   ├── service.py           # SearchService
│   │   └── routes.py            # Search/filter endpoints
│   └── reports/
│       ├── __init__.py
│       ├── service.py           # ReportService
│       └── routes.py            # Report generation/export endpoints
├── database/
│   ├── __init__.py
│   ├── base.py                  # SQLAlchemy Base, engine, session factory
│   ├── migrations.py            # Schema creation/migration
│   └── seed.py                  # Demo data seeding
├── document_processing/
│   ├── __init__.py
│   ├── uploader.py              # File upload handler
│   ├── validator.py             # File type/size/duplicate/version validation
│   ├── parser.py                # PDF + DOCX parsing with metadata retention
│   └── chunker.py               # Content chunking with traceability
├── document_validation/         # (Document-level validation — distinct from plan validation)
│   ├── __init__.py
│   └── version_control.py       # Active vs obsolete document management
├── role_matrix/
│   ├── __init__.py
│   ├── load_matrix.py           # CSV loader with validation
│   ├── repository.py            # RoleMatrixRepository
│   └── role_requirement_matrix_seed.csv  # (existing input data)
├── genai_pipeline/
│   ├── __init__.py
│   ├── base_provider.py         # BaseGenAIProvider ABC
│   ├── gemini_provider.py       # GeminiProvider implementation
│   ├── plan_generator.py        # PlanGenerationService (GenAI orchestration)
│   ├── module_generator.py      # Learning module generation
│   ├── quiz_generator.py        # Quiz generation + distractor validation
│   ├── assessment_generator.py  # Assessment + rubric generation
│   ├── schema_validator.py      # Pydantic schema validation for GenAI output
│   ├── retry_manager.py         # Retry logic with cap + logging
│   └── injection_guard.py       # Prompt injection defense
├── prompt_templates/
│   ├── onboarding_plan_v1.json
│   ├── learning_module_v1.json
│   ├── quiz_generation_v1.json
│   ├── assessment_v1.json
│   └── scenario_task_v1.json
├── schemas/
│   ├── __init__.py
│   ├── plan_schema.py           # OnboardingPlan Pydantic models
│   ├── module_schema.py         # LearningModule Pydantic models
│   ├── quiz_schema.py           # QuizQuestion Pydantic models
│   ├── assessment_schema.py     # Assessment Pydantic models
│   ├── validation_schema.py     # ValidationReport Pydantic models
│   └── common_schema.py         # Shared enums, base schemas
├── python_validation/
│   ├── __init__.py
│   ├── base_validator.py        # BaseValidator ABC
│   ├── coverage_validator.py    # CoverageValidator
│   ├── traceability_validator.py # TraceabilityValidator
│   ├── duplicate_validator.py   # DuplicateValidator
│   ├── contradiction_validator.py # ContradictionValidator
│   ├── role_relevance_validator.py # RoleRelevanceValidator
│   ├── hallucination_detector.py # HallucinationDetector
│   ├── sequence_validator.py    # SequenceValidator
│   ├── schema_validator.py      # SchemaValidator (Pipeline 2 version)
│   └── pipeline.py              # ValidationPipeline compositor
├── comparison_engine/
│   ├── __init__.py
│   ├── comparator.py            # ComparisonEngine — structured attribute comparison
│   └── consistency_tester.py    # ConsistencyService — repeat & compare
├── hallucination_checks/
│   ├── __init__.py
│   └── detector.py              # Hallucination detection utilities (shared by python_validation)
├── contradiction_checks/
│   ├── __init__.py
│   ├── detector.py              # Contradiction detection logic
│   └── precedence.py            # Policy precedence rule engine
├── security/
│   ├── __init__.py
│   ├── injection_guard.py       # Injection detection + sanitization
│   └── test_suite.py            # Security testing suite
├── templates/
│   ├── base.html                # Base Jinja2 layout
│   ├── login.html
│   ├── employee_dashboard.html
│   ├── admin_dashboard.html
│   ├── role_dashboard.html
│   ├── review_queue.html
│   ├── document_upload.html
│   ├── plan_view.html
│   └── report_view.html
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── app.js
│   └── img/
├── tests/
│   ├── __init__.py
│   ├── test_document_processing.py
│   ├── test_document_validation.py
│   ├── test_matrix_loading.py
│   ├── test_genai_pipeline.py
│   ├── test_validation_pipeline.py
│   ├── test_comparison_engine.py
│   ├── test_hallucination.py
│   ├── test_contradiction.py
│   ├── test_injection.py
│   ├── test_auth.py
│   ├── test_dashboards.py
│   ├── test_reports.py
│   └── test_hidden_readiness.py
├── sample_documents/            # (existing — 24 docs, 38 files across 6 subdirs)
│   ├── compliance/              # COMP-01 (DOCX)
│   ├── faqs/                    # FAQ-01, FAQ-02 (DOCX)
│   ├── handbook/                # HANDBOOK-01 (DOCX)
│   ├── policies/                # POL-01 (DOCX), POL-02–POL-05 (DOCX+PDF)
│   ├── role_descriptions/       # ROLE-01–ROLE-10 (DOCX+PDF, all 10 roles)
│   └── sops/                    # SOP-01–SOP-05 (DOCX)
├── hidden_test_ready/
│   ├── README.md                # Instructions for evaluators
│   ├── demo_data.json           # Pre-loaded demo state
│   └── evaluator_credentials.md
├── documentation/
│   ├── dataset_special_cases_index.md  # (existing)
│   ├── dataset_verification_report.md  # (existing)
│   ├── architecture_diagrams/
│   └── api_docs/
├── screenshots/
├── reports/
└── config/
    ├── settings.py
    ├── logging_config.py
    └── policy_precedence.yaml
```

---

## [DOCUMENT INVENTORY]

> **24 unique documents, 38 files on disk.** PDF files are identical to their
> DOCX counterparts — they exist so the system can be tested with multiple
> import formats (PDF, Word, TXT, Markdown, CSV) wherever required.

| Doc ID | Document Title | Subdirectory | DOCX | PDF |
|---|---|---|---|---|
| HANDBOOK-01 | Employee Handbook | handbook/ | [X] | [ ] |
| POL-01 | HR Policy | policies/ | [X] | [ ] |
| POL-02 | Leave Policy | policies/ | [X] | [X] |
| POL-03 | Information Security Policy | policies/ | [X] | [X] |
| POL-04 | Workplace Conduct Policy | policies/ | [X] | [X] |
| POL-05 | Data Privacy Policy | policies/ | [X] | [X] |
| SOP-01 | Engineering Deployment SOP | sops/ | [X] | [ ] |
| SOP-02 | Customer Support Refund SOP | sops/ | [X] | [ ] |
| SOP-03 | Payment Data Handling SOP | sops/ | [X] | [ ] |
| SOP-04 | Warehouse Incident Reporting SOP | sops/ | [X] | [ ] |
| SOP-05 | Vendor Invoice Processing SOP | sops/ | [X] | [ ] |
| ROLE-01 | Software Engineer Role Description | role_descriptions/ | [X] | [X] |
| ROLE-02 | DevOps/Infrastructure Engineer Role Description | role_descriptions/ | [X] | [X] |
| ROLE-03 | QA Engineer Role Description | role_descriptions/ | [X] | [X] |
| ROLE-04 | Customer Support Representative Role Description | role_descriptions/ | [X] | [X] |
| ROLE-05 | Payments Operations Specialist Role Description | role_descriptions/ | [X] | [X] |
| ROLE-06 | HR Generalist Role Description | role_descriptions/ | [X] | [X] |
| ROLE-07 | Recruiter Role Description | role_descriptions/ | [X] | [X] |
| ROLE-08 | Financial Analyst Role Description | role_descriptions/ | [X] | [X] |
| ROLE-09 | Accounts Payable Clerk Role Description | role_descriptions/ | [X] | [X] |
| ROLE-10 | Warehouse Operations Coordinator Role Description | role_descriptions/ | [X] | [X] |
| FAQ-01 | New Employee Onboarding FAQ | faqs/ | [X] | [ ] |
| FAQ-02 | Customer Refunds & Returns FAQ | faqs/ | [X] | [ ] |
| COMP-01 | Compliance Escalation Procedures | compliance/ | [X] | [ ] |

**Totals**: 24 DOCX + 14 PDF = 38 files. ROLE-07 through ROLE-10 added in Addendum v1.1 (2026-09-25).

---

## [CONSTRAINTS ACKNOWLEDGED]

1. **GenAI non-determinism**: Different executions produce different wording — comparison engine uses structured attributes (IDs, booleans, enums), never exact NL matching.
2. **Source document quality**: System effectiveness bounded by document completeness — 4 known vague/missing-info cases documented.
3. **Context limits**: Large document sets may exceed model context window — chunking strategy must enable selective retrieval.
4. **API availability**: GenAI API outages handled gracefully (retry with cap, cached results where applicable, user notification).
5. **Privacy/Security**: No PII beyond what's specified in Employee model; API keys in environment variables, never committed; uploaded documents treated as confidential organizational data.
6. **10 adversarial injection cases**: Embedded in corpus by design for testing — InjectionGuard must detect and neutralize all 10.
