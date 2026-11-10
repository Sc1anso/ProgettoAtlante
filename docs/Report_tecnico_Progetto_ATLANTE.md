# Report tecnico — Progetto ATLANTE

Documento tecnico di architettura, requisiti, installazione e gestione operativa. I dettagli dei flussi e della UI sono nella [guida di deployment](../server/DEPLOYMENT_AND_USAGE.md) e nel [manuale utente](Manuale_utente_Progetto_ATLANTE.md).

## Architettura

- **API/UI**: FastAPI serve la webapp, API job, storico, visualizzatori e download sulla porta TCP 8084.
- **Coda**: Redis e Celery coordinano job isolati nel volume Docker persistente `job-data`.
- **Worker GPU**: uno per default, facoltativamente un secondo tramite profilo `dual-gpu`; ogni worker processa un job per volta.
- **Pipeline RGB**: estrazione/filtraggio frame, creazione e raffinamento maschere, COLMAP su GPU, training RaDe-GS, estrazione `recon.ply` e generazione preset viewer.
- **Dataset COLMAP**: validazione ZIP, estrazione isolata, training RaDe-GS ed estrazione mesh senza ripetere frame, COLMAP, rembg o DiGS.
- **Servizi opzionali**: Gaussian Monitor/noVNC sulla porta 50001; Caddy per TLS sulla porta 8443, con porta 80 necessaria alla verifica ACME.

I risultati derivati (preset alleggeriti, GLB, riparazioni conservative e video preview) non sostituiscono il PLY originale. I dati sono nei volumi Docker; rimuovere i container non rimuove i volumi, mentre `docker compose down -v` li elimina.

## Requisiti di sistema

| Risorsa | Minimo pratico | Consigliato |
| --- | --- | --- |
| Sistema | Linux x86_64 o WSL2 | Linux nativo per un host server dedicato |
| GPU | NVIDIA con 16 GB VRAM, compatibilità da verificare | Tesla V100 o GPU validata con lo stack CUDA 12.1; più VRAM per preset elevati |
| CPU | 8 core | 16+ core per build e preprocessing |
| RAM | 32 GB | 64 GB per video/mesh grandi |
| Storage libero | 100 GB SSD | 250 GB+ NVMe, oltre allo spazio per job, checkpoint e cache Docker |
| Software | Docker Compose v2, driver NVIDIA, NVIDIA Container Toolkit | WSL2 + Docker Desktop/WSL integration se su Windows |

Sono valori di pianificazione, non garanzie di capacità: risoluzione e durata del video, numero di frame, preset e mesh incidono molto su VRAM, tempo e storage. Il primo build compila componenti CUDA ed è oneroso; la prima elaborazione può scaricare il modello rembg.

### Note per WSL2

Usare WSL2 e driver NVIDIA per WSL installati su Windows; Docker Desktop deve essere avviato con integrazione abilitata per la distribuzione. Non installare un driver NVIDIA Linux separato nella distro WSL. Tenere il repository nel filesystem Linux (non `/mnt/c`) e verificare `nvidia-smi` e l'accesso GPU Docker prima del setup.

## Installazione e avvio

Dal root del progetto:

```bash
bash server/setup-service.sh
```

Lo script supporta CentOS/RHEL/Rocky/Alma 9, Ubuntu, Debian e WSL2 con Docker Desktop già predisposto. Configura i prerequisiti quando possibile, verifica l'accesso GPU al container, costruisce e avvia Redis, API e worker. UI su `http://localhost:8084` in WSL oppure `http://IP-DEL-SERVER:8084` in LAN.

```bash
bash server/start-service.sh  # riavvio senza rebuild
bash server/stop-service.sh   # arresto, volumi conservati
```

Secondo worker: `PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/setup-service.sh`. Monitor: `PAVAROTTI_ENABLE_MONITOR=1 bash server/setup-service.sh` (build separata e uso GPU 0). Consultare la guida server per log, aggiornamento, backup e troubleshooting.

### HTTPS e sicurezza

HTTPS è opzionale e richiede un hostname DNS pubblico e raggiungibilità della porta TCP 80 per il challenge ACME. Configurazione d'esempio:

```bash
PAVAROTTI_ENABLE_HTTPS=1 PAVAROTTI_PUBLIC_HOST=atlante.example.org bash server/setup-service.sh
```

L'endpoint HTTPS usa la porta 8443. Il servizio non include login/autenticazione, quote di upload o gestione utenti; TLS da solo non è sufficiente per esporre l'app a Internet. Prima di un deploy pubblico servono autenticazione, limiti upload, firewall, backup e retention definiti. Evitare di versionare `server/.env` o dati reali.

## Preparazione repo e distribuzione

Il repository locale è preparato sul branch `main`, senza remote GitHub e senza push. Il sample video (circa 203 MB) è configurato con Git LFS. I file `.env`, dati, output, cache e artefatti compilati sono esclusi. Le fonti upstream hanno termini indipendenti, inclusi vincoli non commerciali: vedere [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Prima di una pubblicazione pubblica occorre confermare i diritti su sorgenti, modello, dataset e demo media; non è stata assegnata una licenza complessiva.
