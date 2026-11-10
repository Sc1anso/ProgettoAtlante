# Installazione, utilizzo e gestione — Progetto ATLANTE

Questa guida copre Linux nativo e WSL2, installazione, modalità disponibili, operazioni e diagnostica. Per l'introduzione al progetto vedere il [README principale](../README.md).

## 1. Requisiti

- Host x86_64 Linux (CentOS/RHEL/Rocky/Alma 9, Ubuntu o Debian) oppure WSL2.
- GPU NVIDIA, driver compatibile con CUDA 12.1 e NVIDIA Container Toolkit; build di riferimento Tesla V100/compute capability 7.0.
- Minimo pratico: 8 core CPU, 32 GB RAM, GPU con 16 GB VRAM e 100 GB SSD liberi. Consigliati 16+ core, 64 GB RAM, più VRAM e 250 GB+ NVMe per job pesanti.
- Docker Engine con Compose v2. In WSL: Docker Desktop in esecuzione, WSL integration e GPU attiva. Tenere il progetto nel filesystem Linux della distro, non in `/mnt/c`.
- Internet per il primo build/scaricamento dipendenze e per il modello rembg al primo job che ne ha bisogno.

Sono valori indicativi: il consumo dipende da durata/risoluzione del video, FPS del preset e dimensione della mesh.

## 2. Installazione e avvio

Dalla radice del progetto:

```bash
bash server/setup-service.sh
```

Lo script configura prerequisiti dove supportato, verifica l'accesso GPU da Docker, costruisce e avvia Redis, API/UI e un worker GPU. Apri `http://localhost:8084` da Windows/WSL oppure `http://IP-DEL-SERVER:8084` dalla LAN.

Per host a due GPU si può abilitare un secondo worker:

```bash
PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/setup-service.sh
```

Per l'uso quotidiano, dalla radice:

```bash
bash server/start-service.sh
bash server/stop-service.sh
```

Lo start non ricostruisce le immagini. Lo stop conserva i volumi. Evita `docker compose down -v` se vuoi mantenere job e mesh.

### WSL2

Installa il driver NVIDIA WSL su Windows e Docker Desktop con WSL integration abilitata. Nella distro verifica `nvidia-smi`, `docker compose version` e `docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi`. Poi lancia il setup come sopra. Non installare un driver Linux NVIDIA separato dentro WSL.

### HTTPS opzionale

Il profilo Caddy termina TLS sulla porta 8443 e richiede DNS pubblico e challenge ACME raggiungibile dalla porta TCP 80. La porta pubblica 80 deve essere inoltrata al container; aprire/inoltrare anche 8443 per raggiungere la UI HTTPS. La configurazione inclusa non offre DNS challenge: se la porta 80 non è accessibile, l'emissione automatica del certificato non funzionerà.

```bash
PAVAROTTI_ENABLE_HTTPS=1 PAVAROTTI_PUBLIC_HOST=atlante.example.org bash server/setup-service.sh
```

Dopo il setup apri `https://atlante.example.org:8443`. Il QR usa l'origine HTTPS quando la UI viene aperta tramite tale indirizzo. Non sono presenti login o autenticazione: non pubblicare il servizio direttamente su Internet; predisporre reverse proxy autenticato, limiti upload e policy di conservazione.

### Gaussian Monitor opzionale

Il Monitor usa GPU 0 e un container desktop noVNC separato. Non viene costruito dal setup predefinito:

```bash
PAVAROTTI_ENABLE_MONITOR=1 bash server/setup-service.sh
```

Oppure dalla directory `server`:

```bash
docker compose --profile monitor build monitor
docker compose --profile monitor up -d monitor
```

Porta `50001` (per esempio `http://IP-DEL-SERVER:50001/vnc.html`). È in sola lettura sul volume dei job, ma può competere per VRAM con il worker GPU 0.

## 3. Modalità d'ingresso

- **Video RGB**: estrazione dei frame in base al preset, filtraggio frame mossi, mascheramento/raffinamento, COLMAP GPU, training RaDe-GS, estrazione mesh e preparazione delle viste web.
- **Dataset COLMAP già preparato**: ZIP validato ed estratto in un'area isolata del job; salta frame extraction, COLMAP, rembg e DiGS; esegue RaDe-GS ed estrazione mesh direttamente.

Il formato ZIP COLMAP supporta sia le directory del dataset alla radice, sia un'unica directory radice contenitore. Requisiti minimi:

```text
dataset.zip
└── nome-scena/                 # opzionale
    ├── images/
    │   └── 0001.jpg
    └── sparse/0/
        ├── cameras.bin
        ├── images.bin
        └── points3D.bin
```

`images/` deve contenere almeno un PNG/JPG/JPEG. `input/` può essere mantenuta; cartelle ausiliarie come `masks/`, `input_masks/`, `distorted/` o `stereo/` sono opzionali. Sono rifiutati path non sicuri, symlink, duplicati, dataset incompleti e archivi oltre i limiti di sicurezza. Scene `*_densified` prodotte da DiGS sono candidate utili: il flusso COLMAP diretto non esegue una nuova densificazione.

Il flusso ZED/DiGS rimane nel codice backend per compatibilità e per input agent già supportati; non è esposto come selezione ordinaria nell'interfaccia corrente.

## 4. Preset, risultati e persistenza

I profili RGB sono Rapida, Bilanciata, Alta e Molto alta; aumentando il preset aumentano frame elaborati, iterazioni/qualità della ricostruzione, durata e spazio necessario. Le card di avanzamento sono separate per job. Un worker gestisce un job alla volta; job aggiuntivi attendono la GPU finché il worker non si libera.

Il file sorgente è `output/recon.ply`. Preset viewer, GLB, gaussian preview e riparazioni conservative sono output derivati. I job sono nel volume `job-data`; i modelli rembg nel volume `rembg-models`. Salvaguardare i volumi e predisporre un backup se i dati hanno valore. `docker compose down` non elimina i volumi; `docker compose down -v` li cancella.

## 5. Comandi operativi

Da `server/`:

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker-v100-0
docker compose restart
docker compose up -d
# Monitor opzionale
docker compose --profile monitor logs -f monitor
```

Per aggiornare codice o immagini, dalla directory `server`: `docker compose build` e poi `docker compose up -d`. La ricreazione di un worker interrompe un task in esecuzione; verifica prima che non ci siano job attivi.

## 6. Troubleshooting

| Problema | Controllo |
| --- | --- |
| UI non raggiungibile | `docker compose ps`, porta 8084 e firewall host. |
| Nessuna GPU | `nvidia-smi` sull'host e test `docker run --rm --gpus all ... nvidia-smi`; verificare toolkit NVIDIA o WSL integration. |
| Job in attesa GPU | Controllare worker e job già attivi; è comportamento normale con un job per worker. |
| Job fallito | `docker compose logs -f worker-v100-0` e `worker.log` nel volume job-data. |
| COLMAP non ricostruisce | Ripresa con più sovrapposizione, frame nitidi, texture e parallax; evitare soggetto mosso e riflessi. |
| Mesh con sfondo/rumore | Migliorare ripresa, separazione e maschere; riparazione buchi non rimuove l'ambiente. |
| HTTPS certificato non emesso | Verificare DNS e raggiungibilità pubblica della porta 80 per ACME, oltre a 8443 per il servizio. |
| Monitor irraggiungibile | `docker compose --profile monitor ps`, porta 50001 e profilo monitor attivo. |

## 7. Riferimenti

- [Manuale utente](../docs/Manuale_utente_Progetto_ATLANTE.md)
- [Report tecnico](../docs/Report_tecnico_Progetto_ATLANTE.md)
- [Note licenze e terze parti](../THIRD_PARTY_NOTICES.md)
