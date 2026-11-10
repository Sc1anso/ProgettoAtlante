# Server: installazione e avvio

Per installazione completa, requisiti Linux/WSL, flussi supportati e troubleshooting vedere [DEPLOYMENT_AND_USAGE.md](DEPLOYMENT_AND_USAGE.md). Per una panoramica del repository consultare il [README principale](../README.md).

## Setup e uso quotidiano

Dalla radice del progetto:

```bash
bash server/setup-service.sh
bash server/start-service.sh
bash server/stop-service.sh
```

Il setup costruisce le immagini e avvia Redis, API/UI e un worker GPU. Lo start riavvia i container già creati senza rebuild; lo stop preserva i volumi Docker (job, mesh e cache). Non eseguire `docker compose down -v` se si vogliono conservare i risultati.

Opzioni facoltative:

```bash
PAVAROTTI_ENABLE_SECOND_GPU=1 bash server/setup-service.sh
PAVAROTTI_ENABLE_MONITOR=1 bash server/setup-service.sh
PAVAROTTI_ENABLE_HTTPS=1 PAVAROTTI_PUBLIC_HOST=atlante.example.org bash server/setup-service.sh
```

La seconda GPU e il monitor richiedono hardware adeguato. HTTPS usa Caddy: la porta 80 pubblica deve essere raggiungibile per il certificato ACME; la UI HTTPS è esposta sulla 8443. Serve un hostname DNS pubblico. Non è configurata autenticazione: non esporre il servizio direttamente su Internet.

## Compose e log

Dalla directory `server`:

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker-v100-0
docker compose --profile monitor logs -f monitor
```

I dati persistenti si trovano nei volumi `job-data` e `rembg-models`. Vedere `DEPLOYMENT_AND_USAGE.md` per i dettagli di retention, backup, HTTPS, formati ZIP e limiti operativi.
