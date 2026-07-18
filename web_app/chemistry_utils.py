"""Chemistry helpers shared by compilation and the web viewer."""

from __future__ import annotations

import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request


def smiles_to_iupac(smiles: str, timeout: int = 15) -> str:
    """Return an IUPAC name for a SMILES string, if it can be resolved."""
    cleaned = (smiles or "").strip()
    if not cleaned or cleaned.upper() == "NA":
        return ""

    obabel = shutil.which("obabel")
    if obabel:
        try:
            proc = subprocess.run(
                [obabel, f"-:{cleaned}", "-oname"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                name = proc.stdout.strip().splitlines()[0].strip()
                if name:
                    return name
        except (OSError, subprocess.TimeoutExpired):
            pass

    try:
        encoded = urllib.parse.quote(cleaned, safe="")
        url = f"https://cactus.nci.nih.gov/chemical/structure/{encoded}/iupac_name"
        with urllib.request.urlopen(url, timeout=timeout) as response:
            name = response.read().decode("utf-8", errors="replace").strip()
            if name and "html" not in name.lower():
                return name
    except (urllib.error.URLError, TimeoutError, ValueError):
        pass

    return "Name unavailable"
