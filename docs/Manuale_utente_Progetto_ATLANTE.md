# Manuale utente — Progetto ATLANTE

Guida alla preparazione del video, all'avvio di una ricostruzione e alla consultazione dei risultati. La versione DOCX impaginata accompagna questo file.

## 1. Preparare una buona ripresa

La ricostruzione non può recuperare superfici mai riprese. Mantieni immobile il soggetto e muovi lentamente la camera:

- gira attorno al soggetto per almeno 180°, preferibilmente 360°, con distanza costante e ampie sovrapposizioni tra viste;
- esegui un secondo giro a un'altezza diversa, includendo viste oblique e le parti superiori/inferiori visibili;
- usa luce diffusa e uniforme, fuoco stabile e ripresa nitida; evita scatti, zoom digitale, motion blur e cambi repentini di esposizione;
- scegli uno sfondo semplice e distante; riduci riflessi, superfici trasparenti o lucide e oggetti in movimento;
- mantieni il soggetto interamente nell'inquadratura e abbastanza grande nel frame.

Se lo sfondo occupa molto spazio o le maschere includono l'ambiente, semplificare la scena e separare il soggetto dallo sfondo spesso aiuta più di un post-processing aggressivo.

## 2. Avviare un job

1. In **Nuova ricostruzione**, scegli **Video RGB** per caricare MP4, MOV, MKV o WebM. In alternativa scegli **Dataset COLMAP già preparato** e carica uno ZIP contenente `images/` e `sparse/0/{cameras.bin,images.bin,points3D.bin}`; è supportata anche una singola cartella radice esterna nello ZIP.
2. Seleziona il preset: **Rapida** per prove, **Bilanciata** per uso ordinario, **Alta** o **Molto alta** per riprese pulite quando sono disponibili più tempo e VRAM.
3. Seleziona il file e premi **Avvia ricostruzione**. Da telefono premi **Carica da telefono · QR**, scansiona il codice e scegli **Scegli dalla galleria** o **Registra video**.
4. Segui la card specifica del job: mostra identificativo, input, preset, fase e percentuale. Ogni GPU worker elabora un job alla volta; quello successivo può rimanere in attesa.

Nel flusso RGB il server estrae e filtra i frame, prepara/raffina le maschere, esegue COLMAP e RaDe-GS e ricava la mesh. Nel flusso COLMAP già pronto vengono saltati estrazione frame, mascheramento, COLMAP e DiGS. Le scene `*_densified` prodotte da DiGS sono adatte se conservano la struttura richiesta.

## 3. Archivio delle mesh e viewer

Dallo storico puoi rinominare o eliminare una ricostruzione, scaricare il PLY originale o scegliere una qualità per il GLB. **Qualità GLB** si riferisce solo all'esportazione GLB; il PLY originale resta alla qualità prodotta dal job.

**Visualizza** apre il viewer mesh: trascina per ruotare, usa la rotella per zoomare e il tasto destro per traslare. **Qualità viewer** sceglie una versione alleggerita per la visualizzazione web, senza cambiare il download originale. Usa **Espandi** per dedicare la pagina alla scena e **Riduci** per tornare alla card.

**Gaussian preview** apre il viewer del Gaussian Splatting, affiancato al video RGB originale quando disponibile. Il modello ruota automaticamente; puoi interagire con i controlli standard. La preview è campionata/ compressa e non sostituisce il PLY. **Migliora buchi** genera una variante conservativa mirata a piccoli bordi topologici: non ricostruisce lati mai ripresi e non garantisce la chiusura di aperture ampie.

## 4. Upload da telefono

Il QR apre la pagina mobile. Usa **Scegli dalla galleria** per un video esistente oppure **Registra video** per acquisirne uno; attendi la fine dell'upload prima di chiudere la pagina. Telefono e server devono comunicare sulla stessa rete, oppure il servizio deve essere raggiunto via HTTPS. Il QR non rende automaticamente raggiungibile un host privato.

Per l'accesso esterno serve DNS pubblico, certificato TLS e porte/reverse proxy configurati correttamente. Il deploy incluso non prevede autenticazione: non esporlo direttamente a Internet.

## 5. Problemi frequenti

| Sintomo | Cosa controllare |
| --- | --- |
| Job in attesa GPU | Un worker sta elaborando un altro job oppure non vede la GPU; controlla stato e log del worker. |
| Ricostruzione con sfondo/rumore | Migliora separazione soggetto-sfondo, luce e qualità delle maschere nel video sorgente. |
| Mesh con grandi buchi | Verifica la copertura video: la riparazione conservativa copre solo piccoli bordi, non superfici mancanti. |
| Viewer lento | Prova una qualità viewer più leggera; la mesh PLY originale può essere molto più pesante. |
| Upload mobile fermo | Verifica rete, spazio sul telefono e raggiungibilità dell'indirizzo mostrato dal QR. |

Per installazione, comandi di log e diagnostica vedere [DEPLOYMENT_AND_USAGE.md](../server/DEPLOYMENT_AND_USAGE.md).
