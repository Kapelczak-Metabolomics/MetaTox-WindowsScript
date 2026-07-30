# MetaTox Docker deployment

Run MetaTox as a self-contained Docker service with a browser-based GUI. No WSL, no Windows `.exe`, and no local Singularity installation required on the host.

## What you get

- **Web GUI** at `http://localhost:8501` (Flask + Tailwind CSS + Flowbite)
- **Bundled dependencies** inside the container (Apptainer/Singularity, Python, pipeline scripts)
- **Persistent outputs** in `./data/output`
- **One-command deploy** with Docker Compose

## Requirements

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
- ~8 GB free disk space for Singularity images on first run
- Internet access on first prediction (downloads BioTransformer, SygMa, GLORYx, MetaTrans images)

### macOS (Apple Silicon)

Docker Desktop on M-series Macs builds `linux/arm64` images by default. Apptainer only publishes amd64 `.deb` files on GitHub, so the Dockerfile installs Apptainer from the Ubuntu PPA on arm64.

For the most compatible setup (recommended), build and run the service as `linux/amd64` so the bundled Singularity images match the architecture they were published for:

```bash
docker compose -f docker-compose.yml -f docker-compose.mac.yml up --build
```

Native arm64 builds are also supported:

```bash
docker compose up --build
```

If Singularity steps fail on a native arm64 build, switch to the `docker-compose.mac.yml` overlay above. In Docker Desktop, enabling **Use Rosetta for x86_64/amd64 emulation** can improve amd64 performance on Apple Silicon.

## Quick start

From the repository root:

```bash
docker compose up --build
```

On Windows PowerShell, you can also use the helper script (recommended):

```powershell
.\docker\up.ps1
```

This uses `docker compose` with `privileged: true` and the Apptainer security options required for BioTransformer, SygMa, GLORYx, and MetaTrans. **Do not** start the service with a plain `docker run` unless you include every flag shown in the troubleshooting section below.

Open your browser:

```text
http://localhost:8501
```

Stop the service:

```bash
docker compose down
```

## Disk space and cached Singularity images

MetaTox stores downloaded Singularity/Apptainer images in a **named Docker volume**:

```text
metatox-singularity-cache  ->  /var/lib/metatox/singularity-cache
```

This cache can be several gigabytes after BioTransformer, SygMa, GLORYx, and MetaTrans have been downloaded.

| Action | Container removed? | Singularity cache removed? | Your result files removed? |
|--------|------------------|----------------------------|----------------------------|
| `docker compose down` | Yes | **No** (volume kept) | **No** (`./data/output` is a bind mount) |
| `docker compose down -v` | Yes | **Yes** | **No** |
| Delete container in Docker Desktop | Yes | **No** (unless you also delete the volume) | **No** |
| `docker compose build --no-cache` | N/A | **No** | **No** |

To remove the container **and** reclaim cached Singularity image space:

```bash
docker compose down -v
```

To remove only the cache volume while keeping the compose project definition:

```bash
docker volume rm metatox-singularity-cache
```

Your prediction outputs in `./data/output/` live on the host filesystem and are **not** deleted when the container is removed.

Old Docker **build** layers from previous `docker compose build` runs are managed separately by Docker Desktop (use **Build cache** / **Clean / Purge data** in Docker Desktop if you need to reclaim that space).

## First run

1. Open the **Run** tab
2. Upload a text file (`MoleculeName,SMILES` per line) or use the bundled example
3. Adjust options in the sidebar
4. Click **Run prediction**
5. Download results from the **Results** tab when finished

Outputs are written to:

```text
data/output/Results_Prediction/
```

## Input format

```text
Nicotine,CN1CCC[C@H]1c2cccnc2
```

## Optional: prefetch Singularity images

The first prediction downloads several large images. To prefetch them at startup:

```bash
METATOX_PREFETCH_IMAGES=true docker compose up --build
```

## Optional: Meta-Predictor

Meta-Predictor is disabled by default because it requires CUDA and an extra setup step.

To enable it:

1. Clone Meta-Predictor into the repository before building:

```bash
git clone https://github.com/zhukeyun/Meta-Predictor
mkdir -p Meta-Predictor/prediction
mv "Meta-Predictor/model/SoM identifier" Meta-Predictor/model/SoM_identifier
mv "Meta-Predictor/model/metabolite predictor" Meta-Predictor/model/metabolite_predictor
chmod +x Meta-Predictor/predict-top15.sh
```

2. Rebuild the image
3. Enable **Meta-Predictor** in the sidebar

## Custom port

```bash
METATOX_PORT=8080 docker compose up --build
```

## Pull prebuilt image

If your repository publishes images to GitHub Container Registry:

```bash
docker pull ghcr.io/kapelczak-metabolomics/metatox:latest
docker run --rm -it \
  --privileged \
  --shm-size=4g \
  --security-opt seccomp=unconfined \
  --security-opt apparmor=unconfined \
  --device /dev/fuse \
  -p 8501:8501 \
  -v "$(pwd)/data/output:/app/data/output" \
  -v "$(pwd)/data/input:/app/data/input" \
  ghcr.io/kapelczak-metabolomics/metatox:latest
```

## Troubleshooting

### Container exits immediately

- Check logs: `docker compose logs -f metatox`
- Ensure port `8501` is free

### Permission errors with Apptainer

- Docker Compose runs the service with `privileged: true` so Apptainer can execute nested containers
- The image also installs `apptainer-suid` so Apptainer can fall back to setuid mode when user namespaces are blocked
- Compose also enables `seccomp:unconfined`, `apparmor:unconfined`, and `/dev/fuse` for nested Apptainer on Ubuntu 24.04 hosts
- On hardened hosts, ask your admin to allow privileged containers

### `Failed to create user namespace: not allowed to create user namespace`

This is **not** caused by changing the host port (`8501`, `8080`, etc.). Port mapping only affects how you reach the web UI.

It means Apptainer cannot run nested Singularity images inside the MetaTox Docker container. The image now forces Apptainer **setuid mode** (`allow user ns = no`) because user namespaces are blocked inside Docker, especially on Docker Desktop.

**Use this exact startup sequence on Windows:**

```powershell
cd C:\path\to\MetaTox-WindowsScript
git pull
docker compose down
docker compose build --no-cache
docker compose up
```

Or:

```powershell
.\docker\up.ps1 -NoCache
```

(`docker\up.ps1` rebuilds and starts with the correct compose settings.)

After startup, check the logs for:

```text
Apptainer setuid starter enabled
allow user ns = no
Apptainer runtime check: OK
```

If the runtime check fails, the web UI will not start and the container logs will show the exact Apptainer error.

Fix checklist:

1. **Use Docker Compose** (recommended):
   ```bash
   docker compose down
   docker compose build --no-cache
   docker compose up
   ```
2. **Do not remove `privileged: true`** from `docker-compose.yml`.
3. If you use `docker run` manually, include all of these flags:
   ```bash
   docker run --rm -it \
     --privileged \
     --shm-size=4g \
     --security-opt seccomp=unconfined \
     --security-opt apparmor=unconfined \
     --device /dev/fuse \
     -p 8501:8501 \
     -v "$(pwd)/data/output:/app/data/output" \
     -v "$(pwd)/data/input:/app/data/input" \
     metatox:latest
   ```
4. After rebuilding, check startup logs for `Apptainer setuid starter enabled` and `setuid starter: ready`.
5. Optional full smoke test inside the running container:
   ```bash
   docker compose exec metatox /app/docker/verify-nested-singularity.sh
   ```

If you deploy to Kubernetes, Nomad, or a cloud platform that blocks privileged containers, nested Apptainer will not work in this image. Run MetaTox on bare Linux/WSL2 with Apptainer installed on the host instead.

### `bash\r: No such file or directory`

This means shell scripts were saved with Windows line endings. Rebuild with the latest image:

```bash
docker compose down
docker compose build --no-cache
docker compose up
```

The Dockerfile now converts all `*.sh` files to Unix line endings during the build.

### `file: command not found`

Rebuild with the latest image. The container installs the `file` package and `Metatox.sh` falls back to `dos2unix` when `file` is unavailable.

### Meta-Predictor failed

Meta-Predictor is not included in the default Docker image. Leave it **disabled** in the sidebar unless you install Conda, CUDA, and the Meta-Predictor repository (see optional setup above).

### Singularity steps fail inside Docker

1. Rebuild with verbose logging enabled (default in the latest image):
   ```bash
   docker compose down
   docker compose build --no-cache
   METATOX_PREFETCH_IMAGES=true docker compose up
   ```
2. Check the **Pipeline log** panel for detailed Apptainer errors after each step.
3. Ensure Docker Desktop has enough RAM (8 GB+) and disk space for image downloads.
4. The container must run with `privileged: true` (already set in `docker-compose.yml`).

If BioTransformer, SygMa, or GLORYx fail but MetaTrans succeeds, inspect files in `log/` inside the container:
```bash
docker compose exec metatox ls -la /app/log
docker compose exec metatox tail -n 80 /app/log/JNJ-40418677_Biotransformer3_log.txt
```

### Predictions are slow the first time

- Expected: Singularity images are downloaded on demand
- Use `METATOX_PREFETCH_IMAGES=true` to warm the cache at startup

### Results tab is empty

- Wait until the log shows `Execution completed !`
- Check `data/output/Results_Prediction/`

## Architecture

```text
Browser -> Flask web UI (Tailwind CSS + Flowbite)
                |
                v
         Metatox.sh pipeline
                |
                v
   Apptainer/Singularity images
   (BioTransformer3, SygMa, GLORYx, MetaTrans, RDKit)
```
