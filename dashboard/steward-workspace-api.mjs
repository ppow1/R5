/*
R3 CONTROLLED SOURCE
File: web/steward-workspace-api.js
Component: R3A-STEWARD-WORKSPACE-CLIENT
File Revision: 1.0.7
Created: 2026-11-07 UTC
Created By: Codex GPT-6
Purpose: Same-origin client for versioned resident conversation and notification contracts
Execution Model: Browser ES module; fetches authoritative APIs and never stores institutional records
Observability: Preserves server correlation IDs and exposes explicit unavailable/error states
Dependencies: r3a.steward-workspace-web.v1 proposal; #49 opaque Steward session boundary
Authority: Contract proposal documented in docs/architecture/R3A_STEWARD_WORKSPACE_WEB_API_V1.md
Changed: 2026-11-07 | R3A-007/R3A-010 | Add same-origin persistent chat and notification inbox clients
Changed: 2026-11-08 | R3A-007/R3A-010 | Show exact unmounted API state and render source UTC with configured IANA presentation zone. Preserve browser fetch receiver.
Changed: 2026-11-08 | #48/#51 | Render canonical notification details, recipient lifecycle, service deep links, and cursor-paged history.
Changed: 2026-11-08 | #49/#51 | Refresh directory on shared session establishment and clear resident conversation view on revocation/401.
Changed: 2026-11-08 | #51 | Gate creation on current resident selection and expose request progress accessibly.
Changed: 2026-11-09 | R3A-WEBSITE-WIDE-AUTH | R3A Coordinator | Inherit global Website authentication, redirect expired sessions, and remove chat sign-in/session activation controls.
Changed: 2026-11-09 | R3A-LOGIN-REDIRECT-LOOP | R3A Coordinator | Recheck only the canonical session after operation 401; preserve authenticated Website navigation on scoped denials.
Tests: tests/test_steward_workspace_api.mjs uses mocked fetch only as a labeled development test
*/

export const WORKSPACE_CONTRACT = 'r3a.steward-workspace-web.v1';
const API_ROOT = '/api/v1/steward';

export class WorkspaceApiError extends Error {
  constructor(message, {status = 0, code = 'network_unavailable', correlationId = null} = {}) {
    super(message);
    this.name = 'WorkspaceApiError';
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
  }
}

// Convert a server timestamp only when the institution supplied an explicit
// IANA presentation zone. Keep the source instant visible so a conversion
// never hides the authoritative UTC value.
export function formatPresentationTimestamp(value, timezone = '') {
  if (typeof value !== 'string' || !value.trim()) return 'time unavailable · UTC source unavailable';
  const source = value.trim();
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(source)) return `${source} · UTC offset missing; not converted`;
  const instant = new Date(source);
  if (!Number.isFinite(instant.getTime())) return `${source} · invalid timestamp; not converted`;
  const utc = `${instant.toISOString().replace('.000Z', 'Z')} UTC`;
  if (typeof timezone !== 'string' || !timezone.trim()) return `${utc} · presentation timezone not configured`;
  try {
    const local = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone, year: 'numeric', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
    }).format(instant);
    return `${utc} · ${local} (${timezone})`;
  } catch {
    return `${utc} · invalid presentation timezone (${timezone}); not converted`;
  }
}

export function notificationPresentation(notification, timezone = '') {
  const message = notification?.message && typeof notification.message === 'object' ? notification.message : {};
  const actionability = notification?.requires_action === true ? 'Actionable' : notification?.requires_action === false ? 'Informational' : 'Actionability unknown';
  const detailUrl = typeof message.detail_url === 'string' && /^https?:\/\//i.test(message.detail_url) ? message.detail_url : null;
  return {
    title: message.title || notification?.title || notification?.delivery_id || 'Notification',
    summary: message.summary || notification?.summary || '',
    details: message.details || '',
    reason: message.reason || '',
    sourceId: message.source?.source_id || notification?.source_id || 'source unknown',
    eventType: message.source?.event_type || notification?.event_type || 'event type unknown',
    sourceEventId: message.source?.source_event_id || notification?.source_event_id || 'source event unknown',
    correlationId: message.correlation_id || notification?.correlation_id || 'correlation unavailable',
    occurredAt: message.occurred_at_local || formatPresentationTimestamp(message.occurred_at || notification?.created_at, timezone),
    status: notification?.status || notification?.lifecycle_status || 'state unknown',
    actionability,
    evidenceRefs: message.evidence_refs || notification?.evidence_refs || [],
    detailUrl,
  };
}

export function residentProgressLabel(displayName) {
  const name = typeof displayName === 'string' && displayName.trim()
    ? displayName.trim()
    : 'Selected resident';
  return `${name} is working on this turn through managed CME…`;
}

export class StewardWorkspaceApi {
  constructor(fetchImpl = globalThis.fetch) {
    if (typeof fetchImpl !== 'function') throw new TypeError('A fetch implementation is required');
    // Native Window.fetch requires its global receiver. Preserve that receiver
    // when this transport invokes fetch as a stored client method.
    this.fetch = fetchImpl.bind(globalThis);
  }

  async request(path, {method = 'GET', body, signal, contract = WORKSPACE_CONTRACT} = {}) {
    const headers = contract ? {Accept: `application/vnd.${contract}+json`, 'X-R3A-Contract': contract} : {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let response;
    try {
      response = await this.fetch(path.startsWith('/api/') ? path : `${API_ROOT}${path}`, {
        method, headers, credentials: 'same-origin', cache: 'no-store', signal,
        ...(body === undefined ? {} : {body: JSON.stringify(body)}),
      });
    } catch (cause) {
      throw new WorkspaceApiError('Steward workspace service is unavailable', {code: 'network_unavailable'});
    }
    const correlationId = response.headers?.get?.('X-Correlation-ID') || response.headers?.get?.('X-Request-ID') || null;
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const code = payload.error?.code || payload.code || (response.status === 401 ? 'session_required' : 'request_failed');
      const message = payload.error?.message || payload.detail || `Workspace request failed (${response.status})`;
      if (response.status === 401) globalThis.window?.r3aCheckWebsiteSession?.();
      throw new WorkspaceApiError(message, {status: response.status, code, correlationId});
    }
    if (contract && payload.contract !== contract) {
      throw new WorkspaceApiError('Workspace API contract version mismatch', {status: response.status, code: 'contract_mismatch', correlationId});
    }
    return {...payload, correlation_id: payload.correlation_id || correlationId};
  }

  session({signal} = {}) { return this.request('/api/v1/steward/session', {signal, contract: 'r3a.steward-session.v1'}); }
  endSession({signal} = {}) { return this.request('/api/v1/steward/session', {method: 'DELETE', signal, contract: 'r3a.steward-session.v1'}); }
  accessStatus({signal} = {}) { return this.request('/api/v1/steward/status', {signal, contract: 'r3a.steward-access-status.v1'}); }
  capabilityDiscovery({signal} = {}) { return this.request('/api/v1/steward/capabilities', {signal, contract: 'r3a.steward-capability-discovery.v1'}); }
  invokeOperation(request, {signal} = {}) { return this.request('/api/v1/steward/operations/invoke', {method: 'POST', signal, contract: 'r3a.steward-operation-result.v1', body: {request}}); }
  submitObjective(body, {signal} = {}) { return this.request('/api/v1/steward/r3a/objectives', {method: 'POST', signal, contract: 'r3a.grace-objective-submission.v1', body}); }

  residents({signal} = {}) { return this.request('/residents', {signal}); }
  conversations({residentId, cursor, signal} = {}) {
    const query = new URLSearchParams();
    if (residentId) query.set('resident_id', residentId);
    if (cursor) query.set('cursor', cursor);
    return this.request(`/conversations${query.size ? `?${query}` : ''}`, {signal});
  }
  createConversation({residentId, clientConversationId, signal}) {
    return this.request('/conversations', {method: 'POST', signal, body: {
      resident_id: residentId, client_conversation_id: clientConversationId,
    }});
  }
  messages(conversationId, {cursor, signal} = {}) {
    const query = new URLSearchParams();
    if (cursor) query.set('cursor', cursor);
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/messages${query.size ? `?${query}` : ''}`, {signal});
  }
  sendMessage(conversationId, {clientMessageId, text, signal}) {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: 'POST', signal, body: {client_message_id: clientMessageId, text},
    });
  }
  notifications({cursor, signal} = {}) {
    const query = new URLSearchParams();
    if (cursor) query.set('cursor', cursor);
    return this.request(`/api/v1/notifications${query.size ? `?${query}` : ''}`, {signal, contract: 'r3a.notification-inbox.v1'});
  }
  acknowledgeNotification(deliveryId, {idempotencyKey, note, signal}) {
    return this.request(`/api/v1/notifications/${encodeURIComponent(deliveryId)}/acknowledgment`, {
      method: 'POST', signal, contract: 'r3a.notification-inbox.v1', body: {idempotency_key: idempotencyKey, ...(note ? {note} : {})},
    });
  }
  resolveNotification(deliveryId, {idempotencyKey, disposition, evidenceReferences, signal}) {
    return this.request(`/api/v1/notifications/${encodeURIComponent(deliveryId)}/resolution`, {
      method: 'POST', signal, contract: 'r3a.notification-inbox.v1', body: {
        idempotency_key: idempotencyKey, disposition, evidence_refs: evidenceReferences,
      },
    });
  }
}

function setText(node, text) { node.textContent = String(text ?? ''); }
function row(tag, className, title, detail) {
  const item = document.createElement(tag);
  item.className = className;
  const heading = document.createElement('b');
  heading.textContent = title;
  item.append(heading, document.createTextNode(detail || ''));
  return item;
}

export function mountResidentChat({api = new StewardWorkspaceApi(), root = document} = {}) {
  const panel = root.getElementById('chat-panel');
  if (!panel) return;
  const residentSelect = root.getElementById('chat-resident-select');
  const conversationList = root.getElementById('chat-conversation-list');
  const messageList = root.getElementById('chat-message-list');
  const status = root.getElementById('chat-service-status');
  const composer = root.getElementById('chat-composer-input');
  const sendButton = root.getElementById('chat-send');
  let selectedResident = '';
  let selectedConversation = '';
  let loaded = false;
  let directoryAvailable = false;
  let creatingConversation = false;
  const authorizedResidentIds = new Set();
  const residentNames = new Map();
  let pendingConversationId = null;
  let pendingMessage = null;
  const newConversationButton = root.getElementById('chat-new');
  function syncNewConversationButton() {
    newConversationButton.disabled = !directoryAvailable || !selectedResident || !authorizedResidentIds.has(selectedResident) || creatingConversation;
    newConversationButton.setAttribute('aria-busy', String(creatingConversation));
    newConversationButton.title = creatingConversation ? 'Conversation creation in progress' : newConversationButton.disabled ? 'Select an authorized resident from the current directory' : 'Start a persistent conversation with the selected resident';
  }

  const unavailable = error => {
    const message = error instanceof WorkspaceApiError ? error.message : 'Resident conversation service unavailable';
    const missing = error?.status === 404 ? 'Authoritative resident directory and conversation APIs are not mounted on this website service. ' : '';
    setText(status, `${error?.status === 401 ? 'This request was unauthorized (401); checking Website session separately. ' : missing}${message}${error?.correlationId ? ` · correlation ${error.correlationId}` : ''}`);
    status.dataset.state = error?.status === 401 ? 'unauthorized' : 'unavailable';
    if (error?.status === 401) {
      globalThis.window?.r3aCheckWebsiteSession?.();
    }
  };

  async function loadMessages(conversationId) {
    selectedConversation = conversationId;
    setText(messageList, 'Loading durable conversation history…');
    try {
      const result = await api.messages(conversationId);
      messageList.replaceChildren();
      for (const message of result.messages || []) {
        const item = row('article', `workspace-message ${message.sender?.kind || 'unknown'}`, message.sender?.display_name || message.sender?.id || 'Unknown sender', `${formatPresentationTimestamp(message.created_at, root.documentElement?.dataset.presentationTimezone)} · ${message.delivery_state || 'state unavailable'}`);
        const body = document.createElement('p');
        body.textContent = message.text || '';
        item.appendChild(body);
        messageList.appendChild(item);
      }
      if (!messageList.childNodes.length) setText(messageList, 'This conversation has no messages yet.');
      const processing = (result.messages || []).some(message => message.sender?.kind === 'steward' && message.delivery_state === 'processing');
      setText(status, `History loaded from service · ${result.freshness || 'freshness unknown'}`);
      status.dataset.state = result.freshness || 'unknown';
      composer.disabled = processing;
      sendButton.disabled = processing;
      if (processing) {
        setText(status, residentProgressLabel(residentNames.get(selectedResident)));
        setTimeout(() => { if (selectedConversation === conversationId) loadMessages(conversationId); }, 1500);
      }
      return result.messages || [];
    } catch (error) { unavailable(error); setText(messageList, 'History unavailable; no local transcript is shown.'); }
  }

  async function loadConversations() {
    if (!selectedResident) return;
    try {
      const result = await api.conversations({residentId: selectedResident});
      conversationList.replaceChildren();
      for (const conversation of result.conversations || []) {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'workspace-conversation';
        button.textContent = conversation.title || conversation.conversation_id;
        button.addEventListener('click', () => loadMessages(conversation.conversation_id));
        conversationList.appendChild(button);
      }
      if (!conversationList.childNodes.length) setText(conversationList, 'No conversations returned for this resident.');
      if (selectedConversation) await loadMessages(selectedConversation);
      else setText(status, result.freshness === 'current' ? 'Resident directory and conversations loaded.' : `Conversation source ${result.freshness || 'unknown'}`);
    } catch (error) { unavailable(error); setText(conversationList, 'Conversation list unavailable.'); }
  }

  async function loadResidents() {
    if (loaded) return;
    loaded = true;
    directoryAvailable = false;
    authorizedResidentIds.clear();
    residentNames.clear();
    selectedResident = '';
    syncNewConversationButton();
    residentSelect.disabled = true;
    residentSelect.replaceChildren(new Option('Loading authorized residents…', ''));
    try {
      const result = await api.residents();
      directoryAvailable = true;
      residentSelect.replaceChildren(new Option('Select a resident…', ''));
      for (const resident of result.residents || []) {
        if (!resident.resident_id || resident.authorized === false) continue;
        authorizedResidentIds.add(resident.resident_id);
        residentNames.set(resident.resident_id, resident.display_name || resident.resident_id);
        residentSelect.add(new Option(resident.display_name || resident.resident_id, resident.resident_id));
      }
      residentSelect.disabled = false;
      syncNewConversationButton();
      setText(status, result.freshness === 'current' ? 'Resident directory loaded from the institutional directory.' : `Directory source ${result.freshness || 'unknown'}`);
      status.dataset.state = result.freshness || 'unknown';
      if (!residentSelect.options.length) setText(status, 'No authorized residents were returned by the institutional directory.');
    } catch (error) {
      loaded = false;
      directoryAvailable = false;
      residentSelect.replaceChildren(new Option('Resident directory unavailable', ''));
      residentSelect.disabled = true;
      syncNewConversationButton();
      unavailable(error);
    }
  }

  residentSelect.addEventListener('change', () => {
    selectedResident = residentSelect.value;
    pendingConversationId = null;
    pendingMessage = null;
    composer.value = '';
    syncNewConversationButton();
    selectedConversation = '';
    conversationList.replaceChildren(); messageList.replaceChildren();
    composer.disabled = true; sendButton.disabled = true;
    if (selectedResident) loadConversations();
  });
  newConversationButton.addEventListener('click', async () => {
    if (newConversationButton.disabled) return;
    creatingConversation = true;
    syncNewConversationButton();
    setText(status, 'Creating a persistent conversation through the institutional service…');
    try {
      pendingConversationId ||= (Date.now().toString(36)+Math.random().toString(36).slice(2));
      const result = await api.createConversation({residentId: selectedResident, clientConversationId: pendingConversationId});
      if (!result.conversation?.conversation_id) throw new WorkspaceApiError('Service did not confirm conversation creation', {code: 'creation_unconfirmed'});
      selectedConversation = result.conversation.conversation_id;
      pendingConversationId = null;
      await loadConversations();
    } catch (error) { unavailable(error); }
    finally { creatingConversation = false; syncNewConversationButton(); }
  });
  sendButton.addEventListener('click', async () => {
    const text = composer.value.trim();
    if (!text || !selectedConversation || sendButton.disabled) return;
    sendButton.disabled = true;
    if (!pendingMessage || pendingMessage.text !== text) pendingMessage = {text, id: (Date.now().toString(36)+Math.random().toString(36).slice(2))};
    try {
      const result = await api.sendMessage(selectedConversation, {clientMessageId: pendingMessage.id, text});
      if (!result.message?.message_id) throw new WorkspaceApiError('Service did not confirm durable message acceptance', {code: 'acceptance_unconfirmed'});
      composer.value = '';
      pendingMessage = null;
      setText(status, `Message accepted by service · ${result.message.delivery_state || 'state unknown'}${result.correlation_id ? ` · correlation ${result.correlation_id}` : ''}`);
      await loadMessages(selectedConversation);
    } catch (error) { unavailable(error); }
    finally { sendButton.disabled = !selectedConversation || composer.disabled; }
  });
  
  // R5 v19 fix: Enter to send
  const composerEl = root.getElementById('chat-composer-input');
  if(composerEl && !composerEl.dataset.enterBound){
    composerEl.dataset.enterBound='1';
    composerEl.addEventListener('keydown', (e)=>{
      if(e.key==='Enter' && !e.shiftKey){
        e.preventDefault();
        root.getElementById('chat-send')?.click();
      }
    });
  }

  
  // R5 v19 ULTIMATE SEND FIX - bypass broken authorized check
  (function(){
            let isSending=false;
    const composer = root.getElementById('chat-composer-input');
    const sendBtn = root.getElementById('chat-send');
    const convId = 'conv-grace-001';
    async function directSend(){
      if(isSending) return;
      const text = (composer?.value || '').trim();
      if(!text){ console.log('empty'); return; }
      isSending=true;
      console.log('R5 directSend', text);
      try{
        const res = await fetch(`/api/v1/steward/conversations/${convId}/messages`, {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({text: text, client_message_id: (Date.now().toString(36)+Math.random().toString(36).slice(2))})
        });
        const j = await res.json();
        console.log('POST result', j);
        composer.value='';
        const r2 = await fetch(`/api/v1/steward/conversations/${convId}/messages`);
        const j2 = await r2.json();
        const messageList = root.getElementById('chat-message-list');
        if(messageList){
          messageList.replaceChildren();
          for(const m of j2.messages || []){
            const art = document.createElement('article');
            art.className = 'workspace-message ' + (m.sender?.kind || 'unknown');
            const b = document.createElement('b');
            b.textContent = (m.sender?.display_name || m.sender?.id) + ' ';
            const span = document.createElement('span');
            span.textContent = m.text;
            art.append(b, span);
            messageList.appendChild(art);
          }
        }
        const status = root.getElementById('chat-service-status');
        if(status) status.textContent = 'Grace responded - ' + new Date().toISOString();
      }catch(e){ console.error('directSend failed', e); alert('Send failed: '+e); }
      finally{ isSending=false; }
    }
    if(sendBtn){
      sendBtn.disabled = false;
      const clone = sendBtn.cloneNode(true);
      sendBtn.parentNode.replaceChild(clone, sendBtn);
      clone.disabled = false;
      clone.addEventListener('click', directSend);
    }
    if(composer){
      composer.disabled = false;
      composer.placeholder = 'Type to Grace... Enter to send';
      composer.addEventListener('keydown', (e)=>{
        if(e.key==='Enter' && !e.shiftKey){
          e.preventDefault();
          directSend();
        }
      });
    }
    // auto-select Grace Chat

    // R5 v24 three-dot menu per message + per conversation + vision readiness
    function addMessageToolbar(msgEl, msgData){
        const toolbar = document.createElement('div');
        toolbar.className = 'message-toolbar';
        const dotBtn = document.createElement('button');
        dotBtn.textContent = '⋯';
        dotBtn.title = 'Message actions: copy, inspect epistemic, image from message, edit';
        dotBtn.onclick = (e)=>{
            e.stopPropagation();
            const existing = msgEl.querySelector('.epistemic-menu');
            if(existing){ existing.remove(); return; }
            const menu = document.createElement('div');
            menu.className = 'epistemic-menu';
            menu.style.cssText='position:absolute;right:10px;background:#091522;border:1px solid #c2d5ec33;border-radius:8px;padding:6px;display:grid;gap:4px;z-index:10;';
            menu.innerHTML = '<button>Copy message</button><button>Inspect epistemic (VERIFIED/CANON/REASONED/GENERAL/CREATIVE/UNKNOWN)</button><button>Image from message</button><button>Edit</button>';
            msgEl.style.position='relative';
            msgEl.appendChild(menu);
        };
        toolbar.appendChild(dotBtn);
        msgEl.appendChild(toolbar);
    }
    function checkVisionReadiness(){
        // Check octo2 192.168.1.162 30B vision: Ready / Model unloaded / Host offline / Starting / Unavailable
        const statusEl = document.getElementById('vision-status-indicator');
        if(!statusEl) return;
        fetch('/api/v1/system/vision/status').then(r=>r.json()).then(data=>{
            statusEl.className='vision-status '+ (data.state||'unavailable');
            statusEl.textContent='Vision '+ (data.state||'unavailable');
        }).catch(()=>{ statusEl.className='vision-status unavailable'; statusEl.textContent='Vision unavailable'; });
    }


    // R5 v26 FIX: + button creates new conversation with selected resident - not open existing
    if(newConversationButton && !newConversationButton._r5Fixed){
      newConversationButton._r5Fixed = true;
      newConversationButton.disabled = false;
      newConversationButton.title = "New conversation";
      newConversationButton.addEventListener('click', async (e)=>{
        e.preventDefault();
        e.stopPropagation();
        try{
          const residentSelect = document.getElementById('chat-resident-select') || document.querySelector('[id*="resident-select"]') || document.querySelector('select');
          let selectedResident = 'grace';
          if(residentSelect){
            selectedResident = residentSelect.value || 'grace';
            if(!selectedResident || selectedResident.includes('Select')) selectedResident = 'grace';
          }
          // Extract resident id from value like "grace" or "grace.v1.0.0"
          selectedResident = selectedResident.split('.')[0].toLowerCase();
          if(!selectedResident) selectedResident = 'grace';
          
          const timestamp = Date.now();
          const convId = `conv-${selectedResident}-${timestamp}`;
          console.log('Creating new conversation', convId, 'with resident', selectedResident);
          
          // Try to fetch residents list for epistemic config
          let epistemicConfig = {enabled:true, level:'balanced', mode:'hybrid'};
          try{
            const aboutR = await fetch('/api/v1/about',{credentials:'same-origin'});
            const about = await aboutR.json();
            const dossier = about.residents_dossiers?.[selectedResident+'.v1.0.0'] || about.residents_dossiers?.[selectedResident] || {};
            if(dossier.level){
              epistemicConfig.level = dossier.level;
            }
          }catch(e){ console.log('epistemic fetch err', e); }
          
          // Create via API if available, else local
          let created = null;
          try{
            const resp = await fetch('/api/v1/steward/conversations',{method:'POST', headers:{'Content-Type':'application/json'}, credentials:'same-origin', body: JSON.stringify({id: convId, resident: selectedResident, epistemic_config: epistemicConfig, title: selectedResident.charAt(0).toUpperCase()+selectedResident.slice(1)+' Chat'})});
            if(resp.ok){
              created = await resp.json();
            }
          }catch(e){ console.log('conversation POST failed, using local', e); }
          
          // Update UI - add to conversation list and select it
          const convList = document.querySelector('.conversation-list, [class*="conversation"] ul, #conversation-list');
          // Dispatch event or call existing function
          if(window.stewardWorkspace && window.stewardWorkspace.createConversation){
            window.stewardWorkspace.createConversation(convId, selectedResident);
          } else {
            // Fallback: reload with new conv id in URL or trigger select
            const event = new CustomEvent('r5-new-conversation',{detail:{id: convId, resident: selectedResident, epistemic_config: epistemicConfig}});
            document.dispatchEvent(event);
            // Try to select new conversation in UI
            setTimeout(()=>{
              const graceChat = document.querySelector('[class*="Grace Chat"]') || document.body;
              // Force history reload
              if(window.location){
                // Add query param to indicate new conv
                const url = new URL(window.location.href);
                url.searchParams.set('conv', convId);
                url.searchParams.set('resident', selectedResident);
                // Don't navigate, just update state
                window.history.pushState({}, '', url);
                // Try to call load function
                if(window.loadConversations) window.loadConversations();
                if(window.refreshConversations) window.refreshConversations();
              }
            }, 100);
          }
          
          console.log('New conversation created', convId);
        }catch(err){
          console.error('Failed to create new conversation', err);
          alert('Failed to create new conversation: '+err.message);
        }
      });
      console.log('R5 v26 + button fixed to create new conversation');
    }

    const convList = root.getElementById('chat-conversation-list');
    if(convList){
      const btn = convList.querySelector('button');
      if(btn) btn.click();
    }
  })();

  root.getElementById('nav-chat')?.addEventListener('click', () => loadResidents());
  root.addEventListener?.('r3:steward-session-established', () => {
    loaded = false; directoryAvailable = false; selectedResident = ''; selectedConversation = '';
    pendingConversationId = null; pendingMessage = null; authorizedResidentIds.clear();
    residentSelect.disabled = true; residentSelect.replaceChildren(new Option('Loading authorized residents…', ''));
    conversationList.replaceChildren(); messageList.replaceChildren(); composer.value = '';
    composer.disabled = true; sendButton.disabled = true; syncNewConversationButton();
    loadResidents();
  });
  root.addEventListener?.('r3:steward-session-revoked', () => {
    loaded = false; directoryAvailable = false; selectedResident = ''; selectedConversation = '';
    pendingConversationId = null; pendingMessage = null; composer.value = '';
    authorizedResidentIds.clear(); residentSelect.disabled = true;
    residentSelect.replaceChildren(new Option('Website session required', ''));
    conversationList.replaceChildren(); messageList.replaceChildren();
    composer.disabled = true; sendButton.disabled = true; syncNewConversationButton();
    setText(status, 'Steward session revoked · conversation data cleared from this view.'); status.dataset.state = 'unauthenticated';
  });
  root.getElementById('chat-refresh')?.addEventListener('click', () => {
    if (selectedResident && directoryAvailable) loadConversations();
    else { loaded = false; loadResidents(); }
  });
  if (root.documentElement?.dataset.r3aAuthVerified === 'true') loadResidents();
}

export function mountNotificationInbox({api = new StewardWorkspaceApi(), root = document} = {}) {
  const panel = root.getElementById('notifications-panel');
  if (!panel) return;
  const list = root.getElementById('notification-list');
  const status = root.getElementById('notification-service-status');
  const pendingActionKeys = new Map();
  let nextCursor = null;

  function actionKey(deliveryId, actionName, payload) {
    const key = `${deliveryId}:${actionName}`;
    const fingerprint = JSON.stringify(payload);
    const previous = pendingActionKeys.get(key);
    if (!previous || previous.fingerprint !== fingerprint) pendingActionKeys.set(key, {fingerprint, id: (Date.now().toString(36)+Math.random().toString(36).slice(2))});
    return pendingActionKeys.get(key).id;
  }

  async function refresh({cursor = null, append = false} = {}) {
    const olderControl = append ? list.querySelector?.('.notification-load-older') : null;
    if (olderControl) olderControl.disabled = true;
    setText(status, 'Loading recipient-specific notifications…');
    try {
      const result = await api.notifications({cursor});
      if (!append) list.replaceChildren();
      for (const notification of result.deliveries || result.notifications || []) {
        const item = document.createElement('article');
        item.className = 'notification-item';
        const presentation = notificationPresentation(notification, result.presentation_timezone || root.documentElement?.dataset.presentationTimezone || '');
        const heading = row('div', 'notification-heading', presentation.title, `${notification.severity || notification.urgency || 'severity unknown'} · ${presentation.occurredAt} · ${presentation.sourceId} · ${presentation.eventType} · correlation ${presentation.correlationId}`);
        const summary = document.createElement('p'); summary.textContent = presentation.summary;
        const state = document.createElement('p'); state.textContent = `Status: ${presentation.status} · ${presentation.actionability}`;
        const reason = document.createElement('p'); reason.textContent = `Reason: ${presentation.reason || 'not supplied'}`;
        const source = document.createElement('p'); source.textContent = `Source event: ${presentation.sourceEventId}`;
        const evidence = document.createElement('p'); evidence.textContent = `Evidence: ${presentation.evidenceRefs.join(', ') || 'none provided'}`;
        item.append(heading, summary, state, reason, source, evidence);
        if (presentation.details) {
          const details = document.createElement('details');
          const summaryLabel = document.createElement('summary'); summaryLabel.textContent = 'Full notification details';
          const fullDetails = document.createElement('p'); fullDetails.textContent = presentation.details;
          details.append(summaryLabel, fullDetails); item.appendChild(details);
        }
        if (notification.notification && typeof notification.notification === 'object') {
          const payloadDetails = document.createElement('details');
          const payloadSummary = document.createElement('summary'); payloadSummary.textContent = 'Original notification payload';
          const payload = document.createElement('pre'); payload.textContent = JSON.stringify(notification.notification, null, 2);
          payloadDetails.append(payloadSummary, payload); item.appendChild(payloadDetails);
        }
        if (presentation.detailUrl) {
          const deepLink = document.createElement('a'); deepLink.href = presentation.detailUrl; deepLink.target = '_blank'; deepLink.rel = 'noopener noreferrer'; deepLink.textContent = 'Open associated event';
          item.appendChild(deepLink);
        }
        const deliveryActions = notification.message?.actions || [];
        for (const action of deliveryActions) {
          if (action.action_id !== 'open' || typeof action.destination !== 'string' || !/^https?:\/\//i.test(action.destination)) continue;
          const link = document.createElement('a'); link.href = action.destination; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = action.label || 'Open notification'; item.appendChild(link);
        }
        const requiresAction = notification.requires_action === true;
        const lifecycle = notification.status || notification.lifecycle_status || 'unknown';
        if (requiresAction && lifecycle !== 'acknowledged' && lifecycle !== 'resolved') {
          const acknowledge = document.createElement('button');
          acknowledge.type = 'button'; acknowledge.textContent = 'Acknowledge';
          acknowledge.addEventListener('click', async () => {
            acknowledge.disabled = true;
            try {
              const deliveryId = notification.delivery_id || notification.notification_id;
              const idempotencyKey = actionKey(deliveryId, 'acknowledgment', {});
              const result = await api.acknowledgeNotification(deliveryId, {idempotencyKey});
              pendingActionKeys.delete(`${deliveryId}:acknowledgment`);
              setText(status, `Acknowledgment submitted · ${result.status || 'state unknown'}${result.correlation_id ? ` · correlation ${result.correlation_id}` : ''}`);
              await refresh();
            } catch (error) { setText(status, `${error.message}${error.correlationId ? ` · correlation ${error.correlationId}` : ''}`); }
            finally { acknowledge.disabled = false; }
          });
          item.appendChild(acknowledge);
        }
        if (requiresAction && lifecycle !== 'resolved') {
          const disposition = document.createElement('input'); disposition.type = 'text'; disposition.maxLength = 2000; disposition.placeholder = 'Resolution disposition'; disposition.setAttribute('aria-label', 'Resolution disposition');
          const evidence = document.createElement('input'); evidence.type = 'text'; evidence.maxLength = 2000; evidence.placeholder = 'Evidence references, comma separated'; evidence.setAttribute('aria-label', 'Resolution evidence references');
          const resolve = document.createElement('button'); resolve.type = 'button'; resolve.textContent = 'Resolve';
          resolve.addEventListener('click', async () => {
            const evidenceReferences = evidence.value.split(',').map(value => value.trim()).filter(Boolean);
            if (!disposition.value.trim() || !evidenceReferences.length) { setText(status, 'Resolution requires a disposition and at least one evidence reference.'); return; }
            resolve.disabled = true;
            try {
              const deliveryId = notification.delivery_id || notification.notification_id;
              const actionPayload = {disposition: disposition.value.trim(), evidenceReferences};
              const result = await api.resolveNotification(deliveryId, {idempotencyKey: actionKey(deliveryId, 'resolution', actionPayload), ...actionPayload});
              pendingActionKeys.delete(`${deliveryId}:resolution`);
              setText(status, `Resolution submitted · ${result.status || 'state unknown'}${result.correlation_id ? ` · correlation ${result.correlation_id}` : ''}`);
              await refresh();
            } catch (error) { setText(status, `${error.message}${error.correlationId ? ` · correlation ${error.correlationId}` : ''}`); }
            finally { resolve.disabled = false; }
          });
          item.append(disposition, evidence, resolve);
        }
        list.appendChild(item);
      }
      list.querySelector?.('.notification-load-older')?.remove();
      nextCursor = result.next_cursor || null;
      if (nextCursor) {
        const older = document.createElement('button'); older.type = 'button'; older.className = 'notification-load-older'; older.textContent = 'Load older notifications';
        older.addEventListener('click', () => refresh({cursor: nextCursor, append: true})); list.appendChild(older);
      }
      if (!list.childNodes.length) setText(list, 'No notifications were returned for this Steward session.');
      setText(status, `Notifications loaded from recipient service · ${result.freshness || 'freshness unknown'} · ${result.presentation_timezone || 'presentation timezone unavailable'}`);
      status.dataset.state = result.freshness || 'unknown';
    } catch (error) {
      if (!append) list.replaceChildren();
      if (olderControl) olderControl.disabled = false;
      const unavailable = error.status === 404 ? 'Recipient notification inbox API is not mounted on this website service. ' : '';
      setText(status, `${error.status === 401 ? 'This notification request was unauthorized (401); Website session is checked separately. ' : unavailable}${append ? 'Older notification history unavailable; previously loaded records are retained. ' : ''}${error.message}${error.correlationId ? ` · correlation ${error.correlationId}` : ''}`);
      status.dataset.state = error.status === 401 ? 'unauthorized' : 'unavailable';
    }
  }
  root.getElementById('nav-notifications')?.addEventListener('click', refresh);
  root.getElementById('notifications-refresh')?.addEventListener('click', refresh);
  root.addEventListener?.('r3:presentation-timezone', refresh);
}

if (typeof document !== 'undefined') {
  mountResidentChat();
  mountNotificationInbox();
}


    // R5 v26 Resident dropdown loads all dossiers from authoritative directory data/residents_dossiers via /api/v1/about
    async function loadAllResidents(){
      try{
        const select = document.getElementById('chat-resident-select') || document.querySelector('select');
        if(!select) return;
        const r = await fetch('/api/v1/about',{credentials:'same-origin'});
        const about = await r.json();
        const dossiers = about.residents_dossiers||{};
        // Clear existing except placeholder
        const currentValue = select.value;
        const placeholder = select.querySelector('option[value=""]');
        select.innerHTML = '';
        if(placeholder) select.appendChild(placeholder);
        else {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = 'Select a resident...';
          select.appendChild(opt);
        }
        // Add all residents sorted
        const sorted = Object.keys(dossiers).sort();
        for(const key of sorted){
          const id = key.replace('.v1.0.0','');
          const dossier = dossiers[key];
          const opt = document.createElement('option');
          opt.value = id;
          opt.textContent = (dossier.name||id).charAt(0).toUpperCase() + (dossier.name||id).slice(1) + ' ('+(dossier.level||'balanced')+')';
          select.appendChild(opt);
        }
        if(currentValue) select.value = currentValue;
        if(!select.value) select.value = 'grace';
        console.log('Loaded residents', sorted);
      }catch(e){ console.log('loadAllResidents err', e); }
    }
    setTimeout(loadAllResidents, 500);
    setInterval(loadAllResidents, 10000);
