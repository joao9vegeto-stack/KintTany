# Colab cell — GitHub Actions -> Google Drive (KaKaRoTiOS)
# !pip -q install requests google-api-python-client google-auth

import os
import re
import json
import time
import math
import hashlib
import zipfile
import threading
import requests
from pathlib import Path, PurePosixPath
from concurrent.futures import ThreadPoolExecutor, as_completed
from getpass import getpass

from google.colab import auth
import google.auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ------------------------------------------------------------
# CONFIGURAÇÃO — IDs/SHAs DE RUN E ARTIFACT SÃO SEMPRE DINÂMICOS
# ------------------------------------------------------------

REPO = "joao9vegeto-stack/KintTany"
BRANCH = "KaKaRoTiOS"
WORKFLOW_PATH = ".github/workflows/kakarot_ios.yml"
ARTIFACT_NAME = "KaKaRoTiOS-Kakarot-IPA"

# Pasta raiz já configurada no notebook KaKaRoTiOS; a célula usa/cria
# uma subpasta "ipa" dentro dela, sem misturar a IPA com RomFS/AOC.
DRIVE_ROOT_FOLDER_ID = "11dK8vadW7ANKlUkb14C-umcSoEnpYI3p"
DRIVE_IPA_FOLDER_NAME = "ipa"

IPA_NAME = "KaKaRoTiOS.ipa"
WORK = Path("/content/kakarot_drive_transfer")
WORK.mkdir(parents=True, exist_ok=True)
ZIP_PATH = WORK / "github-artifact.zip"
IPA_PATH = WORK / IPA_NAME

RUNS_MAX_PAGES = 10
ARTIFACTS_MAX_PAGES = 5
RANGE_WORKERS = 8
RANGE_SIZE = 32 * 1024 * 1024       # 32 MiB por faixa; download paralelo
DOWNLOAD_CHUNK = 4 * 1024 * 1024    # 4 MiB por bloco dentro de cada faixa
DRIVE_CHUNK = 16 * 1024 * 1024     # upload resumable de 16 MiB
KEEP_LOCAL_FILES = False

# ------------------------------------------------------------
# 1. AUTENTICAR GOOGLE DRIVE
# ------------------------------------------------------------

print("1/5 — Autenticando Google Drive...")
auth.authenticate_user()
credentials, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/drive"]
)
drive = build(
    "drive", "v3",
    credentials=credentials,
    cache_discovery=False,
)

root_folder = drive.files().get(
    fileId=DRIVE_ROOT_FOLDER_ID,
    fields="id,name,mimeType,trashed",
).execute()
if root_folder.get("mimeType") != "application/vnd.google-apps.folder":
    raise RuntimeError("O ID configurado para o Drive não é uma pasta.")
if root_folder.get("trashed"):
    raise RuntimeError("A pasta raiz do Kakarot está na lixeira do Drive.")
print("Drive autenticado:", root_folder["name"])

# ------------------------------------------------------------
# 2. DESCOBRIR A ÚLTIMA IPA BEM-SUCEDIDA DA BRANCH
# ------------------------------------------------------------

print(f"\n2/5 — Procurando a última IPA válida de {BRANCH}...")
headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "KaKaRoTiOS-Colab-Drive-Transfer",
}
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
if GITHUB_TOKEN:
    headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

session = requests.Session()
session.headers.update(headers)
api_root = f"https://api.github.com/repos/{REPO}"
_token_prompted = False


def prompt_github_token():
    global GITHUB_TOKEN, _token_prompted
    if _token_prompted:
        raise RuntimeError("O GitHub recusou a autenticação fornecida.")
    _token_prompted = True
    token = getpass(
        "GitHub exige autenticação. PAT com permissão Actions: Read: "
    ).strip()
    if not token:
        raise RuntimeError("Token GitHub não fornecido.")
    GITHUB_TOKEN = token
    session.headers["Authorization"] = f"Bearer {token}"


def github_get(url, params=None):
    response = session.get(url, params=params, timeout=(30, 120))
    if response.status_code in (401, 403):
        response.close()
        prompt_github_token()
        response = session.get(url, params=params, timeout=(30, 120))
    if not response.ok:
        detail = response.text[:800]
        code = response.status_code
        response.close()
        raise RuntimeError(f"GitHub API HTTP {code}: {detail}")
    try:
        return response.json()
    finally:
        response.close()


# HEAD remoto da branch atual: usado apenas para informar se a IPA encontrada
# corresponde exatamente ao código mais recente da branch.
branch_data = github_get(f"{api_root}/branches/{BRANCH}")
LATEST_BRANCH_SHA = branch_data["commit"]["sha"]

runs = []
for page in range(1, RUNS_MAX_PAGES + 1):
    payload = github_get(
        f"{api_root}/actions/runs",
        params={
            "branch": BRANCH,
            "status": "completed",
            "per_page": 100,
            "page": page,
        },
    )
    batch = payload.get("workflow_runs", [])
    runs.extend(batch)
    if len(batch) < 100:
        break

# Só considera o workflow exato, branch exata e conclusão success.
runs = [
    run for run in runs
    if run.get("head_branch") == BRANCH
    and run.get("path") == WORKFLOW_PATH
    and run.get("status") == "completed"
    and run.get("conclusion") == "success"
]
runs.sort(
    key=lambda run: (run.get("created_at", ""), run.get("id", 0)),
    reverse=True,
)

selected_run = None
selected_artifact = None
for run in runs:
    artifacts = []
    artifacts_url = run.get("artifacts_url") or (
        f"{api_root}/actions/runs/{run['id']}/artifacts"
    )
    for page in range(1, ARTIFACTS_MAX_PAGES + 1):
        payload = github_get(
            artifacts_url,
            params={"per_page": 100, "page": page},
        )
        batch = payload.get("artifacts", [])
        artifacts.extend(batch)
        if len(batch) < 100:
            break

    valid = [
        artifact for artifact in artifacts
        if artifact.get("name") == ARTIFACT_NAME
        and not artifact.get("expired", False)
    ]
    if valid:
        valid.sort(
            key=lambda artifact: (
                artifact.get("created_at", ""), artifact.get("id", 0)
            ),
            reverse=True,
        )
        selected_run = run
        selected_artifact = valid[0]
        break

if not selected_run or not selected_artifact:
    raise RuntimeError(
        "Nenhuma execução bem-sucedida com o artifact IPA KaKaRoTiOS "
        "não expirado foi encontrada. Nada foi baixado ou enviado ao Drive."
    )

RUN_ID = int(selected_run["id"])
ARTIFACT_ID = int(selected_artifact["id"])
EXPECTED_ARTIFACT_SIZE = int(selected_artifact.get("size_in_bytes") or 0)
EXPECTED_ARTIFACT_SHA256 = str(
    selected_artifact.get("digest") or ""
).removeprefix("sha256:").lower()
COMMIT_SHA = selected_run["head_sha"]
COMMIT_SHORT = COMMIT_SHA[:12]
RUN_URL = selected_run.get(
    "html_url", f"https://github.com/{REPO}/actions/runs/{RUN_ID}"
)
COMMIT_URL = f"https://github.com/{REPO}/commit/{COMMIT_SHA}"

commit_data = github_get(f"{api_root}/commits/{COMMIT_SHA}")
COMMIT_MESSAGE = commit_data.get("commit", {}).get("message", "").splitlines()[0]
COMMIT_DATE = commit_data.get("commit", {}).get("committer", {}).get("date", "")

print("\n" + "=" * 72)
print("PROVENIÊNCIA DA IPA — DESCOBERTA PELA API DO GITHUB")
print("=" * 72)
print("Repositório:", REPO)
print("Branch:", BRANCH)
print("HEAD ATUAL da branch:", LATEST_BRANCH_SHA)
print("Commit da IPA:", COMMIT_SHA)
print("Commit curto:", COMMIT_SHORT)
print("Mensagem:", COMMIT_MESSAGE)
print("Data do commit:", COMMIT_DATE)
print("Workflow:", selected_run.get("name"))
print("Run:", RUN_ID)
print("Criado:", selected_run.get("created_at"))
print("Status:", selected_run.get("status"), "| conclusão:", selected_run.get("conclusion"))
print("URL:", RUN_URL)
print("Artifact:", selected_artifact.get("name"))
print("Artifact ID (dinâmico):", ARTIFACT_ID)
print("Tamanho ZIP esperado:", f"{EXPECTED_ARTIFACT_SIZE:,}", "bytes")
print("SHA-256 oficial:", EXPECTED_ARTIFACT_SHA256 or "não informado pela API")
print("Expira em:", selected_artifact.get("expires_at"))
if COMMIT_SHA != LATEST_BRANCH_SHA:
    print("\nATENÇÃO: a IPA é a publicação válida mais recente, mas não corresponde ao HEAD atual.")
else:
    print("\nCONFIRMADO: a IPA foi gerada pelo HEAD atual da branch.")
print("=" * 72)

# ------------------------------------------------------------
# 3. BAIXAR ARTIFACT DO GITHUB DIRETO AO DISCO DO COLAB
#    Usa HTTP Range em paralelo quando o endpoint/CDN permite.
# ------------------------------------------------------------

print("\n3/5 — Baixando o artifact GitHub -> Colab...")
download_api_url = f"{api_root}/actions/artifacts/{ARTIFACT_ID}/zip"
response = session.get(
    download_api_url,
    stream=True,
    allow_redirects=False,
    timeout=(30, 180),
)
if response.status_code in (401, 403):
    response.close()
    prompt_github_token()
    response = session.get(
        download_api_url,
        stream=True,
        allow_redirects=False,
        timeout=(30, 180),
    )

signed_download_url = None
initial_stream_response = None
if response.status_code in (301, 302, 303, 307, 308):
    signed_download_url = response.headers.get("Location")
    response.close()
    if not signed_download_url:
        raise RuntimeError("GitHub redirecionou o download sem fornecer URL temporária.")
elif response.status_code == 200:
    # Compatibilidade caso o GitHub entregue o ZIP diretamente sem redirect.
    initial_stream_response = response
else:
    detail = response.text[:800]
    code = response.status_code
    response.close()
    raise RuntimeError(f"Download do artifact recusado pelo GitHub: HTTP {code}: {detail}")


def stream_response_to_file(stream_response, destination, expected_size=0):
    total_header = int(stream_response.headers.get("Content-Length") or 0)
    total = total_header or expected_size
    downloaded = 0
    last_percent = -5
    with open(destination, "wb") as output:
        for chunk in stream_response.iter_content(chunk_size=8 * 1024 * 1024):
            if not chunk:
                continue
            output.write(chunk)
            downloaded += len(chunk)
            pct = int(downloaded * 100 / total) if total else 0
            if total and (pct >= last_percent + 5 or pct == 100):
                print(f"GitHub -> Colab: {pct}% ({downloaded:,}/{total:,} bytes)")
                last_percent = pct
    stream_response.close()
    if expected_size and downloaded != expected_size:
        raise RuntimeError(
            f"Tamanho baixado divergente: esperado {expected_size:,}; recebido {downloaded:,}."
        )


def parallel_range_download(url, total_size, destination):
    # Probe: confirma que a URL assinada aceita Range e identifica o tamanho total.
    probe = requests.get(
        url,
        headers={"Range": "bytes=0-0"},
        stream=True,
        timeout=(30, 90),
    )
    supports_ranges = probe.status_code == 206
    content_range = probe.headers.get("Content-Range", "")
    match = re.fullmatch(r"bytes\s+0-0/(\d+)", content_range.strip())
    if supports_ranges and match:
        range_total = int(match.group(1))
        probe.close()
        if total_size and range_total != total_size:
            raise RuntimeError(
                f"Content-Range do GitHub ({range_total:,}) não corresponde "
                f"ao tamanho do artifact ({total_size:,})."
            )
        total_size = range_total
    else:
        probe.close()
        return False

    if total_size <= 0:
        return False

    # Pré-aloca o ZIP e grava cada faixa em offset próprio (sem arquivos temporários extras).
    with open(destination, "wb") as output:
        output.truncate(total_size)

    ranges = []
    for start in range(0, total_size, RANGE_SIZE):
        end = min(start + RANGE_SIZE - 1, total_size - 1)
        ranges.append((start, end))

    completed_bytes = 0
    progress_lock = threading.Lock()
    last_percent = [-5]

    def fetch_range(index, start, end):
        nonlocal completed_bytes
        expected_length = end - start + 1
        last_error = None
        for attempt in range(1, 6):
            try:
                with requests.get(
                    url,
                    headers={"Range": f"bytes={start}-{end}"},
                    stream=True,
                    timeout=(30, 180),
                ) as part:
                    if part.status_code != 206:
                        raise RuntimeError(
                            f"Faixa {index}: HTTP {part.status_code}, esperado 206."
                        )
                    expected_range = f"bytes {start}-{end}/{total_size}"
                    actual_range = part.headers.get("Content-Range", "")
                    if actual_range.strip() != expected_range:
                        raise RuntimeError(
                            f"Faixa {index}: Content-Range inesperado: {actual_range!r}."
                        )
                    received = 0
                    with open(destination, "r+b") as output:
                        output.seek(start)
                        for chunk in part.iter_content(chunk_size=DOWNLOAD_CHUNK):
                            if chunk:
                                output.write(chunk)
                                received += len(chunk)
                    if received != expected_length:
                        raise RuntimeError(
                            f"Faixa {index}: esperado {expected_length:,}; recebido {received:,}."
                        )

                with progress_lock:
                    completed_bytes += received
                    percent = int(completed_bytes * 100 / total_size)
                    if percent >= last_percent[0] + 5 or percent == 100:
                        print(
                            f"GitHub -> Colab (Range paralelo): {percent}% "
                            f"({completed_bytes:,}/{total_size:,} bytes)"
                        )
                        last_percent[0] = percent
                return received
            except Exception as exc:
                last_error = exc
                if attempt < 5:
                    time.sleep(min(2 ** (attempt - 1), 12))
        raise RuntimeError(f"Falha ao baixar faixa {index}: {last_error}")

    with ThreadPoolExecutor(max_workers=RANGE_WORKERS) as pool:
        futures = [
            pool.submit(fetch_range, index, start, end)
            for index, (start, end) in enumerate(ranges, 1)
        ]
        for future in as_completed(futures):
            future.result()
    return True


if initial_stream_response is not None:
    print("GitHub entregou o ZIP diretamente; usando stream sequencial.")
    stream_response_to_file(
        initial_stream_response, ZIP_PATH, EXPECTED_ARTIFACT_SIZE
    )
else:
    # A URL temporária é pública/assinada; não enviar o PAT do GitHub ao CDN.
    head = requests.head(
        signed_download_url,
        allow_redirects=True,
        timeout=(30, 90),
    )
    cdn_size = int(head.headers.get("Content-Length") or 0)
    accepts_ranges = "bytes" in head.headers.get("Accept-Ranges", "").lower()
    head.close()
    total_size = cdn_size or EXPECTED_ARTIFACT_SIZE
    if EXPECTED_ARTIFACT_SIZE and total_size and total_size != EXPECTED_ARTIFACT_SIZE:
        raise RuntimeError(
            f"Tamanho do CDN ({total_size:,}) diverge do artifact API "
            f"({EXPECTED_ARTIFACT_SIZE:,})."
        )

    range_ok = False
    if accepts_ranges or total_size:
        range_ok = parallel_range_download(
            signed_download_url, total_size, ZIP_PATH
        )
    if not range_ok:
        print("CDN não aceitou HTTP Range; usando stream sequencial direto.")
        sequential = requests.get(
            signed_download_url,
            stream=True,
            timeout=(30, 180),
        )
        sequential.raise_for_status()
        stream_response_to_file(
            sequential, ZIP_PATH, EXPECTED_ARTIFACT_SIZE
        )

if not ZIP_PATH.is_file() or ZIP_PATH.stat().st_size < 100_000_000:
    raise RuntimeError("ZIP baixado ausente ou pequeno demais; artifact inesperado.")

DOWNLOADED_ZIP_SIZE = ZIP_PATH.stat().st_size
zip_hash = hashlib.sha256()
with open(ZIP_PATH, "rb") as source:
    for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
        zip_hash.update(chunk)
DOWNLOADED_ZIP_SHA256 = zip_hash.hexdigest().lower()

if EXPECTED_ARTIFACT_SIZE and DOWNLOADED_ZIP_SIZE != EXPECTED_ARTIFACT_SIZE:
    raise RuntimeError(
        "INTEGRIDADE REPROVADA: tamanho ZIP diferente do publicado pelo GitHub. "
        f"Esperado={EXPECTED_ARTIFACT_SIZE:,}; recebido={DOWNLOADED_ZIP_SIZE:,}. "
        "A IPA não será extraída nem enviada."
    )
if EXPECTED_ARTIFACT_SHA256 and DOWNLOADED_ZIP_SHA256 != EXPECTED_ARTIFACT_SHA256:
    raise RuntimeError(
        "INTEGRIDADE REPROVADA: SHA-256 do ZIP diferente do digest do GitHub. "
        f"Esperado={EXPECTED_ARTIFACT_SHA256}; recebido={DOWNLOADED_ZIP_SHA256}. "
        "A IPA não será extraída nem enviada."
    )
if not zipfile.is_zipfile(ZIP_PATH):
    raise RuntimeError("O arquivo baixado não é um ZIP válido.")

print("DOWNLOAD E SHA-256 DO ARTIFACT CONFIRMADOS.")
print("Artifact ID:", ARTIFACT_ID)
print("Tamanho ZIP:", f"{DOWNLOADED_ZIP_SIZE:,}", "bytes")
print("SHA-256 ZIP:", DOWNLOADED_ZIP_SHA256)

# ------------------------------------------------------------
# 4. EXTRAIR E VALIDAR SOMENTE A IPA
# ------------------------------------------------------------

print("\n4/5 — Extraindo IPA e conferindo build-report.json...")
with zipfile.ZipFile(ZIP_PATH, "r") as archive:
    ipa_members = [
        info for info in archive.infolist()
        if not info.is_dir() and info.filename.lower().endswith(".ipa")
    ]
    if len(ipa_members) != 1:
        raise RuntimeError(
            f"Esperada exatamente uma IPA; encontradas: {[x.filename for x in ipa_members]}"
        )
    ipa_info = ipa_members[0]
    if ipa_info.file_size < 100_000_000:
        raise RuntimeError("O tamanho declarado da IPA dentro do ZIP é inválido.")

    reports = [
        info for info in archive.infolist()
        if not info.is_dir() and PurePosixPath(info.filename).name == "build-report.json"
    ]
    if len(reports) != 1:
        raise RuntimeError(
            f"Esperado exatamente um build-report.json; encontrados: {len(reports)}."
        )
    build_report = json.loads(archive.read(reports[0]).decode("utf-8"))
    if build_report.get("project") != "KaKaRoTiOS":
        raise RuntimeError("build-report.json não pertence ao projeto KaKaRoTiOS.")
    if build_report.get("title_id") != "010051C0134F8000":
        raise RuntimeError("build-report.json não pertence ao Title ID 010051C0134F8000 do Kakarot.")
    if build_report.get("branch") != BRANCH:
        raise RuntimeError("build-report.json indica uma branch diferente de KaKaRoTiOS.")
    if int(build_report.get("ipa_size_bytes", -1)) != int(ipa_info.file_size):
        raise RuntimeError("Tamanho da IPA diverge do build-report.json.")
    report_ipa_name = PurePosixPath(str(build_report.get("ipa", ""))).name
    if report_ipa_name and report_ipa_name != IPA_NAME:
        raise RuntimeError(
            f"Nome da IPA no build report é inesperado: {report_ipa_name!r}."
        )

    ipa_sha = hashlib.sha256()
    ipa_md5_hash = hashlib.md5()
    extracted_size = 0
    with archive.open(ipa_info, "r") as source, open(IPA_PATH, "wb") as target:
        while True:
            chunk = source.read(8 * 1024 * 1024)
            if not chunk:
                break
            target.write(chunk)
            ipa_sha.update(chunk)
            ipa_md5_hash.update(chunk)
            extracted_size += len(chunk)

IPA_SIZE = IPA_PATH.stat().st_size
IPA_SHA256 = ipa_sha.hexdigest().lower()
IPA_MD5 = ipa_md5_hash.hexdigest().lower()
if extracted_size != ipa_info.file_size or IPA_SIZE != int(build_report["ipa_size_bytes"]):
    raise RuntimeError("IPA extraída não corresponde ao tamanho confirmado no ZIP/build report.")

print("IPA extraída:", IPA_PATH)
print("Tamanho:", f"{IPA_SIZE:,}", "bytes")
print("IPA SHA-256:", IPA_SHA256)
print("IPA MD5:", IPA_MD5)
print("Build report:", build_report.get("project"), build_report.get("branch"))

# ------------------------------------------------------------
# 5. ENVIAR AO DRIVE E VERIFICAR TAMANHO/MD5/PROVENIÊNCIA
# ------------------------------------------------------------

print("\n5/5 — Enviando IPA para a subpasta ipa do Kakarot no Drive...")
folder_query = (
    f"'{DRIVE_ROOT_FOLDER_ID}' in parents and "
    f"name = '{DRIVE_IPA_FOLDER_NAME}' and "
    "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
)
folder_results = drive.files().list(
    q=folder_query,
    fields="files(id,name,mimeType,modifiedTime)",
    pageSize=100,
    orderBy="modifiedTime desc",
).execute().get("files", [])

if folder_results:
    ipa_folder_id = folder_results[0]["id"]
else:
    created_folder = drive.files().create(
        body={
            "name": DRIVE_IPA_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [DRIVE_ROOT_FOLDER_ID],
        },
        fields="id,name",
    ).execute()
    ipa_folder_id = created_folder["id"]
    print("Subpasta criada:", created_folder["name"])

DRIVE_PROVENANCE_DESCRIPTION = (
    f"KaKaRoTiOS provenance | branch={BRANCH} | commit={COMMIT_SHA} | "
    f"run_id={RUN_ID} | run_created_at={selected_run.get('created_at')} | "
    f"artifact={ARTIFACT_NAME} | artifact_id={ARTIFACT_ID} | "
    f"artifact_sha256={DOWNLOADED_ZIP_SHA256} | ipa_sha256={IPA_SHA256} | "
    f"ipa_md5={IPA_MD5} | run_url={RUN_URL} | commit_url={COMMIT_URL} | "
    "signature=ad-hoc; sideload re-sign may be required"
)

file_query = (
    f"'{ipa_folder_id}' in parents and "
    f"name = '{IPA_NAME}' and trashed = false"
)
existing_files = drive.files().list(
    q=file_query,
    fields="files(id,name,size,md5Checksum,modifiedTime)",
    pageSize=100,
    orderBy="modifiedTime desc",
).execute().get("files", [])

media = MediaFileUpload(
    str(IPA_PATH),
    mimetype="application/octet-stream",
    resumable=True,
    chunksize=DRIVE_CHUNK,
)

if existing_files:
    target_file_id = existing_files[0]["id"]
    request = drive.files().update(
        fileId=target_file_id,
        body={"description": DRIVE_PROVENANCE_DESCRIPTION},
        media_body=media,
        fields="id,name,size,md5Checksum,description,webViewLink,parents",
    )
    print("Atualizando IPA existente no Drive:", target_file_id)
else:
    request = drive.files().create(
        body={
            "name": IPA_NAME,
            "parents": [ipa_folder_id],
            "description": DRIVE_PROVENANCE_DESCRIPTION,
        },
        media_body=media,
        fields="id,name,size,md5Checksum,description,webViewLink,parents",
    )
    print("Criando IPA no Drive...")

uploaded = None
last_percent = -5
while uploaded is None:
    status, uploaded = request.next_chunk(num_retries=5)
    if status:
        percent = int(status.progress() * 100)
        if percent >= last_percent + 5 or percent == 100:
            print(f"Colab -> Google Drive: {percent}%")
            last_percent = percent

print("Verificando arquivo remoto no Drive...")
remote = drive.files().get(
    fileId=uploaded["id"],
    fields="id,name,size,md5Checksum,description,webViewLink,parents",
).execute()

if int(remote.get("size", -1)) != IPA_SIZE:
    raise RuntimeError(
        f"Tamanho remoto divergente: local={IPA_SIZE:,}; Drive={remote.get('size')}."
    )
if remote.get("md5Checksum", "").lower() != IPA_MD5:
    raise RuntimeError(
        f"MD5 remoto divergente: local={IPA_MD5}; Drive={remote.get('md5Checksum')}."
    )
if remote.get("description") != DRIVE_PROVENANCE_DESCRIPTION:
    raise RuntimeError("A proveniência gravada no Drive não corresponde à transferência atual.")
if ipa_folder_id not in remote.get("parents", []):
    raise RuntimeError("O arquivo foi enviado para uma pasta diferente da subpasta ipa do Kakarot.")

print("\n" + "=" * 72)
print("UPLOAD_VERIFICADO — SUCESSO")
print("=" * 72)
print("Arquivo:", remote["name"])
print("Projeto:", "KaKaRoTiOS — Dragon Ball Z: Kakarot")
print("Repositório:", REPO)
print("Branch:", BRANCH)
print("Commit da IPA:", COMMIT_SHA)
print("HEAD atual da branch:", LATEST_BRANCH_SHA)
print("Commit da IPA é o HEAD?", "SIM" if COMMIT_SHA == LATEST_BRANCH_SHA else "NÃO — IPA válida mais recente, mas não é o HEAD")
print("Workflow run:", RUN_ID)
print("Run URL:", RUN_URL)
print("Artifact:", ARTIFACT_NAME)
print("Artifact ID descoberto:", ARTIFACT_ID)
print("Artifact ZIP SHA-256:", DOWNLOADED_ZIP_SHA256)
print("IPA tamanho:", f"{IPA_SIZE:,}", "bytes")
print("IPA SHA-256:", IPA_SHA256)
print("IPA MD5 Drive:", remote["md5Checksum"])
print("Drive file ID:", remote["id"])
print("Drive link:", remote.get("webViewLink"))
print("Pasta:", f"https://drive.google.com/drive/folders/{ipa_folder_id}")
print("Proveniência gravada:", remote.get("description"))
print("=" * 72)

if not KEEP_LOCAL_FILES:
    ZIP_PATH.unlink(missing_ok=True)
    IPA_PATH.unlink(missing_ok=True)
    print("ZIP e IPA temporários removidos do Colab após a verificação.")
else:
    print("Cópias locais preservadas em:", WORK)
