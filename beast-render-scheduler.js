(() => {
  let revision=0,frame=0,controller=null,disposeActive=null;
  async function request(page,renderer,options={}){
    const myRevision=++revision;controller?.abort('superseded');controller=new AbortController();cancelAnimationFrame(frame);
    await new Promise(resolve=>{frame=requestAnimationFrame(resolve)});if(myRevision!==revision)return;
    const outlet=document.getElementById('beastPageOutlet');if(!outlet)throw new Error('Missing #beastPageOutlet');
    outlet.setAttribute('aria-busy','true');outlet.dataset.transitioning='true';
    let result;
    try{
      result=await renderer({page,signal:controller.signal,revision:myRevision,options});
      if(myRevision!==revision||controller.signal.aborted){result?.dispose?.();return false}
      disposeActive?.();disposeActive=null;
      // Force a real compositor handoff so a stale route layer cannot remain visible.
      outlet.replaceChildren();
      void outlet.offsetHeight;
      let nextNode=null;
      if(typeof result==='string'){outlet.innerHTML=result;}
      else if(result instanceof Node){nextNode=result;}
      else if(result?.node instanceof Node){nextNode=result.node;disposeActive=typeof result.dispose==='function'?result.dispose:null}
      if(nextNode)outlet.append(nextNode);
      outlet.dataset.renderRevision=String(myRevision);outlet.dataset.renderPage=page;
      document.dispatchEvent(new CustomEvent('beast:render-committed',{detail:{page,revision:myRevision}}));return true;
    }catch(error){
      if(controller.signal.aborted||myRevision!==revision)return false;
      console.error('[BEAST Render]',page,error);document.dispatchEvent(new CustomEvent('beast:render-error',{detail:{page,error}}));
      if(!outlet.firstElementChild){const card=document.createElement('section');card.className='beast-runtime-error-card';card.innerHTML=`<h2>Renderer fault: ${page}</h2><p>${String(error.message||error).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'})[c])}</p>`;outlet.replaceChildren(card)}
      return false;
    }finally{if(myRevision===revision){outlet.removeAttribute('aria-busy');delete outlet.dataset.transitioning}}
  }
  function cancel(){revision++;controller?.abort('cancelled');cancelAnimationFrame(frame);disposeActive?.();disposeActive=null}
  window.BeastRenderScheduler={request,cancel,get revision(){return revision}};
})();
