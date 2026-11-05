"""Small, opt-in GitHub release checker. It never installs updates itself."""
from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
from urllib.error import URLError
from urllib.request import Request, urlopen


APP_VERSION = "1.1.2"


def version_tuple(value):
    numbers = re.findall(r"\d+", str(value or ""))
    return tuple(int(number) for number in (numbers[:4] or [0]))


def is_newer(latest, current=APP_VERSION):
    left, right = version_tuple(latest), version_tuple(current)
    size = max(len(left), len(right))
    return left + (0,) * (size - len(left)) > right + (0,) * (size - len(right))


def verified_ssl_context():
    """Use Python roots plus the Windows ROOT store without disabling verification."""
    context = ssl.create_default_context()
    enum_certificates = getattr(ssl, "enum_certificates", None)
    if enum_certificates:
        certificates = []
        for certificate, encoding, _trust in enum_certificates("ROOT"):
            if encoding == "x509_asn":
                certificates.append(ssl.DER_cert_to_PEM_cert(certificate))
        if certificates:
            context.load_verify_locations(cadata="".join(certificates))
    return context


def powershell_latest_release(repository, timeout=8):
    """Use Windows' native TLS stack when frozen Python cannot build a valid chain."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("GitHub 仓库地址格式无效")
    uri = f"https://api.github.com/repos/{repository}/releases/latest"
    script = (
        "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';"
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "$h=@{'User-Agent'='XuanShu-Workbench-Updater/1.1.2';'Accept'='application/vnd.github+json'};"
        f"$r=Invoke-RestMethod -Uri '{uri}' -Headers $h -TimeoutSec {int(timeout)};"
        "@{tag_name=$r.tag_name;html_url=$r.html_url;name=$r.name}|ConvertTo-Json -Compress"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, encoding="utf-8", errors="replace", timeout=timeout + 5,
        creationflags=flags, check=False,
    )
    if result.returncode:
        raise ValueError((result.stderr or "Windows 网络请求失败").strip())
    return json.loads(result.stdout.strip())


def latest_release(repository, timeout=8, opener=None):
    repository = str(repository or "").strip().strip("/")
    if not repository or "/" not in repository:
        raise ValueError("尚未配置 GitHub 仓库")
    request = Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "XuanShu-Workbench-Updater/1.1.2"},
    )
    if opener is None:
        try:
            response_context = urlopen(request, timeout=timeout, context=verified_ssl_context())
            with response_context as response:
                data = json.loads(response.read().decode("utf-8"))
        except (URLError, ssl.SSLError, OSError):
            if os.name != "nt":
                raise
            data = powershell_latest_release(repository, timeout)
    else:
        with opener(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    page = str(data.get("html_url") or f"https://github.com/{repository}/releases").strip()
    if not tag:
        raise ValueError("GitHub 最新发布缺少版本号")
    return {"version": tag.lstrip("vV"), "url": page, "name": str(data.get("name") or tag)}
