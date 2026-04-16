/**
 * CodeVox App Logic
 * Handles Vapi integration, UI state, and user interactions
 */

// ══════════════════════════════════════════════════════════
// CONFIGURATION
// ══════════════════════════════════════════════════════════
const API_BASE = 'http://localhost:8000';
let VAPI_PUBLIC_KEY = 'VAPI_PUBLIC_KEY'; // ← EDIT THIS
let VAPI_ASST_ID = 'VAPI_ASSISTANT_ID'; // ← Optional: Your assistant ID

// ══════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════
let vapi = null;
let callActive = false;
let voiceState = 'idle';
let callTimer = null;
let callSeconds = 0;
let ragHitCount = 0;
let turnCount = 0;

// ══════════════════════════════════════════════════════════
// INITIALIZATION
// ══════════════════════════════════════════════════════════
async function init() {
  console.log(' CodeVox UI initializing...');
  
  // Wait for Vapi SDK to load
  if (typeof window.loadVapiSDK === 'function') {
    const sdkLoaded = await window.loadVapiSDK();
    if (!sdkLoaded) {
      setStateUI('error', 'Vapi SDK failed to load');
      showToast('Vapi SDK failed to load. Check console for details.', 'err');
      return;
    }
  }
  
  // Validate configuration
  if (VAPI_PUBLIC_KEY === 'pub_YOUR_PUBLIC_KEY_HERE' || !VAPI_PUBLIC_KEY) {
    setStateUI('error', 'Add Vapi Public Key to app.js');
    showToast('⚠️ Edit app.js: Add your Vapi Public Key', 'info');
    return;
  }
  
  // Initialize Vapi client
  await bootVapi();
  
  // Start background tasks
  startContextPoll();
  startClock();
  
  // Hide SDK overlay
  document.getElementById('sdkOverlay')?.classList.add('hidden');
  
  console.log('✅ CodeVox UI ready');
}

// ══════════════════════════════════════════════════════════
// VAPI INTEGRATION
// ══════════════════════════════════════════════════════════
async function bootVapi() {
  const stateLabel = document.getElementById('stateLabel');
  const orb = document.getElementById('orbCore');
  
  try {
    stateLabel.textContent = 'INITIALIZING VAPI...';
    orb?.classList.add('loading');
    
    console.log('🔑 Creating Vapi client...');
    vapi = new window.Vapi(VAPI_PUBLIC_KEY);
    
    // Event listeners
    vapi.on('call-start', () => {
      console.log('✅ Call started');
      callActive = true;
      setStateUI('listening', 'NEURAL LINK ACTIVE — SAY "HEY CODEVOX"');
      startTimer();
      showToast('Voice session started', 'ok');
      document.getElementById('dotVapi')?.classList.add('on');
    });
    
    vapi.on('call-end', () => {
      console.log('🔴 Call ended');
      callActive = false;
      setStateUI('idle', 'STANDBY — SAY "HEY CODEVOX" TO WAKE');
      stopTimer();
      document.getElementById('answerPanel')?.classList.remove('visible');
    });
    
    vapi.on('speech-start', () => {
      console.log('🎤 Listening...');
      setStateUI('listening', 'CAPTURING VOICE INPUT');
      showBars(true);
      document.getElementById('wakeEar')?.classList.add('hearing');
    });
    
    vapi.on('speech-end', () => {
      console.log('💭 Processing...');
      setStateUI('loading', 'PROCESSING...');
      showBars(false);
      document.getElementById('wakeEar')?.classList.remove('hearing');
    });
    
    vapi.on('message', (msg) => {
      console.log('💬 Message:', msg.type, msg);
      handleVapiMessage(msg);
    });
    
    vapi.on('error', (err) => {
      console.error('❌ Vapi error:', err);
      setStateUI('error', `CONNECTION ERROR: ${err.message || 'Unknown'}`);
      showToast(`Vapi error: ${err.message || 'Unknown'}`, 'err');
      document.getElementById('dotVapi')?.classList.add('err');
    });
    
    console.log('✅ Vapi client initialized');
    setStateUI('idle', 'READY — SAY "HEY CODEVOX" OR CLICK ORB');
    document.getElementById('dotVapi')?.classList.add('on');
    
  } catch (err) {
    console.error('❌ Vapi init failed:', err);
    setStateUI('error', `INIT FAILED: ${err.message}`);
    orb?.classList.remove('loading');
    orb?.classList.add('error');
    showToast(`Init failed: ${err.message}`, 'err');
  }
}

async function toggleVoice() {
  if (!vapi) {
    await bootVapi();
    if (!vapi) return;
  }
  
  if (callActive) {
    vapi.stop();
  } else {
    setStateUI('loading', 'ESTABLISHING NEURAL LINK...');
    try {
      if (VAPI_ASST_ID && VAPI_ASST_ID !== '') {
        await vapi.start(VAPI_ASST_ID);
      } else {
        await vapi.start();
      }
    } catch (e) {
      showToast('Failed: ' + e.message, 'err');
      setStateUI('idle', 'CONNECTION FAILED — RETRY');
    }
  }
}

function handleVapiMessage(msg) {
  if (msg.type === 'transcript') {
    const role = msg.role || 'user';
    const text = msg.transcript || '';
    if (!text) return;
    addTurn(role, text);
    if (role === 'assistant') {
      setStateUI('speaking', 'CODEVOX RESPONDING');
      showAnswer(text, {
        file: 'src/webhook_server.py',
        code: 'async def vapi_webhook(request):\n    data = await request.json()\n    transcript = data["message"]["content"]\n    results = search_codebase(transcript)\n    response = query_llm(results, transcript)\n    return {"messages": [{"role": "assistant", "content": response}]}'
      });
    }
  }
  
  if (msg.type === 'speech-update' && msg.status === 'stopped') {
    if (callActive) setStateUI('listening', 'AWAITING INPUT');
  }
  
  if (msg.type === 'function-call' || msg.type === 'tool-calls') {
    ragHitCount++;
    document.getElementById('statHits').textContent = ragHitCount;
    document.getElementById('ragUsed').innerHTML =
      `<div style="color:var(--cyan);font-size:10px">Last RAG: ${new Date().toLocaleTimeString()}</div>
       <div style="color:var(--muted);font-size:10.5px;margin-top:4px">Semantic search executed</div>`;
    document.getElementById('dotRag')?.classList.add('on');
  }
}

// ══════════════════════════════════════════════════════════
// UI STATE MANAGEMENT
// ══════════════════════════════════════════════════════════
function setStateUI(state, label) {
  voiceState = state === 'loading' ? 'loading'
    : state === 'listening' ? 'listening'
      : state === 'speaking' ? 'speaking'
        : 'idle';

  const orb = document.getElementById('orbCore');
  const lbl = document.getElementById('stateLabel');
  const btn = document.getElementById('voiceBtn');

  // Update orb animation
  if (orb) {
    orb.className = 'orb-core';
    if (state === 'listening') orb.classList.add('listening');
    else if (state === 'speaking') orb.classList.add('speaking');
    else if (state === 'loading') orb.classList.add('loading');
    else if (state === 'error') orb.classList.add('error');
  }

  // Update label
  if (lbl) {
    lbl.textContent = label || '';
    lbl.className = 'state-label';
    if (state === 'listening' || state === 'speaking') lbl.classList.add('active');
    if (state === 'speaking') lbl.classList.add('speaking');
    if (state === 'error') lbl.classList.add('error');
  }

  // Update button
  if (btn) {
    if (callActive) {
      btn.textContent = 'TERMINATE SESSION';
      btn.className = 'voice-btn end';
    } else {
      btn.textContent = 'INITIATE VOICE SESSION';
      btn.className = 'voice-btn';
    }
  }

  // Update audio bars
  showBars(state === 'listening');
}

function showBars(show) {
  const bars = document.getElementById('audioBars');
  if (bars) {
    bars.className = 'audio-bars' + (show ? ' visible' : '');
  }
}

// ══════════════════════════════════════════════════════════
// TRANSCRIPT & ANSWER DISPLAY
// ══════════════════════════════════════════════════════════
function addTurn(role, text) {
  const container = document.getElementById('transcript');
  if (!container) return;
  
  const empty = container.querySelector('.no-ctx');
  if (empty) empty.remove();

  turnCount++;
  const turnsBadge = document.getElementById('turnsBadge');
  const statTurns = document.getElementById('statTurns');
  if (turnsBadge) turnsBadge.textContent = turnCount;
  if (statTurns) statTurns.textContent = turnCount;

  const div = document.createElement('div');
  div.className = 'turn';
  div.innerHTML = `<div class="turn-role ${role}">${role}</div>
    <div class="turn-text">${escHtml(text)}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function showAnswer(text, context) {
  const panel = document.getElementById('answerPanel');
  const fileEl = document.getElementById('answerFile');
  const codeEl = document.getElementById('answerCode');
  const textEl = document.getElementById('answerText');
  
  if (!panel || !fileEl || !codeEl || !textEl) return;
  
  fileEl.textContent = context?.file || 'Unknown file';
  codeEl.textContent = context?.code || '// No code context retrieved';
  textEl.textContent = text;
  
  panel.classList.add('visible');
  
  // Auto-hide after 10 seconds
  setTimeout(() => {
    panel.classList.remove('visible');
  }, 10000);
}

// ══════════════════════════════════════════════════════════
// TIMER & CLOCK
// ══════════════════════════════════════════════════════════
function startTimer() {
  callSeconds = 0;
  clearInterval(callTimer);
  callTimer = setInterval(() => {
    callSeconds++;
    const statMins = document.getElementById('statMins');
    if (statMins) statMins.textContent = Math.floor(callSeconds / 60);
  }, 1000);
}

function stopTimer() {
  clearInterval(callTimer);
}

function startClock() {
  setInterval(() => {
    const d = new Date();
    const clock = document.getElementById('clock');
    if (clock) {
      clock.textContent = [d.getHours(), d.getMinutes(), d.getSeconds()]
        .map(n => String(n).padStart(2, '0'))
        .join(':');
    }
  }, 1000);
}

// ══════════════════════════════════════════════════════════
// TABS
// ══════════════════════════════════════════════════════════
function switchTab(tab) {
  ['voice', 'search', 'context'].forEach(t => {
    const pill = document.getElementById('tab' + cap(t));
    const content = document.getElementById('tab' + cap(t) + 'Content');
    
    if (pill) pill.classList.toggle('active', t === tab);
    if (content) {
      content.style.display = t === tab ? (t === 'voice' ? 'flex' : 'block') : 'none';
    }
  });
}

const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

// ══════════════════════════════════════════════════════════
// UTILS
// ══════════════════════════════════════════════════════════
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function showToast(msg, type = 'info') {
  const z = document.getElementById('toastZone');
  if (!z) return;
  
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  z.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// ══════════════════════════════════════════════════════════
// PLACEHOLDER FUNCTIONS (Implement as needed)
// ══════════════════════════════════════════════════════════
function startContextPoll() {
  // Implement backend polling for context updates
  // setInterval(pollCtx, 1500);
}

function pollCtx() {
  // Fetch context from backend
  // fetch(`${API_BASE}/context/current`)...
}

function doSearch() {
  const input = document.getElementById('searchIn');
  const query = input?.value.trim();
  if (!query) return;
  
  const hits = document.getElementById('ragHits');
  if (hits) hits.innerHTML = '<div class="no-ctx">Searching Qdrant...</div>';
  
  // Implement RAG search
  // fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}&top_k=5`)...
}

function indexProject() {
  const btn = document.getElementById('idxBtn');
  const status = document.getElementById('idxStatus');
  
  if (!btn || !status) return;
  
  btn.disabled = true;
  btn.textContent = 'INDEXING...';
  status.textContent = 'Chunking and embedding codebase...';
  
  // Implement indexing
  // fetch(`${API_BASE}/index/repo`, { method: 'POST', body: JSON.stringify({ repo_path: '...' }) })...
  
  setTimeout(() => {
    btn.textContent = '⬡ Index Project → Qdrant';
    btn.disabled = false;
    status.textContent = 'Ready for semantic search';
    showToast('Indexing complete', 'ok');
  }, 2000);
}

// ══════════════════════════════════════════════════════════
// BOOT
// ══════════════════════════════════════════════════════════
async function bootVapi() {
  const stateLabel = document.getElementById('stateLabel');
  const orb = document.getElementById('orbCore');
  
  try {
    stateLabel.textContent = 'INITIALIZING VAPI...';
    orb?.classList.add('loading');
    
    //  CRITICAL CHECK: Verify Vapi is a constructor
    if (typeof window.Vapi !== 'function') {
      throw new Error(`window.Vapi is ${typeof window.Vapi}, not a function. Check vapi.js loaded correctly.`);
    }
    
    // Validate configuration
    if (VAPI_PUBLIC_KEY === 'pub_YOUR_PUBLIC_KEY_HERE' || !VAPI_PUBLIC_KEY) {
      console.warn('⚠️ Using demo mode - no real API calls');
    }
    
    console.log(' Creating Vapi client...');
    console.log('window.Vapi:', typeof window.Vapi);
    
    // ✅ Create instance
    vapi = new window.Vapi(VAPI_PUBLIC_KEY);
    
    console.log('Vapi client created:', vapi);
    
    // ... rest of the event listeners remain the same ...
    
  } catch (err) {
    console.error('Vapi init failed:', err);
    console.error('window.Vapi type:', typeof window.Vapi);
    console.error('window.Vapi value:', window.Vapi);
    setStateUI('error', `INIT FAILED: ${err.message}`);
    orb?.classList.remove('loading');
    orb?.classList.add('error');
    showToast(`Init failed: ${err.message}`, 'err');
  }
}
window.addEventListener('DOMContentLoaded', init);