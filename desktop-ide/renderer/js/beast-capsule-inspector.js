(() => {
  const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const drawer=()=>document.getElementById('beastCapsuleInspector');
  function open(data={}){
    const node=drawer(), body=document.getElementById('beastCapsuleInspectorBody'); if(!node||!body)return;
    document.getElementById('beastCapsuleInspectorTitle').textContent=data.name||data.identity||'Capsule Inspector';
    const groups=[['INTEGRITY',[['Digest',data.digest],['Kernel seals',data.sealed?'WRITE · GROW · SHRINK · SEAL':'UNVERIFIED'],['Signer',data.signer],['Signature',data.signature||'unknown']]],['AUTHORITY',[['Ceiling',data.authority],['Capability',data.capability],['Consumed',data.consumed],['Execution count',data.executions??0]]],['APPLICABILITY',[['Workspace',data.workspace],['Policy generation',data.policy],['Source state',data.source],['Expiry',data.expiry]]],['ECONOMICS',[['Preparation debt',data.debt],['Realised value',data.value],['Break-even',data.breakEven],['Residency',data.residency]]],['LIFECYCLE',[['Promotion',data.promotion],['Pin',data.pin],['Pressure state',data.pressure],['Last receipt',data.receipt]]]];
    body.innerHTML=`<div class="capsule-truth"><span class="${data.sealed?'good':'warn'}">SEALED ${data.sealed?'YES':'UNKNOWN'}</span><span class="${data.authorized?'good':'bad'}">AUTHORIZED ${data.authorized?'YES':'NO'}</span></div>${groups.map(([title,rows])=>`<section><h3>${title}</h3>${rows.map(([k,v])=>`<div><span>${k}</span><b>${esc(v)}</b></div>`).join('')}</section>`).join('')}`;
    node.classList.add('open');node.setAttribute('aria-hidden','false');
  }
  function close(){const node=drawer();node?.classList.remove('open');node?.setAttribute('aria-hidden','true');}
  document.addEventListener('DOMContentLoaded',()=>document.getElementById('beastCapsuleInspectorClose')?.addEventListener('click',close));
  window.BeastCapsuleInspector={open,close};
})();
