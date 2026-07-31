# MetaTox on Windows

MetaTox depends on Linux-only tools (Singularity containers, optional CUDA-based Meta-Predictor). On Windows, the native GUI launches the existing `Metatox.sh` pipeline inside **WSL2**.

## What you get

- `MetaToxGUI.exe`: a desktop app with file pickers, prediction options, live logs, and one-click access to exported results
- The same output format as the Linux workflow:
  - `Results_Prediction/<Molecule>_CompileResults.tsv`
  - `Results_Prediction/<Molecule>_figures/`

## Requirements

1. Windows 10 or Windows 11 with **WSL2**
2. A Linux distribution in WSL (Ubuntu is recommended)
3. **Singularity** installed inside WSL
4. Optional: **Conda** and Meta-Predictor setup inside WSL if you enable Meta-Predictor

## One-time WSL setup

Open PowerShell as Administrator and run:

```powershell
wsl --install
```

Restart if prompted, then open your Linux distribution and install the Linux dependencies described in the main [README](../README.md):

```bash
# Inside WSL
sudo apt update
sudo apt install -y gawk dos2unix

# Install Singularity (follow Sylabs documentation for your distro)
# https://docs.sylabs.io/

# Add Sylabs remote for custom images
singularity remote add --no-login SylabsCloud cloud.sycloud.io

# Clone MetaTox inside WSL or use the Windows copy via /mnt/c/...
cd /mnt/c/path/to/MetaTox

# Optional Meta-Predictor setup
git clone https://github.com/zhukeyun/Meta-Predictor
mkdir -p Meta-Predictor/prediction
mv "Meta-Predictor/model/SoM identifier" Meta-Predictor/model/SoM_identifier
mv "Meta-Predictor/model/metabolite predictor" Meta-Predictor/model/metabolite_predictor
chmod +x Meta-Predictor/predict-top15.sh
```

## Build the Windows executable

On a Windows machine with Python 3.10+ installed:

```bat
windows_app\build.bat
```

The build creates:

```text
dist\MetaToxGUI\MetaToxGUI.exe
```

## Recommended installation layout

Place the built app in the MetaTox repository root:

```text
MetaTox\
  MetaToxGUI.exe
  Metatox.sh
  Scripts\
  CondaEnv\
  ExempleInput.txt
  Results_Prediction\
```

The GUI auto-detects `Metatox.sh` in the same folder as the executable. You can also choose a different MetaTox folder from the **Run** tab.

## Using the GUI

1. Launch `MetaToxGUI.exe`
2. Open the **Environment** tab and click **Refresh checks**
3. On the **Run** tab:
   - Select your input file (`MoleculeName,SMILES` per line)
   - Confirm the output folder name (default: `Results_Prediction`)
4. Adjust options on the **Options** tab if needed
5. Click **Run prediction**
6. When finished, click **Open output folder**

## Input format

```text
Nicotine,CN1CCC[C@H]1c2cccnc2
```

## Troubleshooting

### WSL not detected

- Install WSL2: `wsl --install`
- Verify: `wsl -l -v`

### Singularity not found in WSL

- Install Singularity inside your Linux distribution, not on Windows
- Verify inside WSL: `which singularity`

### Permission denied on Metatox.sh

The GUI runs `chmod +x Metatox.sh` automatically inside WSL.

### Slow first run

The first execution downloads Singularity images and may create the Meta-Predictor conda environment. This is expected.

### Meta-Predictor errors

Meta-Predictor requires CUDA inside WSL. Leave it disabled unless your GPU/CUDA stack is configured.

### Results not created

Check:

- `log/` in the MetaTox folder
- The log panel in the GUI
- That your input file uses comma-separated `name,SMILES` lines

## Development/testing without building

From the repository root:

```bat
python windows_app\metatox_gui.py
```

This requires WSL on Windows. On Linux, use `./Metatox.sh` directly.
