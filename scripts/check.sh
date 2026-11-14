#!/usr/bin/env bash
# Run host checks without root privileges, image mounts or device access.
set -euo pipefail
cd "$(dirname "$0")/.."

with_kernel=false
case "${1:-}" in
    '') ;;
    --with-kernel) with_kernel=true ;;
    --help|-h)
        printf 'Usage: bash scripts/check.sh [--with-kernel]\n'
        exit 0
        ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { printf 'Expected at most one option.\n' >&2; exit 2; }

printf 'Checking Bash syntax...\n'
bash -n build.sh
for script in scripts/*.sh; do
    bash -n "$script"
done

printf 'Checking Python syntax...\n'
python3 - <<'PY'
from pathlib import Path

paths = sorted(Path("scripts").glob("*.py")) + sorted(Path("tests").glob("*.py"))
paths.append(Path("config/charge-limit/negroni-charge-limit"))
paths.append(Path("config/cpu-performance/negroni-cpu-performance"))
paths.extend(sorted(Path("config/audio/voice").glob("*.py")))
paths.extend(sorted(Path("config/desktop").glob("*.py")))
paths.append(Path("config/volte/negroni-ims-recovery.py"))
for path in paths:
    compile(path.read_bytes(), str(path), "exec")
print(f"{len(paths)} Python files passed")
PY

printf 'Checking audio topology and UCM sources...\n'
python3 -B scripts/verify-audio-image.py --sources-only

printf 'Checking sensor payloads...\n'
python3 -B - <<'PY'
import hashlib
import re
from pathlib import Path

def recorded(path):
    match = re.search(r"^sha256 ([0-9a-f]{64})$", Path(path).read_text(), re.M)
    if not match:
        raise SystemExit(f"missing sha256 in {path}")
    return match.group(1)

blob = Path("config/sensors/smem-sensor.bin").read_bytes()
digest = hashlib.sha256(blob).hexdigest()
if len(blob) != 5140 or digest != recorded("config/sensors/smem-sensor.bin.source"):
    raise SystemExit("smem-sensor.bin does not match its source note")
proxy = Path("config/sensors/iio-sensor-proxy").read_bytes()
if hashlib.sha256(proxy).hexdigest() != recorded("config/sensors/iio-sensor-proxy.source"):
    raise SystemExit("iio-sensor-proxy does not match its source note")
gyro = Path("config/sensors/negroni-gyro").read_bytes()
if hashlib.sha256(gyro).hexdigest() != recorded("config/sensors/negroni-gyro.source"):
    raise SystemExit("negroni-gyro does not match its source note")
if gyro[:4] != b"\x7fELF" or gyro[18:20] != b"\xb7\x00":
    raise SystemExit("negroni-gyro is not an aarch64 ELF binary")
qcom = Path("config/sensors/qcom")
note = Path("config/sensors/qcom.source").read_text()
if len(list((qcom / "config").glob("*.json"))) != 65:
    raise SystemExit("config/sensors/qcom/config must hold the 65 served JSON files")
for edited in (qcom / "config/waipio_qrd_alsps.json", qcom / "sns_reg.conf"):
    if f"sha256 {hashlib.sha256(edited.read_bytes()).hexdigest()}" not in note:
        raise SystemExit(f"{edited} does not match qcom.source")
print("sensor payloads match")
PY
for script in config/sensors/negroni-sensor-files config/sensors/hexagonrpcd-sdsp-wait; do
    sh -n "$script"
    if grep -q $'\r' "$script"; then
        printf '%s has CRLF line endings\n' "$script" >&2
        exit 1
    fi
done

printf 'Running experimental voice test cleanup checks...\n'
python3 -B tests/test-voice-test.py
python3 -B tests/test-call-audio.py

printf 'Running charge-limit service tests...\n'
python3 -B tests/test-charge-limit-service.py

printf 'Running GNSS assistance protocol checks...\n'
python3 -B tests/test-gnss-assist.py

printf 'Running experimental USB2 recovery guard checks...\n'
python3 -B tests/test-usb2-recover.py

printf 'Running offline camera module parser checks...\n'
python3 -B tests/test-camera-sensormodule.py

printf 'Running software camera meter checks...\n'
python3 -B tests/test-camera-meter.py

printf 'Running gyroscope axis checks...\n'
python3 -B tests/test-gyro-axes.py

printf 'Running IMS bearer recovery tests...\n'
python3 -B tests/test-ims-recovery.py

printf 'Running submodule bundle recovery tests...\n'
python3 -B tests/test-submodule-restore.py

if [[ $with_kernel == true ]]; then
    for source in qcom_battmgr.c oplus_battmgr.c qcom_battmgr_charge_limit.h; do
        [[ -f "linux/drivers/power/supply/$source" ]] || {
            printf 'Missing kernel source. Run: bash scripts/init-submodules.sh\n' >&2
            exit 1
        }
    done
    check_dir=$(mktemp -d "${TMPDIR:-/tmp}/negroni-check.XXXXXX")
    trap 'rm -rf -- "$check_dir"' EXIT
    printf 'Running charge-limit policy and driver tests...\n'
    cc -O2 -Wall -Wextra artifacts/call-audio-research-20261112/tools/adsp-f3.c -o "$check_dir/adsp-f3"
    "$check_dir/adsp-f3" --selftest
    cc -std=c11 -Wall -Wextra -Werror tests/charge-limit-policy.c -o "$check_dir/charge-limit-policy"
    "$check_dir/charge-limit-policy"
    python3 -B tests/test-charge-limit-driver.py
    printf 'Running USB2 PHY and role recovery driver checks...\n'
    python3 -B tests/test-usb2-driver.py
    printf 'Running LPASS capture mixer regression checks...\n'
    python3 -B tests/test-lpass-capture.py
    printf 'Running haptics playback regression checks...\n'
    python3 -B tests/test-haptics-driver.py
    printf 'Checking Docker configuration in fresh and existing kernel outputs...\n'
    python3 -B tests/test-docker-config.py
fi

printf 'All requested checks passed.\n'
