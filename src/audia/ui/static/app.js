/* ─────────────────────────────────────────────────────────
   audia – app.js
   Vanilla JS – no framework dependencies.
   ───────────────────────────────────────────────────────── */

'use strict';

// ── helpers ──────────────────────────────────────────────────────────────────

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function showOverlay(msg = 'Processing…') {
  $('#overlay-msg').textContent = msg;
  $('#overlay').classList.remove('hidden');
}
function hideOverlay() {
  $('#overlay').classList.add('hidden');
}

function setStatus(el, type, msg) {
  el.className = 'status ' + type;
  el.textContent = msg;
  el.classList.remove('hidden');
}

function audioCard(af) {
  return `
    <div class="result-card">
      <div class="icon">🔊</div>
      <div class="info">
        <h3>${escHtml(af.filename || af.audio_filename)}</h3>
        <p>${af.tts_backend || ''} · ${af.tts_voice || ''} ${af.created_at ? '· ' + af.created_at.slice(0,10) : ''}</p>
      </div>
      <div class="actions">
        <a class="btn-download" href="${af.download_url}" download>⬇ Download</a>
      </div>
    </div>`;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Tab navigation ────────────────────────────────────────────────────────────

$$('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    $$('.tab-section').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    const target = btn.dataset.tab;
    $(`#tab-${target}`).classList.add('active');
    if (target === 'library') loadLibrary();
  });
});

// ── Convert tab ───────────────────────────────────────────────────────────────

const dropZone    = $('#drop-zone');
const fileInput   = $('#file-input');
const convertBtn  = $('#convert-btn');
const convertStatus = $('#convert-status');
const resultsList = $('#results-list');
let selectedFiles = [];

// Drag & drop
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave',  () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  handleFiles([...e.dataTransfer.files].filter(f => f.type === 'application/pdf'));
});

// Click to browse
$('#file-input').addEventListener('change', e => handleFiles([...e.target.files]));
// Make the label click work even though input is hidden
dropZone.addEventListener('click', e => {
  if (e.target.classList.contains('link') || e.target === dropZone || e.target.closest('.drop-icon'))
    fileInput.click();
});

function handleFiles(files) {
  selectedFiles = files;
  if (files.length) {
    const names = files.map(f => f.name).join(', ');
    dropZone.querySelector('p').innerHTML =
      `<strong>${files.length} file(s) ready:</strong> ${escHtml(names)}`;
    convertBtn.disabled = false;
  }
}

convertBtn.addEventListener('click', async () => {
  if (!selectedFiles.length) return;
  const voice = $('#voice-select').value;
  resultsList.innerHTML = '';
  convertStatus.classList.add('hidden');

  showOverlay('Extracting & converting… this may take a moment');
  convertBtn.disabled = true;

  for (const file of selectedFiles) {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('voice', voice);

    try {
      const res = await fetch('/api/convert/upload', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Unknown error');
      resultsList.insertAdjacentHTML('beforeend', audioCard({
        filename: file.name.replace('.pdf', '') + ' (audio)',
        audio_filename: data.audio_filename,
        tts_backend: data.tts_backend,
        tts_voice: data.tts_voice,
        download_url: data.download_url,
      }));
    } catch (err) {
      setStatus(convertStatus, 'error', `Error converting ${file.name}: ${err.message}`);
    }
  }

  hideOverlay();
  convertBtn.disabled = false;
  if (resultsList.innerHTML) {
    setStatus(convertStatus, 'success', `Done! ${selectedFiles.length} file(s) converted.`);
  }
});

// ── Research tab ──────────────────────────────────────────────────────────────

const searchInput       = $('#search-input');
const searchBtn         = $('#search-btn');
const searchStatus      = $('#search-status');
const searchResults     = $('#search-results');
const convertSelectedRow = $('#convert-selected-row');
const convertSelectedBtn = $('#convert-selected-btn');

searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') searchBtn.click(); });

searchBtn.addEventListener('click', async () => {
  const query = searchInput.value.trim();
  if (!query) return;

  searchStatus.classList.add('hidden');
  searchResults.innerHTML = '';
  convertSelectedRow.classList.add('hidden');
  showOverlay('Searching ArXiv…');

  try {
    const res = await fetch('/api/research/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, max_results: 10 }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Search failed');

    if (!data.results?.length) {
      setStatus(searchStatus, 'info', 'No results found. Try a different query.');
    } else {
      renderPapers(data.results);
      setStatus(searchStatus, 'success', `Found ${data.results.length} papers.`);
      convertSelectedRow.classList.remove('hidden');
    }
  } catch (err) {
    setStatus(searchStatus, 'error', err.message);
  } finally {
    hideOverlay();
  }
});

function renderPapers(papers) {
  searchResults.innerHTML = papers.map(p => `
    <div class="paper-item">
      <input type="checkbox" class="paper-check" data-id="${escHtml(p.arxiv_id)}" />
      <div class="paper-info">
        <h3>${escHtml(p.title)}</h3>
        <p class="meta">
          ${escHtml((p.authors || []).slice(0,3).join(', '))}
          ${p.authors?.length > 3 ? ' et al.' : ''}
          · ${escHtml(p.published || '')}
          · <a href="https://arxiv.org/abs/${escHtml(p.arxiv_id)}" target="_blank" rel="noopener" style="color:var(--accent)">${escHtml(p.arxiv_id)}</a>
        </p>
        <p class="abstract">${escHtml(p.abstract || '')}</p>
      </div>
    </div>`).join('');
}

convertSelectedBtn.addEventListener('click', async () => {
  const ids = $$('.paper-check:checked').map(cb => cb.dataset.id);
  if (!ids.length) {
    setStatus(searchStatus, 'info', 'Select at least one paper first.');
    return;
  }

  showOverlay(`Converting ${ids.length} paper(s)… this may take several minutes`);
  searchStatus.classList.add('hidden');

  try {
    const res = await fetch('/api/research/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ arxiv_ids: ids }),
    });
    const data = await res.json();

    const successes = data.results.filter(r => !r.error);
    const failures  = data.results.filter(r =>  r.error);

    if (successes.length) {
      setStatus(searchStatus, 'success',
        `Converted ${successes.length} paper(s). Check your Library.`);
    }
    if (failures.length) {
      setStatus(searchStatus, 'error',
        failures.map(r => `${r.arxiv_id}: ${r.error}`).join('\n'));
    }
  } catch (err) {
    setStatus(searchStatus, 'error', err.message);
  } finally {
    hideOverlay();
  }
});

// ── Library tab ───────────────────────────────────────────────────────────────

const libraryList = $('#library-list');

$('#refresh-library-btn').addEventListener('click', loadLibrary);

async function loadLibrary() {
  try {
    const res  = await fetch('/api/library/audio');
    const data = await res.json();
    const files = data.audio_files || [];
    if (!files.length) {
      libraryList.innerHTML = '<p class="hint">No audio files yet. Convert a PDF to get started.</p>';
      return;
    }
    libraryList.innerHTML = files.map(af => audioCard(af)).join('');
  } catch (err) {
    libraryList.innerHTML = `<p class="hint" style="color:var(--danger)">${err.message}</p>`;
  }
}
