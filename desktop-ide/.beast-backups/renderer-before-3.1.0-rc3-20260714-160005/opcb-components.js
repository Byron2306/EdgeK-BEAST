(function () {
  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function metricCard({ label, value, sublabel = '', tone = 'cyan', icon = '' }) {
    return `
      <div class="opcb-metric-card tone-${escapeHtml(tone)}">
        ${icon ? `<img class="opcb-asset-icon opcb-injected-icon" src="${escapeHtml(icon)}" alt="">` : ''}
        <div class="opcb-metric-value">${escapeHtml(value)}</div>
        <div class="opcb-metric-label">${escapeHtml(label)}</div>
        ${sublabel ? `<div class="opcb-metric-sub">${escapeHtml(sublabel)}</div>` : ''}
      </div>
    `;
  }

  function ringMetric({ value, label, tone = 'teal' }) {
    return `
      <div class="opcb-ring tone-${escapeHtml(tone)}" style="--value:${Number(value) || 0}">
        <div class="opcb-ring-core">
          <strong>${escapeHtml(value)}%</strong>
          <span>${escapeHtml(label)}</span>
        </div>
      </div>
    `;
  }

  function gateList(items) {
    return `
      <div class="opcb-gate-list">
        ${items.map(item => `
          <div class="opcb-gate-row tone-${escapeHtml(item.tone || 'teal')}">
            <span>${escapeHtml(item.label)}</span>
            <em>${escapeHtml(item.status)}</em>
          </div>
        `).join('')}
      </div>
    `;
  }

  function eventLedger(events) {
    return `
      <div class="opcb-ledger">
        ${events.map(event => `
          <div class="opcb-ledger-row">
            <time>${escapeHtml(event.time)}</time>
            <span>${escapeHtml(event.label)}</span>
          </div>
        `).join('')}
      </div>
    `;
  }

  function rightRailCard(title, body, action = '', icon = '') {
    return `
      <section class="opcb-rail-card">
        <header><h3>${icon ? `<img class="opcb-asset-icon" src="${escapeHtml(icon)}" alt="">` : ''}${escapeHtml(title)}</h3></header>
        <div>${body}</div>
        ${action ? `<footer>${action}</footer>` : ''}
      </section>
    `;
  }

  window.opcbComponents = {
    escapeHtml,
    metricCard,
    ringMetric,
    gateList,
    eventLedger,
    rightRailCard
  };
})();
