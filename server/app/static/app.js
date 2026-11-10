import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';
import {PLYLoader} from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/PLYLoader.js';
import {OrbitControls} from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js';

const form=document.querySelector('#upload'),job=document.querySelector('#job'),bar=document.querySelector('#progress'),message=document.querySelector('#message'),percent=document.querySelector('#percent'),result=document.querySelector('#result'),comparison=document.querySelector('#comparison'),mode=document.querySelector('#input-mode'),quality=document.querySelector('#reconstruction-quality'),video=document.querySelector('#video'),zed=document.querySelector('#zed'),colmap=document.querySelector('#colmap'),captureHelp=document.querySelector('#capture-help');
const agentUrl='http://127.0.0.1:9764',captureButton=document.querySelector('#capture-zed'),captureDuration=document.querySelector('#zed-duration');
const historyList=document.querySelector('#history-list'),refreshHistoryButton=document.querySelector('#refresh-history'),compareSlider=document.querySelector('#compare-slider'),compareBefore=document.querySelector('.compare-pane.before'),compareAfter=document.querySelector('.compare-pane.after'),compareDivider=document.querySelector('#compare-divider');
const mobileUrl=document.querySelector('#mobile-upload-url'),mobileQr=document.querySelector('#mobile-qr'),mobileQrButton=document.querySelector('#refresh-mobile-qr'),mobileUploadLink=document.querySelector('#open-mobile-upload'),mobileQrNote=document.querySelector('#mobile-qr-note'),mobileDialog=document.querySelector('#phone-upload-dialog'),openMobileDialogButton=document.querySelector('#open-mobile-upload-dialog'),closeMobileDialogButton=document.querySelector('#close-mobile-upload'),viewerPlaceholder=document.querySelector('#viewer-placeholder');
const viewerQuality=document.querySelector('#viewer-quality'),viewerNote=document.querySelector('#viewer-note'),viewerTitle=document.querySelector('#viewer-title'),expandViewerButton=document.querySelector('#expand-viewer'),expandComparisonButton=document.querySelector('#expand-comparison');
const activeJobList=document.querySelector('#active-job-list');
let reconstructionPoll={id:null,wasRunning:false,updatedAt:0},historyTimer,activeJobsTimer,viewerLoadToken=0;

const mobileAssetVersion='20260929-2';
function refreshMobileQr(){let url=mobileUrl.value.trim();try{const parsed=new URL(url);if(!['http:','https:'].includes(parsed.protocol))throw new Error();parsed.pathname='/mobile.html';parsed.search=`?v=${mobileAssetVersion}`;parsed.hash='';url=parsed.toString();mobileUrl.value=url;mobileUploadLink.href=url;mobileQr.src=`/api/mobile-upload-qr.svg?url=${encodeURIComponent(url)}`;mobileQrNote.textContent=location.hostname==='localhost'||location.hostname==='127.0.0.1'?'Per il telefono usa l’IP LAN del server al posto di localhost, poi premi Aggiorna QR.':'Il QR punta all’indirizzo indicato: il telefono deve poterlo raggiungere sulla stessa rete o tramite HTTPS pubblico.'}catch(error){mobileQr.removeAttribute('src');mobileUploadLink.removeAttribute('href');mobileQrNote.textContent='Inserisci un indirizzo HTTP o HTTPS valido, raggiungibile dal telefono.'}}
mobileUrl.value=`${location.origin}/mobile.html?v=${mobileAssetVersion}`;mobileQrButton.onclick=refreshMobileQr;mobileUrl.onchange=refreshMobileQr;openMobileDialogButton.onclick=()=>{refreshMobileQr();mobileDialog.showModal()};closeMobileDialogButton.onclick=()=>mobileDialog.close();mobileDialog.onclick=event=>{if(event.target===mobileDialog)mobileDialog.close()};refreshMobileQr();

async function start(response){response=await response;if(!response.ok)return alert(await response.text());const data=await response.json();reconstructionPoll={id:data.id,wasRunning:false,updatedAt:0};result.hidden=true;comparison.hidden=true;viewerPlaceholder.hidden=false;job.hidden=false;poll(data.id)}
function formatDuration(seconds){seconds=Math.max(0,Math.round(seconds));const hours=Math.floor(seconds/3600),minutes=Math.floor((seconds%3600)/60),secs=seconds%60;return hours?`${hours}h ${minutes}m`:(minutes?`${minutes}m ${secs}s`:`${secs}s`)}
function timingText(state){if(!state.started_at||state.status!=='running')return'';const elapsed=Date.now()/1000-state.started_at,base=` · trascorso ${formatDuration(elapsed)}`;if(Number.isFinite(state.eta_seconds))return `${base} · rimanenti ≈ ${formatDuration(state.eta_seconds)}`;if(state.message.includes('COLMAP'))return `${base} · stima disponibile dopo COLMAP`;if(state.progress<5)return base;const eta=elapsed*(100-state.progress)/state.progress;return `${base} · stima rimanente ≈ ${formatDuration(eta)}`}
const inputModeNames={rgb:'Video RGB',zed:'Pacchetto ZED',colmap:'Dataset COLMAP'},qualityNames={fast:'Rapida',balanced:'Bilanciata',high:'Alta',very_high:'Molto alta'};
function activeJobCard(item){const card=document.createElement('article'),header=document.createElement('div'),title=document.createElement('strong'),status=document.createElement('span'),meta=document.createElement('p'),detail=document.createElement('p'),progressRow=document.createElement('div'),percentage=document.createElement('strong'),progress=document.createElement('progress');card.className='active-job';header.className='active-job-header';title.textContent=`Job ${item.id.slice(0,8)}`;status.textContent=item.status==='queued'?'In attesa della GPU':'In elaborazione';header.append(title,status);meta.className='active-job-meta';meta.textContent=`Input: ${item.input_name||'non disponibile'} · ${inputModeNames[item.input_mode]||item.input_mode} · Preset: ${qualityNames[item.quality]||item.quality}`;detail.className='active-job-message';detail.textContent=item.message||'In attesa del worker';progressRow.className='active-job-progress';percentage.textContent=`${item.progress||0}%`;progress.max=100;progress.value=item.progress||0;progressRow.append(percentage);card.append(header,meta,detail,progressRow,progress);return card}
async function refreshActiveJobs(){clearTimeout(activeJobsTimer);try{const jobs=await fetch('/api/jobs',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error('richiesta non riuscita'))),active=jobs.filter(item=>['queued','running'].includes(item.status));activeJobList.replaceChildren(...active.map(activeJobCard));job.hidden=!active.length;if(active.length)activeJobsTimer=setTimeout(refreshActiveJobs,2000)}catch(error){activeJobsTimer=setTimeout(refreshActiveJobs,4000)}}
function updateInput(){const isZed=mode.value==='zed',isColmap=mode.value==='colmap';video.hidden=isZed||isColmap;video.required=!isZed&&!isColmap;zed.hidden=!isZed;zed.required=isZed;colmap.hidden=!isColmap;colmap.required=isColmap;captureHelp.textContent=isZed?'Carica uno ZIP con esattamente: recording.mp4, depth_data.dp e camera_data.dp nella radice.':isColmap?'Carica uno ZIP con images/ e sparse/0/{cameras.bin, images.bin, points3D.bin}. È consentita una sola cartella radice esterna.':'Video MP4, MOV, MKV o WebM. Il profilo agisce su frame, training e densità della mesh.'}
mode.onchange=updateInput;updateInput();
form.onsubmit=e=>{e.preventDefault();const isZed=mode.value==='zed',isColmap=mode.value==='colmap',data=new FormData();data.append(isZed?'capture':isColmap?'dataset':'video',isZed?zed.files[0]:isColmap?colmap.files[0]:video.files[0]);data.append('quality',quality.value);start(fetch(isZed?'/api/jobs/zed':isColmap?'/api/jobs/colmap':'/api/jobs',{method:'POST',body:data}))};

async function startDirectZed(){captureButton.disabled=true;job.hidden=false;result.hidden=true;comparison.hidden=true;message.textContent='Verifica del Capture Agent ZED locale…';bar.value=0;percent.textContent='0%';try{const health=await fetch(`${agentUrl}/health`).then(r=>r.ok?r.json():Promise.reject(new Error('agent non raggiungibile')));if(!health.zed_sdk_python)throw new Error('ZED SDK o binding Python non disponibile. Installa/avvia il Capture Agent su questo PC.');const capture=await fetch(`${agentUrl}/capture`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({server_url:location.origin,duration_seconds:Number(captureDuration.value),resolution:'HD1080',fps:15,quality:quality.value})}).then(r=>r.ok?r.json():r.text().then(t=>Promise.reject(new Error(t))));pollCaptureAgent(capture.id)}catch(error){message.textContent=`Cattura ZED non disponibile: ${error.message}`;captureButton.disabled=false}}
async function pollCaptureAgent(id){try{const state=await fetch(`${agentUrl}/capture/${id}`).then(r=>r.json());message.textContent=state.message;if(state.status==='completed'){captureButton.disabled=false;message.textContent='Cattura inviata: avvio elaborazione ZED sul server.';poll(state.remote_job_id);return}if(state.status==='failed'){captureButton.disabled=false;message.textContent=`Errore cattura ZED: ${state.message}`;return}setTimeout(()=>pollCaptureAgent(id),1500)}catch(error){captureButton.disabled=false;message.textContent=`Connessione al Capture Agent persa: ${error.message}`}}
captureButton.onclick=startDirectZed;

async function poll(id){
  if(reconstructionPoll.id!==id)reconstructionPoll={id,wasRunning:false,updatedAt:0};
  const state=await fetch(`/api/jobs/${id}`,{cache:'no-store'}).then(r=>r.json());
  const stale=(reconstructionPoll.wasRunning&&state.status==='queued')||(state.updated_at&&state.updated_at<reconstructionPoll.updatedAt);
  if(stale){setTimeout(()=>poll(id),1000);return}
  reconstructionPoll.updatedAt=Math.max(reconstructionPoll.updatedAt,state.updated_at||0);
  reconstructionPoll.wasRunning||=state.status==='running';
  bar.value=state.progress;percent.textContent=`${state.progress}%`;message.textContent=state.message+timingText(state);
  refreshActiveJobs();
  if(state.status==='completed'){displayResult(id);refreshHistory();return}if(state.status==='failed'){message.textContent=`Errore: ${state.message}`;return}setTimeout(()=>poll(id),2000)
}
function displayResult(id,name){const url=`/api/jobs/${id}/result`,glbButton=document.querySelector('#download-glb');closeComparison();viewerPlaceholder.hidden=true;result.hidden=false;viewerTitle.textContent=name||'Mesh 3D';viewerQuality.disabled=false;glbButton.disabled=false;document.querySelector('#download').href=url;document.querySelector('#download').download=`${id}.ply`;glbButton.onclick=()=>requestGlb(id,document.querySelector('#glb-quality').value,glbButton);viewerQuality.onchange=()=>loadViewerMesh(id);loadViewerMesh(id)}
function displayRepairedMesh(url,name){const glbButton=document.querySelector('#download-glb');closeComparison();viewerPlaceholder.hidden=true;result.hidden=false;viewerTitle.textContent=`${name||'Mesh 3D'} · riparata`;viewerQuality.disabled=true;viewerNote.textContent='Mesh riparata chiudendo solo piccoli bordi topologici, senza remesh globale.';document.querySelector('#download').href=url;document.querySelector('#download').download='mesh-riparata.ply';glbButton.disabled=true;renderMesh(document.querySelector('#viewer'),url)}
async function loadViewerMesh(jobId){const quality=viewerQuality.value,token=++viewerLoadToken;disposeMesh(document.querySelector('#viewer'));viewerNote.textContent=`Preparazione viewer ${viewerNames[quality]}…`;try{const response=await fetch(`/api/jobs/${jobId}/viewer/${quality}`,{method:'POST'});if(!response.ok)throw new Error(await response.text());const state=await response.json();if(state.status!=='completed')await waitForViewerMesh(jobId,quality);if(token!==viewerLoadToken)return;viewerNote.textContent=`Viewer ${viewerNames[quality]} pronto. Il PLY scaricato resta alla qualità originale.`;show(`/api/jobs/${jobId}/viewer/${quality}`)}catch(error){if(token!==viewerLoadToken)return;viewerNote.textContent=`Viewer non disponibile: ${error.message}`;document.querySelector('#viewer').textContent='Impossibile preparare questa mesh per il viewer.'}}
async function waitForViewerMesh(jobId,quality){for(;;){const jobs=await fetch('/api/jobs',{cache:'no-store'}).then(r=>r.json()),item=jobs.find(job=>job.id===jobId),state=item?.viewer?.[quality]?.status;if(state==='completed')return;if(state==='failed')throw new Error(item.viewer[quality].message||'semplificazione non riuscita');await new Promise(resolve=>setTimeout(resolve,2000))}}

function renderMesh(host,url){
  if(host._dispose)host._dispose();
  host.replaceChildren();
  const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(50,1,.01,1000),renderer=new THREE.WebGLRenderer({antialias:true}),controls=new OrbitControls(camera,renderer.domElement);
  let stopped=false,frame,radius=1,loaded=false;
  const fitCamera=()=>{const width=Math.max(host.clientWidth,1),height=Math.max(host.clientHeight,1);camera.aspect=width/height;camera.updateProjectionMatrix();renderer.setSize(width,height);if(!loaded)return;const verticalFov=THREE.MathUtils.degToRad(camera.fov),horizontalFov=2*Math.atan(Math.tan(verticalFov/2)*camera.aspect),distance=radius/Math.sin(Math.min(verticalFov,horizontalFov)/2)*1.18;camera.position.set(0,0,distance);controls.target.set(0,0,0);controls.minDistance=radius*.2;controls.maxDistance=radius*20;controls.update()};
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));host.append(renderer.domElement);scene.add(new THREE.HemisphereLight(0xffffff,0x222233,3));controls.enableDamping=true;controls.dampingFactor=.08;controls.autoRotate=true;controls.autoRotateSpeed=1.5;
  const observer=new ResizeObserver(fitCamera);observer.observe(host);fitCamera();
  host._dispose=()=>{stopped=true;cancelAnimationFrame(frame);observer.disconnect();controls.dispose();renderer.dispose()};
  new PLYLoader().load(url,geometry=>{if(stopped){geometry.dispose();return}geometry.computeVertexNormals();geometry.center();geometry.computeBoundingSphere();radius=Math.max(geometry.boundingSphere?.radius||1,.001);loaded=true;fitCamera();const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({vertexColors:true,roughness:.8,side:THREE.DoubleSide}));mesh.rotation.x=Math.PI;scene.add(mesh);(function animate(){if(stopped)return;frame=requestAnimationFrame(animate);controls.update();renderer.render(scene,camera)})()},undefined,()=>{if(!stopped)host.textContent='Impossibile caricare questa mesh.'})
}
const glbNames={low:'Bassa',medium:'Media',high:'Alta (piena)'},viewerNames={low:'Rapido (250k triangoli)',medium:'Bilanciato (750k triangoli)',high:'Dettagliato (1,5M triangoli)'};
async function requestGlb(jobId,quality,button){
  const originalLabel=button.textContent;button.disabled=true;button.textContent='Accodo GLB…';
  try{
    const response=await fetch(`/api/jobs/${jobId}/glb/${quality}`,{method:'POST'});
    if(!response.ok)throw new Error(await response.text());
    const state=await response.json();
    if(state.status==='completed'){window.location.assign(`/api/jobs/${jobId}/glb/${quality}`);return}
    button.textContent='Preparazione GLB…';
    await waitForGlb(jobId,quality);
    window.location.assign(`/api/jobs/${jobId}/glb/${quality}`);
  }catch(error){alert(`Impossibile preparare il GLB: ${error.message}`)}finally{button.disabled=false;button.textContent=originalLabel;refreshHistory()}
}
async function waitForGlb(jobId,quality){
  for(;;){
    const jobs=await fetch('/api/jobs',{cache:'no-store'}).then(r=>r.json()),item=jobs.find(job=>job.id===jobId),state=item?.glb?.[quality]?.status;
    if(state==='completed')return;
    if(state==='failed')throw new Error(item.glb[quality].message||'esportazione non riuscita');
    await new Promise(resolve=>setTimeout(resolve,2000));
  }
}
function disposeMesh(host){if(host._dispose)host._dispose();host.replaceChildren()}
function setPageViewer(card,button,expanded){card.classList.toggle('page-viewer',expanded);button.textContent=expanded?'Riduci':'Espandi';setTimeout(()=>window.dispatchEvent(new Event('resize')),0)}
function closeComparison(){setPageViewer(comparison,expandComparisonButton,false);disposeMesh(document.querySelector('#before-viewer'));disposeMesh(document.querySelector('#after-viewer'));comparison.hidden=true;if(result.hidden)viewerPlaceholder.hidden=false}
function closeViewer(){setPageViewer(result,expandViewerButton,false);viewerLoadToken++;disposeMesh(document.querySelector('#viewer'));result.hidden=true;if(comparison.hidden)viewerPlaceholder.hidden=false}
document.querySelector('#close-viewer').onclick=closeViewer;
document.querySelector('#close-comparison').onclick=closeComparison;
expandViewerButton.onclick=()=>setPageViewer(result,expandViewerButton,!result.classList.contains('page-viewer'));
expandComparisonButton.onclick=()=>setPageViewer(comparison,expandComparisonButton,!comparison.classList.contains('page-viewer'));
function show(url){closeComparison();renderMesh(document.querySelector('#viewer'),url)}
function updateComparisonDivider(){const position=`${compareSlider.value}%`;compareBefore.style.width=position;compareAfter.style.left=position;compareAfter.style.width=`${100-Number(compareSlider.value)}%`;compareDivider.style.left=position}
compareSlider.oninput=updateComparisonDivider;updateComparisonDivider();
function compareMeshes(rawUrl,processedUrl){closeViewer();viewerPlaceholder.hidden=true;comparison.hidden=false;updateComparisonDivider();renderMesh(document.querySelector('#before-viewer'),rawUrl);renderMesh(document.querySelector('#after-viewer'),processedUrl);comparison.scrollIntoView({behavior:'smooth',block:'center'})}

function historyDate(timestamp){return timestamp?new Date(timestamp*1000).toLocaleString('it-IT',{dateStyle:'short',timeStyle:'short'}):'—'}
async function renameMesh(item){const name=prompt('Nome della mesh',item.mesh_name||`Mesh ${item.id.slice(0,8)}`);if(name===null)return;const response=await fetch(`/api/jobs/${item.id}/mesh-name`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});if(!response.ok){alert(await response.text());return}refreshHistory()}
async function postprocessMesh(item){const response=await fetch(`/api/jobs/${item.id}/postprocess`,{method:'POST'});if(!response.ok){alert(await response.text());return}await refreshHistory()}
async function deleteMesh(item){const name=item.mesh_name||`Mesh ${item.id.slice(0,8)}`;if(!confirm(`Eliminare definitivamente “${name}”?\\n\\nSaranno rimossi anche file di input, output PLY/GLB e log di questa ricostruzione.`))return;const response=await fetch(`/api/jobs/${item.id}`,{method:'DELETE'});if(!response.ok){alert(await response.text());return}closeViewer();closeComparison();await refreshHistory()}
function makeButton(label,action,disabled=false,className=''){const button=document.createElement('button');button.type='button';button.textContent=label;button.disabled=disabled;button.onclick=action;button.className=className;return button}
async function updatePostprocessCards(){
  try{
    const jobs=(await fetch('/api/jobs',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error('richiesta non riuscita')))).filter(item=>item.has_result);
    let redraw=false,active=false;
    for(const item of jobs){
      const row=historyList.querySelector(`[data-job-id="${item.id}"]`),processing=['queued','running'].includes(item.postprocess_status);
      if(!row){redraw=true;break}
      if(row.dataset.postprocessStatus!==item.postprocess_status){redraw=true;break}
      if(processing){active=true;const progress=row.querySelector('.postprocess-progress'),status=row.querySelector('.postprocess-status');if(progress)progress.value=item.postprocess_progress||0;if(status)status.textContent=`${item.postprocess_progress||0}% · ${item.postprocess_message||'In attesa del worker'}`}
    }
    if(redraw){refreshHistory();return}
    if(active)historyTimer=setTimeout(updatePostprocessCards,2000);
  }catch(error){historyTimer=setTimeout(updatePostprocessCards,4000)}
}
async function refreshHistory(){
  clearTimeout(historyTimer);
  historyList.replaceChildren();
  try{
    const jobs=(await fetch('/api/jobs',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error('richiesta non riuscita')))).filter(item=>item.has_result);
    if(!jobs.length){historyList.innerHTML='<p class="note">Nessuna mesh 3D completata disponibile.</p>';return}
    for(const item of jobs){
      const row=document.createElement('article'),top=document.createElement('div'),title=document.createElement('strong'),meta=document.createElement('span'),detail=document.createElement('p'),actions=document.createElement('div'),primaryActions=document.createElement('div'),downloadActions=document.createElement('div'),managementActions=document.createElement('div'),rawUrl=`/api/jobs/${item.id}/result`,processedUrl=`/api/jobs/${item.id}/processed-result`;
      row.className='history-item completed';row.dataset.jobId=item.id;row.dataset.postprocessStatus=item.postprocess_status;title.textContent=item.mesh_name||`Mesh ${item.id.slice(0,8)}`;meta.textContent=historyDate(item.updated_at);detail.textContent=`ID: ${item.id}`;top.append(title,meta);
      actions.className='history-actions';primaryActions.className='action-group';downloadActions.className='action-group';managementActions.className='action-group management-group';primaryActions.append(makeButton('Visualizza',()=>{displayResult(item.id,item.mesh_name||`Mesh ${item.id.slice(0,8)}`);document.querySelector('#viewer').scrollIntoView({behavior:'smooth',block:'center'})},false,'primary'));primaryActions.append(makeButton('Gaussian preview',()=>window.open(`/gaussian.html?job=${item.id}`,'pavarotti-gaussian-preview')));
      const processing=['queued','running'].includes(item.postprocess_status);
      if(item.has_processed){primaryActions.append(makeButton('Visualizza riparata',()=>displayRepairedMesh(processedUrl,item.mesh_name||`Mesh ${item.id.slice(0,8)}`),false,'primary'));primaryActions.append(makeButton('Confronta riparazione',()=>compareMeshes(rawUrl,processedUrl)))}else{primaryActions.append(makeButton(processing?'Riparazione piccoli buchi in corso…':'Ripara piccoli buchi',()=>postprocessMesh(item),processing))}
      managementActions.append(makeButton('Rinomina',()=>renameMesh(item)));
      managementActions.append(makeButton('Elimina',()=>deleteMesh(item),processing,'danger'));
      downloadActions.append(makeButton('Scarica PLY',()=>window.location.assign(rawUrl)));
      const quality=document.createElement('select');for(const name of ['low','medium','high']){const option=document.createElement('option');option.value=name;option.textContent=glbNames[name];if(name==='medium')option.selected=true;quality.append(option)}
      const glbQuality=document.createElement('label');glbQuality.className='download-quality';glbQuality.append('Qualità GLB',quality);
      const glbButton=makeButton('Scarica GLB',()=>requestGlb(item.id,quality.value,glbButton));downloadActions.append(glbQuality,glbButton);
      actions.append(primaryActions,downloadActions,managementActions);
      row.append(top,detail,actions);
      if(processing){const progress=document.createElement('progress'),status=document.createElement('p');progress.className='postprocess-progress';progress.max=100;progress.value=item.postprocess_progress||0;status.className='note postprocess-status';status.textContent=`${item.postprocess_progress||0}% · ${item.postprocess_message||'In attesa del worker'}`;row.append(status,progress)}
      if(item.postprocess_status==='failed'){const note=document.createElement('p');note.className='note';note.textContent='L’elaborazione della mesh non è riuscita: puoi riprovare.';row.append(note)}
      historyList.append(row);
    }
    if(jobs.some(item=>['queued','running'].includes(item.postprocess_status)))historyTimer=setTimeout(updatePostprocessCards,2000);
  }catch(error){historyList.innerHTML='<p class="note">Catalogo mesh non disponibile: riprova tra poco.</p>'}
}
refreshHistoryButton.onclick=refreshHistory;refreshHistory();refreshActiveJobs();
