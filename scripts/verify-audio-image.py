#!/usr/bin/env python3
"""Check the Negroni AudioReach topology and ALSA UCM, in sources and in an offline ext4 image."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
TOPOLOGY = "/usr/lib/firmware/qcom/sm8450/OnePlus-10-Pro-tplg.bin"
CARD_UCM = "/usr/share/alsa/ucm2/conf.d/sm8450/OnePlus-10-Pro.conf"
VERB_UCM = "/usr/share/alsa/ucm2/OnePlus/negroni/HiFi.conf"
FILES = {
    TOPOLOGY: "config/audio/firmware/OnePlus-10-Pro-tplg.bin",
    CARD_UCM: "config/audio/ucm2/conf.d/sm8450/OnePlus-10-Pro.conf",
    VERB_UCM: "config/audio/ucm2/OnePlus/negroni/HiFi.conf",
}
UCM_ROOT = "/usr/share/alsa/ucm2"


def ucm_includes():
    """Shared alsa-ucm-conf fragments the Negroni UCM includes, as image paths."""
    text = "".join((PROJECT / FILES[path]).read_text() for path in (CARD_UCM, VERB_UCM))
    includes = set(re.findall(r'File\s+"(/[^"]+)"', text))
    includes.discard(VERB_UCM.removeprefix(UCM_ROOT))
    return sorted(UCM_ROOT + path for path in includes)


def check_sources():
    """Host-only consistency checks that need no image."""
    provenance = (PROJECT / "config/audio/firmware/OnePlus-10-Pro-tplg.source").read_text()
    recorded = re.search(r"^sha256 ([0-9a-f]{64})$", provenance, re.M)
    topology = (PROJECT / FILES[TOPOLOGY]).read_bytes()
    if not recorded or hashlib.sha256(topology).hexdigest() != recorded[1]:
        raise RuntimeError("topology binary does not match OnePlus-10-Pro-tplg.source")
    card = (PROJECT / FILES[CARD_UCM]).read_text()
    verb = (PROJECT / FILES[VERB_UCM]).read_text()
    if 'File "/OnePlus/negroni/HiFi.conf"' not in card:
        raise RuntimeError("card UCM does not point at /OnePlus/negroni/HiFi.conf")
    # hw:2 (TX_CODEC_DMA_TX_3) only accepts 2 channels; mono makes PipeWire drop the mic.
    if re.search(r"CaptureChannels\s+1\b", verb):
        raise RuntimeError("Negroni capture PCM is stereo-only; CaptureChannels 1 is invalid")
    for device in ("Speaker", "Headphones", "Mic1", "Mic2"):
        if f'SectionDevice."{device}"' not in verb:
            raise RuntimeError(f"UCM device {device} is missing")
    return ucm_includes()


def verify(image_dir, log_dir):
    dependencies = check_sources()
    image = image_dir / "root.img"
    log_dir.mkdir(parents=True, exist_ok=True)
    report = log_dir / "audio-verification.json"
    report.unlink(missing_ok=True)

    def debugfs(command):
        result = subprocess.run(["debugfs", "-R", command, str(image)],
           capture_output=True, check=True)
        diagnostics = result.stderr.decode().splitlines()[1:]
        if diagnostics:
            raise RuntimeError("\n".join(diagnostics))
        return result.stdout

    hashes = {}
    for target, source in FILES.items():
        data = debugfs(f"cat {target}")
        if data != (PROJECT / source).read_bytes():
            raise RuntimeError(f"image/source mismatch: {target}")
        metadata = debugfs(f"stat {target}").decode()
        if (not re.search(r"Type:\s+regular\s+Mode:\s+0644", metadata)
                or not re.search(r"User:\s+0\s+Group:\s+0", metadata)):
            raise RuntimeError(f"{target} must be a root-owned regular file, mode 0644")
        hashes[target] = hashlib.sha256(data).hexdigest()
    for target in dependencies:
        if not debugfs(f"cat {target}"):
            raise RuntimeError(f"missing alsa-ucm-conf fragment: {target}")

    verification = {
        "image": str(image),
        "files_match_sources": True,
        "installed_files_sha256": hashes,
        "ucm_dependencies_present": dependencies,
        "requires_kernel_dt": "linux ead3411b6e6 (audio-routing, Tertiary MI2S speakers)",
        "scope": "Offline file check; card probe needs the matching vendor_boot DTB",
        "hardware_tested": "2026-11-12 NE2210: speakers audible, internal mic records",
    }
    report.write_text(json.dumps(verification, indent=2) + "\n")
    print("Audio image verified: topology and UCM match sources, alsa-ucm-conf fragments present")
    return verification


if __name__ == "__main__":
    if sys.argv[1:] == ["--sources-only"]:
        print(f"Audio sources consistent; UCM includes {len(check_sources())} shared fragments")
    elif len(sys.argv) == 3:
        verify(*map(Path, sys.argv[1:]))
    else:
        raise SystemExit("Usage: verify-audio-image.py IMAGE_DIRECTORY LOG_DIRECTORY | --sources-only")
