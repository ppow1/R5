/*
R5 CONTROLLED SOURCE
File: web/steward-login.js
Component: R5-AP3-STEWARD-ACCESS
File Revision: 5.0.0
Created: 2026-11-09T18:10:00Z
Created By: R5 Coordinator
Purpose: Submit native R5 credentials over same-origin HTTPS and return locally to Riverview.
Execution Model: Fetch uses same-origin cookies, no-store, and the native AP3 session endpoint.
Observability: Renders only generic state; never serializes credentials or challenge values to storage/logs.
Dependencies: r3a.steward-login-request.v1; POST /api/v1/steward/session.
Authority: AP3/R5-010; Steward-approved R5 authentication independence.
Changed: 2026-11-09T18:10:00Z | AP3/R5-010 | R5 Coordinator | Implement native login, enrollment, recovery, and safe local return.
Changed: 2026-11-09T19:57:00Z | AP3/R5-010-LIVE-LOGIN | R5 Coordinator | Resume an existing native session when the base Website routes through login.
Supersedes: None.
Contracts: r3a.steward-login-request.v1; r3a.steward-session.v1.
Tests: tests/test_r3a_website.py; browser acceptance pending trusted HTTPS and Steward enrollment.
History/Predecessor: New interface for Remote Access commit 16b6230d5b48bb9bd1872f687f43678faeb296d7.
*/
const form = document.getElementById('login-form');
const intent = document.getElementById('intent');
const password = document.getElementById('password');
const challenge = document.getElementById('challenge');
const challengeField = document.getElementById('challenge-field');
const submit = document.getElementById('submit');
const status = document.getElementById('status');

async function resumeExistingSession() {
  try {
    const response = await fetch('/api/v1/steward/session', {
      credentials: 'same-origin', cache: 'no-store', headers: {Accept: 'application/json'}
    });
    if (!response.ok) return;
    const body = await response.json();
    if (body.contract && body.contract.includes('steward-session') && body.state === 'authenticated' || body.status === 'active') {
      window.location.replace('/steward');
    }
  } catch { /* A new login remains available when no current session can be read. */ }
}

resumeExistingSession();

function syncIntent() {
  const governed = intent.value !== 'login';
  challengeField.hidden = !governed;
  challenge.required = governed;
  password.minLength = governed ? 14 : 1;
  password.autocomplete = governed ? 'new-password' : 'current-password';
  submit.textContent = intent.value === 'login' ? 'Sign in to R5'
    : intent.value === 'enroll' ? 'Complete R5 enrollment' : 'Recover R5 credentials';
  status.textContent = '';
}

intent.addEventListener('change', syncIntent);
syncIntent();

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (window.location.protocol !== 'https:' && !window.location.hostname.match(/^192\.168\.|localhost|127\.0\.0\.1/)) {
    status.textContent = 'Sign in requires browser-trusted HTTPS on the private R5 network.';
    return;
  }
  status.textContent = 'Contacting R5 authentication…';
  submit.disabled = true;
  const payload = {intent: intent.value,
    login_name: document.getElementById('login-name').value,
    password: password.value};
  if (intent.value !== 'login') payload.challenge = challenge.value;
  try {
    const response = await fetch('/api/v1/steward/session', {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
    });
    let body = {};
    try { body = await response.json(); } catch { /* Keep a generic error below. */ }
    if (!response.ok || body.contract !== 'r3a.steward-session.v1'
        || body.state !== 'authenticated') {
      status.textContent = response.status === 401
        ? 'Sign in could not be verified. Check the entered values or contact the authorized operator.'
        : response.status === 403 ? 'This request origin is not authorized.'
        : 'R5 authentication is temporarily unavailable.';
      return;
    }
    status.textContent = 'Signed in. Returning to Riverview…';
    window.location.replace('/steward');
  } catch {
    status.textContent = 'R5 authentication is temporarily unavailable.';
  } finally {
    password.value = '';
    challenge.value = '';
    submit.disabled = false;
  }
});
