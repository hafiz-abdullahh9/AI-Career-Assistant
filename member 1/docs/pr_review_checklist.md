# Pull Request Review Checklist (AGENT 02)

As **Member 1 (Project Lead & Integration Engineer)**, use this checklist to validate all incoming feature branches (`feature/*`) before approving and merging them into the `develop` branch.

---

## 1. Branching & Commit Conventions
- [ ] **Branch Naming**: Verify the branch name matches the assigned team role:
  - Member 2: `feature/job-scraping-verification`
  - Member 3: `feature/matching-documents`
  - Member 4: `feature/application-automation`
  - Member 5: `feature/skillgap-interview-infra`
- [ ] **Conventional Commits**: Verify commit headers start with a standard type:
  - `feat:` (new feature, tool, or agent)
  - `fix:` (bug fix in tool or helper)
  - `docs:` (documentation changes only)
  - `test:` (adding or correcting unit tests)
  - `chore:` (updating dependencies, configuration)

---

## 2. API Contract & Response Envelopes
- [ ] **Interface Schema Compliance**: Ensure tool signatures match those defined in [tool_interface_spec.md](file:///e:/Antigravity%20Projects/Member%201/docs/tool_interface_spec.md).
- [ ] **Standardized Envelopes**:
  - Success responses must wrap payloads in `{"status": "SUCCESS", "data": {}}`.
  - Failure responses must wrap payloads in `{"status": "ERROR", "error": {"code": "...", "message": "..."}}`.
- [ ] **Naming Conventions**:
  - Python functions must be `snake_case`.
  - JSON parameters must be `snake_case`.
  - Status results must be `UPPERCASE` strings.

---

## 3. Data Integrity & ProfileContext
- [ ] **ProfileContext Compatibility**: Verify that the branch does not modify the frozen `ProfileContext` schema in [profile_context.py](file:///e:/Antigravity%20Projects/Member%201/infra/profile_context.py) without Lead approval.
- [ ] **Authoritative Store Synchronization**: Ensure that whenever context is updated, it is synchronized using `ProfileContextManager.save_context` to guarantee database persistence in PostgreSQL.
- [ ] **No Local State Persistence**: Ensure agents do not store state variables in local fields; all state must persist inside the shared `ProfileContext`.

---

## 4. Security & Sensitive Metadata
- [ ] **No Hardcoded Secrets**: Scan files for hardcoded API keys, tokens, client IDs, or passwords.
- [ ] **Encrypted Token Store**: If the PR touches OAuth tokens (Member 4), verify they are managed strictly via the AES-256-GCM `TokenManager` in [token_manager.py](file:///e:/Antigravity%20Projects/Member%201/infra/security/token_manager.py).
- [ ] **PII Protection**: Ensure raw CV or user profile fields are passed through the PII scrubbing logic before sending data to external LLM services.

---

## 5. Retry, Recovery & Fault Tolerance
- [ ] **Exponential Backoff Wrapper**: Ensure all functions performing network queries or external API calls are decorated with `@retry_on_exception` from `core.retry`.
- [ ] **Graceful Degradation**: Verify that if a specialist tool fails (e.g. Indeed scraping), it does not crash the orchestrator; it must catch the error, populate the standard error envelope, and allow the orchestrator to route to a designated fallback state.

---

## 6. Logging & Observability
- [ ] **Session Correlation ID**: Ensure all logger calls include the unique `user_id` or `session_id` to allow event tracing across files.
- [ ] **Standard Log Levels**:
  - `INFO`: For state transitions, starting scrapers, successfully sending emails.
  - `WARNING`: For retry occurrences, non-critical API timeouts, data warnings.
  - `ERROR`: For failed stages, failed database queries, or guardrail breaches.

---

## 7. Testing & Quality Assurance
- [ ] **Test Coverage Rule**: Verify the PR includes at least one unit test case per new function.
- [ ] **Green Verification**: Run the full test suite locally (`python -m pytest tests/`) and ensure all checks remain green before merging.
- [ ] **No Business Logic Pollution**: Ensure the tests do not mock core system exceptions or bypass the Profile Integrity Monitor guardrail.
