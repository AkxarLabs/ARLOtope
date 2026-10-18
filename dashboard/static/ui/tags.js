/* Free labels, shared by study records and declarative workflow metadata. */
(function(){
  const N=window.NL,{html,useState,useEffect,useRef}=N;
  N.normalizeTags=value=>[...new Set((Array.isArray(value)?value:String(value||'').split(',')).map(t=>t.trim().toLocaleLowerCase().replace(/\s+/g,'-')).filter(Boolean))];
  N.Tags=({value=[]})=>value.length?html`<span class="tags">${value.map(tag=>html`<span class="tag">${tag}</span>`)}</span>`:null;
  let count=0;
  N.TagInput=({value=[],onChange,suggestions=[],ariaLabel='Tags'})=>{
    const [text,setText]=useState(value.join(', ')),focused=useRef(false),[id]=useState(()=>'tag-options-'+(++count));
    useEffect(()=>{if(!focused.current)setText(value.join(', '))},[JSON.stringify(value)]);
    const prefix=text.includes(',')?text.slice(0,text.lastIndexOf(',')+1)+' ':'';
    const options=[...new Set([...suggestions,...(N.getState()?.tags||[])])];
    return html`<span class="tag-input"><input class="input" aria-label=${ariaLabel} list=${id} value=${text} placeholder="e.g. replication, vision" onFocus=${()=>{focused.current=true}}
      onInput=${e=>{setText(e.target.value);onChange(N.normalizeTags(e.target.value))}} onBlur=${()=>{focused.current=false;setText(N.normalizeTags(text).join(', '))}}/>
      <datalist id=${id}>${options.filter(tag=>!value.includes(tag)).map(tag=>html`<option value=${prefix+tag}/>` )}</datalist></span>`;
  };
  N.StudyTags=({it})=>{
    const [value,setValue]=useState(it.tags||[]),[saved,setSaved]=useState(it.tags||[]);
    useEffect(()=>{setValue(it.tags||[]);setSaved(it.tags||[])},[it.id,JSON.stringify(it.tags)]);
    const save=async()=>{const r=await N.act('/api/study/tags',{study:it.id,tags:value},'Tags saved');if(r.ok)setSaved(r.tags)};
    return html`<details class="study-tags"><summary>Tags ${it.tags?.length?html`<${N.Tags} value=${it.tags}/>`:null}</summary><div class="row"><${N.TagInput} value=${value} onChange=${setValue}/><${N.Btn} small disabled=${JSON.stringify(value)===JSON.stringify(saved)} onClick=${save}>Save tags</${N.Btn}></div></details>`;
  };
})();
