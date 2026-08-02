(() => {
  'use strict';

  function parseActionIntent(value) {
    let body = String(value || '').trim();
    const fence = body.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
    if (fence) body = fence[1].trim();
    const start = body.indexOf('{');
    const end = body.lastIndexOf('}');
    if (start < 0 || end <= start) return null;
    try {
      const parsed = JSON.parse(body.slice(start, end + 1));
      return parsed && (parsed.kind === 'beast.action_intent.v1' || Array.isArray(parsed.actions)) ? parsed : null;
    } catch (_) { return null; }
  }

  function looksLikeActionIntent(value) {
    const body = String(value || '').trim();
    return /^(?:```(?:json|action_ir)?\s*)?\s*\{[\s\S]{0,600}"(?:kind|actions)"\s*:/i.test(body)
      || (/"kind"\s*:\s*"beast\.action_intent\.v1"/.test(body) && /"actions"\s*:/.test(body));
  }

  window.BeastAIIntent = Object.freeze({ parseActionIntent, looksLikeActionIntent });
})();
