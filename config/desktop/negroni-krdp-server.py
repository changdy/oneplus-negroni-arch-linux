#!/usr/bin/env python3
"""Start KRDP and prepare user-local TLS on first use."""
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


def tls_arguments():
    read_config = ["/usr/bin/kreadconfig6", "--file", "krdpserverrc", "--group", "General", "--key"]
    for key in ("Certificate", "CertificateKey"):
        if subprocess.check_output([*read_config, key], text=True).strip():
            return []  # Let KRDP read the user's certificate settings.

    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    data_dir = data_home / "negroni"
    tls_dir = data_dir / "krdp"
    if not tls_dir.is_dir():
        data_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=data_dir) as temporary:
            staging = Path(temporary) / "tls"
            staging.mkdir(mode=0o700)
            subprocess.run([
                "/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-noenc",
                "-days", "3650", "-subj", "/CN=Negroni KRDP",
                "-out", str(staging / "krdp.crt"), "-keyout", str(staging / "krdp.key"),
            ], check=True)
            staging.rename(tls_dir)
    return ["--certificate", str(tls_dir / "krdp.crt"), "--certificate-key", str(tls_dir / "krdp.key")]


if __name__ == "__main__":
    server = "/usr/bin/krdpserver"
    os.execv(server, [server, *tls_arguments()])
