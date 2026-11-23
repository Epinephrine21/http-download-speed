"""Measure HTTP download speed with ten sequential GET requests."""

import argparse
import http.client
import math
import sys
from dataclasses import dataclass
from time import perf_counter
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class Result:
    byte_count: int
    seconds: float


def http_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid HTTP or HTTPS URL.") from exc
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or port == 0
        or any(char.isspace() or ord(char) < 32 for char in value)
    ):
        raise ValueError("Enter an absolute HTTP or HTTPS URL without credentials.")
    return parsed._replace(fragment="").geturl()


class HTTPOnlyRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, http_url(newurl))


def download(opener, url: str, timeout: float) -> Result:
    request = Request(
        url,
        headers={"Accept-Encoding": "identity", "Cache-Control": "no-cache"},
        method="GET",
    )
    start = perf_counter()
    byte_count = 0
    with opener.open(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise ValueError(f"Unexpected HTTP status {response.status}.")
        expected_length = response.length
        while chunk := response.read(CHUNK_SIZE):
            byte_count += len(chunk)
        if expected_length is not None and byte_count != expected_length:
            raise ValueError(f"Incomplete response: expected {expected_length} bytes, got {byte_count}.")
    return Result(byte_count, perf_counter() - start)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Direct HTTP or HTTPS URL of the file")
    parser.add_argument("--timeout", type=float, default=20, help="Socket timeout in seconds (default: 20)")
    args = parser.parse_args()
    try:
        url = http_url(args.url)
    except ValueError as exc:
        parser.error(str(exc))
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a finite positive number")

    opener = build_opener(HTTPOnlyRedirects())
    results = []
    for number in range(1, REQUEST_COUNT + 1):
        try:
            result = download(opener, url, args.timeout)
        except (URLError, OSError, http.client.HTTPException, ValueError) as exc:
            print(f"Request {number}/{REQUEST_COUNT} failed: {exc}", file=sys.stderr)
            return 1
        results.append(result)
        print(f"{number:02d}/{REQUEST_COUNT}  {result.byte_count:>12,} bytes  {result.seconds:>8.3f} s")

    total_bytes = sum(result.byte_count for result in results)
    total_seconds = sum(result.seconds for result in results)
    print(f"\nAverage request time: {total_seconds / REQUEST_COUNT:.3f} s")
    print(f"Total downloaded:     {total_bytes:,} bytes")
    print(f"Download speed:       {8 * total_bytes / total_seconds / 1_000_000:.3f} Mbit/s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
