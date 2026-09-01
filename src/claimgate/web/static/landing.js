"use strict";

async function fetchDiagnostics() {
  const response = await fetch("/api/diagnostics", { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

function integrationRow(name, capability, connected) {
  const row = document.createElement("article");
  row.className = "landing-integration-card";
  const title = document.createElement("h3");
  title.textContent = name;
  const description = document.createElement("p");
  description.textContent = capability;
  const status = document.createElement("span");
  status.className = `status-pill ${connected ? "ready" : "neutral"}`;
  status.textContent = connected ? "CONNECTED" : "NOT CONFIGURED";
  row.append(title, description, status);
  return row;
}

async function populateIntegrations() {
  const target = document.getElementById("landing-integrations");
  if (!target) return;
  try {
    const diagnostics = await fetchDiagnostics();
    target.replaceChildren(
      integrationRow("Foxit PDF", "Generate and re-read final documents", diagnostics.foxit_pdf_configured),
      integrationRow("Foxit eSign", "Human-triggered signature execution", diagnostics.foxit_esign_configured),
    );
  } catch (error) {
    target.replaceChildren(
      integrationRow("Foxit PDF", "Generate and re-read final documents", false),
      integrationRow("Foxit eSign", "Human-triggered signature execution", false),
    );
  }
}

populateIntegrations();
