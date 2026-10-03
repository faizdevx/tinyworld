const state = {
  status: {},
  world: {},
  npcs: [],
  events: [],
  communications: [],
  beliefs: [],
  truth: [],
  interventions: [],
  metrics: {},
  snapshots: [],
  checkpoints: [],
  activeSection: 'world',
};

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = 'Request failed.';
    try {
      const json = await response.json();
      detail = json.detail || json.message || detail;
    } catch (error) {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
  return response.text();
};

function setStatusMessage(message, isError = false) {
  const summary = document.getElementById('statusSummary');
  if (!summary) return;
  summary.innerHTML = message;
  summary.style.color = isError ? '#7d1e1e' : '#172210';
}

async function loadStatus() {
  try {
    state.status = await api('/api/status');
    const status = state.status;
    document.getElementById('statusSummary').innerHTML = `
      <span>Experiment: ${status.experiment_id}</span>
      <span>Day ${status.day}</span>
      <span>Hour ${status.hour}</span>
      <span>Population ${status.population}</span>
      <span>Events ${status.event_count}</span>
      <span>Food ${status.resource_food}</span>
    `;
  } catch (error) {
    setStatusMessage(`Error: ${error.message}`, true);
  }
}

async function loadWorld() {
  state.world = await api('/api/world');
  renderWorld();
}

async function loadNpcs() {
  state.npcs = await api('/api/npcs');
  renderNpcs();
}

async function loadEvents() {
  state.events = await api('/api/events');
  renderEvents();
}

async function loadCommunications() {
  state.communications = await api('/api/communications');
  renderCommunications();
}

async function loadBeliefs() {
  state.beliefs = await api('/api/beliefs');
  renderBeliefs();
}

async function loadTruth() {
  state.truth = await api('/api/truth-vs-belief');
  renderTruth();
}

async function loadInterventions() {
  state.interventions = await api('/api/interventions');
  renderInterventions();
}

async function loadMetrics() {
  state.metrics = await api('/api/metrics');
  renderMetrics();
}

async function loadSnapshots() {
  state.snapshots = await api('/api/snapshots');
  renderSnapshots();
}

async function loadCheckpoints() {
  state.checkpoints = (await api('/api/checkpoints')).checkpoints || [];
  renderCheckpoints();
}

async function loadAll() {
  await Promise.all([
    loadStatus(),
    loadWorld(),
    loadNpcs(),
    loadEvents(),
    loadCommunications(),
    loadBeliefs(),
    loadTruth(),
    loadInterventions(),
    loadMetrics(),
    loadSnapshots(),
    loadCheckpoints(),
  ]);
}

function renderWorld() {
  const world = state.world;
  const map = document.getElementById('worldMap');
  if (!map) return;

  const terrain = [
    'grass', 'grass', 'grass', 'grass', 'grass', 'road', 'forest', 'grass', 'river', 'grass', 'field', 'settlement',
    'grass', 'forest', 'grass', 'field', 'road', 'grass', 'forest', 'grass', 'water', 'grass', 'house', 'shop',
    'grass', 'river', 'grass', 'grass', 'road', 'grass', 'grass', 'forest', 'water', 'grass', 'grass', 'road',
    'grass', 'field', 'grass', 'forest', 'grass', 'road', 'grass', 'grass', 'house', 'grass', 'forest', 'river',
    'grass', 'grass', 'road', 'grass', 'grass', 'field', 'forest', 'grass', 'road', 'grass', 'water', 'grass',
  ];

  map.innerHTML = terrain.map((tile) => `<div class="tile ${tile}">${tile === 'water' ? '≈' : tile === 'road' ? '▩' : tile === 'forest' ? '🌲' : tile === 'house' ? '🏠' : tile === 'shop' ? '🏪' : tile === 'field' ? '🌾' : tile === 'river' ? '≈' : tile === 'settlement' ? '▣' : '·'}</div>`).join('');

  const summary = document.getElementById('worldSummary');
  summary.innerHTML = `
    <div class="world-summary-grid">
      <div class="metric-box"><span class="label">Era</span><span class="value">${world.metadata?.era || 'Unknown'}</span></div>
      <div class="metric-box"><span class="label">Geography</span><span class="value">${world.metadata?.geography || 'Unknown'}</span></div>
      <div class="metric-box"><span class="label">Climate</span><span class="value">${world.metadata?.climate || 'Unknown'}</span></div>
      <div class="metric-box"><span class="label">Population</span><span class="value">${world.population || 0}</span></div>
      <div class="metric-box"><span class="label">Food</span><span class="value">${world.resources?.Food || 0}</span></div>
      <div class="metric-box"><span class="label">Entities</span><span class="value">${(world.entities || []).length}</span></div>
      <div class="metric-box"><span class="label">Factions</span><span class="value">${(world.factions || []).length}</span></div>
      <div class="metric-box"><span class="label">Interventions</span><span class="value">${(world.intervention_history || []).length}</span></div>
    </div>
  `;
}

function renderNpcs() {
  const table = document.getElementById('npcTableBody');
  if (!table) return;

  table.innerHTML = state.npcs.map((npc) => `
    <tr data-npc="${npc.name}">
      <td>${npc.name}</td>
      <td>${npc.role}</td>
      <td>${npc.location}</td>
      <td>${npc.money}</td>
      <td>${npc.current_goal || '—'}</td>
      <td>${npc.current_action || '—'}</td>
    </tr>
  `).join('');

  table.querySelectorAll('tr').forEach((row) => {
    row.addEventListener('click', async () => {
      const npc = state.npcs.find((entry) => entry.name === row.dataset.npc);
      if (!npc) return;
      const detail = document.getElementById('npcDetail');
      const personality = npc.personality || {};
      const lines = Object.entries(personality)
        .map(([key, value]) => `<div><strong>${key}</strong>: ${value}</div>`)
        .join('');
      detail.innerHTML = `
        <h3>${npc.name}</h3>
        <p><strong>Role:</strong> ${npc.role}</p>
        <p><strong>Location:</strong> ${npc.location}</p>
        <p><strong>Money:</strong> ${npc.money}</p>
        <p><strong>Goal:</strong> ${npc.current_goal || '—'}</p>
        <p><strong>Action:</strong> ${npc.current_action || '—'}</p>
        <div><strong>Personality</strong>${lines ? `: ${lines}` : '—'}</div>
        <div><strong>Knowledge</strong>: ${(npc.knowledge || []).map((item) => `${item.subject}=${item.value}`).join(', ') || '—'}</div>
        <div><strong>Beliefs</strong>: ${(npc.beliefs || []).map((item) => `${item.subject}:${item.value}`).join(', ') || '—'}</div>
      `;
    });
  });
}

function renderEvents() {
  const target = document.getElementById('eventList');
  if (!target) return;
  target.innerHTML = (state.events || []).slice(-10).reverse().map((event) => `
    <div class="event-item">
      <strong>DAY ${event.day} / ${event.hour}</strong><br>
      <span>${event.event_type}</span><br>
      ${event.actor || 'system'} → ${event.target || 'world'}<br>
      ${event.description || '—'}
    </div>
  `).join('') || '<div class="note">No events recorded.</div>';
}

function renderCommunications() {
  const target = document.getElementById('communicationList');
  if (!target) return;
  target.innerHTML = (state.communications || []).slice(-10).reverse().map((msg) => `
    <div class="communication-item">
      <strong>${msg.sender}</strong> → <strong>${msg.receiver}</strong> | ${msg.message_type}<br>
      ${msg.content}<br>
      <small>source: ${msg.source ?? 'unknown'} • origin: ${msg.origin ?? 'unknown'}</small>
    </div>
  `).join('') || '<div class="note">No communications recorded.</div>';
}

function renderBeliefs() {
  const target = document.getElementById('beliefList');
  if (!target) return;
  target.innerHTML = (state.beliefs || []).slice(-12).reverse().map((belief) => `
    <div class="belief-item">
      <strong>${belief.npc}</strong> • ${belief.subject}.${belief.predicate} = ${belief.value}<br>
      <small>confidence: ${belief.confidence} • source: ${belief.source || 'unknown'} • origin: ${belief.origin_type || 'unknown'}</small>
    </div>
  `).join('') || '<div class="note">No beliefs recorded.</div>';
}

function renderTruth() {
  const target = document.getElementById('truthTable');
  if (!target) return;
  target.innerHTML = `
    <table>
      <thead>
        <tr><th>Subject</th><th>Predicate</th><th>World</th><th>NPC</th><th>Belief</th><th>Status</th></tr>
      </thead>
      <tbody>
        ${(state.truth || []).map((item) => `
          <tr>
            <td>${item.subject}</td>
            <td>${item.predicate}</td>
            <td>${item.world_value ?? 'unknown'}</td>
            <td>${item.npc_name}</td>
            <td>${item.npc_value ?? 'unknown'}</td>
            <td>${item.status || 'unknown'}</td>
          </tr>
        `).join('') || '<tr><td colspan="6">No truth-vs-belief data.</td></tr>'}
      </tbody>
    </table>
  `;
}

function renderInterventions() {
  const target = document.getElementById('interventionList');
  if (!target) return;
  target.innerHTML = (state.interventions || []).map((item) => `
    <div class="intervention-item">
      <strong>${item.operation}</strong> • ${item.target}<br>
      ${item.result?.message || item.message || '—'}
    </div>
  `).join('') || '<div class="note">No interventions recorded.</div>';
}

function renderMetrics() {
  const target = document.getElementById('metricsList');
  if (!target) return;
  const entries = Object.entries(state.metrics || {});
  target.innerHTML = entries.map(([key, value]) => `
    <div class="metric-item">
      <strong>${key}</strong>: ${typeof value === 'object' ? JSON.stringify(value) : value}
    </div>
  `).join('') || '<div class="note">No metrics available.</div>';
}

function renderSnapshots() {
  const target = document.getElementById('snapshotList');
  if (!target) return;
  target.innerHTML = (state.snapshots || []).map((snapshot) => `
    <div class="snapshot-item">
      <strong>${snapshot.saved_at || 'snapshot'}</strong><br>
      Day ${snapshot.timestamp?.[0] ?? '?'} • Population ${snapshot.population || '?'}
    </div>
  `).join('') || '<div class="note">No snapshots captured.</div>';
}

function renderCheckpoints() {
  const target = document.getElementById('checkpointList');
  if (!target) return;
  target.innerHTML = (state.checkpoints || []).map((checkpoint) => `
    <div class="checkpoint-item">
      <strong>${checkpoint}</strong>
    </div>
  `).join('') || '<div class="note">No checkpoints saved.</div>';
}

function setActiveSection(name) {
  state.activeSection = name;
  document.querySelectorAll('.nav-btn').forEach((button) => {
    button.classList.toggle('active', button.dataset.section === name);
  });
  document.querySelectorAll('.panel[id$="Section"]').forEach((panel) => {
    panel.classList.toggle('hidden', panel.id !== `${name}Section`);
  });
}

async function applyIntervention() {
  try {
    const payload = {
      operation: document.getElementById('interventionOperation').value,
      target: document.getElementById('interventionTarget').value,
      value: document.getElementById('interventionValue').value,
      visibility: document.getElementById('interventionVisibility').value,
      properties: JSON.parse(document.getElementById('interventionProperties').value || '{}'),
    };
    const result = await api('/api/interventions', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    await Promise.all([loadStatus(), loadWorld(), loadEvents(), loadInterventions(), loadTruth()]);
    setStatusMessage(`Intervention: ${result.message || 'applied'}`);
  } catch (error) {
    setStatusMessage(`Intervention error: ${error.message}`, true);
  }
}

async function action(name) {
  try {
    if (name === 'start') {
      await api('/api/simulation/start', { method: 'POST' });
    }
    if (name === 'pause') {
      await api('/api/simulation/pause', { method: 'POST' });
    }
    if (name === 'step') {
      await api('/api/simulation/step', { method: 'POST' });
    }
    if (name === 'reset') {
      await api('/api/simulation/reset', { method: 'POST' });
    }
    if (name === 'snapshot') {
      await api('/api/snapshots', { method: 'POST' });
    }
    await loadAll();
  } catch (error) {
    setStatusMessage(`Action error: ${error.message}`, true);
  }
}

function bindControls() {
  document.querySelectorAll('[data-action]').forEach((button) => {
    button.addEventListener('click', () => action(button.dataset.action));
  });

  document.querySelectorAll('.nav-btn').forEach((button) => {
    button.addEventListener('click', () => setActiveSection(button.dataset.section));
  });

  document.getElementById('applyIntervention').addEventListener('click', applyIntervention);
  document.querySelector('[data-preset="spawn"]').addEventListener('click', () => {
    document.getElementById('interventionOperation').value = 'spawn';
    document.getElementById('interventionTarget').value = 'entity:foreign_army';
    document.getElementById('interventionValue').value = '500';
    document.getElementById('interventionVisibility').value = 'god_only';
    document.getElementById('interventionProperties').value = JSON.stringify({ location: 'Northern Road', size: 500 }, null, 2);
  });

  document.querySelector('[data-preset="food"]').addEventListener('click', () => {
    document.getElementById('interventionOperation').value = 'change_resource';
    document.getElementById('interventionTarget').value = 'resource:Food';
    document.getElementById('interventionValue').value = '-20';
    document.getElementById('interventionVisibility').value = 'god_only';
    document.getElementById('interventionProperties').value = JSON.stringify({ resource: 'Food' }, null, 2);
  });

  document.getElementById('saveCheckpoint').addEventListener('click', async () => {
    const checkpointId = document.getElementById('checkpointId').value.trim();
    await api('/api/checkpoints/save', {
      method: 'POST',
      body: JSON.stringify({ checkpoint_id: checkpointId }),
    });
    await loadCheckpoints();
  });

  document.getElementById('loadCheckpoint').addEventListener('click', async () => {
    const checkpointId = document.getElementById('checkpointId').value.trim();
    await api('/api/checkpoints/load', {
      method: 'POST',
      body: JSON.stringify({ checkpoint_id: checkpointId }),
    });
    await loadAll();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  bindControls();
  setActiveSection('world');
  loadAll();
  setInterval(() => {
    if (state.status.running) {
      loadStatus();
      loadWorld();
      loadEvents();
      loadInterventions();
      loadMetrics();
    }
  }, 1000);
});
