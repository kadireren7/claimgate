"use strict";

const elements = {
  artifactDropzone: document.getElementById("artifact-dropzone"),
  artifactFileInput: document.getElementById("artifact-file-input"),
  artifactDropzoneEmpty: document.getElementById("artifact-dropzone-empty"),
  artifactDropzoneFile: document.getElementById("artifact-dropzone-file"),
  artifactFileName: document.getElementById("artifact-file-name"),
  artifactFileRemove: document.getElementById("artifact-file-remove"),
  policyProfileSelect: document.getElementById("policy-profile-select"),
  policyProfileDescription: document.getElementById("policy-profile-description"),
  evidenceCount: document.getElementById("evidence-count"),
  evidenceInputs: document.getElementById("evidence-inputs"),
  addEvidenceButton: document.getElementById("add-evidence-button"),
  generateButton: document.getElementById("generate-button"),
  generateButtonHint: document.getElementById("generate-button-hint"),
  emptyState: document.getElementById("empty-state"),
  runView: document.getElementById("run-view"),
  runReference: document.getElementById("run-reference"),
  progressState: document.getElementById("progress-state"),
  progressSteps: document.getElementById("progress-steps"),
  errorPanel: document.getElementById("error-panel"),
  errorCopy: document.getElementById("error-copy"),
  resultView: document.getElementById("result-view"),
  decisionBanner: document.getElementById("decision-banner"),
  decisionLabel: document.getElementById("decision-label"),
  decisionExplanation: document.getElementById("decision-explanation"),
  publicEvidenceUpdate: document.getElementById("public-evidence-update"),
  publicPreviousStatus: document.getElementById("public-previous-status"),
  publicSourceCount: document.getElementById("public-source-count"),
  publicCurrentStatus: document.getElementById("public-current-status"),
  publicUpdateTitle: document.getElementById("public-update-title"),
  publicUpdateDetail: document.getElementById("public-update-detail"),
  selectedProfileName: document.getElementById("selected-profile-name"),
  baselineDecision: document.getElementById("baseline-decision"),
  profileDecision: document.getElementById("profile-decision"),
  finalDecision: document.getElementById("final-decision"),
  profileBlockers: document.getElementById("profile-blockers"),
  pdfLink: document.getElementById("pdf-link"),
  pdfPreview: document.getElementById("pdf-preview"),
  extractionQuality: document.getElementById("extraction-quality"),
  extractionQualityBadge: document.getElementById("extraction-quality-badge"),
  extractionCoverage: document.getElementById("extraction-coverage"),
  extractionQualityMessage: document.getElementById("extraction-quality-message"),
  extractionWarnings: document.getElementById("extraction-warnings"),
  claimCount: document.getElementById("claim-count"),
  claimList: document.getElementById("claim-list"),
  graphSummaryPanel: document.getElementById("graph-summary-panel"),
  graphClaimCount: document.getElementById("graph-claim-count"),
  graphSourceCount: document.getElementById("graph-source-count"),
  graphSupportCount: document.getElementById("graph-support-count"),
  graphConflictCount: document.getElementById("graph-conflict-count"),
  graphUncertainCount: document.getElementById("graph-uncertain-count"),
  evidenceChain: document.getElementById("evidence-chain"),
  chainClaimTitle: document.getElementById("chain-claim-title"),
  chainClaimValue: document.getElementById("chain-claim-value"),
  chainEdgeCount: document.getElementById("chain-edge-count"),
  evidenceChainList: document.getElementById("evidence-chain-list"),
  approvalPanel: document.getElementById("approval-panel"),
  humanConfirmation: document.getElementById("human-confirmation"),
  approveSendButton: document.getElementById("approve-send-button"),
  sendStatus: document.getElementById("send-status"),
  sendStatusLabel: document.getElementById("send-status-label"),
  sendStatusDetail: document.getElementById("send-status-detail"),
  auditMetadata: document.getElementById("audit-metadata"),
  receiptPanel: document.getElementById("receipt-panel"),
  receiptId: document.getElementById("receipt-id"),
  receiptDecision: document.getElementById("receipt-decision"),
  receiptHash: document.getElementById("receipt-hash"),
  receiptChain: document.getElementById("receipt-chain"),
  verifyReceiptButton: document.getElementById("verify-receipt-button"),
  downloadReceiptJson: document.getElementById("download-receipt-json"),
  generateReceiptPdf: document.getElementById("generate-receipt-pdf"),
  openReceiptPdf: document.getElementById("open-receipt-pdf"),
  receiptVerification: document.getElementById("receipt-verification"),
  structuredReceiptJson: document.getElementById("structured-receipt-json"),
  replayPanel: document.getElementById("replay-panel"),
  replayOriginalDecision: document.getElementById("replay-original-decision"),
  replayWorkflowState: document.getElementById("replay-workflow-state"),
  replayPolicyProfile: document.getElementById("replay-policy-profile"),
  replayLatestReceipt: document.getElementById("replay-latest-receipt"),
  replayPdfHash: document.getElementById("replay-pdf-hash"),
  replayEvidenceHash: document.getElementById("replay-evidence-hash"),
  auditTimeline: document.getElementById("audit-timeline"),
  replayReceiptSelect: document.getElementById("replay-receipt-select"),
  replayPresetSelect: document.getElementById("replay-preset-select"),
  replayPresetDescription: document.getElementById("replay-preset-description"),
  runReplayButton: document.getElementById("run-replay-button"),
  replayResult: document.getElementById("replay-result"),
  replayStatus: document.getElementById("replay-status"),
  replayStatusDetail: document.getElementById("replay-status-detail"),
  replayChecks: document.getElementById("replay-checks"),
  invariantCount: document.getElementById("invariant-count"),
  securityInvariants: document.getElementById("security-invariants"),
  attackScenarios: document.getElementById("attack-scenarios"),
  actionPipelineDetail: document.getElementById("action-pipeline-detail"),
  actionDetailId: document.getElementById("action-detail-id"),
  actionDetailHash: document.getElementById("action-detail-hash"),
  actionDetailRisk: document.getElementById("action-detail-risk"),
  actionDetailOutcome: document.getElementById("action-detail-outcome"),
  protectedActionsGrid: document.getElementById("protected-actions-grid"),
  brandSubtitle: document.getElementById("brand-subtitle"),
  foxitStatusPill: document.getElementById("foxit-status-pill"),
  diagnosticsGrid: document.getElementById("diagnostics-grid"),

  // Platform shell (Phase 15)
  topbarIntegrationsChipLabel: document.getElementById("topbar-integrations-chip-label"),
  topbarNotifBadge: document.getElementById("topbar-notif-badge"),
  sidebarApprovalsBadge: document.getElementById("sidebar-approvals-badge"),
  overviewMetrics: document.getElementById("overview-metrics"),
  overviewWorkflowsTbody: document.getElementById("overview-workflows-tbody"),
  overviewApprovalsPreview: document.getElementById("overview-approvals-preview"),
  overviewPolicySummary: document.getElementById("overview-policy-summary"),
  overviewDiagnosticsGrid: document.getElementById("overview-diagnostics-grid"),
  overviewAuditTbody: document.getElementById("overview-audit-tbody"),
  workflowsTbody: document.getElementById("workflows-tbody"),
  workflowsSearch: document.getElementById("workflows-search"),
  workflowsStatusFilter: document.getElementById("workflows-status-filter"),
  workflowsActionFilter: document.getElementById("workflows-action-filter"),
  approvalsQueue: document.getElementById("approvals-queue"),
  evidenceProvenanceLegend: document.getElementById("evidence-provenance-legend"),
  evidenceCatalog: document.getElementById("evidence-catalog"),
  policiesCatalog: document.getElementById("policies-catalog"),
  auditLedgerTbody: document.getElementById("audit-ledger-tbody"),
  settingsDiagnosticsGrid: document.getElementById("settings-diagnostics-grid"),
  settingsWorkspaceName: document.getElementById("settings-workspace-name"),
  settingsOperatorEmail: document.getElementById("settings-operator-email"),
  topbarWorkspaceLabel: document.getElementById("topbar-workspace-label"),
  topbarUserButton: document.getElementById("topbar-user-button"),
  topbarUserAvatar: document.getElementById("topbar-user-avatar"),
  topbarUserName: document.getElementById("topbar-user-name"),
  topbarUserDropdown: document.getElementById("topbar-user-dropdown"),
  topbarUserEmail: document.getElementById("topbar-user-email"),
  topbarUserWorkspace: document.getElementById("topbar-user-workspace"),
  topbarLogoutButton: document.getElementById("topbar-logout-button"),
  currentPageTitle: document.getElementById("current-page-title"),
};

const state = {
  policyProfiles: [],
  selectedPolicyProfile: null,
  artifactFile: null,
  evidenceItems: [],
  running: false,
  runId: null,
  approvalAvailable: false,
  evidenceGraph: null,
  receipt: null,
  auditHistory: null,
  attackScenarios: [],
  session: null,
};

let evidenceItemSeq = 0;

function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined && text !== null) item.textContent = text;
  return item;
}

// Plain-language provenance metadata for each evidence authority level. Purely
// presentational — derived client-side from the authority string the API already
// returns, never a new trust signal and never fed back into any decision.
const AUTHORITY_INFO = {
  AUTHORITATIVE_INTERNAL: {
    tier: "authoritative",
    label: "Authoritative",
    sourceType: "Internal business record",
    origin: "Internal business source",
    why:
      "Organization-approved source of truth. ClaimGate does not let the AI promote " +
      "arbitrary evidence to authoritative status — this label is set by how the " +
      "evidence entered the system, not by anything the model said about it.",
  },
  INTERNAL: {
    tier: "internal",
    label: "Internal",
    sourceType: "Internal supporting record",
    origin: "Internal business source",
    why: "Internal supporting evidence. Useful context, but not treated as a standalone source of truth.",
  },
  VERIFIED_EXTERNAL: {
    tier: "verified-external",
    label: "Verified external",
    sourceType: "Public record, domain-verified",
    origin: "External source with a trusted, verified domain",
    why: "Public evidence from a source whose domain is trusted. It can support a claim but cannot itself authorize an action.",
  },
  UNVERIFIED_EXTERNAL: {
    tier: "unverified-external",
    label: "Unverified external",
    sourceType: "Public record, unverified domain",
    origin: "External source of unknown or unverified standing",
    why: "Public evidence that cannot independently satisfy strict policies. Search rank alone never promotes it to authoritative.",
  },
};

function authorityInfo(authority) {
  return (
    AUTHORITY_INFO[authority] || {
      tier: "unverified-external",
      label: (authority || "unknown").replaceAll("_", " "),
      sourceType: "Unclassified source",
      origin: "Unknown origin",
      why: "This source's trust level could not be classified.",
    }
  );
}

function copyToClipboard(button, value) {
  if (!value || value === "—") return;
  const original = button.textContent;
  const done = () => {
    button.textContent = "Copied";
    button.classList.add("copied");
    window.setTimeout(() => {
      button.textContent = original;
      button.classList.remove("copied");
    }, 1400);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(value).then(done).catch(() => {
      button.textContent = "Copy failed";
    });
  }
}

function withCopyButton(valueText) {
  const wrap = node("span", "copyable-value");
  wrap.append(node("code", "", valueText));
  if (valueText && valueText !== "—") {
    const button = node("button", "copy-hash-btn", "Copy");
    button.type = "button";
    button.setAttribute("aria-label", "Copy value to clipboard");
    button.addEventListener("click", () => copyToClipboard(button, valueText));
    wrap.append(button);
  }
  return wrap;
}

// FastAPI returns a plain string in `detail` for most errors, but a request
// body that fails Pydantic validation gets an ARRAY of {loc, msg, type}
// objects instead. Rendering that array directly (e.g. via `new Error(arr)`)
// stringifies each object to the useless "[object Object],[object Object]".
// This normalizes either shape into one readable sentence.
function formatApiErrorDetail(detail, fallback) {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === "object" ? item.msg : String(item)))
      .filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  return fallback;
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = `ClaimGate API returned ${response.status}`;
    try {
      const errorPayload = await response.json();
      detail = formatApiErrorDetail(errorPayload.detail, detail);
    } catch (error) {
      // Retain the status-only message for non-JSON server errors.
    }
    throw new Error(detail);
  }
  return response.json();
}

async function uploadFile(kind, file) {
  const formData = new FormData();
  formData.append("kind", kind);
  formData.append("file", file);
  const response = await fetch("/api/uploads", { method: "POST", body: formData });
  if (!response.ok) {
    let detail = `Upload failed (${response.status})`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (error) {
      // Retain the status-only message for non-JSON server errors.
    }
    throw new Error(detail);
  }
  return response.json();
}

function setArtifactFile(file) {
  state.artifactFile = file;
  elements.artifactDropzoneEmpty.hidden = Boolean(file);
  elements.artifactDropzoneFile.hidden = !file;
  elements.artifactFileName.textContent = file ? file.name : "";
  resetResults();
  updateGenerateButtonState();
}

function initArtifactUpload() {
  elements.artifactDropzone.addEventListener("click", () => elements.artifactFileInput.click());
  elements.artifactDropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      elements.artifactFileInput.click();
    }
  });
  elements.artifactFileInput.addEventListener("change", () => {
    setArtifactFile(elements.artifactFileInput.files[0] || null);
  });
  elements.artifactFileRemove.addEventListener("click", (event) => {
    event.stopPropagation();
    elements.artifactFileInput.value = "";
    setArtifactFile(null);
  });
  ["dragover", "dragenter"].forEach((type) => {
    elements.artifactDropzone.addEventListener(type, (event) => {
      event.preventDefault();
      elements.artifactDropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((type) => {
    elements.artifactDropzone.addEventListener(type, (event) => {
      event.preventDefault();
      elements.artifactDropzone.classList.remove("dragover");
    });
  });
  elements.artifactDropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer && event.dataTransfer.files[0];
    if (file) setArtifactFile(file);
  });
}

function addEvidenceRow() {
  evidenceItemSeq += 1;
  state.evidenceItems.push({ id: evidenceItemSeq, title: "", text: "", file: null });
  renderEvidenceInputs();
}

function removeEvidenceRow(id) {
  state.evidenceItems = state.evidenceItems.filter((item) => item.id !== id);
  renderEvidenceInputs();
}

function renderEvidenceInputs() {
  elements.evidenceInputs.replaceChildren();
  state.evidenceItems.forEach((item) => {
    const row = node("div", "evidence-input-row");
    const head = node("div", "evidence-input-row-head");
    const titleInput = document.createElement("input");
    titleInput.type = "text";
    titleInput.className = "evidence-input-title";
    titleInput.placeholder = "Evidence title (e.g. Purchase order)";
    titleInput.value = item.title;
    titleInput.addEventListener("input", () => {
      item.title = titleInput.value;
    });
    const removeButton = node("button", "evidence-input-remove", "Remove");
    removeButton.type = "button";
    removeButton.addEventListener("click", () => removeEvidenceRow(item.id));
    head.append(titleInput, removeButton);

    const textarea = document.createElement("textarea");
    textarea.className = "evidence-input-text";
    textarea.placeholder = "Paste evidence text — or attach a file below";
    textarea.value = item.text;
    textarea.addEventListener("input", () => {
      item.text = textarea.value;
      updateGenerateButtonState();
    });

    const fileRow = node("div", "evidence-input-file-row");
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "application/pdf,.txt,text/plain";
    fileInput.className = "evidence-input-file";
    const fileName = node("span", "evidence-input-file-name", item.file ? item.file.name : "");
    fileInput.addEventListener("change", () => {
      item.file = fileInput.files[0] || null;
      fileName.textContent = item.file ? item.file.name : "";
      updateGenerateButtonState();
    });
    fileRow.append(fileInput, fileName);

    row.append(head, textarea, fileRow);
    elements.evidenceInputs.append(row);
  });
  const count = state.evidenceItems.length;
  elements.evidenceCount.textContent = `${count} source${count === 1 ? "" : "s"}`;
  updateGenerateButtonState();
}

function updateGenerateButtonState() {
  const hasValidEvidence = state.evidenceItems.some(
    (item) => item.file || (item.text && item.text.trim()),
  );
  elements.generateButton.disabled =
    state.running || !state.artifactFile || !state.selectedPolicyProfile || !hasValidEvidence;
}

function renderPolicyProfiles() {
  elements.policyProfileSelect.replaceChildren();
  state.policyProfiles.forEach((profile) => {
    const option = node("option", "", profile.name);
    option.value = profile.id;
    elements.policyProfileSelect.append(option);
  });
  elements.policyProfileSelect.disabled = state.running || !state.policyProfiles.length;
  if (state.policyProfiles.length) {
    elements.policyProfileSelect.value = "standard-contract-v1";
    selectPolicyProfile(elements.policyProfileSelect.value);
  }
}

function selectPolicyProfile(profileId) {
  if (state.running) return;
  state.selectedPolicyProfile = state.policyProfiles.find(
    (profile) => profile.id === profileId,
  );
  elements.policyProfileDescription.textContent = state.selectedPolicyProfile
    ? state.selectedPolicyProfile.description
    : "Select a deterministic policy profile.";
  resetResults();
  updateGenerateButtonState();
}

function resetResults() {
  elements.emptyState.hidden = false;
  elements.runView.hidden = true;
  elements.resultView.hidden = true;
  elements.errorPanel.hidden = true;
  elements.runReference.textContent = "";
  state.runId = null;
  state.approvalAvailable = false;
  state.evidenceGraph = null;
  state.receipt = null;
  state.auditHistory = null;
  elements.replayPanel.hidden = true;
  elements.publicEvidenceUpdate.hidden = true;
  elements.actionPipelineDetail.hidden = true;
  elements.pdfPreview.removeAttribute("src");
  resetSendControls();
}

function setRunning(running) {
  state.running = running;
  updateGenerateButtonState();
  elements.generateButton.firstElementChild.textContent = running
    ? "Verifying document…"
    : "Verify document";
  elements.policyProfileSelect.disabled = running || !state.policyProfiles.length;
  elements.artifactFileRemove.disabled = running;
  elements.addEvidenceButton.disabled = running;
  elements.generateButtonHint.hidden = true;
}

async function startDocumentRun() {
  if (state.running) return;
  const validEvidence = state.evidenceItems.filter(
    (item) => item.file || (item.text && item.text.trim()),
  );
  if (!state.artifactFile || !state.selectedPolicyProfile || !validEvidence.length) return;
  setRunning(true);
  try {
    const artifactUpload = await uploadFile("artifact", state.artifactFile);
    const evidencePayload = [];
    for (const item of validEvidence) {
      const title = item.title && item.title.trim() ? item.title.trim() : "Supporting evidence";
      if (item.file) {
        const uploaded = await uploadFile("evidence", item.file);
        evidencePayload.push({ upload_id: uploaded.upload_id, title });
      } else {
        evidencePayload.push({ text: item.text.trim(), title });
      }
    }
    const started = await apiRequest("/api/runs/document", {
      method: "POST",
      body: JSON.stringify({
        artifact_upload_id: artifactUpload.upload_id,
        evidence: evidencePayload,
        policy_profile: state.selectedPolicyProfile.id,
      }),
    });
    setArtifactFile(null);
    state.evidenceItems = [];
    renderEvidenceInputs();
    // Starting a run always opens its workflow-detail record; the router's
    // loadWorkflowDetail()/pollWorkflow() picks up polling from here.
    navigate(`/app/workflows/${started.run_id}`);
  } catch (error) {
    elements.generateButtonHint.textContent =
      error.message || "Unable to start the verification workflow. Check the server connection.";
    elements.generateButtonHint.hidden = false;
    setRunning(false);
  }
}

function defaultProgress() {
  return [
    ["reading_document", "Reading uploaded document"],
    ["extracting_pdf", "Extracting final PDF"],
    ["extracting_claims", "Extracting material claims"],
    ["checking_evidence", "Checking evidence"],
    ["applying_policy", "Applying deterministic policy"],
  ].map(([id, label]) => ({ id, label, status: "pending" }));
}

function renderProgress(steps) {
  elements.progressSteps.replaceChildren();
  steps.forEach((step) => {
    const item = node("li", `progress-step ${step.status}`, step.label);
    elements.progressSteps.append(item);
  });
}

function showError(message) {
  elements.progressState.textContent = "Failed";
  elements.progressState.className = "progress-state failed";
  elements.errorCopy.textContent = message;
  elements.errorPanel.hidden = false;
  elements.resultView.hidden = true;
}

function renderResult(result) {
  const passed = result.decision === "READY_FOR_HUMAN_APPROVAL";
  elements.progressState.textContent = "Complete";
  elements.progressState.className = "progress-state complete";
  elements.resultView.hidden = false;
  elements.errorPanel.hidden = true;

  elements.decisionBanner.className = `decision-banner ${passed ? "pass" : "block"}`;
  elements.decisionLabel.textContent = formatDecisionHeadline(result);
  elements.decisionExplanation.textContent = passed
    ? "All critical claims are supported. The exact verified PDF may now be reviewed by a human."
    : primaryBlocker(result.blockers);

  renderPolicyEvaluation(result.policy_evaluation, result.audit);

  elements.pdfLink.href = result.pdf_url;
  elements.pdfPreview.src = result.pdf_url;
  renderExtractionQuality(result.extraction);
  renderEvidenceGraph(result.evidence_graph);
  renderClaims(result.claims, result.evidence_graph);
  renderAudit(result.audit);
  renderReceipt(result.receipt);
  renderAuditHistory(result.audit_history);
  renderActionPipelineDetail(result.action);
  elements.approvalPanel.hidden = !passed;
  resetSendControls();
  if (passed && result.send && result.send.attempted) {
    renderSendOutcome(result.send);
  } else if (passed) {
    state.approvalAvailable = result.approval_available;
  }
}

function renderExtractionQuality(extraction) {
  const status = extraction.status.toLowerCase();
  elements.extractionQuality.className = `extraction-quality ${status}`;
  elements.extractionQualityBadge.className = `extraction-quality-badge ${status}`;
  elements.extractionQualityBadge.textContent =
    `Extraction quality: ${status.charAt(0).toUpperCase()}${status.slice(1)}`;
  elements.extractionCoverage.textContent =
    `${extraction.pages_with_text}/${extraction.page_count} pages with text`;
  const details = [];
  if (extraction.used_ocr) details.push("Foxit OCR fallback used");
  if (extraction.chunked) details.push(`${extraction.chunk_count} stable page chunks analyzed`);
  if (extraction.table_detected) details.push("Table-like content detected");
  if (!extraction.page_provenance_available) details.push("Page boundaries unavailable in text output");
  elements.extractionQualityMessage.textContent = details.length
    ? details.join(" · ")
    : "Full text coverage; source citations remain subject to exact-quotation validation.";
  elements.extractionWarnings.replaceChildren();
  [...extraction.checks, ...extraction.ambiguities].forEach((warning) => {
    elements.extractionWarnings.append(
      node("li", "", `${warning.code.replaceAll("_", " ")}: ${warning.message}`),
    );
  });
  elements.extractionWarnings.hidden = !elements.extractionWarnings.children.length;
}

// Display-only headline for the decision banner (Phase 16 copy tightening).
// `result.decision` — the enum the rest of the app branches on — is untouched;
// this only reformats `decision_label` for presentation.
function formatDecisionHeadline(result) {
  return result.decision === "READY_FOR_HUMAN_APPROVAL"
    ? "Ready for human approval"
    : "Blocked by deterministic policy";
}

function primaryBlocker(blockers) {
  if (!blockers.length) return "Deterministic policy requirements were not satisfied.";
  return blockers[0].explanation || blockers[0].message;
}

function renderPolicyEvaluation(evaluation, audit) {
  elements.selectedProfileName.textContent = audit.selected_profile_name;
  const decisions = [
    [elements.baselineDecision, evaluation.baseline],
    [elements.profileDecision, evaluation.profile],
    [elements.finalDecision, evaluation.final],
  ];
  decisions.forEach(([element, value]) => {
    element.textContent = value;
    element.className = value === "PASS" || value === "READY" ? "pass" : "block";
  });
  elements.profileBlockers.replaceChildren();
  elements.profileBlockers.hidden = !evaluation.profile_blockers.length;
  evaluation.profile_blockers.forEach((blocker) => {
    const item = node("div", "profile-blocker");
    item.append(
      node("strong", "", blocker.code.replaceAll("_", " ")),
      node("span", "", blocker.message),
    );
    elements.profileBlockers.append(item);
  });
}

function renderClaims(claims, graph) {
  elements.claimCount.textContent = `${claims.length} claims`;
  elements.claimList.replaceChildren();
  claims.forEach((claim) => {
    const statusClass = claim.status.toLowerCase();
    const card = node("article", `claim-card ${statusClass}`);
    card.tabIndex = 0;
    card.dataset.claimId = claim.claim_id;
    card.setAttribute("aria-pressed", "false");
    const topLine = node("div", "claim-topline");
    topLine.append(
      node("span", "claim-category", claim.category.replaceAll("_", " ")),
      node("span", "claim-status", claim.status),
    );
    const quote = claim.evidence_quote || "No evidence quotation supplied";
    const pageLabel = claim.page_numbers.length
      ? ` · Page ${claim.page_numbers.join(", ")}`
      : "";
    const tableLabel = claim.table_origin ? " · Table" : "";
    const evidencePageLabel = claim.evidence_page_numbers.length
      ? ` · Evidence page ${claim.evidence_page_numbers.join(", ")}`
      : "";
    const source = claim.evidence_source_title
      ? `${claim.evidence_source_title} · ${claim.evidence_source_id}${pageLabel}${evidencePageLabel}${tableLabel}`
      : "No evidence source";
    card.append(
      topLine,
      node("p", "claim-value", claim.value),
      node("blockquote", "claim-quote", `“${quote}”`),
      node("p", "claim-source", source),
    );
    if (claim.public_search && claim.public_search.eligible) {
      const searchButton = node("button", "public-search-button", "Search Public Evidence");
      searchButton.type = "button";
      searchButton.addEventListener("click", (event) => {
        event.stopPropagation();
        runPublicEvidence(claim, searchButton);
      });
      card.append(searchButton);
    } else if (claim.public_search && claim.public_search.attempted) {
      card.append(node("span", "public-search-complete", "PUBLIC SEARCH COMPLETE"));
    }
    card.addEventListener("click", () => selectGraphClaim(claim.claim_id));
    elements.claimList.append(card);
  });
  const firstClaim = graph && graph.claims.length ? graph.claims[0].claim_id : null;
  if (firstClaim) selectGraphClaim(firstClaim);
}

function renderEvidenceGraph(graph) {
  state.evidenceGraph = graph;
  elements.graphSummaryPanel.hidden = !graph;
  elements.evidenceChain.hidden = !graph;
  if (!graph) return;
  const summary = graph.summary;
  elements.graphClaimCount.textContent = summary.material_claims;
  elements.graphSourceCount.textContent = summary.evidence_sources;
  elements.graphSupportCount.textContent = summary.support_count;
  elements.graphConflictCount.textContent = summary.conflict_count;
  elements.graphUncertainCount.textContent = summary.uncertain_count;
}

function selectGraphClaim(claimId) {
  const graph = state.evidenceGraph;
  if (!graph) return;
  const claim = graph.claims.find((item) => item.claim_id === claimId);
  if (!claim) return;
  document.querySelectorAll(".claim-card").forEach((card) => {
    const selected = card.dataset.claimId === claimId;
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  const edges = graph.edges.filter((edge) => edge.claim_id === claimId);
  const sourceById = Object.fromEntries(
    graph.evidence.map((source) => [source.source_id, source]),
  );
  elements.chainClaimTitle.textContent = claim.category.replaceAll("_", " ");
  elements.chainClaimValue.textContent = claim.value;
  elements.chainEdgeCount.textContent = `${edges.length} relationship${edges.length === 1 ? "" : "s"}`;
  elements.evidenceChainList.replaceChildren();
  if (!edges.length) {
    elements.evidenceChainList.append(
      node("p", "chain-empty", "No source relationship was available for this claim."),
    );
    return;
  }
  edges.forEach((edge) => {
    const source = sourceById[edge.evidence_id];
    const relationshipClass = edge.relationship.toLowerCase();
    const item = node("article", `chain-edge ${relationshipClass}`);
    if (source.public) item.classList.add("public-source");
    const heading = node("div", "chain-edge-heading");
    heading.append(
      node("span", `relationship-badge ${relationshipClass}`, edge.relationship),
      node(
        "span",
        `authority-badge ${source.authoritative ? "authoritative" : ""}`,
        source.authority.replaceAll("_", " "),
      ),
    );
    item.append(
      heading,
      node("h5", "", source.title),
      node("p", "chain-source-id", `${source.source_id} · ${source.kind.replaceAll("_", " ")}`),
      node("blockquote", "chain-quote", `“${edge.quotation}”`),
    );
    if (source.provenance) {
      const provenance = node("div", "public-provenance");
      const sourceLink = node("a", "", source.provenance.domain);
      sourceLink.href = source.provenance.source_url;
      sourceLink.target = "_blank";
      sourceLink.rel = "noopener";
      provenance.append(
        node("strong", "", "PUBLIC EVIDENCE · UNTRUSTED CONTENT"),
        sourceLink,
        node("span", "", source.provenance.source_type.replaceAll("_", " ")),
        node("span", "", `Provider: ${source.provenance.provider}`),
        node("span", "", `Query: ${source.provenance.query}`),
        node("time", "", new Date(source.provenance.retrieved_at).toLocaleString()),
      );
      item.append(provenance);
    }
    elements.evidenceChainList.append(item);
  });
}

async function runPublicEvidence(claim, button) {
  if (!state.runId || !claim.public_search?.url) return;
  button.disabled = true;
  button.textContent = "Searching public evidence…";
  try {
    const result = await apiRequest(claim.public_search.url, { method: "POST" });
    renderResult(result);
    renderPublicEvidenceUpdate(result.public_evidence_update);
  } catch (error) {
    elements.publicEvidenceUpdate.className = "public-evidence-update failed";
    elements.publicUpdateTitle.textContent = "Public evidence search failed closed";
    elements.publicUpdateDetail.textContent = error.message;
    elements.publicEvidenceUpdate.hidden = false;
    button.textContent = "Search unavailable";
  }
}

function renderPublicEvidenceUpdate(update) {
  if (!update) return;
  const discovery = update.discovery;
  elements.publicPreviousStatus.textContent = update.previous_status;
  elements.publicCurrentStatus.textContent = update.current_status;
  elements.publicSourceCount.textContent = `${discovery.sources.length} SOURCE${
    discovery.sources.length === 1 ? "" : "S"
  } DISCOVERED`;
  elements.publicUpdateTitle.textContent = update.reevaluated
    ? "Deterministic policy reevaluated"
    : "Public evidence did not enter verification";
  elements.publicUpdateDetail.textContent = update.reevaluated
    ? `${discovery.message} Public evidence changed the evidence snapshot; the semantic comparison was validated and policy ran again.`
    : `${discovery.message} The original historical decision remains unchanged.`;
  elements.publicEvidenceUpdate.className = `public-evidence-update ${
    update.reevaluated ? "reevaluated" : "failed"
  }`;
  elements.publicEvidenceUpdate.hidden = false;
}

function renderAudit(audit) {
  const rows = [
    ["PDF SHA-256", audit.pdf_sha256],
    ["Evidence SHA-256", audit.evidence_sha256],
    ["Policy version", audit.policy_version],
    ["Baseline policy version", audit.baseline_policy_version],
    ["Selected profile", `${audit.selected_profile_name} · ${audit.selected_profile}`],
    ["Profile SHA-256", audit.policy_profile_hash],
    [
      "Profile blockers",
      audit.profile_specific_blockers.length
        ? audit.profile_specific_blockers.join(" | ")
        : "None",
    ],
    ["Workflow state", audit.workflow_state],
  ];
  elements.auditMetadata.replaceChildren();
  rows.forEach(([label, value]) => {
    elements.auditMetadata.append(node("dt", "", label), node("dd", "", value));
  });
}

function renderReceipt(receipt) {
  state.receipt = receipt;
  elements.receiptPanel.hidden = !receipt;
  if (!receipt) return;
  elements.receiptId.textContent = receipt.receipt_id;
  const passed = receipt.final_decision === "PASS";
  elements.receiptDecision.textContent = passed ? "PASS" : "BLOCKED";
  elements.receiptDecision.className = passed ? "pass" : "block";
  elements.receiptHash.textContent = receipt.receipt_sha256;
  elements.receiptChain.textContent = receipt.previous_receipt_sha256
    ? `Previous: ${receipt.previous_receipt_sha256}`
    : "Genesis receipt";
  elements.downloadReceiptJson.href = receipt.canonical_json_url;
  elements.verifyReceiptButton.dataset.url = receipt.verify_url;
  elements.generateReceiptPdf.dataset.url = receipt.generate_pdf_url;
  elements.openReceiptPdf.hidden = !receipt.pdf_url;
  if (receipt.pdf_url) elements.openReceiptPdf.href = receipt.pdf_url;
  elements.receiptVerification.hidden = true;
  elements.receiptVerification.replaceChildren();
  elements.structuredReceiptJson.textContent = JSON.stringify(
    receipt.structured,
    null,
    2,
  );
}

const replayPresetDescriptions = {
  CLEAN_REPLAY: "Use the unchanged server-held PDF, evidence, policy, approval, and chain context.",
  PDF_DRIFT: "Keep the receipt valid while simulating different current PDF bytes.",
  EVIDENCE_DRIFT: "Keep the receipt valid while simulating changed current evidence.",
  POLICY_DRIFT: "Keep the same profile ID while simulating changed profile contents.",
  BROKEN_CHAIN: "Verify the receipt against an incorrect expected previous-receipt hash.",
};

function renderAuditHistory(history) {
  state.auditHistory = history;
  elements.replayPanel.hidden = !history;
  if (!history) return;
  elements.replayOriginalDecision.textContent = history.original_final_decision;
  elements.replayOriginalDecision.className =
    history.original_final_decision === "PASS" ? "pass" : "block";
  elements.replayWorkflowState.textContent = history.current_workflow_state;
  elements.replayPolicyProfile.textContent = history.policy_profile_id;
  elements.replayLatestReceipt.textContent =
    history.receipts[history.receipts.length - 1].receipt_sha256;
  elements.replayPdfHash.textContent = history.pdf_sha256;
  elements.replayEvidenceHash.textContent = history.evidence_sha256;

  elements.auditTimeline.replaceChildren();
  history.timeline.forEach((event) => {
    const item = node("li", "timeline-event");
    const marker = node("span", "timeline-marker", "");
    const content = node("div", "timeline-content");
    const heading = node("div", "timeline-heading");
    heading.append(
      node("strong", "", event.kind.replaceAll("_", " ")),
      node("time", "", new Date(event.timestamp).toLocaleTimeString()),
    );
    content.append(heading, node("p", "", event.detail));
    if (event.receipt_sha256) {
      content.append(node("code", "", event.receipt_sha256));
    }
    if (event.blocker_codes.length) {
      content.append(node("span", "timeline-blocker", event.blocker_codes.join(" · ")));
    }
    item.append(marker, content);
    elements.auditTimeline.append(item);
  });

  const selectedReceipt = elements.replayReceiptSelect.value;
  elements.replayReceiptSelect.replaceChildren();
  history.receipts.forEach((receipt) => {
    const option = node(
      "option",
      "",
      `Receipt ${receipt.sequence} · ${receipt.workflow_state} · ${receipt.receipt_sha256.slice(0, 12)}`,
    );
    option.value = receipt.receipt_sha256;
    elements.replayReceiptSelect.append(option);
  });
  if (history.receipts.some((receipt) => receipt.receipt_sha256 === selectedReceipt)) {
    elements.replayReceiptSelect.value = selectedReceipt;
  }

  const selectedPreset = elements.replayPresetSelect.value || "CLEAN_REPLAY";
  elements.replayPresetSelect.replaceChildren();
  history.replay_presets.forEach((preset) => {
    const option = node("option", "", preset.replaceAll("_", " "));
    option.value = preset;
    elements.replayPresetSelect.append(option);
  });
  elements.replayPresetSelect.value = history.replay_presets.includes(selectedPreset)
    ? selectedPreset
    : "CLEAN_REPLAY";
  updateReplayPresetDescription();
  elements.runReplayButton.dataset.url = history.replay_url;
  elements.replayResult.hidden = true;
}

function updateReplayPresetDescription() {
  elements.replayPresetDescription.textContent =
    replayPresetDescriptions[elements.replayPresetSelect.value] || "";
}

async function runReplay() {
  const url = elements.runReplayButton.dataset.url;
  if (!url) return;
  elements.runReplayButton.disabled = true;
  elements.runReplayButton.textContent = "REPLAYING…";
  try {
    const result = await apiRequest(url, {
      method: "POST",
      body: JSON.stringify({
        receipt_sha256: elements.replayReceiptSelect.value,
        preset: elements.replayPresetSelect.value,
      }),
    });
    renderReplayResult(result);
  } catch (error) {
    elements.replayResult.className = "replay-result invalid";
    elements.replayStatus.textContent = "REPLAY FAILED";
    elements.replayStatusDetail.textContent = error.message;
    elements.replayChecks.replaceChildren();
    elements.replayResult.hidden = false;
  } finally {
    elements.runReplayButton.disabled = false;
    elements.runReplayButton.textContent = "REPLAY VERIFICATION";
  }
}

function renderReplayResult(result) {
  const verified = result.status === "VERIFIED";
  elements.replayResult.className = `replay-result ${verified ? "verified" : "drift"}`;
  elements.replayStatus.textContent = result.status;
  elements.replayStatusDetail.textContent = verified
    ? "The historical decision remains provable against every current binding."
    : result.status === "INVALID_RECEIPT"
      ? "Receipt integrity failed. This is receipt tampering, not artifact drift."
      : "The receipt remains historical; one or more current bindings no longer match.";
  elements.replayChecks.replaceChildren();
  result.checks.forEach((check) => {
    const passed = check.status === "PASS";
    const item = node("article", `replay-check ${passed ? "passed" : "failed"}`);
    const heading = node("div", "replay-check-heading");
    heading.append(
      node("span", "replay-check-icon", passed ? "✓" : "×"),
      node("strong", "", check.label),
      node("span", "replay-check-status", check.status),
    );
    const values = node("div", "replay-values");
    values.append(
      node("span", "", "Expected"),
      node("code", "", check.expected_value),
      node("span", "", "Observed"),
      node("code", "", check.observed_value),
    );
    item.append(heading, node("p", "", check.explanation), values);
    if (check.blocker_code) item.append(node("code", "replay-blocker", check.blocker_code));
    elements.replayChecks.append(item);
  });
  elements.replayResult.hidden = false;
}

async function verifyCurrentReceipt() {
  const url = elements.verifyReceiptButton.dataset.url;
  if (!url) return;
  elements.verifyReceiptButton.disabled = true;
  elements.verifyReceiptButton.textContent = "Verifying…";
  try {
    const verification = await apiRequest(url, { method: "POST" });
    const verified = verification.status === "VERIFIED";
    elements.receiptVerification.className = `receipt-verification ${
      verified ? "verified" : "tampered"
    }`;
    elements.receiptVerification.replaceChildren(
      node("strong", "", verification.status),
      node(
        "span",
        "",
        verified
          ? "Canonical hash and current artifact bindings match."
          : verification.blocker_codes.join(" · "),
      ),
    );
    elements.receiptVerification.hidden = false;
  } catch (error) {
    elements.receiptVerification.className = "receipt-verification tampered";
    elements.receiptVerification.replaceChildren(
      node("strong", "", "VERIFICATION FAILED"),
      node("span", "", error.message),
    );
    elements.receiptVerification.hidden = false;
  } finally {
    elements.verifyReceiptButton.disabled = false;
    elements.verifyReceiptButton.textContent = "Verify Receipt";
  }
}

async function generateReceiptPdf() {
  const url = elements.generateReceiptPdf.dataset.url;
  if (!url) return;
  elements.generateReceiptPdf.disabled = true;
  elements.generateReceiptPdf.textContent = "Generating PDF…";
  try {
    const generated = await apiRequest(url, { method: "POST" });
    elements.openReceiptPdf.href = generated.pdf_url;
    elements.openReceiptPdf.hidden = false;
    elements.generateReceiptPdf.textContent = "Regenerate PDF";
  } catch (error) {
    elements.generateReceiptPdf.textContent = "PDF generation failed";
  } finally {
    elements.generateReceiptPdf.disabled = false;
  }
}

function resetSendControls() {
  elements.humanConfirmation.checked = false;
  elements.humanConfirmation.disabled = false;
  elements.approveSendButton.disabled = true;
  elements.approveSendButton.textContent = "Approve & send with Foxit eSign";
  elements.sendStatus.hidden = true;
  elements.sendStatus.className = "send-status";
  elements.sendStatusLabel.textContent = "";
  elements.sendStatusDetail.textContent = "";
}

async function approveAndSend() {
  if (!state.runId || !elements.humanConfirmation.checked) return;
  elements.humanConfirmation.disabled = true;
  elements.approveSendButton.disabled = true;
  elements.approveSendButton.textContent = "Sending for signature…";
  try {
    const outcome = await apiRequest(`/api/runs/${state.runId}/approve-and-send`, {
      method: "POST",
      body: JSON.stringify({ confirmed: true }),
    });
    renderSendOutcome(outcome);
    updateAuditWorkflowState(outcome.state);
    const refreshed = await apiRequest(`/api/runs/${state.runId}`);
    renderReceipt(refreshed.result.receipt);
    renderAuditHistory(refreshed.result.audit_history);
  } catch (error) {
    elements.sendStatus.hidden = false;
    elements.sendStatus.className = "send-status failed";
    elements.sendStatusLabel.textContent = "SEND PREVENTED";
    elements.sendStatusDetail.textContent = error.message;
    elements.approveSendButton.textContent = "Send not attempted";
  }
}

function renderSendOutcome(outcome) {
  const sent = outcome.state === "SENT";
  state.approvalAvailable = false;
  elements.humanConfirmation.disabled = true;
  elements.approveSendButton.disabled = true;
  elements.approveSendButton.textContent = sent ? "Sent" : "Send failed";
  elements.sendStatus.hidden = false;
  elements.sendStatus.className = `send-status ${sent ? "sent" : "failed"}`;
  elements.sendStatusLabel.textContent = outcome.state || "SEND_FAILED";
  elements.sendStatusDetail.textContent = sent
    ? `Signature folder ID: ${outcome.folder_id}`
    : outcome.error || "Send failed. The request was not retried.";
}

function updateAuditWorkflowState(workflowState) {
  const labels = elements.auditMetadata.querySelectorAll("dt");
  const values = elements.auditMetadata.querySelectorAll("dd");
  labels.forEach((label, index) => {
    if (label.textContent === "Workflow state") values[index].textContent = workflowState;
  });
}

function renderActionPipelineDetail(action) {
  if (!action) {
    elements.actionPipelineDetail.hidden = true;
    return;
  }
  elements.actionDetailId.textContent = action.action_id;
  elements.actionDetailHash.textContent = action.action_sha256;
  elements.actionDetailRisk.textContent = action.risk;
  elements.actionDetailOutcome.textContent = action.approval && action.approval.valid
    ? "APPROVED"
    : action.authorization_outcome;
  elements.actionPipelineDetail.hidden = false;
}

async function loadActionCatalog() {
  const data = await apiRequest("/api/actions/catalog");
  elements.protectedActionsGrid.replaceChildren();
  data.capabilities
    .filter((capability) => capability.action_type !== "SIGN_DOCUMENT")
    .forEach((capability) => {
      const card = node("article", "protected-action-card");
      card.append(
        node("strong", "", capability.action_type.replaceAll("_", " ")),
        node("span", "simulation-badge", "SIMULATION ONLY — NO EXTERNAL EXECUTION"),
        node("p", "", `Adapter: ${capability.adapter}`),
      );
      elements.protectedActionsGrid.append(card);
    });
}

function renderAttackLab(data) {
  state.attackScenarios = data.scenarios;
  const passedCount = data.security_invariants.filter((item) => item.passed).length;
  elements.invariantCount.textContent = `${passedCount}/${data.security_invariants.length} enforced`;
  elements.invariantCount.className = `count-badge ${
    passedCount === data.security_invariants.length ? "secure" : "failed"
  }`;
  elements.securityInvariants.replaceChildren();
  data.security_invariants.forEach((assertion) => {
    const item = node(
      "article",
      `invariant-item ${assertion.passed ? "secure" : "failed"}`,
    );
    item.append(
      node("span", "invariant-icon", assertion.passed ? "✓" : "×"),
      node("strong", "", assertion.statement),
      node("p", "", assertion.observed_evidence),
    );
    elements.securityInvariants.append(item);
  });

  elements.attackScenarios.replaceChildren();
  data.scenarios.forEach((scenario) => {
    const card = node("article", "attack-card");
    const heading = node("div", "attack-card-heading");
    heading.append(
      node("span", "attack-label", "ATTACK ATTEMPT"),
      node("span", "attack-id", scenario.scenario_id.replaceAll("_", " ")),
    );
    const boundary = node("div", "attack-boundary");
    boundary.append(
      node("span", "", "Targeted boundary"),
      node("strong", "", scenario.targeted_boundary),
    );
    const expected = node("div", "attack-expected");
    expected.append(
      node("span", "", "Expected invariant"),
      node("p", "", scenario.expected_invariant),
    );
    card.append(
      heading,
      node("h3", "", scenario.name),
      node("p", "attack-attempt", scenario.attempted_attack),
      boundary,
      expected,
    );
    if (scenario.untrusted_evidence) {
      const untrusted = node("div", "untrusted-evidence");
      untrusted.append(
        node("strong", "", "UNTRUSTED EVIDENCE — NOT INSTRUCTIONS"),
        node("pre", "", scenario.untrusted_evidence),
      );
      card.append(untrusted);
    }
    const resultPanel = node("div", "attack-result");
    resultPanel.hidden = true;
    resultPanel.id = `attack-result-${scenario.scenario_id}`;
    const runButton = node("button", "run-attack-button", "RUN ATTACK");
    runButton.type = "button";
    runButton.addEventListener("click", () =>
      runAttack(scenario.scenario_id, runButton, resultPanel),
    );
    card.append(runButton, resultPanel);
    elements.attackScenarios.append(card);
  });
}

async function runAttack(scenarioId, button, resultPanel) {
  button.disabled = true;
  button.textContent = "RUNNING CONTROLLED ATTACK…";
  resultPanel.hidden = true;
  try {
    const result = await apiRequest(`/api/attack-lab/${scenarioId}/run`, {
      method: "POST",
    });
    const contained = result.passed_security_assertion;
    resultPanel.className = `attack-result ${contained ? "contained" : "failed"}`;
    resultPanel.replaceChildren();
    const flow = node("div", "observed-attack-flow");
    flow.append(
      node("span", "attempt", "ATTACK ATTEMPT"),
      node("b", "", "→"),
      node("span", "boundary", result.targeted_boundary),
      node("b", "", "→"),
      node("span", contained ? "blocked" : "failed", result.observed_outcome),
    );
    const codes = node("div", "attack-blocker-codes");
    result.blocker_codes.forEach((code) => codes.append(node("code", "", code)));
    resultPanel.append(
      flow,
      node(
        "strong",
        "attack-result-title",
        contained ? "SECURITY ASSERTION PASSED" : "SECURITY ASSERTION FAILED",
      ),
      node("p", "", result.observed_detail),
      codes,
      node("span", "attack-state", `Final workflow state: ${result.workflow_state}`),
    );
    resultPanel.hidden = false;
    button.textContent = "RUN AGAIN";
  } catch (error) {
    resultPanel.className = "attack-result failed";
    resultPanel.replaceChildren(
      node("strong", "attack-result-title", "LAB EXECUTION FAILED"),
      node("p", "", error.message),
    );
    resultPanel.hidden = false;
    button.textContent = "RETRY ATTACK";
  } finally {
    button.disabled = false;
  }
}

let diagnosticsCache = null;

async function loadDiagnostics() {
  diagnosticsCache = await apiRequest("/api/diagnostics");
  renderDiagnostics(diagnosticsCache);
}

function diagnosticsRows(data) {
  return [
    ["Foxit PDF", data.foxit_pdf_configured, "Connected", "Not configured"],
    ["Foxit eSign", data.foxit_esign_configured, "Connected", "Not configured"],
    ["OpenAI", null, data.semantic_provider === "openai" ? "Configured" : "Scripted", null],
    ["SerpApi", null, data.serpapi_configured ? "Configured" : data.public_evidence_provider === "scripted" ? "Scripted" : "Not configured", null],
  ];
}

// One row builder feeding every diagnostics surface (Overview, Integrations,
// Settings, the topbar chip) from the single /api/diagnostics fetch, so
// "live" can never be shown in one place and "simulated" in another.
function populateDiagnosticsGrid(target, data) {
  if (!target) return;
  target.replaceChildren();
  diagnosticsRows(data).forEach(([label, boolValue, trueLabel, falseLabel]) => {
    const displayValue = boolValue === null ? trueLabel : boolValue ? trueLabel : falseLabel;
    const dd = node("dd", "", displayValue);
    if (boolValue !== null) dd.classList.add(boolValue ? "diagnostics-yes" : "diagnostics-no");
    // Each label/value pair is wrapped so the grid lays out whole pairs, not
    // individual dt/dd siblings — otherwise a 3-column grid interleaves
    // labels and values from different rows (HTML5 permits wrapping dt/dd
    // pairs in a div inside dl for exactly this kind of grouping).
    const field = node("div", "diagnostics-field");
    field.append(node("dt", "", label), dd);
    target.append(field);
  });
}

function renderTopbarIntegrationSummary(data) {
  if (!elements.topbarIntegrationsChipLabel) return;
  const totalIntegrations = 2;
  const liveIntegrations = [data.foxit_pdf_configured, data.foxit_esign_configured].filter(
    Boolean,
  ).length;
  elements.topbarIntegrationsChipLabel.textContent = `Integrations ${liveIntegrations}/${totalIntegrations} live`;
  const chip = document.getElementById("topbar-integrations-chip");
  if (chip) chip.classList.toggle("warn", liveIntegrations < totalIntegrations);
}

function renderDiagnostics(data) {
  populateDiagnosticsGrid(elements.diagnosticsGrid, data);
  populateDiagnosticsGrid(elements.overviewDiagnosticsGrid, data);
  populateDiagnosticsGrid(elements.settingsDiagnosticsGrid, data);
  renderDocumentEngineStatusPill(data);
  renderTopbarIntegrationSummary(data);
}

function renderDocumentEngineStatusPill(data) {
  const live = Boolean(data.foxit_pdf_configured);
  elements.foxitStatusPill.className = `foxit-status-pill ${live ? "live" : "scripted"}`;
  elements.foxitStatusPill.textContent = live ? "DOCUMENT ENGINE LIVE" : "DOCUMENT ENGINE NOT CONFIGURED";
  elements.foxitStatusPill.hidden = false;
}

/* ------------------------------------------------------------------ */
/* Platform shell — client-side router and page renderers (Phase 15)  */
/* ------------------------------------------------------------------ */

let runsCache = [];

async function loadRuns() {
  const data = await apiRequest("/api/runs");
  runsCache = data.runs;
  // Keep the sidebar/topbar approval badges live regardless of which page
  // triggered this fetch — not just when Overview happens to be open.
  updateApprovalsBadges(pendingApprovals(runsCache).length);
  return runsCache;
}

function pendingApprovals(runs) {
  return runs.filter((run) => run.approval_available);
}

function updateApprovalsBadges(count) {
  [elements.sidebarApprovalsBadge, elements.topbarNotifBadge].forEach((badge) => {
    if (!badge) return;
    badge.hidden = count === 0;
    badge.textContent = String(count);
  });
}

function formatRelativeTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  const diffMin = Math.round((Date.now() - date.getTime()) / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return date.toLocaleDateString();
}

function workflowStatusPill(run) {
  if (run.status === "running") return node("span", "status-pill running", "RUNNING");
  if (run.status === "failed") return node("span", "status-pill failed", "FAILED");
  if (run.decision === "READY_FOR_HUMAN_APPROVAL") {
    if (run.send_attempted) {
      return node(
        "span",
        `status-pill ${run.send_state === "SENT" ? "sent" : "failed"}`,
        run.send_state || "SEND_FAILED",
      );
    }
    return node("span", "status-pill ready", "READY");
  }
  if (run.decision === "SIGNING_BLOCKED") return node("span", "status-pill blocked", "BLOCKED");
  return node("span", "status-pill neutral", run.status.toUpperCase());
}

function workflowRowLink(run) {
  const link = node("a", "row-link", run.preset_title);
  link.href = `/app/workflows/${run.run_id}`;
  link.dataset.route = "";
  return link;
}

function tableEmptyRow(message, colSpan) {
  const tr = node("tr");
  const td = node("td", "table-empty", message);
  td.colSpan = colSpan;
  tr.append(td);
  return tr;
}

function approvalQueueRow(run) {
  const row = node("div", "approval-queue-row");
  const titleWrap = node("div");
  const link = workflowRowLink(run);
  link.classList.add("aq-title");
  titleWrap.append(link, node("div", "aq-meta", `${run.action_type} · ${run.preset_title}`));
  const riskCell = node("div", "aq-col-risk", (run.risk || "—").toUpperCase());
  const hashCell = node("div", "aq-col-hash", formatRelativeTime(run.created_at));
  const profileCell = node("div", "aq-col-profile", run.policy_profile_name || run.policy_profile);
  const reviewLink = node("a", "approval-review-link", "Review →");
  reviewLink.href = `/app/workflows/${run.run_id}`;
  reviewLink.dataset.route = "";
  row.append(titleWrap, riskCell, hashCell, profileCell, reviewLink);
  return row;
}

function renderApprovalsInto(target, runs, emptyMessage) {
  if (!target) return;
  target.replaceChildren();
  if (target === elements.approvalsQueue) {
    const header = node("div", "approval-table-head");
    ["Workflow", "Risk", "Requested", "Policy", "Status"].forEach((label) =>
      header.append(node("span", "", label)),
    );
    target.append(header);
  }
  if (!runs.length) {
    target.append(node("p", "table-empty", emptyMessage));
    return;
  }
  runs.forEach((run) => target.append(approvalQueueRow(run)));
}

function renderOverviewMetrics(runs, diagnostics) {
  const completed = runs.filter((run) => run.status === "complete");
  const pending = pendingApprovals(runs).length;
  const blocked = completed.filter((run) => run.decision === "SIGNING_BLOCKED").length;
  const verified = completed.filter((run) => run.decision === "READY_FOR_HUMAN_APPROVAL").length;
  const totalIntegrations = 2;
  const liveIntegrations = diagnostics
    ? [diagnostics.foxit_pdf_configured, diagnostics.foxit_esign_configured].filter(Boolean).length
    : 0;
  const cards = [
    ["pending", "Pending approvals", String(pending), `${completed.length} workflow${completed.length === 1 ? "" : "s"} total`],
    ["blocked", "Blocked actions", String(blocked), "Signing blocked by deterministic policy"],
    ["verified", "Verified actions", String(verified), "Reached READY_FOR_APPROVAL or sent"],
    [
      "live",
      "Live integrations",
      diagnostics ? `${liveIntegrations}/${totalIntegrations}` : "—",
      "Document Engine + E-Signature",
    ],
  ];
  elements.overviewMetrics.replaceChildren();
  cards.forEach(([cls, label, value, detail]) => {
    const card = node("div", `metric-card ${cls}`);
    card.append(
      node("p", "metric-label", label),
      node("div", "metric-value", value),
      node("p", "metric-detail", detail),
    );
    elements.overviewMetrics.append(card);
  });
  updateApprovalsBadges(pending);
}

function renderOverviewWorkflowsTable(runs) {
  const rows = runs.slice(0, 6);
  elements.overviewWorkflowsTbody.replaceChildren();
  if (!rows.length) {
    elements.overviewWorkflowsTbody.append(
      tableEmptyRow("No workflow runs yet. Start one from Workflows.", 5),
    );
    return;
  }
  rows.forEach((run) => {
    const tr = node("tr");
    const titleTd = node("td");
    titleTd.append(workflowRowLink(run));
    const statusTd = node("td");
    statusTd.append(workflowStatusPill(run));
    const profileTd = node("td", "", run.policy_profile_name || run.policy_profile);
    const approvalTd = node(
      "td",
      "",
      run.approval_available ? "Pending" : run.send_attempted ? run.send_state || "—" : "—",
    );
    const updatedTd = node("td", "", formatRelativeTime(run.created_at));
    tr.append(titleTd, statusTd, profileTd, approvalTd, updatedTd);
    elements.overviewWorkflowsTbody.append(tr);
  });
}

function renderOverviewAuditTable(runs) {
  const rows = runs.filter((run) => run.latest_receipt_sha256).slice(0, 6);
  elements.overviewAuditTbody.replaceChildren();
  if (!rows.length) {
    elements.overviewAuditTbody.append(tableEmptyRow("No receipts issued yet.", 4));
    return;
  }
  rows.forEach((run) => {
    const tr = node("tr");
    const titleTd = node("td");
    titleTd.append(workflowRowLink(run));
    const decisionTd = node("td");
    decisionTd.append(workflowStatusPill(run));
    const hashTd = node("td");
    hashTd.append(node("code", "", `${run.latest_receipt_sha256.slice(0, 16)}…`));
    const recordedTd = node("td", "", formatRelativeTime(run.created_at));
    tr.append(titleTd, decisionTd, hashTd, recordedTd);
    elements.overviewAuditTbody.append(tr);
  });
}

function renderOverviewPolicySummary(runs) {
  const completed = runs.filter((run) => run.status === "complete");
  elements.overviewPolicySummary.replaceChildren();
  if (!completed.length) {
    elements.overviewPolicySummary.append(node("p", "table-empty", "No completed workflows yet."));
    return;
  }
  const ready = completed.filter((run) => run.decision === "READY_FOR_HUMAN_APPROVAL").length;
  const blocked = completed.filter((run) => run.decision === "SIGNING_BLOCKED").length;
  const grid = node("div", "policy-layer-grid");
  const readyCell = node("div");
  readyCell.append(node("span", "", "Ready"), node("strong", "pass", String(ready)));
  const blockedCell = node("div");
  blockedCell.append(node("span", "", "Blocked"), node("strong", "block", String(blocked)));
  const totalCell = node("div");
  totalCell.append(node("span", "", "Total"), node("strong", "", String(completed.length)));
  grid.append(readyCell, blockedCell, totalCell);
  elements.overviewPolicySummary.append(grid);
}

async function refreshOverview() {
  if (!diagnosticsCache) await loadDiagnostics();
  const runs = await loadRuns();
  renderOverviewMetrics(runs, diagnosticsCache);
  renderOverviewWorkflowsTable(runs);
  renderApprovalsInto(
    elements.overviewApprovalsPreview,
    pendingApprovals(runs).slice(0, 4),
    "No workflows are waiting on human approval.",
  );
  renderOverviewAuditTable(runs);
  renderOverviewPolicySummary(runs);
}

// Status filter values map directly onto the same states the table/status
// pill already renders — no new server-side concept, just a client-side
// view over the run list already fetched via loadRuns().
function workflowFilterStatus(run) {
  if (run.decision === "READY_FOR_HUMAN_APPROVAL") {
    if (run.send_attempted) return run.send_state === "SENT" ? "sent" : "blocked";
    return run.approval_available ? "pending" : "ready";
  }
  if (run.decision === "SIGNING_BLOCKED") return "blocked";
  return "pending";
}

function filterWorkflowRuns(runs) {
  const query = (elements.workflowsSearch?.value || "").trim().toLowerCase();
  const status = elements.workflowsStatusFilter?.value || "all";
  const action = elements.workflowsActionFilter?.value || "all";
  return runs.filter((run) => {
    const matchesQuery = !query || run.preset_title.toLowerCase().includes(query);
    const matchesStatus = status === "all" || workflowFilterStatus(run) === status;
    const matchesAction = action === "all" || run.action_type === action;
    return matchesQuery && matchesStatus && matchesAction;
  });
}

function initWorkflowsFilter() {
  [elements.workflowsSearch, elements.workflowsStatusFilter, elements.workflowsActionFilter].forEach((input) => {
    if (!input) return;
    input.addEventListener("input", () => renderWorkflowsTable(runsCache));
  });
}

function renderWorkflowsTable(allRuns) {
  const runs = filterWorkflowRuns(allRuns);
  elements.workflowsTbody.replaceChildren();
  if (!allRuns.length) {
    elements.workflowsTbody.append(
      tableEmptyRow("No workflow runs yet. Select a workflow template below to start one.", 7),
    );
    return;
  }
  if (!runs.length) {
    elements.workflowsTbody.append(tableEmptyRow("No workflows match this filter.", 7));
    return;
  }
  runs.forEach((run) => {
    const tr = node("tr");
    const titleTd = node("td");
    titleTd.append(workflowRowLink(run));
    const actionTd = node("td", "", run.action_type);
    const statusTd = node("td");
    statusTd.append(workflowStatusPill(run));
    const profileTd = node("td", "", run.policy_profile_name || run.policy_profile);
    const approvalTd = node(
      "td",
      "",
      run.approval_available ? "Pending" : run.send_attempted ? run.send_state || "—" : "—",
    );
    const integrationTd = node("td", "", run.integration);
    const updatedTd = node("td", "", formatRelativeTime(run.created_at));
    tr.append(titleTd, actionTd, statusTd, profileTd, approvalTd, integrationTd, updatedTd);
    elements.workflowsTbody.append(tr);
  });
}

async function refreshWorkflowsList() {
  const runs = await loadRuns();
  renderWorkflowsTable(runs);
}

async function refreshApprovalsQueue() {
  const runs = await loadRuns();
  renderApprovalsInto(
    elements.approvalsQueue,
    pendingApprovals(runs),
    "No workflows are waiting on human approval.",
  );
}

function renderAuditLedgerTable(runs) {
  const rows = runs.filter((run) => run.latest_receipt_sha256);
  elements.auditLedgerTbody.replaceChildren();
  if (!rows.length) {
    elements.auditLedgerTbody.append(
      tableEmptyRow("No receipts issued yet. Complete a workflow to generate one.", 6),
    );
    return;
  }
  rows.forEach((run) => {
    const tr = node("tr");
    const titleTd = node("td");
    titleTd.append(workflowRowLink(run));
    const decisionTd = node("td");
    decisionTd.append(workflowStatusPill(run));
    const stateTd = node("td", "", (run.workflow_state || "—").replaceAll("_", " "));
    const hashTd = node("td");
    hashTd.append(node("code", "", `${run.latest_receipt_sha256.slice(0, 20)}…`));
    const recordedTd = node("td", "", formatRelativeTime(run.created_at));
    const linkTd = node("td");
    const openLink = node("a", "row-link", "Open →");
    openLink.href = `/app/workflows/${run.run_id}`;
    openLink.dataset.route = "";
    linkTd.append(openLink);
    tr.append(titleTd, decisionTd, stateTd, hashTd, recordedTd, linkTd);
    elements.auditLedgerTbody.append(tr);
  });
}

async function refreshAuditLedger() {
  const runs = await loadRuns();
  renderAuditLedgerTable(runs);
}

function renderEvidenceProvenanceLegend() {
  if (!elements.evidenceProvenanceLegend) return;
  elements.evidenceProvenanceLegend.replaceChildren();
  ["AUTHORITATIVE_INTERNAL", "INTERNAL", "VERIFIED_EXTERNAL", "UNVERIFIED_EXTERNAL"].forEach((key) => {
    const info = authorityInfo(key);
    const item = node("div", "provenance-legend-item");
    const head = node("div", "evidence-item-head");
    head.append(
      node("span", "evidence-item-title", info.sourceType),
      node("span", `trust-pill ${info.tier}`, info.label),
    );
    item.append(head, node("p", "", info.why));
    elements.evidenceProvenanceLegend.append(item);
  });
}

function renderEvidenceCatalogCards() {
  if (!elements.evidenceCatalog) return;
  elements.evidenceCatalog.replaceChildren();
  if (!runsCache.length) {
    elements.evidenceCatalog.append(
      node(
        "p",
        "empty-hint",
        "No workflows yet. Upload a document to verify and its evidence will appear here.",
      ),
    );
    return;
  }
  const list = node("div", "evidence-library");
  const header = node("div", "evidence-library-head");
  ["Source", "Type", "Trust level", "Origin", "Used by", "Added"].forEach((label) =>
    header.append(node("span", "", label)),
  );
  list.append(header);
  runsCache.forEach((run) => {
    const card = node("div", "evidence-library-row");
    const source = node("div", "evidence-source-cell");
    const link = node("a", "row-link", run.preset_title || run.run_id);
    link.href = `/app/workflows/${run.run_id}`;
    link.dataset.route = "";
    source.append(link, node("small", "", run.run_id.slice(0, 8).toUpperCase()));
    card.append(
      source,
      node("span", "", "Workflow evidence"),
      node("span", "trust-pill internal", "Bound"),
      node("span", "", "Workflow upload"),
      node("span", "", "1 workflow"),
      node("span", "", formatRelativeTime(run.created_at)),
    );
    list.append(card);
  });
  elements.evidenceCatalog.append(list);
}

function refreshEvidenceCatalog() {
  renderEvidenceProvenanceLegend();
  renderEvidenceCatalogCards();
}

function refreshPoliciesCatalog() {
  if (!elements.policiesCatalog) return;
  elements.policiesCatalog.replaceChildren();
  state.policyProfiles.forEach((profile) => {
    const card = node("div", "catalog-card");
    card.append(node("h3", "", profile.name), node("p", "catalog-card-meta", profile.description));
    card.append(withCopyButton(profile.profile_hash));
    elements.policiesCatalog.append(card);
  });
}

const APP_PAGE_IDS = new Set([
  "overview",
  "workflows",
  "approvals",
  "evidence",
  "policies",
  "audit",
  "integrations",
  "security",
  "settings",
]);

// /app is the primary product prefix. Stripping it here means every page-id
// match below works identically whether the browser is on /app/workflows or
// the compatibility path /workflows.
function currentRoute() {
  const rawPath = window.location.pathname;
  const path = rawPath.startsWith("/app") ? rawPath.slice(4) : rawPath;
  const workflowDetail = path.match(/^\/workflows\/([^/]+)\/?$/);
  if (workflowDetail) return { id: "workflow-detail", runId: decodeURIComponent(workflowDetail[1]) };
  const pageId = path.replace(/^\//, "").replace(/\/$/, "");
  if (APP_PAGE_IDS.has(pageId)) return { id: pageId };
  return { id: "overview" };
}

function navigate(path, { replace = false } = {}) {
  if (window.location.pathname !== path) {
    if (replace) window.history.replaceState({}, "", path);
    else window.history.pushState({}, "", path);
  }
  renderRoute();
}

function renderRoute() {
  const route = currentRoute();
  const pageTitles = {
    overview: "Overview",
    workflows: "Workflows",
    "workflow-detail": "Workflow review",
    approvals: "Approvals",
    evidence: "Evidence",
    policies: "Policies",
    audit: "Audit",
    integrations: "Integrations",
    security: "Security",
    settings: "Settings",
  };
  if (elements.currentPageTitle) elements.currentPageTitle.textContent = pageTitles[route.id];
  document.querySelectorAll(".app-page").forEach((section) => {
    section.hidden = section.dataset.page !== route.id;
  });
  document.querySelectorAll(".app-nav-link[data-page]").forEach((link) => {
    const active =
      link.dataset.page === route.id ||
      (link.dataset.page === "workflows" && route.id === "workflow-detail");
    link.classList.toggle("active", active);
  });
  document.querySelectorAll(".app-topbar-nav a[data-topbar-page]").forEach((link) => {
    const active =
      link.dataset.topbarPage === route.id ||
      (link.dataset.topbarPage === "workflows" && route.id === "workflow-detail");
    link.classList.toggle("active", active);
  });
  window.scrollTo(0, 0);
  if (route.id === "overview") refreshOverview();
  else if (route.id === "workflows") refreshWorkflowsList();
  else if (route.id === "workflow-detail") loadWorkflowDetail(route.runId);
  else if (route.id === "approvals") refreshApprovalsQueue();
  else if (route.id === "evidence") refreshEvidenceCatalog();
  else if (route.id === "policies") refreshPoliciesCatalog();
  else if (route.id === "audit") refreshAuditLedger();
}

function initRouter() {
  window.addEventListener("popstate", renderRoute);
  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest("a[data-route]");
    if (!link) return;
    event.preventDefault();
    navigate(link.getAttribute("href"));
  });
}

function initSecurityTabs() {
  const tabs = document.querySelectorAll(".page-tab[data-security-tab]");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const targetId = tab.dataset.securityTab;
      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      document.querySelectorAll(".page-tab-panel[data-security-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.securityPanel !== targetId;
      });
    });
  });
}

// Workflow detail's Artifact/Claims & Evidence/Policy/Audit tabs — same
// pattern as Security, kept as a distinct init so switching
// tabs never needs to re-fetch or re-render the underlying run data.
function initWorkflowDetailTabs() {
  const tabs = document.querySelectorAll(".page-tab[data-detail-tab]");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const targetId = tab.dataset.detailTab;
      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      document.querySelectorAll(".page-tab-panel[data-detail-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.detailPanel !== targetId;
      });
    });
  });
}

function resetWorkflowDetailTabs() {
  const tabs = document.querySelectorAll(".page-tab[data-detail-tab]");
  tabs.forEach((tab) => {
    const active = tab.dataset.detailTab === "artifact";
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll(".page-tab-panel[data-detail-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.detailPanel !== "artifact";
  });
}

async function loadWorkflowDetail(runId) {
  state.runId = runId;
  const summary = runsCache.find((run) => run.run_id === runId);
  if (summary) {
    const title = document.getElementById("page-workflow-detail-title");
    const action = document.getElementById("workflow-detail-action");
    const created = document.getElementById("workflow-detail-created");
    const status = document.getElementById("workflow-header-status");
    const policy = document.getElementById("workflow-header-policy");
    const risk = document.getElementById("workflow-header-risk");
    if (title) title.textContent = summary.preset_title;
    if (action) action.textContent = (summary.action_type || "SIGN_DOCUMENT").replaceAll("_", " ");
    if (created) {
      created.textContent = `Created ${formatRelativeTime(summary.created_at)} · Review the verified artifact and authorization record.`;
    }
    if (status) {
      const statusView = workflowStatusPill(summary);
      status.className = statusView.className;
      status.textContent = statusView.textContent;
    }
    if (policy) policy.textContent = summary.policy_profile_name || summary.policy_profile;
    if (risk) risk.textContent = `${summary.risk || "—"} risk`;
  }
  elements.emptyState.hidden = true;
  elements.runView.hidden = false;
  elements.resultView.hidden = true;
  elements.errorPanel.hidden = true;
  elements.runReference.textContent = `RUN ${runId.slice(0, 8).toUpperCase()}`;
  elements.progressState.textContent = "Loading";
  elements.progressState.className = "progress-state";
  renderProgress(defaultProgress());
  resetWorkflowDetailTabs();
  await pollWorkflow(`/api/runs/${runId}`);
}

async function pollWorkflow(statusUrl) {
  try {
    const run = await apiRequest(statusUrl);
    renderProgress(run.progress);
    if (run.status === "complete") {
      renderResult(run.result);
      setRunning(false);
      return;
    }
    if (run.status === "failed") {
      showError(run.error || "The verification workflow failed.");
      setRunning(false);
      return;
    }
    window.setTimeout(() => pollWorkflow(statusUrl), 650);
  } catch (error) {
    showError("Lost contact with the verification workflow.");
    setRunning(false);
  }
}

async function loadSession() {
  try {
    const data = await apiRequest("/api/auth/session");
    state.session = data.user;
    applySession(data.user);
  } catch (error) {
    state.session = null;
  }
}

function applySession(user) {
  if (!user) return;
  if (elements.topbarWorkspaceLabel) elements.topbarWorkspaceLabel.textContent = user.workspace_name;
  if (elements.topbarUserName) elements.topbarUserName.textContent = user.full_name;
  if (elements.topbarUserEmail) elements.topbarUserEmail.textContent = user.email;
  if (elements.topbarUserWorkspace) elements.topbarUserWorkspace.textContent = user.workspace_name;
  if (elements.topbarUserAvatar) {
    const initial = (user.full_name || user.email || "?").trim().charAt(0).toUpperCase();
    elements.topbarUserAvatar.textContent = initial || "?";
  }
  if (elements.settingsWorkspaceName) elements.settingsWorkspaceName.textContent = user.workspace_name;
  if (elements.settingsOperatorEmail) elements.settingsOperatorEmail.textContent = user.email;
}

function initUserMenu() {
  if (!elements.topbarUserButton || !elements.topbarUserDropdown) return;
  elements.topbarUserButton.addEventListener("click", (event) => {
    event.stopPropagation();
    const expanded = elements.topbarUserButton.getAttribute("aria-expanded") === "true";
    elements.topbarUserButton.setAttribute("aria-expanded", expanded ? "false" : "true");
    elements.topbarUserDropdown.hidden = expanded;
  });
  document.addEventListener("click", () => {
    elements.topbarUserButton.setAttribute("aria-expanded", "false");
    elements.topbarUserDropdown.hidden = true;
  });
  elements.topbarUserDropdown.addEventListener("click", (event) => event.stopPropagation());
  if (elements.topbarLogoutButton) {
    elements.topbarLogoutButton.addEventListener("click", async () => {
      try {
        await apiRequest("/api/auth/logout", { method: "POST" });
      } catch (error) {
        // Ignore — redirect regardless.
      }
      window.location.href = "/login";
    });
  }
}

async function initialize() {
  initArtifactUpload();
  initUserMenu();
  addEvidenceRow();
  try {
    const [profileData, attackLabData] = await Promise.all([
      apiRequest("/api/policy-profiles"),
      apiRequest("/api/attack-lab"),
      loadActionCatalog(),
      loadDiagnostics(),
      loadRuns(),
      loadSession(),
    ]);
    state.policyProfiles = profileData.profiles;
    renderPolicyProfiles();
    renderAttackLab(attackLabData);
    initRouter();
    initSecurityTabs();
    initWorkflowDetailTabs();
    initWorkflowsFilter();
    renderRoute();
  } catch (error) {
    elements.generateButtonHint.textContent = "Unable to load workspace data. Refresh the page.";
    elements.generateButtonHint.hidden = false;
  }
}

elements.addEvidenceButton.addEventListener("click", addEvidenceRow);
elements.generateButton.addEventListener("click", startDocumentRun);
elements.policyProfileSelect.addEventListener("change", () => {
  selectPolicyProfile(elements.policyProfileSelect.value);
});
elements.humanConfirmation.addEventListener("change", () => {
  elements.approveSendButton.disabled =
    !state.approvalAvailable || !elements.humanConfirmation.checked;
});
elements.approveSendButton.addEventListener("click", approveAndSend);
elements.verifyReceiptButton.addEventListener("click", verifyCurrentReceipt);
elements.generateReceiptPdf.addEventListener("click", generateReceiptPdf);
elements.replayPresetSelect.addEventListener("change", updateReplayPresetDescription);
elements.runReplayButton.addEventListener("click", runReplay);
initialize();
