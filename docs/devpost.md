# ClaimGate — hackathon submission draft

## Event and challenge

- **Event:** DevNetwork [API + Cloud + AI] Hackathon 2026
- **Challenge:** Foxit — Your Agent Shouldn’t Sign That
- **Project:** ClaimGate — AI Action Authorization Platform

This wording identifies the event and challenge only. It does not imply a prize, placement,
partnership, sponsorship, endorsement, or winner status.

## Tagline

**Authorization infrastructure for AI agents performing irreversible actions.**

## Short description

ClaimGate controls what AI agents are allowed to do before irreversible execution. It verifies
the final artifact against trusted evidence, applies deterministic policy, binds explicit human
approval to the exact reviewed action, and exposes execution only through backend capabilities.
Document signing through Foxit PDF Services and Foxit eSign is the first live implementation.

## The problem

Agent frameworks make it easy to connect a model to a tool. That becomes dangerous when the tool
can sign a contract, send money, deploy code, or modify production data. Model confidence is not
authority, and a prompt instruction such as “ask before acting” is not a reliable security
boundary.

ClaimGate supplies the missing control plane between proposal and execution.

## What ClaimGate does

For the implemented document-signing flow:

1. Foxit generates and re-reads the final PDF artifact.
2. A schema-constrained semantic layer extracts material claims and compares them with evidence.
3. Python validates that cited source text and evidence quotations are verbatim-grounded.
4. A deterministic, fail-closed policy returns `READY_FOR_APPROVAL` or `BLOCKED`.
5. An optional Policy-as-Code profile may add blockers but cannot remove baseline blockers.
6. A human reviews and approves the exact artifact, evidence, policy, and action bindings.
7. The backend re-verifies those bindings and, only when the operator latch is enabled, invokes
   Foxit eSign.
8. ClaimGate records the decision in a tamper-evident receipt that can be checked by read-only
   historical replay.

The AI agent does not hold Foxit eSign credentials, cannot call the signing adapter, and cannot
express an approval in the semantic output schema.

## Foxit integration

- **Foxit PDF Services:** produces and extracts the final artifact through the configured official
  MCP server boundary.
- **Foxit eSign:** receives a document only after explicit human authorization and server-side
  binding verification.
- **Backend-only credentials:** neither the browser nor the semantic provider receives eSign
  credentials.
- **Human-triggered execution:** a live send requires both the per-request confirmation and the
  environment-level `FOXIT_ESIGN_CONFIRM_SEND=YES` safety latch.

Foxit eSign is the only live irreversible action adapter. Additional action types are represented
and policy-gated but intentionally execute through simulation-only adapters.

## Why the security boundary holds

- Strict semantic schemas contain no approval or execution fields.
- The semantic provider has no tools.
- Evidence quotations must exist in the cited source.
- Baseline policy is deterministic and fail-closed.
- Policy profiles are strictly additive.
- Approval is cryptographically bound to material state.
- Protected state is re-verified immediately before execution.
- The execution-capability registry is static and code-owned.
- Decision Receipts and replay expose tampering and later drift without re-executing anything.

## General authorization model

ClaimGate defines a typed `ProposedAction` for document signing, email, software deployment,
purchase, payment, and database-write actions. This demonstrates how the authorization boundary
generalizes while remaining honest about implementation status: only document signing uses a live
backend in this repository.

## Suggested two-minute demo

1. **Open the product page.** State the rule: “AI proposes. ClaimGate verifies evidence and
   policy. Humans authorize. Backends execute.”
2. **Start a document workflow.** Upload the final PDF and evidence, then select a policy profile.
3. **Show verification.** Point out the claim/evidence table, cited sources, and deterministic
   policy result.
4. **Show the approval boundary.** Explain that the button authorizes the exact hashes currently
   under review; it is not a reusable approval.
5. **Show a blocked result.** Change a material value or use conflicting evidence and show that
   the approval action is unavailable.
6. **Show audit and replay.** Open the Decision Receipt and demonstrate that replay is read-only.
7. **Close on the Foxit boundary.** The agent never receives eSign credentials; the human-triggered
   backend is the only component that can send.

## Technology

Python, FastAPI, Pydantic strict models, Foxit PDF Services through the official MCP boundary,
Foxit eSign, optional OpenAI structured responses, optional SerpApi discovery, server-rendered
HTML/CSS/JavaScript, Pytest, and Ruff.

## Current limitations

- Users, sessions, workflows, and audit state are process-local.
- Documents and evidence use local filesystem storage.
- Authentication is intended for local evaluation rather than production tenancy.
- Live Foxit workflows require operator-provided credentials and MCP setup.
- Non-signing action adapters are simulated.

## Next steps

Move workflow and audit state to PostgreSQL, store artifacts in object storage, add production
identity and multi-tenant workspaces, introduce RBAC approval chains and background workers,
complete the Foxit eSign lifecycle, and add further evidence connectors and irreversible action
adapters without weakening the existing authorization boundary.

## One-sentence close

**AI can propose. ClaimGate verifies evidence and policy. Humans authorize. Backends execute.**
