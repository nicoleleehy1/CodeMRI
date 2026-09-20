let pending;
export function cancelNodeClick(){if(pending)clearTimeout(pending);pending=undefined;}
/** Delay single-click selection so its layout change cannot swallow a double-click. */
export function bindNodeInteractions(element,node,select,drill) {
  element.onclick=event=>{
    if(!drill){select(node);return;}
    cancelNodeClick();
    if((event?.detail||1)>1)return;
    pending=setTimeout(()=>{pending=undefined;select(node);},350);
  };
  element.ondblclick=event=>{event?.preventDefault?.();event?.stopPropagation?.();cancelNodeClick();(drill||select)(node);};
  element.onkeydown=event=>{
    if(event.key==='Enter'||event.key===' '){event.preventDefault();cancelNodeClick();(event.key==='Enter'&&drill?drill:select)(node);}
  };
}
