# Progetto ATLANTE

Webapp locale per ricostruire e consultare mesh 3D a partire da video RGB o da scene COLMAP già preparate. Il progetto coordina RaDe-GS, COLMAP, elaborazione delle maschere, estrazione della mesh e viewer nel browser tramite Docker Compose.

> **Stato e licenze:** questa è una preparazione locale del repository, non è stata effettuata alcuna pubblicazione GitHub. Il codice integra componenti di ricerca con licenze e condizioni proprie, alcune non commerciali. Leggere [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) e ottenere le autorizzazioni necessarie prima di redistribuire o rendere pubblico il repository. Non è stata aggiunta una licenza globale al progetto.

## Funzionalità

- Ricostruzione da video RGB e da ZIP di dataset COLMAP esistenti.
- Preset di elaborazione (Rapida, Bilanciata, Alta, Molto alta) e card di avanzamento per job.
- Storico delle mesh, viewer mesh e Gaussian, download PLY/GLB e strumenti conservativi per piccoli buchi.
- Upload da telefono tramite QR; HTTPS è una configurazione opzionale, non attiva per impostazione predefinita.
- Gaussian Splatting Monitor opzionale, eseguito in un container separato.

Il flusso RGB prepara frame e maschere, esegue COLMAP e RaDe-GS, quindi estrae `recon.ply`. Il flusso COLMAP accetta un archivio ZIP con `images/` e `sparse/0/{cameras.bin,images.bin,points3D.bin}` e salta preprocessing e COLMAP. I risultati e i job sono conservati nel volume Docker `job-data`; cache rembg nel volume `rembg-models`.

## Requisiti

- Linux x86_64 oppure WSL2; Docker Engine/Compose v2 (o Docker Desktop con integrazione WSL).
- GPU NVIDIA compatibile, driver host e NVIDIA Container Toolkit; il riferimento di build è CUDA 12.1 / Tesla V100.
- Consigliati almeno 8 core CPU, 32 GB RAM, 16 GB VRAM e 100 GB di spazio libero; video lunghi e preset elevati richiedono sensibilmente più risorse.
- Accesso Internet per la prima build e per scaricare dipendenze/modelli. In WSL conservare il checkout nel filesystem Linux, non sotto `/mnt/c`.

## Avvio rapido

Dalla radice del repository:

```bash
bash server/setup-service.sh
```

La webapp è disponibile su `http://localhost:8084` (WSL) oppure `http://IP-DEL-SERVER:8084` (Linux). Gli script `server/start-service.sh` e `server/stop-service.sh` avviano e fermano i container mantenendo i volumi. Per due GPU: `PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/setup-service.sh`.

Per avviare l'opzionale Gaussian Monitor durante il setup: `PAVAROTTI_ENABLE_MONITOR=1 bash server/setup-service.sh`.

HTTPS richiede un hostname DNS raggiungibile e l'accesso alla porta pubblica TCP 80 per il certificato ACME; il servizio HTTPS è pubblicato sulla porta 8443. La configurazione attuale non include autenticazione: non esporre direttamente la webapp o noVNC a Internet.

## Documentazione

- [Guida installazione, uso e troubleshooting](server/DEPLOYMENT_AND_USAGE.md)
- [README operativo del server](server/README.md)
- [Manuale utente (Markdown)](docs/Manuale_utente_Progetto_ATLANTE.md) · [PDF/DOCX impaginato](docs/Manuale_utente_Progetto_ATLANTE.docx)
- [Report tecnico (Markdown)](docs/Report_tecnico_Progetto_ATLANTE.md) · [DOCX impaginato](docs/Report_tecnico_Progetto_ATLANTE.docx)
- [Note sui componenti e sulle licenze](THIRD_PARTY_NOTICES.md)
- [Linee guida per contribuire](CONTRIBUTING.md)

## Repository e file voluminosi

Il video demo `server/samples/pavarotti-demo.mp4` è mantenuto per compatibilità con l'endpoint demo, ma supera il limite ordinario di upload GitHub: è configurato per Git LFS. Per un clone completo occorre avere Git LFS installato. I file locali `.env`, dataset, job, output e artefatti compilati sono esclusi dal versionamento.

Prima di pubblicare il repository, confermare i diritti sul video demo e su ogni sorgente upstream; non inserire dati o credenziali locali.
