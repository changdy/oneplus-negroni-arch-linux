from pathlib import Path
p = Path("/home/oneplus/android-ro/odm_b/etc/nfc/libnfc-mtp-SN100.conf_20846")
lines = p.read_bytes().decode("latin1", errors="replace").splitlines()
keys = ("NXP_SYS_CLK", "NXP_CLOCK", "NXP_SYS_CLOCK", "ENABLE_VEN")
for i, line in enumerate(lines):
    if any(k in line for k in keys):
        start = max(0, i - 18)
        print(f"\n----- line {i+1} -----")
        for j in range(start, min(len(lines), i + 3)):
            print(f"{j+1}: {lines[j][:200]}")
