# Client di acquisizione ZED

Questo client viene eseguito sul PC Windows/Linux con la camera ZED collegata;
non va eseguito nel container del server.

## Requisiti

1. Installa [ZED SDK](https://www.stereolabs.com/developers/release/) e la sua
   binding Python `pyzed.sl` per la versione di Python in uso.
2. Installa le dipendenze Python usate dallo script:

   ```bash
   pip install numpy opencv-python matplotlib
   ```

## Acquisizione e upload

Esegui l'acquisizione in una nuova directory:

```bash
python capture_video.py
```

Alla chiusura, la directory contiene `recording.mp4`, `depth_data.dp` e
`camera_data.dp`. Crea lo ZIP portabile con:

```bash
python make_capture_zip.py . pavarotti-zed.zip
```

Carica poi `pavarotti-zed.zip` nella modalità **Pacchetto ZED con profondità**
della webapp. Non rinominare i tre file e non inserirli in una sottocartella:
la validazione server richiede che siano nella radice dello ZIP.
