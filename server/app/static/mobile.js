const form=document.querySelector('#mobile-upload');
const gallery=document.querySelector('#mobile-gallery');
const camera=document.querySelector('#mobile-camera');
const quality=document.querySelector('#mobile-quality');
const button=document.querySelector('#mobile-submit');
const status=document.querySelector('#mobile-status');
const fileName=document.querySelector('#mobile-file-name');
const securityNote=document.querySelector('#mobile-security-note');
let selectedFile=null;

function selectVideo(file){
  if(!file)return;
  selectedFile=file;
  fileName.textContent=`Selezionato: ${file.name} (${(file.size/1024/1024).toFixed(1)} MB)`;
  status.textContent='Video pronto per l’invio.';
  button.disabled=false;
}

gallery.onchange=()=>selectVideo(gallery.files[0]);
camera.onchange=()=>selectVideo(camera.files[0]);
if(location.protocol!=='https:'&&location.hostname!=='localhost'&&location.hostname!=='127.0.0.1'){
  securityNote.hidden=false;
  securityNote.textContent='Connessione HTTP: la scelta del file può funzionare sulla rete locale, ma per upload affidabili da rete esterna usa l’indirizzo HTTPS del server.';
}

function upload(data){
  return new Promise((resolve,reject)=>{
    const request=new XMLHttpRequest();
    request.open('POST','/api/jobs');
    request.responseType='json';
    request.upload.onprogress=event=>{
      if(event.lengthComputable){
        const percent=Math.round(event.loaded/event.total*100);
        status.textContent=`Caricamento del video… ${percent}%`;
      }
    };
    request.onload=()=>{
      const body=request.response||request.responseText;
      if(request.status<200||request.status>=300){
        const detail=typeof body==='string'?body:JSON.stringify(body);
        reject(new Error(detail||`risposta HTTP ${request.status}`));
        return;
      }
      resolve(body);
    };
    request.onerror=()=>reject(new Error('connessione al server non riuscita. Verifica di usare l’indirizzo HTTPS corretto o che telefono e server siano sulla stessa rete.'));
    request.ontimeout=()=>reject(new Error('tempo massimo di caricamento superato. Riprova con Wi‑Fi stabile o un video più breve.'));
    request.timeout=20*60*1000;
    request.send(data);
  });
}

form.onsubmit=async event=>{
  event.preventDefault();
  if(!selectedFile)return;
  button.disabled=true;
  status.textContent='Preparazione del caricamento…';
  const data=new FormData();
  data.append('video',selectedFile);
  data.append('quality',quality.value);
  try{
    const job=await upload(data);
    status.textContent=`Video ricevuto. Elaborazione avviata (ID ${job.id.slice(0,8)}). Puoi tornare alla webapp sul computer per seguirla.`;
    form.reset();
    selectedFile=null;
    fileName.textContent='Nessun video selezionato.';
  }catch(error){
    status.textContent=`Upload non riuscito: ${error.message}`;
  }finally{
    button.disabled=!selectedFile;
  }
};
