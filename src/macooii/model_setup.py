"""Isolated, cancellable speech model downloader, also used by the packaged application."""
import hashlib
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

TURBO_REVISION = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"
TURBO_FILES = {
    "config.json": (2263, "b0253ea6c0d3bea6b1e19e91a02acfd3b53f4467362efcb5a3e6b16c9b3a9b7e"),
    "preprocessor_config.json": (340, "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711"),
    "tokenizer.json": (2710337, "297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd"),
    "vocabulary.json": (1068114, "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1"),
    "model.bin": (1617884929, "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da"),
}


def parallel_model(client, url: str, target: Path, size: int, digest: str):
    """Use bounded HTTP ranges to avoid a slow single large-file connection."""
    block = 16 * 1024 * 1024
    parts = target.parent / "download-parts"
    parts.mkdir(exist_ok=True)
    sequential = target.with_name(target.name + ".part")
    available = sequential.stat().st_size if sequential.is_file() else 0
    jobs = []
    completed = 0
    if available:
        with sequential.open("rb") as source:
            for offset in range(0, min(available, size), block):
                count = min(block, size - offset)
                if offset + count > available:
                    break
                piece = parts / f"{offset:012d}.chunk"
                if not piece.is_file() or piece.stat().st_size != count:
                    source.seek(offset)
                    piece.write_bytes(source.read(count))
    for offset in range(0, size, block):
        count = min(block, size - offset)
        piece = parts / f"{offset:012d}.chunk"
        if piece.is_file() and piece.stat().st_size == count:
            completed += count
        else:
            jobs.append((offset, count, piece))

    def fetch(job):
        offset, count, piece = job
        temporary = piece.with_suffix(".part")
        try:
            with client.stream("GET", url, params={"download": "true", "macooii_range": str(offset)},
                               headers={"Range": f"bytes={offset}-{offset + count - 1}"}) as response:
                response.raise_for_status()
                if response.status_code != 206 or not response.headers.get("content-range", "").startswith(f"bytes {offset}-{offset + count - 1}/"):
                    raise ValueError("The model server did not honor the requested download range.")
                received = 0
                with temporary.open("wb") as stream:
                    for chunk in response.iter_bytes(1024 * 1024):
                        received += len(chunk)
                        if received > count:
                            raise ValueError("Download range exceeded its expected size.")
                        stream.write(chunk)
                if received != count:
                    raise ValueError("The model download range was incomplete. Retry to resume.")
            temporary.replace(piece)
            return count
        finally:
            temporary.unlink(missing_ok=True)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch, job) for job in jobs]
        last_percent = -1
        for future in as_completed(futures):
            completed += future.result()
            percent = completed * 100 // size
            if percent // 5 != last_percent // 5:
                print(f"Downloading recognition model: {percent}%", flush=True)
                last_percent = percent
    checksum = hashlib.sha256()
    with sequential.open("wb") as output:
        for offset in range(0, size, block):
            with (parts / f"{offset:012d}.chunk").open("rb") as source:
                while data := source.read(1024 * 1024):
                    output.write(data)
                    checksum.update(data)
    if sequential.stat().st_size != size or checksum.hexdigest() != digest:
        sequential.unlink(missing_ok=True)
        for offset in range(0, size, block):
            (parts / f"{offset:012d}.chunk").unlink(missing_ok=True)
        raise ValueError("The recognition model checksum did not match. Retry the download.")
    sequential.replace(target)
    for offset in range(0, size, block):
        (parts / f"{offset:012d}.chunk").unlink(missing_ok=True)
    parts.rmdir()


def download_turbo(destination: str):
    import httpx

    folder = Path(destination) / "models--dropbox-dash--faster-whisper-large-v3-turbo/snapshots" / TURBO_REVISION
    folder.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/resolve/{TURBO_REVISION}/"
    with httpx.Client(timeout=90, follow_redirects=True, trust_env=False) as client:
        for name, (size, digest) in TURBO_FILES.items():
            target = folder / name
            if target.is_file():
                with target.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() == digest:
                        continue
            if name == "model.bin":
                parallel_model(client, base + name, target, size, digest)
                continue
            part = folder / (name + ".part")
            received = part.stat().st_size if part.is_file() else 0
            if received > size:
                part.unlink()
                received = 0
            checksum = hashlib.sha256()
            if received:
                with part.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        checksum.update(chunk)
            if received < size:
                headers = {"Range": f"bytes={received}-"} if received else {}
                with client.stream("GET", base + name, params={"download": "true", "macooii_offset": str(received)}, headers=headers) as response:
                    response.raise_for_status()
                    if received and response.status_code == 200:
                        received, checksum = 0, hashlib.sha256()
                    if response.status_code == 206 and not response.headers.get("content-range", "").startswith(f"bytes {received}-"):
                        raise ValueError("The model download returned an incorrect byte range.")
                    with part.open("ab" if received else "wb") as stream:
                        last_percent = -1
                        for chunk in response.iter_bytes(1024 * 1024):
                            received += len(chunk)
                            if received > size:
                                raise ValueError("The model download exceeded the expected size.")
                            checksum.update(chunk)
                            stream.write(chunk)
                            percent = received * 100 // size
                            if percent // 10 != last_percent // 10:
                                print(f"Downloading {name}: {percent}%", flush=True)
                                last_percent = percent
            if received != size or checksum.hexdigest() != digest:
                if received == size:
                    part.unlink(missing_ok=True)
                raise ValueError("Speech model download is incomplete or its checksum did not match. Retry to resume.")
            part.replace(target)


def download(destination: str, model_size: str = "small"):
    from .config import SPEECH_MODELS
    if model_size not in SPEECH_MODELS:
        raise ValueError("Unsupported speech model")
    if model_size == "large-v3-turbo":
        return download_turbo(destination)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from faster_whisper.utils import download_model
    Path(destination).mkdir(parents=True, exist_ok=True)
    download_model(SPEECH_MODELS[model_size], cache_dir=destination, use_auth_token=False)


if __name__ == "__main__":
    download(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "small")
