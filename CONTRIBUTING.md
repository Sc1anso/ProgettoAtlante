# Contribuire a Progetto ATLANTE

Prima di proporre una modifica, leggi il [README](README.md), la [guida operativa](server/DEPLOYMENT_AND_USAGE.md) e le [note sulle licenze](THIRD_PARTY_NOTICES.md). Il repository integra componenti con licenze indipendenti: non cambiare o rimuovere i relativi avvisi e non aggiungere una licenza globale senza una verifica dei diritti.

## Regole per le modifiche

- Non aggiungere dataset storici, video di utenti, output di job, checkpoint, credenziali o file `server/.env`.
- Mantieni fuori dal versionamento build CUDA/CMake, cache, volumi e output. Per file binari grandi da distribuire, verifica prima i diritti e usa Git LFS solo se necessario.
- Mantieni i flussi RGB e COLMAP coerenti con le guide; documenta esplicitamente cambiamenti a modalità, parametri, porte o persistenza.
- Evita di esporre API/noVNC senza autenticazione. Non inserire indirizzi IP, token o hostname privati nella documentazione.

## Verifiche locali

Per modifiche ai container controlla la sintassi degli script (`bash -n ...`) e la configurazione Compose (`cd server && docker compose config --quiet`). I test automatici specifici vanno eseguiti quando sono disponibili le dipendenze previste dal container. Non lanciare un training reale come controllo ordinario: richiede GPU, tempo e spazio di storage.

Le build CUDA possono essere lunghe e richiedere molta memoria. Specifica nel contributo i comandi di verifica effettivamente eseguiti e quelli non eseguiti.
