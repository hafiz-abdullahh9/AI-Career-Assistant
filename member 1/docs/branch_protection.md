# Branch Protection & Merge Guidelines (AGENT 02)

To ensure code stability, schema consistency, and smooth multi-agent integration, this repository enforces strict branch protection rules.

---

## 1. Branch Hierarchy & Flow

```
  main (Authoritative Release Branch)
    ▲
    │ (Staged Release / Tagging)
  develop (Integration Branch — Frozen Orchestration)
    ▲
    ├── feature/job-scraping-verification (Member 2)
    ├── feature/matching-documents (Member 3)
    ├── feature/application-automation (Member 4)
    └── feature/skillgap-interview-infra (Member 5)
```

---

## 2. Protected Branches Policy

### Target: `develop` and `main`
* **No Direct Pushes**: Direct pushes to these branches are blocked. All code must enter via a Pull Request (PR).
* **PR Approvals**: Every PR requires at least **one approved review** from the Project Lead (Member 1) before it is eligible for merging.
* **Review SLA**: The Project Lead will review and provide feedback on submitted PRs within 24 hours.

---

## 3. Mandatory Build & Test Validation
Before any PR can be merged:
* **All Tests Must Pass**: Pytest check suite (`python -m pytest tests/`) must execute and complete with a green exit status (0 failures).
* **Zero Compilation Warnings**: Any compiler errors or syntax warnings must be resolved.
* **Test Coverage**: The PR must contain corresponding test cases verifying new components.

---

## 4. Git Merge Policies
* **Squash and Merge**: We enforce "Squash and Merge" for all feature branches entering `develop`. This groups all work into a single clear conventional commit, preserving a readable, linear history.
* **Conflict Resolution**:
  * Developers are responsible for resolving merge conflicts locally.
  * Developers must pull the latest changes from `develop` and merge/rebase them into their feature branch prior to request validation.

---

## 5. Standard Rejection Conditions
A Pull Request will be immediately **rejected** or blocked if it contains:
1. **Plaintext Secrets**: Hardcoded API keys, tokens, client credentials, or private access parameters.
2. **Schema Incompatibilities**: Any unauthorized alterations to core schemas or db mappings in [profile_context.py](file:///e:/Antigravity%20Projects/Member%201/infra/profile_context.py).
3. **Guardrail Violations**: Attempts to disable or bypass the passive factual accuracy checks of the `ProfileIntegrityMonitor`.
4. **Incorrect Branch Naming**: Creating custom branches that do not match the assigned team member syntax.
5. **Contract Divergence**: Deviating from input or output structures defined in the tool specifications.
