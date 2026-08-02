(() => {
  let mountedRoot = null;

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  }

  function profileFor(path) {
    return window.BeastEditorDocumentModel?.get?.(path)?.safety_profile || { mode: 'NORMAL' };
  }

  function editorOptions(path) {
    const profile = profileFor(path);
    const constrained = profile.mode !== 'NORMAL';
    return {
      minimap: { enabled: !profile.disable_minimap },
      folding: !profile.disable_code_folding,
      codeLens: !profile.disable_expensive_decorations,
      lightbulb: { enabled: constrained ? 'off' : 'on' },
      links: !profile.disable_expensive_decorations,
      occurrencesHighlight: profile.disable_expensive_decorations ? 'off' : 'singleFile',
      renderValidationDecorations: profile.disable_diagnostics ? 'off' : 'on',
      semanticHighlighting: { enabled: !profile.disable_semantic_tokens },
      stickyScroll: { enabled: !constrained },
      wordWrap: profile.word_wrap === 'bounded' ? 'bounded' : 'off',
      wordWrapColumn: 160,
      maxTokenizationLineLength: Number(profile.max_tokenization_line_length || 20000),
      bracketPairColorization: { enabled: !profile.disable_expensive_decorations },
      guides: { bracketPairs: !profile.disable_expensive_decorations, indentation: !profile.disable_expensive_decorations },
    };
  }

  function badges(document) {
    const profile = document?.safety_profile || {};
    const values = [];
    if (document?.binary) values.push('BINARY');
    if (document?.large_file_mode) values.push('LARGE FILE');
    if (profile.generated) values.push('GENERATED');
    if (profile.very_long_lines) values.push('LONG LINES');
    if (profile.unknown_encoding) values.push('UNKNOWN ENCODING');
    if (document?.partial_content) values.push('PARTIAL PREVIEW');
    return values;
  }

  function warning(document) {
    const profile = document?.safety_profile || {};
    if (document?.binary) return 'Binary content is isolated from the text editor. Use the bounded hex preview or open it with the operating system.';
    if (profile.unknown_encoding) return 'The encoding could not be decoded safely. This document is read-only until an explicit encoding is selected.';
    if (document?.large_file_mode) return 'Large-file mode disables expensive editor services to preserve responsiveness.';
    if (profile.very_long_lines) return 'Very long lines detected. Tokenization, folding, and decorations are constrained.';
    if (profile.generated) return 'Generated-file mode reduces diagnostics, semantic analysis, and automatic formatting.';
    return '';
  }

  function renderMetadata(document) {
    return `
      <div class="cortex-safety-meta">
        <p><b>Type</b><span>${escapeHtml(document.file_signature || document.kind || 'File')}</span></p>
        <p><b>Size</b><span>${Number(document.size_bytes || 0).toLocaleString()} bytes</span></p>
        <p><b>Encoding</b><span>${escapeHtml(document.encoding || 'unknown')}</span></p>
        <p><b>Mode</b><span>${escapeHtml(document.safety_profile?.mode || 'NORMAL')}</span></p>
      </div>`;
  }

  async function renderBinary(path, offset = 0) {
    const panel = mountedRoot?.querySelector?.('[data-editor-safety-workbench]');
    const document = window.BeastEditorDocumentModel?.get?.(path);
    if (!panel || !document?.binary) return;
    panel.classList.remove('hidden');
    panel.innerHTML = `<header><span><b>Binary safety fallback</b><small>${escapeHtml(path)}</small></span><div><button data-binary-action="previous">Previous bytes</button><button data-binary-action="next">Next bytes</button><button data-binary-action="external">Open externally</button></div></header>${renderMetadata(document)}<pre class="cortex-hex-preview">Loading bounded hex preview…</pre>`;
    try {
      const preview = await window.BeastEditorDocumentModel.binaryPreview(path, { offset, length: 512 });
      panel.dataset.offset = String(preview.offset || 0);
      panel.querySelector('.cortex-hex-preview').textContent = (preview.rows || []).map(row => `${Number(row.offset).toString(16).padStart(8, '0')}  ${String(row.hex).padEnd(47)}  |${row.ascii}|`).join('\n') || 'No bytes available.';
    } catch (error) {
      panel.querySelector('.cortex-hex-preview').textContent = String(error.message || error);
    }
    panel.querySelector('[data-binary-action="previous"]')?.addEventListener('click', () => renderBinary(path, Math.max(0, Number(panel.dataset.offset || 0) - 512)));
    panel.querySelector('[data-binary-action="next"]')?.addEventListener('click', () => renderBinary(path, Number(panel.dataset.offset || 0) + 512));
    panel.querySelector('[data-binary-action="external"]')?.addEventListener('click', () => window.BeastEditorDocumentModel.openExternal(path));
  }

  function apply(path, editors = []) {
    const document = window.BeastEditorDocumentModel?.get?.(path);
    const panel = mountedRoot?.querySelector?.('[data-editor-safety-workbench]');
    const banner = mountedRoot?.querySelector?.('[data-editor-safety-banner]');
    const editorStage = mountedRoot?.querySelector?.('[data-editor-text-surface]');
    const options = editorOptions(path);
    editors.filter(Boolean).forEach(instance => instance.updateOptions(options));
    if (!document) {
      panel?.classList.add('hidden');
      banner?.classList.add('hidden');
      editorStage?.classList.remove('hidden');
      return options;
    }
    const activeBadges = badges(document);
    const message = warning(document);
    if (banner) {
      banner.classList.toggle('hidden', !activeBadges.length);
      banner.innerHTML = activeBadges.length ? `<span>${activeBadges.map(value => `<b>${escapeHtml(value)}</b>`).join('')}</span><small>${escapeHtml(message)}</small>` : '';
    }
    if (document.binary) {
      editorStage?.classList.add('hidden');
      renderBinary(path, 0);
    } else {
      editorStage?.classList.remove('hidden');
      panel?.classList.add('hidden');
    }
    return options;
  }

  function mount(root) {
    mountedRoot = root;
  }

  window.BeastEditorSafety = { mount, apply, editorOptions, profileFor, renderBinary };
})();
