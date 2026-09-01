# ClaimGate architecture

ClaimGate is authorization infrastructure for AI agents performing irreversible actions. Its
core architectural rule is simple:

> **AI reasons. ClaimGate authorizes. Humans approve. Backends execute.**

This document describes the implemented trust boundaries and the code that enforces them.

## System context

```text
┌───────────────────────────────────────────────────────────────────────┐
│ UNTRUSTED                                                             │
│ Browser input · uploaded documents · semantic output · search output  │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │ strict validation and grounding
┌──────────────────────────────────▼────────────────────────────────────┐
│ APPLICATION-CONTROLLED                                                │
│ FastAPI orchestration · canonical hashing · Evidence Graph            │
│ deterministic policy · additive policy profiles · approval bindings   │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │ explicit human confirmation
┌──────────────────────────────────▼────────────────────────────────────┐
│ HUMAN AUTHORIZATION                                                   │
│ Review exact artifact/action · confirm approval · operator send latch │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │ bindings re-verified before call
┌──────────────────────────────────▼────────────────────────────────────┐
│ BACKEND EXECUTION                                                     │
│ Foxit eSign for SIGN_DOCUMENT · simulated adapters for other actions │
└───────────────────────────────────────────────────────────────────────┘
```

No lower-trust layer can grant itself authority in a higher-trust layer. A semantic result is
data, a browser click is a request, and an approval is valid only while its cryptographic
bindings still match server state.

## FastAPI application boundary

`src/claimgate/web/app.py` is the HTTP composition root. It serves the public product page, local
authentication flow, authenticated application shell, workflow APIs, diagnostics, approval
requests, receipts, replay, and security validation endpoints.

The web layer coordinates existing services; it is not the policy authority. Requests pass into
typed application and domain objects before an authorization decision is made. Credentials are
read by backend integrations and are not serialized to the browser. Uploads are size- and
type-checked by `claimgate.web.uploads.UploadStore` and kept in the configured local artifact
directory in this development implementation.

Users, sessions, and run state are currently process-local. Production identity, durable state,
multi-tenancy, and distributed execution are roadmap items rather than implied capabilities.

## Foxit PDF pipeline

Document signing is the first fully implemented irreversible action. The final artifact is
handled as follows:

1. `claimgate.integrations.foxit_mcp_launcher` starts the configured official Foxit PDF MCP
   server.
2. `claimgate.integrations.foxit_pdf` requests PDF generation or extraction through that
   boundary.
3. ClaimGate re-reads the produced artifact and computes its canonical SHA-256 binding.
4. Extracted text enters the semantic boundary for structured claim extraction and evidence
   comparison.
5. The artifact is re-read again before live execution; cached UI state is not treated as proof.

The PDF artifact is therefore part of the authorization input, not a decorative output produced
after the decision.

## Semantic provider boundary

`claimgate.semantic` is allowed to extract and compare natural-language data. It is deliberately
unable to authorize:

- Semantic models use strict Pydantic validation with `extra="forbid"`.
- Output schemas contain no `approved`, `execute`, adapter, or credential field.
- `StructuredSemanticProvider` exposes one structured-completion method and no tools.
- The OpenAI provider sends structured requests without execution tools.
- Extracted source text and evidence quotations must be present verbatim in their claimed source.
- Criticality is checked against code-owned claim categories rather than trusted from model
  output.
- The semantic package has no import path to the action executors or Foxit eSign client.

The scripted provider is deterministic and enabled by default. The OpenAI provider is optional;
switching providers does not change the authorization semantics.

## Deterministic policy

`claimgate.domain.policy.DeterministicPolicyEngine` is the baseline authorization authority. It
is pure, synchronous, and fail-closed. Unknown, duplicate, missing, conflicting, or uncertain
material inputs add blockers. The result is exactly `READY_FOR_APPROVAL` or `BLOCKED`.

`claimgate.policy_profiles.PolicyProfileEvaluator` applies a selected Policy-as-Code profile on
top of the baseline. Profiles are bounded YAML/JSON data with strict schemas and no executable
tags. `EffectivePolicyEvaluation` enforces the composition invariant: a profile may introduce
additional blockers, but it cannot turn a blocked baseline into an approval-ready decision.

`claimgate.actions.authorization` adds hardcoded action-type requirements for generalized
actions. These requirements are also additive.

## Evidence Graph

`claimgate.evidence_graph` projects the verification result into nodes and edges connecting
claims, evidence sources, policy findings, and authorization outcomes. It exists to explain why
a decision was made; it does not make or override the policy decision.

Evidence carries an explicit authority classification:

| Authority | Meaning |
|---|---|
| `AUTHORITATIVE_INTERNAL` | Curated first-party authoritative source |
| `INTERNAL` | First-party source without authoritative designation |
| `VERIFIED_EXTERNAL` | External source matching known verification rules |
| `UNVERIFIED_EXTERNAL` | Other external source |

Public search results are capped below `AUTHORITATIVE_INTERNAL`. Search rank and provider hints
cannot create internal authority.

## Public-evidence boundary

`claimgate.public_evidence` supports a deterministic scripted provider and an optional backend
SerpApi provider. It normalizes and classifies discovery results before they become evidence.
Browser clients do not receive API keys or arbitrary search controls, and discovery alone does
not authorize an action.

## General `ProposedAction` model

`claimgate.actions.models.ProposedAction` describes the requested effect independently from the
agent that proposed it. Material fields are canonicalized into an action hash. The model covers:

- `SIGN_DOCUMENT`
- `SEND_EMAIL`
- `DEPLOY_SOFTWARE`
- `EXECUTE_PURCHASE`
- `EXECUTE_PAYMENT`
- `DATABASE_WRITE`

`CAPABILITY_REGISTRY` is a static, read-only mapping defined in source. Only `SIGN_DOCUMENT` is
marked for live execution. Other types use `SimulatedActionExecutor`; the UI and diagnostics must
not present them as live.

## Approval bindings

An approval is a binding, not a reusable boolean:

- The baseline binding includes the PDF hash, evidence hash, and policy version.
- Profile approval also includes the profile identifier and profile hash.
- General action approval includes the action identifier, type, and canonical action hash.

`claimgate.application.approval.ApprovalSendService` re-derives the protected state before
creating/accepting approval and immediately before execution. It re-reads the PDF and re-runs
policy evaluation instead of trusting the displayed or cached result. Material drift invalidates
the approval.

## Foxit eSign execution boundary

`claimgate.actions.adapters.FoxitSignDocumentExecutor` is the live adapter for
`SIGN_DOCUMENT`. It wraps the existing eSign sender protocol and rejects all other action types.
`claimgate.web.esign.LiveFoxitESignSender` keeps Foxit credentials on the backend and enforces the
operator-level `FOXIT_ESIGN_CONFIRM_SEND=YES` latch.

A live send requires all of the following:

1. The workflow is policy-ready.
2. The request contains explicit human confirmation.
3. The current artifact/evidence/policy/action bindings match the reviewed state.
4. The environment send latch is explicitly enabled.
5. The capability registry permits a live executor for the action type.

The send path is at-most-once and does not use automatic retries for the irreversible call.

## Decision Receipts

`claimgate.audit` creates canonical Decision Receipts containing the relevant action, artifact,
evidence, policy, approval, and execution data. A receipt hash is calculated over canonical JSON,
and each receipt may bind the previous receipt hash to form a tamper-evident chain.

Receipts record decisions; they are not transferable approvals and cannot trigger execution.

## Historical Replay

`claimgate.replay` captures current server state and compares it with a selected historical
receipt. It distinguishes receipt-integrity failure from later artifact/action drift. Replay is
read-only and does not:

- call the semantic provider,
- alter workflow state,
- mint an approval,
- select an executor, or
- execute an action.

## Security Validation Suite

`claimgate.redteam` runs fixed adversarial scenarios against the real enforcement paths. Coverage
includes prompt injection, invented quotations, artifact and evidence drift, replayed approval,
duplicate send, receipt tampering, policy manipulation, and generalized action-binding attacks.
The suite reports whether the boundary held; it does not expose credentials or add a second
execution route.

## Deployment evolution

The current repository is a local, reviewable implementation of the authorization architecture.
Production evolution requires durable PostgreSQL state, object storage, production identity,
multi-tenant isolation, RBAC and approval chains, workers, enterprise audit retention, and
operational Foxit eSign lifecycle handling. Those changes should preserve the boundaries above
rather than move authorization into an agent framework or UI client.
