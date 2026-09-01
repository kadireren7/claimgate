"use strict";

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

async function submitJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    data = {};
  }
  if (!response.ok) {
    throw new Error(formatApiErrorDetail(data.detail, `Request failed (${response.status})`));
  }
  return data;
}

function showError(message) {
  const errorBox = document.getElementById("auth-error");
  if (!errorBox) return;
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function clearError() {
  const errorBox = document.getElementById("auth-error");
  if (errorBox) errorBox.hidden = true;
}

function setSubmitting(button, submitting, busyLabel) {
  if (!button) return;
  button.disabled = submitting;
  if (submitting) {
    button.dataset.originalHtml = button.innerHTML;
    button.innerHTML = `<span>${busyLabel}</span>`;
  } else if (button.dataset.originalHtml) {
    button.innerHTML = button.dataset.originalHtml;
  }
}

function wireLoginForm() {
  const form = document.getElementById("login-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const submit = document.getElementById("login-submit");
    setSubmitting(submit, true, "Signing in…");
    try {
      await submitJson("/api/auth/login", {
        email: document.getElementById("login-email").value.trim(),
        password: document.getElementById("login-password").value,
      });
      window.location.href = "/app";
    } catch (error) {
      showError(error.message);
      setSubmitting(submit, false);
    }
  });
}

function wireSignupForm() {
  const form = document.getElementById("signup-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const password = document.getElementById("signup-password").value;
    const confirmPassword = document.getElementById("signup-confirm-password").value;
    if (password.length < 6) {
      showError("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirmPassword) {
      showError("Passwords do not match.");
      return;
    }
    const submit = document.getElementById("signup-submit");
    setSubmitting(submit, true, "Creating account…");
    try {
      await submitJson("/api/auth/signup", {
        full_name: document.getElementById("signup-full-name").value.trim(),
        email: document.getElementById("signup-email").value.trim(),
        workspace_name: document.getElementById("signup-workspace").value.trim(),
        password,
        confirm_password: confirmPassword,
      });
      window.location.href = "/app";
    } catch (error) {
      showError(error.message);
      setSubmitting(submit, false);
    }
  });
}

function wireForgotPasswordForm() {
  const form = document.getElementById("forgot-password-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const notice = document.getElementById("auth-notice");
    const submit = document.getElementById("forgot-submit");
    setSubmitting(submit, true, "Sending…");
    try {
      const data = await submitJson("/api/auth/forgot-password", {
        email: document.getElementById("forgot-email").value.trim(),
      });
      if (notice) {
        notice.textContent = data.message;
        notice.hidden = false;
      }
      form.reset();
    } catch (error) {
      showError(error.message);
    } finally {
      setSubmitting(submit, false);
    }
  });
}

wireLoginForm();
wireSignupForm();
wireForgotPasswordForm();
