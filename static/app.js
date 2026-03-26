// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let session = null;
let pdbData = {};         // {serverFilename: {pdb_filename, chains, chain_id, chain_sequence}}
let sequenceLists = {};   // {serverFilename: [{index, id, length}]}
let currentSVG = null;
let generating = false;
let nextGroupId = 1;

// Local group cards: { id, name, threshold, serverFilename, loading }
let localGroups = [];

// Local cross-alignment card (null when not added)
let localCross = null;

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttr(text) {
    return text.replace(/&/g, '&amp;').replace(/'/g, '&#39;')
               .replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function el(id) {
    return document.getElementById(id);
}

function setStatus(message, level) {
    const statusEl = el('upload-status');
    statusEl.textContent = message;
    statusEl.className = level ? 'status-' + level : '';
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

async function api(method, url, body) {
    const opts = { method };
    if (body instanceof FormData) {
        opts.body = body;
    } else if (body !== undefined) {
        opts.headers = { 'Content-Type': 'application/json' };
        opts.body = JSON.stringify(body);
    }
    const resp = await fetch(url, opts);
    if (!resp.ok) {
        let msg = `Server error (${resp.status})`;
        try {
            const err = await resp.json();
            if (err.error) msg = err.error;
        } catch (_) { /* response wasn't JSON */ }
        throw new Error(msg);
    }
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    return data;
}

async function ensureSession() {
    if (!session) {
        session = await api('POST', '/session');
    }
    return session;
}

// ---------------------------------------------------------------------------
// Group card management
// ---------------------------------------------------------------------------

function addGroup() {
    localGroups.push({
        id: nextGroupId++,
        name: 'Group ' + (localGroups.length + 1),
        threshold: 95,
        serverFilename: null,
        loading: false,
    });
    render();
}

function removeGroup(groupId) {
    const group = localGroups.find(g => g.id === groupId);
    if (group && group.serverFilename && session) {
        api('DELETE', `/session/${session.id}/fasta/${encodeURIComponent(group.serverFilename)}`).then(data => {
            session = data;
        }).catch(() => {});
        delete pdbData[group.serverFilename];
        delete sequenceLists[group.serverFilename];
    }
    localGroups = localGroups.filter(g => g.id !== groupId);
    render();
}

function addCross() {
    if (localCross) return; // only one cross-alignment allowed
    localCross = {
        id: nextGroupId++,
        name: 'Cross-alignment',
        threshold: session ? session.cross_threshold : 95,
        serverFilename: null,
        loading: false,
    };
    render();
}

function removeCross() {
    if (localCross && localCross.serverFilename && session) {
        api('DELETE', `/session/${session.id}/fasta/${encodeURIComponent(localCross.serverFilename)}`).then(data => {
            session = data;
        }).catch(() => {});
    }
    localCross = null;
    render();
}

function updateCrossName(name) {
    if (localCross) localCross.name = name;
}

function updateCrossThreshold(value) {
    if (!localCross) return;
    localCross.threshold = parseFloat(value);
    if (session) {
        clearTimeout(updateCrossThreshold._timer);
        updateCrossThreshold._timer = setTimeout(() => {
            api('PATCH', `/session/${session.id}`, {
                cross_threshold: parseFloat(value)
            }).catch(() => {});
        }, 500);
    }
}

function handleCrossTextareaBlur() {
    if (!localCross) return;
    const textarea = document.querySelector('.cross-card .fasta-textarea');
    const content = textarea ? textarea.value.trim() : '';
    if (!content) return;
    if (localCross._lastSubmittedContent === content) return;
    localCross._lastSubmittedContent = content;

    let name = localCross.name.trim();
    if (!/\.(fasta|fa|faa|fas)$/i.test(name)) name += '.fasta';

    replaceCrossFasta(async () => {
        session = await api('POST', `/session/${session.id}/fasta`, {
            name, content, role: 'cross'
        });
        return name;
    });
}

function handleCrossFastaUpload(input) {
    const file = input.files[0];
    if (!file || !localCross) return;

    const baseName = file.name.replace(/\.(fasta|fa|faa|fas)$/i, '');
    localCross.name = baseName;
    localCross._lastSubmittedContent = null;

    const textarea = document.querySelector('.cross-card .fasta-textarea');
    if (textarea) textarea.value = '';

    replaceCrossFasta(async () => {
        const form = new FormData();
        form.append('file', file);
        form.append('role', 'cross');
        session = await api('POST', `/session/${session.id}/fasta`, form);
        return file.name;
    });
}

async function replaceCrossFasta(submitFn) {
    if (!localCross || localCross.loading) return;
    localCross.loading = true;
    renderCross();

    try {
        await ensureSession();

        if (localCross.serverFilename) {
            try {
                session = await api('DELETE', `/session/${session.id}/fasta/${encodeURIComponent(localCross.serverFilename)}`);
            } catch (e) { /* ignore */ }
            localCross.serverFilename = null;
        }

        const newFilename = await submitFn();
        localCross.serverFilename = newFilename;
        if (session) session.cross_threshold = localCross.threshold;
    } catch (e) {
        setStatus('Error: ' + e.message, 'error');
    }

    localCross.loading = false;
    renderCross();
    updateGenerateButton();
}

function updateGroupName(groupId, name) {
    const group = localGroups.find(g => g.id === groupId);
    if (group) group.name = name;
    if (group && group.serverFilename && session) {
        api('PATCH', `/session/${session.id}`, {
            display_names: { [group.serverFilename]: name }
        });
    }
}

function updateGroupThreshold(groupId, value) {
    const group = localGroups.find(g => g.id === groupId);
    if (!group) return;
    group.threshold = parseFloat(value);
    if (group.serverFilename && session) {
        clearTimeout(updateGroupThreshold._timer);
        updateGroupThreshold._timer = setTimeout(() => {
            api('PATCH', `/session/${session.id}`, {
                thresholds: { [group.serverFilename]: parseFloat(value) }
            }).catch(() => {});
        }, 500);
    }
}

// ---------------------------------------------------------------------------
// FASTA submission (replaces previous data for this card)
// ---------------------------------------------------------------------------

async function replaceGroupFasta(group, submitFn) {
    if (group.loading) return;
    group.loading = true;
    updateCardDynamicParts(group);

    try {
        await ensureSession();

        // Remove old FASTA if replacing
        if (group.serverFilename) {
            try {
                session = await api('DELETE', `/session/${session.id}/fasta/${encodeURIComponent(group.serverFilename)}`);
            } catch (e) { /* ignore */ }
            delete pdbData[group.serverFilename];
            delete sequenceLists[group.serverFilename];
            group.serverFilename = null;
        }

        const newFilename = await submitFn();
        group.serverFilename = newFilename;
        await fetchSequenceList(newFilename);
    } catch (e) {
        setStatus('Error: ' + e.message, 'error');
    }

    group.loading = false;
    updateCardDynamicParts(group);
    updateGenerateButton();
}

function handleTextareaBlur(groupId) {
    const group = localGroups.find(g => g.id === groupId);
    if (!group) return;

    const textarea = document.querySelector(`[data-group-id="${groupId}"] .fasta-textarea`);
    const content = textarea ? textarea.value.trim() : '';
    if (!content) return;

    // Skip if content hasn't changed (already submitted)
    if (group._lastSubmittedContent === content) return;
    group._lastSubmittedContent = content;

    let name = group.name.trim();
    if (!/\.(fasta|fa|faa|fas)$/i.test(name)) name += '.fasta';

    replaceGroupFasta(group, async () => {
        session = await api('POST', `/session/${session.id}/fasta`, {
            name, content, role: 'group'
        });
        return name;
    });
}

function handleCardFastaUpload(input, groupId) {
    const file = input.files[0];
    if (!file) return;

    const group = localGroups.find(g => g.id === groupId);
    if (!group) return;

    // Update name to match file
    const baseName = file.name.replace(/\.(fasta|fa|faa|fas)$/i, '');
    group.name = baseName;
    group._lastSubmittedContent = null; // invalidate paste cache

    // Clear textarea
    const textarea = document.querySelector(`[data-group-id="${groupId}"] .fasta-textarea`);
    if (textarea) textarea.value = '';

    replaceGroupFasta(group, async () => {
        const form = new FormData();
        form.append('file', file);
        form.append('role', 'group');
        session = await api('POST', `/session/${session.id}/fasta`, form);
        return file.name;
    });
}

// ---------------------------------------------------------------------------
// ZIP upload — populates cards from server response
// ---------------------------------------------------------------------------

async function handleZipUpload(input) {
    const file = input.files[0];
    input.value = '';
    if (!file) return;

    setStatus('Uploading ZIP...', 'info');
    try {
        await ensureSession();
        const form = new FormData();
        form.append('file', file);
        session = await api('POST', `/session/${session.id}/fasta`, form);
        setStatus('');

        localGroups = [];
        localCross = null;
        for (const [filename, groupConfig] of Object.entries(session.groups)) {
            localGroups.push({
                id: nextGroupId++,
                name: filename.replace(/\.(fasta|fa|faa|fas)$/i, ''),
                threshold: groupConfig.threshold,
                serverFilename: filename,
                loading: false,
            });
        }

        await fetchAllSequenceLists();
        render();
    } catch (e) {
        setStatus('Error: ' + e.message, 'error');
    }
}

async function loadExample() {
    setStatus('Loading example data...', 'info');
    try {
        const resp = await fetch('/example-data');
        const blob = await resp.blob();
        const file = new File([blob], 'globins_example.zip', { type: 'application/zip' });

        await ensureSession();
        const form = new FormData();
        form.append('file', file);
        session = await api('POST', `/session/${session.id}/fasta`, form);

        const exampleDisplayNames = {
            'HBA.fasta': 'Hemoglobin \u03b1',
            'HBB.fasta': 'Hemoglobin \u03b2',
            'MB.fasta':  'Myoglobin',
        };

        localGroups = [];
        localCross = null;
        for (const [filename, groupConfig] of Object.entries(session.groups)) {
            localGroups.push({
                id: nextGroupId++,
                name: exampleDisplayNames[filename] || filename.replace(/\.(fasta|fa|faa|fas)$/i, ''),
                threshold: groupConfig.threshold,
                serverFilename: filename,
                loading: false,
            });
        }

        // Send display names to backend so the SVG uses them
        session = await api('PATCH', `/session/${session.id}`, {
            display_names: exampleDisplayNames,
        });

        // Load PDB structures for the example alignments
        setStatus('Loading PDB structures...', 'info');
        const examplePdbConfig = [
            { fasta: 'HBA.fasta', pdb_id: '1A3N', chain: 'A' },
            { fasta: 'HBB.fasta', pdb_id: '1A3N', chain: 'B' },
            { fasta: 'MB.fasta',  pdb_id: '1A6M', chain: 'A' },
        ];
        const fetchedPdbs = {};
        for (const cfg of examplePdbConfig) {
            if (!session.groups[cfg.fasta]) continue;
            if (!fetchedPdbs[cfg.pdb_id]) {
                try {
                    fetchedPdbs[cfg.pdb_id] = await api('POST', '/fetch-pdb', {
                        session_id: session.id,
                        pdb_id: cfg.pdb_id,
                    });
                } catch (e) {
                    console.warn('Could not fetch PDB', cfg.pdb_id, e);
                }
            }
            const pdbResp = fetchedPdbs[cfg.pdb_id];
            if (!pdbResp) continue;
            const chain = pdbResp.chains.find(c => c.id === cfg.chain) || pdbResp.chains[0];
            pdbData[cfg.fasta] = {
                pdb_filename: pdbResp.pdb_filename,
                chain_id: chain.id,
                chain_sequence: chain.sequence,
                chains: pdbResp.chains,
                pdb_id_value: pdbResp.pdb_filename.replace(/\.(pdb|cif)$/i, ''),
            };
        }

        await fetchAllSequenceLists();
        setStatus('');
        render();
    } catch (e) {
        setStatus('Error: ' + e.message, 'error');
    }
}

// ---------------------------------------------------------------------------
// Sequence lists (for representative dropdowns)
// ---------------------------------------------------------------------------

async function fetchSequenceList(filename) {
    if (!session) return;
    try {
        const data = await api('GET', `/session/${session.id}/fasta/${encodeURIComponent(filename)}/sequences`);
        sequenceLists[filename] = data.sequences;
    } catch (e) {
        console.warn('Failed to fetch sequences for', filename, e);
    }
}

async function fetchAllSequenceLists() {
    if (!session) return;
    const filenames = Object.keys(session.groups);
    await Promise.all(filenames.map(f => fetchSequenceList(f)));
}

// ---------------------------------------------------------------------------
// Representative & PDB actions
// ---------------------------------------------------------------------------

function updateRepresentative(serverFilename, index, isManual) {
    if (!session || !session.groups[serverFilename]) return;
    session.groups[serverFilename].representative_index = parseInt(index);
    if (isManual) {
        const group = localGroups.find(g => g.serverFilename === serverFilename);
        if (group) group.manualRep = true;
    }
    api('PATCH', `/session/${session.id}`, {
        representative_indices: { [serverFilename]: parseInt(index) }
    }).catch(() => {});
}

async function uploadPdb(input, serverFilename) {
    const file = input.files[0];
    if (!file || !session) return;

    const escaped = CSS.escape(serverFilename);
    const statusEl = el('pdb-status-' + escaped);
    statusEl.textContent = 'Uploading...';
    statusEl.className = 'pdb-item-status status-info';

    try {
        const form = new FormData();
        form.append('file', file);
        form.append('fasta_filename', serverFilename);
        const data = await api('POST', `/session/${session.id}/pdb`, form);
        handlePdbSuccess(serverFilename, data, 'Loaded');
    } catch (e) {
        statusEl.textContent = e.message || 'Upload failed';
        statusEl.className = 'pdb-item-status status-error';
    }
}

async function fetchPdb(serverFilename) {
    const escaped = CSS.escape(serverFilename);
    const input = el('pdb-id-' + escaped);
    const pdbId = input.value.trim();

    if (!pdbId) { alert('Please enter a PDB ID'); return; }
    if (!/^[A-Za-z0-9]{4}$/.test(pdbId)) {
        alert('PDB ID must be exactly 4 alphanumeric characters'); return;
    }

    const statusEl = el('pdb-status-' + escaped);
    statusEl.textContent = 'Fetching...';
    statusEl.className = 'pdb-item-status status-info';

    try {
        const data = await api('POST', '/fetch-pdb', {
            session_id: session.id,
            pdb_id: pdbId,
            fasta_filename: serverFilename
        });
        handlePdbSuccess(serverFilename, data, pdbId.toUpperCase() + ' loaded');
    } catch (e) {
        statusEl.textContent = e.message || 'Fetch failed';
        statusEl.className = 'pdb-item-status status-error';
    }
}

function handlePdbSuccess(serverFilename, data, label) {
    const escaped = CSS.escape(serverFilename);

    pdbData[serverFilename] = {
        pdb_filename: data.pdb_filename,
        chain_id: data.chains[0].id,
        chain_sequence: data.chains[0].sequence,
        chains: data.chains,
        pdb_id_value: data.pdb_filename.replace(/\.(pdb|cif)$/i, '')
    };

    const chainSelect = el('chain-' + escaped);
    chainSelect.innerHTML = data.chains.map(c =>
        `<option value="${c.id}">Chain ${c.id} (${c.num_residues} residues)</option>`
    ).join('');
    chainSelect.style.display = 'inline-block';

    const statusEl = el('pdb-status-' + escaped);
    statusEl.className = 'pdb-item-status status-success';

    if (data.pdb_match_warning && data.suggested_representative == null) {
        // No match found — PDB chain doesn't match any FASTA sequence
        statusEl.innerHTML = 'PDB sequence not found in alignment '
            + `<span class="pdb-help-icon" title="${escapeAttr(data.pdb_match_warning)}">?</span>`;
        statusEl.className = 'pdb-item-status status-error';
    } else if (data.pdb_match_warning) {
        // Partial match — above thresholds but not perfect
        const identityStr = data.pdb_identity ? ` (${data.pdb_identity} identity)` : '';
        statusEl.textContent = '\u26a0 ' + label + identityStr;
        statusEl.title = data.pdb_match_warning;
        statusEl.className = 'pdb-item-status status-warning';
    } else {
        const identityStr = data.pdb_identity ? ` (${data.pdb_identity} identity)` : '';
        statusEl.textContent = label + identityStr;
        statusEl.title = '';
    }

    if (data.suggested_representative != null) {
        applySuggestedRepresentative(serverFilename, data.suggested_representative);
    }
}

function applySuggestedRepresentative(serverFilename, index) {
    if (!session || !session.groups[serverFilename]) return;

    // Don't override if the user has manually chosen a representative
    const group = localGroups.find(g => g.serverFilename === serverFilename);
    if (group && group.manualRep) return;

    session.groups[serverFilename].representative_index = index;
    updateRepresentative(serverFilename, index);

    if (group) updateCardDynamicParts(group);
}

async function selectChain(serverFilename, chainId) {
    if (!pdbData[serverFilename]) return;
    pdbData[serverFilename].chain_id = chainId;
    const chain = pdbData[serverFilename].chains.find(c => c.id === chainId);
    if (chain) {
        pdbData[serverFilename].chain_sequence = chain.sequence;
        // Re-query suggested representative for the new chain
        if (session) {
            try {
                const data = await api('GET',
                    `/session/${session.id}/fasta/${encodeURIComponent(serverFilename)}/sequences` +
                    `?chain_sequence=${encodeURIComponent(chain.sequence)}`
                );
                const escaped = CSS.escape(serverFilename);
                const statusEl = el('pdb-status-' + escaped);
                if (data.pdb_match_warning && data.suggested_representative == null) {
                    statusEl.innerHTML = 'PDB sequence not found in alignment '
                        + `<span class="pdb-help-icon" title="${escapeAttr(data.pdb_match_warning)}">?</span>`;
                    statusEl.className = 'pdb-item-status status-error';
                } else if (data.pdb_match_warning) {
                    let base = statusEl.textContent.replace(/^\u26a0 /, '').replace(/ \([\d.]+% identity\)$/, '');
                    statusEl.textContent = '\u26a0 ' + base
                        + (data.pdb_identity ? ` (${data.pdb_identity} identity)` : '');
                    statusEl.title = data.pdb_match_warning;
                    statusEl.className = 'pdb-item-status status-warning';
                } else if (data.pdb_identity) {
                    let base = statusEl.textContent.replace(/^\u26a0 /, '').replace(/ \([\d.]+% identity\)$/, '');
                    statusEl.textContent = base + ` (${data.pdb_identity} identity)`;
                    statusEl.title = '';
                    statusEl.className = 'pdb-item-status status-success';
                }
                if (data.suggested_representative != null) {
                    applySuggestedRepresentative(serverFilename, data.suggested_representative);
                }
            } catch (_) { /* non-fatal */ }
        }
    }
}

// ---------------------------------------------------------------------------
// Generate & result
// ---------------------------------------------------------------------------

async function generate() {
    if (!session) return;

    const loadedGroups = localGroups.filter(g => g.serverFilename);
    if (loadedGroups.length === 0) {
        alert('Add at least one alignment first');
        return;
    }

    generating = true;
    render();

    try {
        const chainAssignments = {};
        for (const [file, pdb] of Object.entries(pdbData)) {
            chainAssignments[file] = {
                pdb_filename: pdb.pdb_filename,
                chain_id: pdb.chain_id
            };
        }

        const thresholds = {};
        const repIndices = {};
        for (const group of localGroups) {
            if (!group.serverFilename || !session.groups[group.serverFilename]) continue;
            thresholds[group.serverFilename] = group.threshold;
            repIndices[group.serverFilename] = session.groups[group.serverFilename].representative_index;
        }

        const patchBody = {
            thresholds,
            chain_assignments: chainAssignments,
            representative_indices: repIndices,
        };
        if (session.all_fasta && localCross) {
            patchBody.cross_threshold = localCross.threshold;
        }

        await api('PATCH', `/session/${session.id}`, patchBody);
        const data = await api('GET', `/session/${session.id}/result`);

        if (data.warnings && data.warnings.length > 0) {
            alert('Warning: ' + data.warnings.join('\n'));
        }

        currentSVG = data.svg;
        showResult(data.svg, data.alignment_info);
    } catch (e) {
        alert('Error: ' + e.message);
    }

    generating = false;
    render();
}

function regenerate() {
    currentSVG = null;
    el('result-section').style.display = 'none';
    generate();
}

function showResult(svgContent, alignmentInfo) {
    el('svg-container').innerHTML = svgContent;

    const detailsEl = el('analysis-details');
    const contentEl = el('analysis-details-content');

    if (alignmentInfo && alignmentInfo.length > 0) {
        const rows = alignmentInfo.map(info => {
            const rep = info.representative ? escapeHtml(info.representative) : '\u2014';
            const pdb = info.pdb_mapped
                ? escapeHtml(info.pdb_mapped) + ' (' + escapeHtml(info.pdb_coverage) + ')'
                : '\u2014';
            const identity = info.pdb_identity ? escapeHtml(info.pdb_identity) : '\u2014';
            return `<tr>
                <td>${escapeHtml(info.name)}</td>
                <td>${info.num_sequences}</td>
                <td>${rep}</td>
                <td>${identity}</td>
                <td>${pdb}</td>
            </tr>`;
        }).join('');

        contentEl.innerHTML =
            '<table class="analysis-table"><thead><tr>' +
            '<th>Alignment</th><th>Sequences</th><th>Representative</th><th>PDB identity</th><th>PDB coverage</th>' +
            '</tr></thead><tbody>' + rows + '</tbody></table>';
        detailsEl.style.display = 'block';
    } else {
        detailsEl.style.display = 'none';
    }

    el('result-section').style.display = 'block';
}

function downloadSVG() {
    if (!currentSVG) { alert('No SVG to download'); return; }
    const blob = new Blob([currentSVG], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'alignment_conservation.svg';
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

// ---------------------------------------------------------------------------
// Session lifecycle
// ---------------------------------------------------------------------------

function resetApp() {
    if (session && session.id) {
        fetch(`/session/${session.id}`, { method: 'DELETE' });
    }
    session = null;
    pdbData = {};
    sequenceLists = {};
    currentSVG = null;
    generating = false;
    nextGroupId = 1;
    localGroups = [];
    localCross = null;
    setStatus('');
    el('svg-container').innerHTML = '';
    el('analysis-details').style.display = 'none';
    el('analysis-details-content').innerHTML = '';
    addGroup();
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

function updateGenerateButton() {
    const loadedCount = localGroups.filter(g => g.serverFilename).length;
    const genBtn = el('generate-btn');
    genBtn.disabled = loadedCount === 0 || generating;
}

function render() {
    el('generating-section').style.display = generating ? 'block' : 'none';
    el('action-section').style.display = generating ? 'none' : '';
    updateGenerateButton();
    renderAllGroupCards();
    renderCross();
}

function renderAllGroupCards() {
    const container = el('groups-container');
    if (localGroups.length === 0) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = localGroups.map(g => buildGroupCardHtml(g)).join('');
}

function renderGroupCard(group) {
    const card = document.querySelector(`[data-group-id="${group.id}"]`);
    if (!card) return;
    const tmp = document.createElement('div');
    tmp.innerHTML = buildGroupCardHtml(group);
    card.replaceWith(tmp.firstElementChild);
}

function updateCardDynamicParts(group) {
    const card = document.querySelector(`[data-group-id="${group.id}"]`);
    if (!card) return;

    const hasData = !!group.serverFilename;
    const serverGroup = hasData && session ? session.groups[group.serverFilename] : null;
    const seqs = hasData ? (sequenceLists[group.serverFilename] || []) : [];

    // Update has-data class
    card.classList.toggle('has-data', hasData);

    // Update meta
    const meta = card.querySelector('.card-meta');
    if (meta) {
        meta.innerHTML = serverGroup
            ? `${serverGroup.num_sequences} sequences &middot; ${serverGroup.alignment_length} positions`
            : '';
    }

    // Update name input
    const nameInput = card.querySelector('.card-name-input');
    if (nameInput) nameInput.value = group.name;

    // Update representative
    const repContainer = card.querySelector('.rep-container');
    if (repContainer) {
        repContainer.innerHTML = buildRepHtml(group, serverGroup, seqs);
    }

    // Update PDB
    const pdbContainer = card.querySelector('.pdb-container');
    if (pdbContainer) {
        pdbContainer.innerHTML = buildPdbHtml(group, hasData);
    }

    // Update loading overlay
    const loadingEl = card.querySelector('.card-loading-overlay');
    if (loadingEl) {
        loadingEl.style.display = group.loading ? 'flex' : 'none';
    }
}

function buildRepHtml(group, serverGroup, seqs) {
    if (seqs.length > 0) {
        const repIndex = serverGroup && serverGroup.representative_index != null ? serverGroup.representative_index : 0;
        const repOptions = seqs.map(s =>
            `<option value="${s.index}" ${s.index === repIndex ? 'selected' : ''}>` +
            `${escapeHtml(s.id)} (${s.length} aa)</option>`
        ).join('');
        return `
            <div class="card-row">
                <label>Representative</label>
                <select class="rep-select" onchange="updateRepresentative('${escapeAttr(group.serverFilename)}', this.value, true)">
                    ${repOptions}
                </select>
            </div>`;
    }
    return `
        <div class="card-row">
            <label>Representative</label>
            <select class="rep-select" disabled>
                <option>No alignment loaded</option>
            </select>
        </div>`;
}

function buildPdbHtml(group, hasData) {
    if (hasData) {
        const pdb = pdbData[group.serverFilename];
        const escaped = CSS.escape(group.serverFilename);
        let chainHtml = '';
        if (pdb && pdb.chains) {
            const chainOptions = pdb.chains.map(c =>
                `<option value="${c.id}" ${c.id === pdb.chain_id ? 'selected' : ''}>` +
                `Chain ${c.id} (${c.num_residues} residues)</option>`
            ).join('');
            chainHtml = `<select class="chain-select" id="chain-${escaped}"
                          onchange="selectChain('${escapeAttr(group.serverFilename)}', this.value)">${chainOptions}</select>`;
        } else {
            chainHtml = `<select class="chain-select" id="chain-${escaped}" style="display:none"></select>`;
        }
        const pdbStatus = pdb
            ? `<span class="pdb-item-status status-success" id="pdb-status-${escaped}">Loaded</span>`
            : `<span class="pdb-item-status" id="pdb-status-${escaped}"></span>`;

        return `
            <div class="card-row">
                <label>PDB structure (optional)</label>
                <div class="pdb-controls">
                    <input type="file" accept=".pdb,.cif"
                           onchange="uploadPdb(this, '${escapeAttr(group.serverFilename)}')">
                    <span class="pdb-or-divider">or</span>
                    <input type="text" class="pdb-id-input" maxlength="4"
                           placeholder="PDB ID" id="pdb-id-${escaped}"
                           value="${pdb && pdb.pdb_id_value ? escapeAttr(pdb.pdb_id_value) : ''}">
                    <button type="button" class="pdb-fetch-btn"
                            onclick="fetchPdb('${escapeAttr(group.serverFilename)}')">Fetch</button>
                    ${chainHtml}
                    ${pdbStatus}
                </div>
            </div>`;
    }
    return `
        <div class="card-row">
            <label>PDB structure (optional)</label>
            <div class="pdb-controls disabled">
                <input type="file" accept=".pdb,.cif" disabled>
                <span class="pdb-or-divider">or</span>
                <input type="text" class="pdb-id-input" maxlength="4" placeholder="PDB ID" disabled>
                <button type="button" class="pdb-fetch-btn" disabled>Fetch</button>
            </div>
        </div>`;
}

function buildGroupCardHtml(group) {
    const hasData = !!group.serverFilename;
    const serverGroup = hasData && session ? session.groups[group.serverFilename] : null;
    const seqs = hasData ? (sequenceLists[group.serverFilename] || []) : [];

    const metaHtml = serverGroup
        ? `<span class="card-meta">${serverGroup.num_sequences} sequences &middot; ${serverGroup.alignment_length} positions</span>`
        : '<span class="card-meta"></span>';

    const fileInputId = `fasta-file-${group.id}`;

    return `
    <div class="group-card ${hasData ? 'has-data' : ''}" data-group-id="${group.id}">
        <div class="card-header">
            <input type="text" class="card-name-input" value="${escapeHtml(group.name)}"
                   onchange="updateGroupName(${group.id}, this.value)"
                   placeholder="Group name">
            ${metaHtml}
            <div class="card-header-right">
                <div class="threshold-inline">
                    <label>Threshold</label>
                    <input type="number" value="${group.threshold}" min="0" max="100" step="1"
                           onchange="updateGroupThreshold(${group.id}, this.value)">
                    <span class="unit">%</span>
                </div>
                <button type="button" class="card-remove" onclick="removeGroup(${group.id})">&times;</button>
            </div>
        </div>
        <div class="card-body">
            <div class="card-col card-col-left">
                <div class="card-fasta-input">
                    <label class="fasta-input-label">Paste the alignment FASTA</label>
                    <textarea class="fasta-textarea" rows="5"
                              placeholder=">seq1&#10;MVLSPADKTN-VKAAWGKVGA&#10;>seq2&#10;MVLSGEDKSN-IKAA--KVGA&#10;..."
                              onblur="handleTextareaBlur(${group.id})"></textarea>
                    <div class="fasta-input-actions">
                        <span class="fasta-or">or upload FASTA file</span>
                        <input type="file" id="${fileInputId}" accept=".fasta,.fa,.faa,.fas" class="fasta-file-input"
                               onchange="handleCardFastaUpload(this, ${group.id})">
                    </div>
                    <div class="card-loading-overlay" style="display:${group.loading ? 'flex' : 'none'}">
                        <div class="spinner small-spinner"></div> Loading...
                    </div>
                </div>
            </div>
            <div class="card-col card-col-right">
                <div class="rep-container">${buildRepHtml(group, serverGroup, seqs)}</div>
                <div class="pdb-container">${buildPdbHtml(group, hasData)}</div>
            </div>
        </div>
    </div>`;
}

function renderCross() {
    const container = el('cross-container');

    // If there's a server-side cross but no local card, create one
    if (session && session.all_fasta && !localCross) {
        localCross = {
            id: nextGroupId++,
            name: session.all_fasta.replace(/\.(fasta|fa|faa|fas)$/i, ''),
            threshold: session.cross_threshold,
            serverFilename: session.all_fasta,
            loading: false,
        };
    }

    if (!localCross) {
        container.innerHTML = '';
        updateCrossButton();
        return;
    }

    const hasData = !!localCross.serverFilename;

    container.innerHTML = `
    <div class="group-card cross-card ${hasData ? 'has-data' : ''}" data-cross-id="${localCross.id}">
        <div class="card-header">
            <input type="text" class="card-name-input" value="${escapeHtml(localCross.name)}"
                   onchange="updateCrossName(this.value)"
                   placeholder="Cross-alignment name">
            <span class="card-badge">cross-alignment</span>
            <span class="card-meta"></span>
            <div class="card-header-right">
                <div class="threshold-inline">
                    <label>Threshold</label>
                    <input type="number" value="${localCross.threshold}" min="0" max="100" step="1"
                           onchange="updateCrossThreshold(this.value)">
                    <span class="unit">%</span>
                </div>
                <button type="button" class="card-remove" onclick="removeCross()">&times;</button>
            </div>
        </div>
        <div class="card-body">
            <div class="card-col">
                <div class="card-fasta-input">
                    <label class="fasta-input-label">Paste the cross-alignment FASTA</label>
                    <textarea class="fasta-textarea" rows="5"
                              placeholder=">seq1&#10;MVLSPADKTN-VKAAWGKVGA&#10;>seq2&#10;MVLSGEDKSN-IKAA--KVGA&#10;..."
                              onblur="handleCrossTextareaBlur()"></textarea>
                    <div class="fasta-input-actions">
                        <span class="fasta-or">or upload FASTA file</span>
                        <input type="file" accept=".fasta,.fa,.faa,.fas" class="fasta-file-input"
                               onchange="handleCrossFastaUpload(this)">
                    </div>
                    <div class="card-loading-overlay" style="display:${localCross.loading ? 'flex' : 'none'}">
                        <div class="spinner small-spinner"></div> Loading...
                    </div>
                </div>
            </div>
        </div>
    </div>`;
    updateCrossButton();
}

function updateCrossButton() {
    const btn = document.querySelector('.add-cross-btn');
    if (btn) btn.disabled = !!localCross;
}

// ---------------------------------------------------------------------------
// Init — start with one empty card
// ---------------------------------------------------------------------------

addGroup();
