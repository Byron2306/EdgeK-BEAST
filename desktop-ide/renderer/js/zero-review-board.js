(() => {
  'use strict';
  const originLabel = Object.freeze({
    zero_phone: 'BEAST Zero phone', desktop_panel: 'Desktop Review panel',
    desktop_pair_programmer: 'Desktop Pair Programmer', zero_cli: 'Zero terminal',
  });
  const ending = new Set(['completed', 'failed', 'cancelled', 'budget_exhausted', 'policy_blocked', 'rejected', 'rolled_back']);
  const validId = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
  const template = `
    <section class="zrb-card" aria-label="Shared Desktop reviews">
      <p class="zrb-muted" data-z="connection" role="status">Checking Desktop Review…</p>
      <p class="zrb-wrap" data-z="workspace"></p>
      <form class="zrb-form">
        <label>Desktop file<input name="path" placeholder="README.md" required maxlength="320" autocomplete="off"></label>
        <label>Review question<textarea name="question" placeholder="What does the first heading say? Cite its line." required maxlength="2000" rows="3"></textarea></label>
        <button type="submit" disabled>Start read-only review</button>
        <p class="zrb-muted zrb-wrap" data-z="submit" role="status"></p>
        <button data-z="retry" type="button" hidden>Retry same request ID</button>
      </form>
      <label class="zrb-picker">Shared review<select data-z="picker"><option value="">Follow latest</option></select></label>
      <button type="button" data-z="latest" hidden>Follow latest review</button>
      <p class="zrb-state" data-z="state">No reviews yet</p>
      <p class="zrb-muted zrb-wrap" data-z="meta"></p>
      <p class="zrb-muted zrb-wrap" data-z="coverage"></p>
      <pre class="zrb-answer" data-z="answer" hidden></pre>
      <p class="zrb-muted">Both screens follow the Desktop run. Reviews cannot edit files, run commands, or grant approvals.</p>
    </section>`;

  function id() {
    return 'zero-review-' + Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
  }

  function mount(host, {rpc, connectedLabel, onState = () => {}, expectedWorkspace = () => '', initialActive = true}) {
    host.innerHTML = template;
    const get = name => host.querySelector('[data-z="' + name + '"]');
    const form = host.querySelector('form');
    const submit = form.querySelector('[type=submit]');
    const retry = get('retry');
    const picker = get('picker');
    const latest = get('latest');
    let workspace = '', selected = '', rows = [], choices = '', detail = null;
    let active = false, pollBusy = false, submitting = false, pending = null, timer, generation = 0, connected = false;

    function buildChoices() {
      const pendingRow = selected && !rows.some(row => row.run_id === selected);
      const next = JSON.stringify([rows.map(row => [row.run_id, row.origin, row.state]), pendingRow ? selected : '']);
      if (next === choices) return;
      choices = next;
      picker.replaceChildren(new Option('Follow latest', ''), ...rows.map(row =>
        new Option(`${originLabel[row.origin] || 'Desktop'} · ${row.state} · ${row.run_id}`, row.run_id)));
      if (pendingRow) picker.add(new Option(selected, selected));
      picker.value = selected;
    }

    function render() {
      const rid = selected || rows[0]?.run_id || '';
      latest.hidden = !selected || !rows[0] || selected === rows[0].run_id;
      if (!latest.hidden) latest.textContent = 'Follow latest · ' + (originLabel[rows[0].origin] || 'Desktop');
      const row = rows.find(item => item.run_id === rid);
      const full = detail?.run_id === rid ? detail : null;
      const state = full?.state || row?.state || (rid ? 'awaiting_receipt' : 'idle');
      get('state').textContent = rid ? state.replaceAll('_', ' ') : 'No reviews yet';
      get('meta').textContent = [originLabel[full?.origin || row?.origin], full?.provider || row?.provider, full?.model || row?.model, rid].filter(Boolean).join(' · ');
      get('coverage').textContent = full?.coverage ? 'Coverage supplied · ' + full.coverage : '';
      get('answer').textContent = full?.answer || full?.error || '';
      get('answer').hidden = !get('answer').textContent;
      onState(connected ? state : 'disconnected', rid);
    }

    function later(delay) {
      clearTimeout(timer);
      if (active) timer = setTimeout(refresh, delay);
    }

    async function refresh() {
      if (!active || pollBusy) return;
      const epoch = generation;
      const expected = expectedWorkspace();
      pollBusy = true;
      try {
        const board = await rpc('list', expected);
        if (!active || epoch !== generation) return;
        if (expected !== expectedWorkspace()) { connected = false; submit.disabled = true; return; }
        if (!board?.ok || typeof board.workspace !== 'string' || !Array.isArray(board.runs)
            || !board.runs.every(row => row && validId.test(row.run_id))) throw new Error('Invalid Desktop review board response.');
        if (workspace && workspace !== board.workspace) {
          selected = '';
          detail = null;
          pending = null;
          retry.hidden = true;
          get('submit').textContent = '';
        }
        workspace = board.workspace;
        rows = board.runs;
        connected = true;
        submit.disabled = submitting || Boolean(pending);
        get('connection').textContent = connectedLabel;
        get('workspace').textContent = [workspace, board.model].filter(Boolean).join(' · ');
        if (pending && rows.some(row => row.run_id === pending.run_id)) confirmed(pending.run_id);
        buildChoices();
        const rid = selected || rows[0]?.run_id;
        const row = rows.find(item => item.run_id === rid);
        if (!rid || detail?.run_id !== rid) detail = null;
        render();
        if (rid && !(detail && ending.has(detail.state) && (!row || row.state === detail.state))) {
          try {
            const answer = await rpc('detail', rid, expected);
            const current = selected || rows[0]?.run_id;
            if (!active || epoch !== generation || rid !== current || expected !== expectedWorkspace()) return;
            if (answer?.ok !== true || answer.run_id !== rid || answer.root_path !== workspace) throw new Error('Desktop review identity does not match.');
            detail = answer;
            if (pending?.run_id === rid) confirmed(rid);
            render();
          } catch (error) {
            const current = selected || rows[0]?.run_id;
            if (rid === current && error.status !== 404) throw error;
          }
        }
      } catch (error) {
        if (active && epoch === generation) {
          connected = false;
          submit.disabled = true;
          if (error.status === 409) {
            rows = [];
            selected = '';
            detail = null;
            get('workspace').textContent = '';
            buildChoices();
          }
          get('connection').textContent = error.message || 'Desktop Review unavailable.';
          render();
        }
      } finally {
        pollBusy = false;
        if (active) later(epoch === generation && expected === expectedWorkspace() ? (document.hidden ? 5500 : 1800) : 0);
      }
    }

    function confirmed(rid) {
      if (pending?.run_id === rid) pending = null;
      retry.hidden = true;
      get('submit').textContent = 'Submitted · ' + rid;
      if (!submitting) submit.disabled = !connected;
    }

    async function send(body) {
      if (!body || submitting) return;
      submitting = true;
      pending = body;
      selected = body.run_id;
      detail = null;
      generation++;
      submit.disabled = retry.disabled = true;
      retry.hidden = true;
      get('submit').textContent = 'Sending to Desktop · ' + body.run_id;
      buildChoices();
      render();
      try {
        const outcome = await rpc('submit', body);
        if (outcome?.ok !== true || outcome.run_id !== body.run_id) throw new Error('Desktop did not confirm the same run ID.');
        confirmed(body.run_id);
      } catch (error) {
        if (pending !== body) return;
        const refused = [403, 409, 422].includes(error.status);
        get('submit').textContent = (error.message || 'Desktop did not acknowledge the request.') +
          (refused ? '' : ' Checking the same ID for its receipt · ' + body.run_id);
        if (refused) {
          pending = null;
          selected = '';
          buildChoices();
          render();
        } else retry.hidden = false;
      } finally {
        submitting = false;
        submit.disabled = !connected || Boolean(pending);
        retry.disabled = false;
        if (active) later(0);
      }
    }

    form.addEventListener('submit', event => {
      event.preventDefault();
      if (!connected || submitting || pending) return;
      const path = form.elements.path.value.trim();
      const question = form.elements.question.value.trim();
      if (!path || !question) return;
      send({run_id: id(), path, question, workspace});
    });
    retry.addEventListener('click', () => send(pending));
    picker.addEventListener('change', () => {
      selected = picker.value;
      detail = null;
      generation++;
      render();
      later(0);
    });
    latest.addEventListener('click', () => {
      picker.value = '';
      selected = '';
      detail = null;
      generation++;
      render();
      later(0);
    });
    function setActive(next) {
      active = Boolean(next);
      generation++;
      clearTimeout(timer);
      if (active) later(0);
    }
    setActive(initialActive);
    return Object.freeze({setActive});
  }

  window.BeastZeroReviewBoard = Object.freeze({mount});
})();
