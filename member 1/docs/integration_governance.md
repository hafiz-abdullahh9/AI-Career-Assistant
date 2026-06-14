# AI Career Assistant — Integration Governance Rules

This document outlines the strict integration policies and architectural boundaries governing the development of **AGENT 02**. All members must comply with these guidelines.

---

## 1. Orchestrator Integration Pattern
* **Decoupled Callbacks**: Specialist agents must never import or execute methods from other specialist agents directly. 
* **Handoff Coordination**: All sequence changes must be routed through the `CareerOrchestrator` using the OpenAI Agents SDK handoff framework.
* **State Isolation**: Agents must not persist state variables locally. The shared `ProfileContext` is the *only* valid session storage.

---

## 2. Strict Schema Freezing
* **Forbidden Changes**: The database models in [profile_context.py](file:///e:/Antigravity%20Projects/Member%201/infra/profile_context.py) and [token_manager.py](file:///e:/Antigravity%20Projects/Member%201/infra/security/token_manager.py) are **frozen**. No engineer may modify:
  * Table names or column definitions.
  * Pydantic schemas properties (e.g., `ProfileData`, `JobItem`, `ApplicationItem`, `ProfileContext`).
* **Exception Process**: Alterations require a formal schema migration proposal approved by the Project Lead (Member 1).

---

## 3. Tool API Contract Rules
* **Signature Alignment**: All tools must match the parameters and argument typing defined in the specification.
* **Envelope Casing**: All response fields must use exact `snake_case` naming conventions.
* **Casing of Status Codes**: Execution status outcomes must be `UPPERCASE` strings (`SUCCESS` or `ERROR`).

---

## 4. State Machine Naming Restrictions
Only the official pipeline states are valid. No member may introduce custom state strings. The standard workflow states are:
* `IDLE`, `STATE_PARSING`, `STATE_DISCOVERY`, `STATE_VERIFICATION`, `STATE_MATCHING`, `STATE_SELECTION_WAIT`, `STATE_CUSTOMIZATION`, `STATE_GUARDRAIL_CHECK`, `STATE_APPLICATION`, `STATE_TRACKING`, `STATE_PREPARATION`, `STATE_COMPLETED`
* Failure states: `STATE_PARSING_FAILED`, `STATE_DISCOVERY_FAILED`, `STATE_VERIFICATION_FAILED`, `STATE_MATCHING_FAILED`, `STATE_CUSTOMIZATION_FAILED`, `STATE_GUARDRAIL_BREACH`, `STATE_APPLICATION_FAILED`

---

## 5. Error Propagation & Isolation
* **Zero Unhandled Exceptions**: Tools must capture all local errors (timeouts, network, parser issues) internally.
* **Standard Error Wrapper**: Return a standard error dict envelope containing a valid `error_code` and retryable status.
* **Orchestration Failure Capture**: The orchestrator wraps stage calls in try-except blocks, transitioning the state to `STATE_<STAGE>_FAILED` on failures, maintaining system stability.

---

## 6. Merge & CI Compliance Rules
* **Lint Compliance**: All code must compile and pass formatting lint guidelines.
* **Test Requirements**:
  * Every pull request must include unit tests for new functionality.
  * All unit and integration tests must run and pass green (`python -m pytest tests/`) before review submission.
* **Rollback Expectation**: If a merged PR triggers pipeline failures on the `develop` branch, it will be immediately **reverted** to maintain repository stability.
