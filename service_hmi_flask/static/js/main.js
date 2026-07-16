// ═══════════════════════════════════════════════════════════════
// SMART MICROGRID DIGITAL TWIN — main.js v3.8
// ═══════════════════════════════════════════════════════════════

// ── Tab switching ──────────────────────────────────────────────
function switchTab(name, btn) {
    document.querySelectorAll('.tab-panel').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    const panel = document.getElementById('tab-' + name);
    panel.classList.add('active');
    if (btn) btn.classList.add('active');
    if (typeof lucide !== 'undefined') lucide.createIcons();
    if (name === 'overview') setTimeout(redrawPowerFlowSVG, 60);
}

// ── Chart global defaults ──────────────────────────────────────
Chart.defaults.color       = '#b2bec3';
Chart.defaults.borderColor = '#dfe6e9';
Chart.defaults.font.family = "'Inter', 'Segoe UI', sans-serif";
Chart.defaults.font.size   = 10;

// ── Chart factory helpers ──────────────────────────────────────
function lineChart(id, color, label, yMin, yMax) {
    return new Chart(document.getElementById(id).getContext('2d'), {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label,
                data: [],
                borderColor: color,
                backgroundColor: color + '1a',
                borderWidth: 1.5,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: { display: false },
                zoom: {
                    pan: { enabled: true, mode: 'x' },
                    zoom: {
                        wheel: { enabled: true },
                        pinch: { enabled: true },
                        mode: 'x',
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    ticks: { maxTicksLimit: 6, font: { size: 9 } },
                    grid: { color: '#f0f3f5' }
                },
                y: {
                    beginAtZero: true,
                    ...(yMin !== undefined ? { min: yMin } : {}),
                    ...(yMax !== undefined ? { max: yMax } : {}),
                    ticks: { font: { size: 9 } },
                    grid: { color: '#f0f3f5' }
                }
            }
        }
    });
}

function multiLineChart(id, datasets) {
    return new Chart(document.getElementById(id).getContext('2d'), {
        type: 'line',
        data: {
            labels: [],
            datasets: datasets.map(d => ({
                label: d.label,
                data: [],
                borderColor: d.color,
                backgroundColor: 'transparent',
                borderWidth: 1.5,
                fill: false,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 4,
                spanGaps: false,
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: {
                    display: true,
                    labels: { usePointStyle: true, font: { size: 10 }, padding: 14 }
                },
                zoom: {
                    pan: { enabled: true, mode: 'x' },
                    zoom: {
                        wheel: { enabled: true },
                        pinch: { enabled: true },
                        mode: 'x',
                    }
                }
            },
            scales: {
                x: {
                    ticks: { maxTicksLimit: 6, font: { size: 9 } },
                    grid: { color: '#f0f3f5' }
                },
                y: {
                    beginAtZero: true,
                    ticks: { font: { size: 9 } },
                    grid: { color: '#f0f3f5' }
                }
            }
        }
    });
}

// ── Initialise all charts ──────────────────────────────────────
const charts = {
    ovSoc:   lineChart('ov-chart-soc',  '#00b894', 'SoC %', 0, 100),
    ovPv:    lineChart('ov-chart-pv',   '#00d8d6', 'PAC Inverter W'),
    ovLoad:  lineChart('ov-chart-load', '#0984e3', 'Load W'),
    pvTotal: multiLineChart('pv-chart-total', [
        { label: 'PV Aktual',          color: '#00d8d6' },
        { label: 'Prediksi PV (PIML)', color: '#e17055' },
    ]),
    pvA: lineChart('pv-chart-a', '#fdcb6e', 'String A W'),
    pvB: lineChart('pv-chart-b', '#e17055', 'String B W'),
    bessSoc:      lineChart('bess-chart-soc',      '#00b894', 'SoC %', 0, 100),
    bessInverter: lineChart('bess-chart-inverter',  '#00d8d6', 'P_Inverter W'),
    bessDcPower:  lineChart('bess-chart-dc',        '#00b894', 'P_BESS DC W'),
    loadTrend:   lineChart('load-chart', '#0984e3', 'Load W'),
    loadCompare: multiLineChart('load-chart-compare', [
        { label: 'Beban Aktual',   color: '#0984e3' },
        { label: 'Estimasi Model', color: '#e17055' },
    ]),
};

// Donut chart — Tab 5
const chartMix = new Chart(document.getElementById('ek-chart-mix').getContext('2d'), {
    type: 'doughnut',
    data: {
        labels: ['PLN', 'EBT (PV+BESS)'],
        datasets: [{
            data: [1, 1],
            backgroundColor: ['#6c5ce7', '#00b894'],
            borderWidth: 0,
            hoverOffset: 6,
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '74%',
        plugins: {
            legend: {
                position: 'bottom',
                labels: { usePointStyle: true, font: { size: 11 }, padding: 16 }
            }
        }
    }
});

// ── Utilities ──────────────────────────────────────────────────
const IDR = v => 'Rp ' + (v || 0).toLocaleString('id-ID', { minimumFractionDigits: 2 });
const W   = v => (v || 0).toFixed(1) + ' W';
const VA  = v => (v || 0).toFixed(1) + ' VA';
const PCT = v => (v || 0).toFixed(1) + '%';
const HZ  = v => (v || 0).toFixed(2) + ' Hz';

const MAX_POINTS = 60;
const timeLabel  = () => new Date().toLocaleTimeString('id-ID', {
    hour: '2-digit', minute: '2-digit', hour12: false
});

function pushChart(chart, label, ...values) {
    if (chart.data.labels.length >= MAX_POINTS) {
        chart.data.labels.shift();
        chart.data.datasets.forEach(ds => ds.data.shift());
    }
    chart.data.labels.push(label);
    chart.data.datasets.forEach((ds, i) => ds.data.push(values[i] ?? null));
    chart.update('none');
}

function setStatusPill(id, freq) {
    const el = document.getElementById(id);
    if (!el) return;
    if (freq > 5) {
        el.className = el.className.replace(/badge-\w+/g, '') + ' badge-online';
        el.textContent = '● ONLINE';
    } else {
        el.className = el.className.replace(/badge-\w+/g, '') + ' badge-offline';
        el.textContent = '● OFFLINE';
    }
}

function setPvStatusPill(id, freq, pvPower) {
    const el = document.getElementById(id);
    if (!el) return;
    const freqValid  = freq > 45 && freq < 55;
    const powerValid = pvPower > 10;
    if (freqValid && powerValid) {
        el.className = el.className.replace(/badge-\w+/g, '') + ' badge-online';
        el.textContent = '● ONLINE';
    } else {
        el.className = el.className.replace(/badge-\w+/g, '') + ' badge-offline';
        el.textContent = '● OFFLINE';
    }
}

function setNodeStatus(nodeId, freq) {
    const el = document.getElementById(nodeId);
    if (!el) return;
    el.classList.toggle('online',  freq > 5);
    el.classList.toggle('offline', freq <= 5);
}

// ── DSS colour map ─────────────────────────────────────────────
const DSS_MAP = {
    'CHARGING':     { color: '#00b894', bg: 'rgba(0,184,148,0.08)',   border: '#00b894' },
    'OPTIMUM':      { color: '#0984e3', bg: 'rgba(9,132,227,0.08)',   border: '#0984e3' },
    'DISCHARGING':  { color: '#fdcb6e', bg: 'rgba(253,203,110,0.08)', border: '#fdcb6e' },
    'GRID SUPPORT': { color: '#6c5ce7', bg: 'rgba(108,92,231,0.08)',  border: '#6c5ce7' },
    'GRID ONLY':    { color: '#d63031', bg: 'rgba(214,48,49,0.08)',   border: '#d63031' },
};

const RULE_MAP = {
    'CHARGING':     'rule-charge',
    'OPTIMUM':      'rule-full',
    'DISCHARGING':  'rule-discharge',
    'GRID SUPPORT': 'rule-grid-support',
    'GRID ONLY':    'rule-grid-only',
};

function resolveDssKey(statusStr) {
    const ORDER = ['DISCHARGING', 'CHARGING', 'OPTIMUM', 'GRID SUPPORT', 'GRID ONLY'];
    return ORDER.find(k => statusStr.includes(k)) || 'OPTIMUM';
}

function applyDssStyle(statusStr) {
    const key   = resolveDssKey(statusStr);
    const cfg   = DSS_MAP[key];
    const card  = document.getElementById('dss-card');
    const badge = document.getElementById('dss-badge');
    if (card) { card.style.background = cfg.bg; card.style.borderColor = cfg.border; }
    if (badge) {
        badge.textContent       = statusStr;
        badge.style.color       = cfg.color;
        badge.style.background  = cfg.bg;
        badge.style.borderColor = cfg.border;
    }
    Object.values(RULE_MAP).forEach(id => {
        document.getElementById(id)?.classList.remove('active-rule');
    });
    const activeRuleId = RULE_MAP[key];
    if (activeRuleId) document.getElementById(activeRuleId)?.classList.add('active-rule');
}

function applyDssOverview(statusStr) {
    const key      = resolveDssKey(statusStr);
    const cfg      = DSS_MAP[key];
    const statusEl = document.getElementById('ov-dss-status');
    if (statusEl) {
        statusEl.textContent      = statusStr;
        statusEl.style.color      = cfg.color;
        statusEl.style.fontWeight = '700';
    }
}

// ══════════════════════════════════════════════════════════════
// POWER FLOW SVG
// ══════════════════════════════════════════════════════════════
function _pfGetRect(id) {
    const el = document.getElementById(id);
    const ct = document.getElementById('pf-container');
    if (!el || !ct) return null;
    const er = el.getBoundingClientRect();
    const cr = ct.getBoundingClientRect();
    return {
        cx:     er.left - cr.left + er.width  / 2,
        cy:     er.top  - cr.top  + er.height / 2,
        left:   er.left - cr.left,
        right:  er.left - cr.left + er.width,
        top:    er.top  - cr.top,
        bottom: er.top  - cr.top  + er.height,
        width:  er.width,
        height: er.height,
    };
}

function _pfMarker(svg, id, color, reverse) {
    let defs = svg.querySelector('defs');
    if (!defs) {
        defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        svg.insertBefore(defs, svg.firstChild);
    }
    if (!svg.querySelector('#' + id)) {
        const m = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
        m.setAttribute('id', id);
        m.setAttribute('viewBox', '0 0 10 10');
        m.setAttribute('markerWidth', '5');
        m.setAttribute('markerHeight', '5');
        m.setAttribute('refY', '5');
        m.setAttribute('refX', reverse ? '2' : '8');
        m.setAttribute('orient', reverse ? 'auto-start-reverse' : 'auto');
        const ph = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        ph.setAttribute('d', 'M2 1L8 5L2 9');
        ph.setAttribute('fill', 'none');
        ph.setAttribute('stroke', color);
        ph.setAttribute('stroke-width', '1.5');
        ph.setAttribute('stroke-linecap', 'round');
        ph.setAttribute('stroke-linejoin', 'round');
        m.appendChild(ph);
        defs.appendChild(m);
    }
}

function _line(svg, d, color, opacity, markerStart, markerEnd) {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', d);
    p.setAttribute('fill', 'none');
    p.setAttribute('stroke', color);
    p.setAttribute('stroke-width', '2.5');
    p.setAttribute('stroke-linecap', 'round');
    p.setAttribute('stroke-linejoin', 'round');
    p.setAttribute('opacity', String(opacity));
    if (markerStart) p.setAttribute('marker-start', 'url(#' + markerStart + ')');
    if (markerEnd)   p.setAttribute('marker-end',   'url(#' + markerEnd   + ')');
    svg.appendChild(p);
    return p;
}

function redrawPowerFlowSVG() {
    const svg = document.getElementById('pf-svg');
    if (!svg) return;
    svg.innerHTML = '<defs></defs>';

    const pv    = _pfGetRect('node-pv');
    const pvinv = _pfGetRect('node-pvinv');
    const dp    = _pfGetRect('dp-panel');
    const load  = _pfGetRect('node-load');
    const grid  = _pfGetRect('node-grid');
    const si    = _pfGetRect('node-si');
    const bess  = _pfGetRect('node-bess');

    if (!pv || !pvinv || !dp || !load || !grid || !si || !bess) return;

    const GAP = 8;
    const st  = window._pfState || { pv: false, pInv: 0, grid: false, load: false, dss: '—' };
    const dss = st.dss || '';

    const C_PV     = '#fdcb6e';
    const C_BESS   = '#00b894';
    const C_BESS_D = '#00d8d6';
    const C_GRID   = '#6c5ce7';
    const C_LOAD   = '#0984e3';
    const C_SI_DP  = '#636e72';
    const C_DIM    = '#dfe6e9';
    const O_ON     = 1;
    const O_DIM    = 0.4;

    let oPv   = O_DIM, cPv   = C_DIM;
    let oBess = O_DIM, cBess = C_DIM;
    let oLoad = O_ON,  cLoad = C_LOAD;

    if (dss.includes('CHARGING')) {
        oPv = O_ON; cPv = C_PV;
        oBess = O_ON; cBess = C_BESS;
    } else if (dss.includes('OPTIMUM')) {
        oPv = O_ON; cPv = C_PV;
        oBess = O_DIM; cBess = C_DIM;
    } else if (dss.includes('DISCHARGING')) {
        oPv = O_DIM; cPv = C_DIM;
        oBess = O_ON; cBess = C_BESS_D;
    } else if (dss.includes('GRID SUPPORT')) {
        oPv = O_ON; cPv = C_PV;
        oBess = O_DIM; cBess = C_DIM;
    } else if (dss.includes('GRID ONLY')) {
        oPv = O_DIM; cPv = C_DIM;
        oBess = O_DIM; cBess = C_DIM;
    } else {
        oPv   = st.pv             ? O_ON  : O_DIM;
        cPv   = st.pv             ? C_PV  : C_DIM;
        oBess = Math.abs(st.pInv) > 10 ? O_ON : O_DIM;
        cBess = st.pInv > 10 ? C_BESS : st.pInv < -10 ? C_BESS_D : C_DIM;
    }

    const markerDefs = [
        ['pv',   cPv],
        ['bess', cBess],
        ['grid', C_GRID],
        ['si',   C_SI_DP],
        ['load', C_LOAD],
        ['dim',  C_DIM],
    ];
    markerDefs.forEach(([id, c]) => {
        _pfMarker(svg, 'me-' + id, c, false);
        _pfMarker(svg, 'ms-' + id, c, true);
    });

    const pvKey   = oPv   === O_ON ? 'pv'   : 'dim';
    const bessKey = oBess === O_ON ? 'bess' : 'dim';

    _line(svg, `M${pv.right + GAP},${pv.cy} H${pvinv.left - GAP}`, cPv, oPv, null, 'me-' + pvKey);
    _line(svg, `M${pvinv.right + GAP},${pvinv.cy} H${dp.left - GAP}`, cPv, oPv, null, 'me-' + pvKey);
    _line(svg, `M${dp.right + GAP},${dp.cy} H${load.left - GAP}`, C_LOAD, O_ON, null, 'me-load');
    _line(svg, `M${grid.right + GAP},${grid.cy} H${si.left - GAP}`, C_GRID, O_ON, null, 'me-grid');
    _line(svg, `M${si.cx},${si.top - GAP} V${dp.bottom + GAP}`, C_SI_DP, O_ON, 'ms-si', 'me-si');
    _line(svg, `M${si.cx},${si.bottom + GAP} V${bess.top - GAP}`, cBess, oBess, 'ms-' + bessKey, 'me-' + bessKey);
}

function updatePowerFlow(grid, pv, pInv, load, dss) {
    const THR = 10;
    window._pfState = {
        pv:   pv   > THR,
        grid: grid > THR,
        pInv: pInv,
        load: load > THR,
        dss:  dss  || '—',
    };
    const nPv   = document.getElementById('node-pv');
    const nBess = document.getElementById('node-bess');
    const nGrid = document.getElementById('node-grid');
    if (nPv)   nPv.style.borderColor   = pv   > THR ? '#fdcb6e' : '#dfe6e9';
    if (nGrid) nGrid.style.borderColor = grid > THR ? '#6c5ce7' : '#dfe6e9';
    if (nBess) {
        if      (pInv >  THR) nBess.style.borderColor = '#00b894';
        else if (pInv < -THR) nBess.style.borderColor = '#00d8d6';
        else                  nBess.style.borderColor = '#dfe6e9';
    }
    redrawPowerFlowSVG();
}

window.addEventListener('resize', redrawPowerFlowSVG);
setTimeout(redrawPowerFlowSVG, 400);

// ══════════════════════════════════════════════════════════════
// MAIN POLL — /api/data setiap 30s
// ══════════════════════════════════════════════════════════════
let lastChartPush = 0;
let isFirstData   = true;
const CHART_PUSH_INTERVAL = 60000;

function fetchData() {
    fetch('/api/data')
        .then(r => r.json())
        .then(d => {
            const grid     = d.grid_va         || 0;
            const pv       = d.pv              || 0;
            const pvA      = d.pv_string_a     || 0;
            const pvB      = d.pv_string_b     || 0;
            const pac      = d.pac_inverter    || 0;
            const pacEst   = (d.pac_estimasi !== null && d.pac_estimasi !== undefined) ? d.pac_estimasi : null;
            const load     = d.load            || 0;
            const soc      = d.soc             || 0;
            const pInv     = d.p_inverter      || 0;
            const bessDc   = d.bess_power_dc   || 0;
            const efiRp    = d.efisiensi_rp    || 0;
            const rf       = d.rf_pct          || 0;
            const rfInstan = d.rf_instan       || 0;
            const lcoe     = d.lcoe            || 0;
            const biayaPln = d.biaya_pln_murni || 0;
            const biayaAkt = d.biaya_aktual    || 0;
            const fGrid    = d.freq_grid       || 0;
            const fBess    = d.freq_bess       || 0;
            const fPv      = d.freq_pv         || 0;
            const essaJam  = d.essa_jam        || 0;
            const co2Kg    = d.co2_kg          || 0;
            const loadEst  = (d.load_estimasi !== null && d.load_estimasi !== undefined) ? d.load_estimasi : null;
            const status   = d.dss_status      || '—';
            const pesan    = d.dss_pesan       || '—';

            document.getElementById('t-grid').textContent       = VA(grid);
            document.getElementById('t-freq-grid').textContent  = HZ(fGrid);
            document.getElementById('t-grid-w').textContent     = VA(grid);
            document.getElementById('t-soc').textContent        = soc.toFixed(1) + ' %';
            document.getElementById('t-bess-freq-sub').textContent = W(bessDc);
            document.getElementById('t-bess-freq-val').textContent = HZ(fBess);
            document.getElementById('t-pv').textContent         = W(pv);
            document.getElementById('t-pac-pv').textContent     = W(pac);
            document.getElementById('t-freq-pv').textContent    = HZ(fPv);
            document.getElementById('t-pvac').textContent       = W(pac);
            document.getElementById('t-load').textContent       = W(load);
            document.getElementById('t-load-w').textContent     = W(load);
            document.getElementById('t-freq-load').textContent  = HZ(fGrid);
            document.getElementById('t-pinv').textContent       = W(pInv);

            const elFreqBessSi = document.getElementById('t-freq-bess-si');
            if (elFreqBessSi) elFreqBessSi.textContent = HZ(fBess);

            setStatusPill('t-status-grid', fGrid);
            setStatusPill('t-status-bess', fBess);
            setPvStatusPill('t-status-pv', fPv, pv);
            setNodeStatus('node-grid', fGrid);
            setNodeStatus('node-bess', fBess);

            const pvOnline = fPv > 45 && fPv < 55 && pv > 10;
            const nodePv = document.getElementById('node-pv');
            if (nodePv) {
                nodePv.classList.toggle('online', pvOnline);
                nodePv.classList.toggle('offline', !pvOnline);
            }

            updatePowerFlow(grid, pv, pInv, load, status);

            document.getElementById('ov-resave').textContent = IDR(efiRp);
            document.getElementById('ov-rf').textContent     = PCT(rfInstan);
            document.getElementById('ov-soc').textContent    = PCT(soc);
            const elOvBessAc = document.getElementById('ov-bess-ac');
            const elOvBessDc = document.getElementById('ov-bess-dc');
            if (elOvBessAc) elOvBessAc.textContent = W(pInv);
            if (elOvBessDc) elOvBessDc.textContent = W(bessDc);
            applyDssOverview(status);

            document.getElementById('pv-total').textContent = W(pv);
            document.getElementById('pv-a').textContent     = W(pvA);
            document.getElementById('pv-b').textContent     = W(pvB);
            document.getElementById('pv-pac').textContent   = W(pac);
            document.getElementById('pv-freq').textContent  = HZ(fPv);
            document.getElementById('pv-eff').textContent   =
                pv > 0 ? ((pac / pv) * 100).toFixed(1) + ' %' : '— %';
            setPvStatusPill('pv-status', fPv, pv);

            document.getElementById('bess-soc').textContent        = PCT(soc);
            document.getElementById('bess-power').textContent      = W(pInv);
            document.getElementById('bess-freq').textContent       = HZ(fBess);
            document.getElementById('bess-mode-label').textContent =
                pInv > 10 ? '↑ Discharge ke Panel' : pInv < -10 ? '↓ Charging' : 'Standby';
            setStatusPill('bess-status', fBess);
            const elBessDc  = document.getElementById('bess-power-dc');
            const elBessAcS = document.getElementById('bess-power-ac-sub');
            if (elBessDc)  elBessDc.textContent  = W(bessDc);
            if (elBessAcS) elBessAcS.textContent = W(pInv);

            const bessDischarge = pInv > 0 ? pInv : 0;
            const ebtSupply     = pac + bessDischarge;
            const neraca        = ebtSupply - load;
            document.getElementById('load-val').textContent    = W(load);
            document.getElementById('load-ebt').textContent    = W(ebtSupply);
            document.getElementById('load-neraca').textContent =
                (neraca >= 0 ? '+' : '') + neraca.toFixed(1) + ' W';
            document.getElementById('load-neraca').style.color =
                neraca >= 0 ? '#00b894' : '#d63031';
            document.getElementById('load-neraca-label').textContent =
                neraca >= 0 ? 'Surplus EBT' : 'Defisit → butuh PLN';
            const total   = load || 1;
            const pvPct   = Math.min((pac          / total) * 100, 100);
            const bessPct = Math.min((bessDischarge / total) * 100, Math.max(0, 100 - pvPct));
            const plnPct  = Math.max(100 - pvPct - bessPct, 0);
            document.getElementById('neraca-pv').style.width   = pvPct   + '%';
            document.getElementById('neraca-bess').style.width = bessPct + '%';
            document.getElementById('neraca-pln').style.width  = plnPct  + '%';

            document.getElementById('ek-resave').textContent       = IDR(efiRp);
            document.getElementById('ek-lcoe').textContent         = IDR(lcoe) + ' / kWh';
            document.getElementById('ek-rf').textContent           = PCT(rfInstan);
            document.getElementById('ek-rf-bar').style.width       = Math.min(rfInstan, 100) + '%';
            document.getElementById('ek-biaya-pln').textContent    = IDR(biayaPln);
            document.getElementById('ek-biaya-aktual').textContent = IDR(biayaAkt);
            document.getElementById('ek-penghematan').textContent  = IDR(efiRp);
            document.getElementById('ek-donut-pct').textContent    = rfInstan.toFixed(0) + '%';

            const bessEssaEl = document.getElementById('bess-essa');
            if (bessEssaEl) bessEssaEl.textContent = essaJam.toFixed(2) + ' jam';

            const co2El = document.getElementById('ek-co2');
            if (co2El) co2El.innerHTML = co2Kg.toFixed(4) + ' <span style="font-size:16px;font-weight:500;">kg</span>';

            const ebtTerpakai = ebtSupply >= load ? load : ebtSupply;
            const plnTerpakai = Math.max(load - ebtSupply, 0);
            if (ebtTerpakai <= 0.5 && plnTerpakai <= 0.5) {
                chartMix.data.datasets[0].data            = [1, 1];
                chartMix.data.datasets[0].backgroundColor = ['#dfe6e9', '#b2bec3'];
            } else {
                chartMix.data.datasets[0].data            = [plnTerpakai, ebtTerpakai];
                chartMix.data.datasets[0].backgroundColor = ['#6c5ce7', '#00b894'];
            }
            chartMix.update('none');

            document.getElementById('dss-pesan').textContent = pesan;
            applyDssStyle(status);

            const now        = Date.now();
            const shouldPush = isFirstData || (now - lastChartPush >= CHART_PUSH_INTERVAL);
            if (shouldPush) {
                isFirstData   = false;
                lastChartPush = now;
                const label   = timeLabel();
                pushChart(charts.ovSoc,  label, soc);
                pushChart(charts.ovPv,   label, pac);
                pushChart(charts.ovLoad, label, load);
                pushChart(charts.pvTotal, label, pac, pacEst);
                pushChart(charts.pvA,     label, pvA);
                pushChart(charts.pvB,     label, pvB);
                pushChart(charts.bessSoc,      label, soc);
                pushChart(charts.bessInverter, label, pInv);
                pushChart(charts.bessDcPower,  label, bessDc);
                pushChart(charts.loadTrend,   label, load);
                pushChart(charts.loadCompare, label, load, loadEst);
            }
        })
        .catch(err => console.error('[fetchData]', err));
}

// ══════════════════════════════════════════════════════════════
// DSS LOG POLL — setiap 60s
// ══════════════════════════════════════════════════════════════
function fetchDssLog() {
    fetch('/api/control/history')
        .then(r => r.json())
        .then(rows => {
            const tbody = document.getElementById('dss-log-body');
            if (!tbody) return;
            if (!rows || !rows.length) {
                tbody.innerHTML = `<tr><td colspan="3" class="text-center py-6 text-muted text-sm">Belum ada log.</td></tr>`;
                return;
            }
            tbody.innerHTML = rows.map(r => {
                const key   = resolveDssKey(r.status_operasi || '');
                const color = DSS_MAP[key]?.color || '#b2bec3';
                return `
                <tr class="border-b border-border">
                    <td class="py-2 px-3 text-xs font-mono text-muted whitespace-nowrap">${r.timestamp || '—'}</td>
                    <td class="py-2 px-3 text-xs font-bold whitespace-nowrap" style="color:${color}">${r.status_operasi || '—'}</td>
                    <td class="py-2 px-3 text-xs text-muted">${r.keputusan_aktif || '—'}</td>
                </tr>`;
            }).join('');
        })
        .catch(err => console.error('[fetchDssLog]', err));
}

// ══════════════════════════════════════════════════════════════
// HISTORICAL ANALYSIS
// ══════════════════════════════════════════════════════════════
let histChartPower = null;
let histChartSoc   = null;
let histChartRf    = null;

function fmtDate(d) {
    return d.toISOString().slice(0, 10);
}

function histPreset(days) {
    const end   = new Date();
    const start = new Date();
    if (days > 0) start.setDate(start.getDate() - days + 1);
    document.getElementById('hist-start').value = fmtDate(start);
    document.getElementById('hist-end').value   = fmtDate(end);
}

function fetchHistory() {
    const start = document.getElementById('hist-start').value;
    const end   = document.getElementById('hist-end').value;
    if (!start || !end) { alert('Pilih tanggal mulai dan selesai.'); return; }

    document.getElementById('hist-info').textContent    = 'Memuat data...';
    document.getElementById('hist-empty').style.display = 'none';

    fetch(`/api/history?start=${start}&end=${end}`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                document.getElementById('hist-info').textContent = 'Error: ' + data.error;
                return;
            }
            if (!data.rows || data.rows.length === 0) {
                document.getElementById('hist-info').textContent = 'Tidak ada data pada rentang tersebut.';
                document.getElementById('hist-empty').style.display = 'block';
                return;
            }

            const s = data.summary;
            const c = data.charts;

            document.getElementById('hist-info').textContent =
                `${s.total_rows} data ditemukan · ${start} s/d ${end}`;

            document.getElementById('hs-pv').textContent   = parseFloat(s.total_pv_kwh  ||0).toFixed(2) + ' kWh';
            document.getElementById('hs-load').textContent = parseFloat(s.total_load_kwh||0).toFixed(2) + ' kWh';
            document.getElementById('hs-rf').textContent   = parseFloat(s.avg_rf_pct    ||0).toFixed(1) + '%';
            document.getElementById('hs-essa').textContent = parseFloat(s.essa_jam      ||0).toFixed(2) + ' jam';
            document.getElementById('hs-co2').textContent  = parseFloat(s.total_co2_kg  ||0).toFixed(4) + ' kg';
            document.getElementById('hs-saving').textContent = 'Rp ' +
                parseFloat(s.total_re_saving||0).toLocaleString('id-ID', { minimumFractionDigits: 2 });

            document.getElementById('hist-summary').style.display     = 'grid';
            document.getElementById('hist-chart1-wrap').style.display  = 'block';
            document.getElementById('hist-chart23-wrap').style.display = 'grid';
            document.getElementById('hist-table-wrap').style.display   = 'block';
            document.getElementById('hist-empty').style.display        = 'none';

            if (histChartPower) histChartPower.destroy();
            histChartPower = new Chart(
                document.getElementById('hist-chart-power').getContext('2d'), {
                type: 'line',
                data: {
                    labels: c.hourly_labels,
                    datasets: [
                        {
                            label: 'PV (kWh)',
                            data: c.hourly_pv_kwh,
                            borderColor: '#fdcb6e',
                            backgroundColor: 'rgba(253,203,110,0.1)',
                            borderWidth: 1.5,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            tension: 0.3,
                            fill: true,
                        },
                        {
                            label: 'Load (kWh)',
                            data: c.hourly_load_kwh,
                            borderColor: '#0984e3',
                            backgroundColor: 'rgba(9,132,227,0.05)',
                            borderWidth: 1.5,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            tension: 0.3,
                            fill: false,
                        }
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: false, animation: false,
                    plugins: {
                        legend: {
                            display: true,
                            labels: { usePointStyle: true, font: { size: 10 }, padding: 14 }
                        },
                        zoom: {
                            pan: { enabled: true, mode: 'x' },
                            zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' }
                        }
                    },
                    scales: {
                        x: {
                            ticks: {
                                maxTicksLimit: 12,
                                font: { size: 9 },
                                callback: (v, i) => {
                                    const lbl = c.hourly_labels[i] || '';
                                    return lbl.slice(11, 16);
                                }
                            },
                            grid: { color: '#f0f3f5' }
                        },
                        y: {
                            beginAtZero: true,
                            title: { display: true, text: 'kWh', font: { size: 9 }, color: '#b2bec3' },
                            ticks: { font: { size: 9 } },
                            grid: { color: '#f0f3f5' }
                        }
                    }
                }
            });

            if (histChartSoc) histChartSoc.destroy();
            histChartSoc = new Chart(
                document.getElementById('hist-chart-soc').getContext('2d'), {
                type: 'line',
                data: {
                    labels: c.labels,
                    datasets: [{
                        label: 'SoC (%)',
                        data: c.soc,
                        borderColor: '#00b894',
                        backgroundColor: 'rgba(0,184,148,0.08)',
                        borderWidth: 1.5,
                        pointRadius: 0,
                        tension: 0.3,
                        fill: true
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false, animation: false,
                    plugins: {
                        legend: { display: false },
                        zoom: {
                            pan: { enabled: true, mode: 'x' },
                            zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' }
                        }
                    },
                    scales: {
                        x: { ticks: { maxTicksLimit: 6, font: { size: 9 } }, grid: { color: '#f0f3f5' } },
                        y: { min: 0, max: 100, ticks: { font: { size: 9 } }, grid: { color: '#f0f3f5' } }
                    }
                }
            });

            if (histChartRf) histChartRf.destroy();
            histChartRf = new Chart(
                document.getElementById('hist-chart-rf').getContext('2d'), {
                type: 'bar',
                data: {
                    labels: c.labels,
                    datasets: [{
                        label: 'RF (%)',
                        data: c.rf_pct,
                        backgroundColor: 'rgba(0,216,214,0.7)',
                        borderColor: '#00d8d6',
                        borderWidth: 0,
                        borderRadius: 2
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false, animation: false,
                    plugins: {
                        legend: { display: false },
                        zoom: {
                            pan: { enabled: true, mode: 'x' },
                            zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' }
                        }
                    },
                    scales: {
                        x: { ticks: { maxTicksLimit: 6, font: { size: 9 } }, grid: { display: false } },
                        y: { min: 0, max: 100, ticks: { font: { size: 9 } }, grid: { color: '#f0f3f5' } }
                    }
                }
            });

            document.getElementById('hist-row-count').textContent = data.rows.length + ' baris';
            const DSS_CLR = {
                'CHARGING':     '#00b894',
                'OPTIMUM':      '#0984e3',
                'DISCHARGING':  '#fdcb6e',
                'GRID SUPPORT': '#6c5ce7',
                'GRID ONLY':    '#d63031',
            };
            function dssClr(s) {
                const k = Object.keys(DSS_CLR).find(k => (s||'').includes(k));
                return k ? DSS_CLR[k] : '#b2bec3';
            }
            document.getElementById('hist-tbody').innerHTML = data.rows.map(r => `
                <tr class="border-b border-border">
                    <td class="py-1.5 px-2 font-mono text-muted whitespace-nowrap">${(r.timestamp||'').slice(0,16)}</td>
                    <td class="py-1.5 px-2 text-right font-mono" style="color:#fdcb6e">${parseFloat(r.pv_dc      ||0).toFixed(1)}</td>
                    <td class="py-1.5 px-2 text-right font-mono" style="color:#0984e3">${parseFloat(r.load_w     ||0).toFixed(1)}</td>
                    <td class="py-1.5 px-2 text-right font-mono" style="color:#00d8d6">${parseFloat(r.p_inverter ||0).toFixed(1)}</td>
                    <td class="py-1.5 px-2 text-right font-mono" style="color:#00b894">${parseFloat(r.soc        ||0).toFixed(1)}</td>
                    <td class="py-1.5 px-2 text-right font-mono" style="color:#00d8d6">${parseFloat(r.rf_pct     ||0).toFixed(1)}</td>
                    <td class="py-1.5 px-2 font-bold whitespace-nowrap"
                        style="color:${dssClr(r.dss_status)};font-size:10px;">${r.dss_status||'-'}</td>
                </tr>`).join('');
        })
        .catch(err => {
            console.error('[fetchHistory]', err);
            document.getElementById('hist-info').textContent = 'Gagal memuat data.';
        });
}

function exportCsv() {
    const start = document.getElementById('hist-start').value;
    const end   = document.getElementById('hist-end').value;
    if (!start || !end) { alert('Pilih tanggal terlebih dahulu.'); return; }
    window.location.href = `/api/history/export?start=${start}&end=${end}`;
}

// ══════════════════════════════════════════════════════════════
// VALIDITY & MICROSERVICE
// ══════════════════════════════════════════════════════════════

const SVC_LABEL = {
    'mqtt_broker':            'Backbone komunikasi MQTT',
    'postgres_microgrid':     'Penyimpanan data terpusat',
    'service_sensor':         'Akuisisi data kelistrikan',
    'service_logger':         'Pencatatan payload MQTT → DB',
    'service_billing':        'Kalkulasi KPI energi & ekonomi',
    'service_control':        'Eksekusi algoritma DSS',
    'service_hmi_flask':      'Dasbor visualisasi HMI',
    'service_watchdog':       'Pemantauan kesehatan container',
    'service_estimation_pv':  'Inferensi model PIML (PV)',
    'service_estimation_load':'Inferensi model DNN (Load)',
    'service_pemantauan':     'Validasi data sensor real-time',
};

function calcUptime(startedAt) {
    if (!startedAt) return '—';
    const start = new Date(startedAt);
    const now   = new Date();
    let diff    = Math.floor((now - start) / 1000);
    if (diff < 0) diff = 0;
    const d = Math.floor(diff / 86400);
    const h = Math.floor((diff % 86400) / 3600);
    const m = Math.floor((diff % 3600) / 60);
    const s = diff % 60;
    if (d > 0) return `${d}d ${h}h ${m}m`;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

function fetchServices() {
    fetch('/api/system/services')
        .then(r => r.json())
        .then(data => {
            const tbody = document.getElementById('svc-tbody');
            if (!tbody) return;

            tbody.innerHTML = data.map(svc => {
                const isUp    = svc.status === 'running';
                const uptime  = isUp ? calcUptime(svc.started_at) : '—';
                const badge   = isUp
                    ? `<span class="badge-online" style="display:inline-flex;align-items:center;gap:3px;padding:2px 10px;border-radius:20px;font-size:9px;font-weight:700;">● RUNNING</span>`
                    : `<span class="badge-offline" style="display:inline-flex;align-items:center;gap:3px;padding:2px 10px;border-radius:20px;font-size:9px;font-weight:700;">● DOWN</span>`;
                const label   = SVC_LABEL[svc.name] || '—';

                return `
                <tr class="border-b border-border">
                    <td class="py-2.5 px-3 font-mono font-bold text-xs" style="color:#2d3436;">${svc.name}</td>
                    <td class="py-2.5 px-3">${badge}</td>
                    <td class="py-2.5 px-3 font-mono text-xs text-muted">${uptime}</td>
                    <td class="py-2.5 px-3 text-xs text-muted">${label}</td>
                </tr>`;
            }).join('');

            const el = document.getElementById('svc-last-update');
            if (el) el.textContent = 'Updated ' + new Date().toLocaleTimeString('id-ID');
        })
        .catch(err => console.error('[fetchServices]', err));
}

function fetchValidity() {
    fetch('/api/system/validity')
        .then(r => r.json())
        .then(data => {

            function fmtTime(tsStr) {
                if (!tsStr || tsStr === '—') return '—';
                const match = tsStr.match(/(\d{2}:\d{2}:\d{2})/);
                return match ? match[1] : tsStr;
            }

            // ── Section 2: Data Source Freshness ──
            const srcContainer = document.getElementById('validity-sources');
            if (srcContainer && data.sources) {
                srcContainer.innerHTML = data.sources.map(src => {
                    const st = src.status;
                    let color, bg, border;
                    if (st === 'FRESH')        { color='#00b894'; bg='rgba(0,184,148,0.08)';   border='#00b894'; }
                    else if (st === 'WARNING') { color='#fdcb6e'; bg='rgba(253,203,110,0.08)'; border='#fdcb6e'; }
                    else if (st === 'STALE')   { color='#d63031'; bg='rgba(214,48,49,0.08)';   border='#d63031'; }
                    else                       { color='#b2bec3'; bg='rgba(178,190,195,0.08)'; border='#b2bec3'; }

                    const stale = src.staleness_s !== null && src.staleness_s >= 0
                        ? src.staleness_s + 's lalu'
                        : '—';
                    const timeStr = fmtTime(src.timestamp);

                    return `
                    <div style="background:${bg};border:2px solid ${border};border-radius:16px;padding:16px;">
                        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                            <p style="font-size:9px;font-weight:700;color:#b2bec3;text-transform:uppercase;letter-spacing:1px;margin:0;">Sumber Data</p>
                            <span style="display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:20px;font-size:9px;font-weight:700;color:${color};border:1px solid ${color};background:white;">● ${st}</span>
                        </div>
                        <p style="font-size:13px;font-weight:700;color:#2d3436;margin:0 0 8px;">${src.name}</p>
                        <p class="font-mono" style="font-size:10px;color:#b2bec3;margin:0 0 2px;">Timestamp: <span style="color:${color};font-weight:600;">${timeStr}</span></p>
                        <p class="font-mono" style="font-size:10px;color:#b2bec3;margin:0;">Selisih: <span style="color:${color};font-weight:600;">${stale}</span></p>
                    </div>`;
                }).join('');
            }

            // ── Section 3: Alert dari service_pemantauan ──
            const badge = document.getElementById('validity-status-badge');
            const alertTbody = document.getElementById('alert-tbody');

            // Update status badge
            if (badge) {
                const sg = data.status_global || 'UNKNOWN';
                let badgeColor, badgeBg;
                if (sg === 'OK') {
                    badgeColor = '#00b894'; badgeBg = 'rgba(0,184,148,0.12)';
                    badge.className = 'badge-online';
                } else if (sg === 'WARNING') {
                    badgeColor = '#fdcb6e'; badgeBg = 'rgba(253,203,110,0.12)';
                    badge.className = '';
                    badge.style.cssText = `display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;color:${badgeColor};background:${badgeBg};border:1px solid ${badgeColor};`;
                } else if (sg === 'ERROR') {
                    badgeColor = '#d63031'; badgeBg = 'rgba(214,48,49,0.12)';
                    badge.className = 'badge-offline';
                } else {
                    badgeColor = '#b2bec3'; badgeBg = 'rgba(178,190,195,0.12)';
                }
                badge.textContent = '● ' + sg;
                badge.style.color = badgeColor;
            }

            // Update tabel alert
            if (alertTbody) {
                const alerts = data.alerts || [];
                if (alerts.length === 0) {
                    alertTbody.innerHTML = `
                    <tr>
                        <td colspan="6" class="text-center py-6">
                            <div style="display:flex;align-items:center;justify-content:center;gap:8px;">
                                <span style="display:inline-flex;align-items:center;gap:4px;padding:4px 14px;border-radius:20px;font-size:11px;font-weight:700;background:rgba(0,184,148,0.12);color:#00b894;border:1px solid rgba(0,184,148,0.3);">
                                    ✓ Tidak ada alert aktif
                                </span>
                            </div>
                            <p class="text-muted font-mono" style="font-size:10px;margin-top:6px;">Semua parameter dalam kondisi normal</p>
                        </td>
                    </tr>`;
                } else {
                    alertTbody.innerHTML = alerts.map(alert => {
                        const isError   = alert.severity === 'ERROR';
                        const sevColor  = isError ? '#d63031' : '#fdcb6e';
                        const sevBg     = isError ? 'rgba(214,48,49,0.12)'   : 'rgba(253,203,110,0.12)';
                        const sevBorder = isError ? 'rgba(214,48,49,0.3)'    : 'rgba(253,203,110,0.3)';
                        const timeStr   = fmtTime(typeof alert.timestamp === 'string'
                            ? alert.timestamp
                            : String(alert.timestamp || ''));
                        const nilaiStr  = alert.nilai_aktual !== null && alert.nilai_aktual !== undefined
                            ? parseFloat(alert.nilai_aktual).toFixed(2)
                            : '—';

                        return `
                        <tr class="border-b border-border">
                            <td class="py-2.5 px-3 font-mono text-xs text-muted whitespace-nowrap">${timeStr}</td>
                            <td class="py-2.5 px-3 font-mono font-bold text-xs" style="color:${sevColor}">${alert.parameter || '—'}</td>
                            <td class="py-2.5 px-3 font-mono text-xs text-right" style="color:#2d3436">${nilaiStr}</td>
                            <td class="py-2.5 px-3 text-xs font-mono" style="color:#636e72">${alert.jenis_alert || '—'}</td>
                            <td class="py-2.5 px-3">
                                <span style="display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:20px;font-size:9px;font-weight:700;color:${sevColor};background:${sevBg};border:1px solid ${sevBorder};">
                                    ${alert.severity || '—'}
                                </span>
                            </td>
                            <td class="py-2.5 px-3 text-xs text-muted">${alert.pesan || '—'}</td>
                        </tr>`;
                    }).join('');
                }
            }
        })
        .catch(err => console.error('[fetchValidity]', err));
}

// ── Start ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    histPreset(0);
});
fetchData();
fetchDssLog();
fetchServices();
fetchValidity();
setInterval(fetchData,    30000);
setInterval(fetchDssLog,  60000);
setInterval(fetchServices, 30000);
setInterval(fetchValidity, 30000);
