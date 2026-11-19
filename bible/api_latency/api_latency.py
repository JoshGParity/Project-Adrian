"""Time three API.Bible calls and save each one to Supabase."""

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE_URL = 'https://rest.api.bible'
KJV_BIBLE_ID = 'de4e12af7f28f599-02'
SAMPLES_TABLE_PATH = '/rest/v1/versuz_bible_api_samples'
REQUEST_TIMEOUT_SECONDS = 30
TEST_START = datetime.datetime(2026, 11, 19, tzinfo=datetime.timezone.utc)
TEST_END = datetime.datetime(2026, 11, 20, 1, tzinfo=datetime.timezone.utc)
FIRST_SLOT_HOUR = 13


def main():
    now = datetime.datetime.now(datetime.timezone.utc)

    # Outside the test window, make no calls.
    if now < TEST_START or now >= TEST_END:
        print(f'Outside the test window at {now.isoformat()}. No calls made.')
        return

    run_number = calculate_run_number(now)
    print(f'Run number {run_number}.')

    endpoints = build_endpoints(run_number)

    # One try per call. No retries.
    all_calls_passed = True
    for endpoint in endpoints:
        call_passed = time_and_save_call(endpoint)
        if not call_passed:
            all_calls_passed = False

    # A failed call turns the run red.
    if not all_calls_passed:
        sys.exit(1)


def calculate_run_number(now):
    # Step back 30 minutes so late starts keep their hour.
    slot_time = now - datetime.timedelta(minutes=30)

    # Modulo wraps midnight: 13:55 is 1, 00:55 is 12.
    return (slot_time.hour - FIRST_SLOT_HOUR + 1) % 24


def build_endpoints(run_number):
    bibles_endpoint = '/v1/bibles'
    verse_path = f'/v1/bibles/{KJV_BIBLE_ID}/verses'
    new_verse_endpoint = f'{verse_path}/JHN.14.{run_number}?content-type=text'
    same_verse_endpoint = f'{verse_path}/JHN.3.16?content-type=text'

    endpoints = []
    endpoints.append(bibles_endpoint)
    endpoints.append(new_verse_endpoint)
    endpoints.append(same_verse_endpoint)
    return endpoints


def time_and_save_call(endpoint):
    called_at = datetime.datetime.now(datetime.timezone.utc)
    call_result = send_timed_request(endpoint)

    http_status = call_result['http_status']
    latency_ms = call_result['latency_ms']
    response_body = call_result['response_body']

    # The Bible list is large, so skip it on success.
    if endpoint == '/v1/bibles' and http_status == 200:
        response_body = None

    sample_row = {
        'called_at': called_at.isoformat(),
        'endpoint': endpoint,
        'http_status': http_status,
        'response_headers': call_result['response_headers'],
        'response_body': response_body,
        'latency_ms': latency_ms,
    }
    save_sample(sample_row)

    x_cache = read_x_cache(call_result['response_headers'])
    print(f'{endpoint}: status {http_status}, {latency_ms} ms, X-Cache {x_cache}.')

    return http_status == 200


def send_timed_request(endpoint):
    # The key is never printed.
    bible_api_key = os.environ['BIBLE_API_KEY']

    request_url = API_BASE_URL + endpoint
    request_headers = {'api-key': bible_api_key, 'Accept': 'application/json'}
    bible_request = urllib.request.Request(request_url, headers=request_headers)

    # urlopen opens a new connection every call.
    start_seconds = time.perf_counter()
    try:
        response = urllib.request.urlopen(bible_request, timeout=REQUEST_TIMEOUT_SECONDS)
        response_bytes = response.read()
    except urllib.error.HTTPError as http_error:
        response = http_error
        response_bytes = http_error.read()
    except Exception as call_error:
        latency_ms = measure_latency_ms(start_seconds)
        error_body = {'error': repr(call_error)}
        return {
            'http_status': None,
            'response_headers': None,
            'response_body': error_body,
            'latency_ms': latency_ms,
        }
    latency_ms = measure_latency_ms(start_seconds)

    http_status = response.status
    header_pairs = read_header_pairs(response)
    response.close()

    return {
        'http_status': http_status,
        'response_headers': header_pairs,
        'response_body': read_body(response_bytes),
        'latency_ms': latency_ms,
    }


def measure_latency_ms(start_seconds):
    elapsed_seconds = time.perf_counter() - start_seconds
    return round(elapsed_seconds * 1000)


def read_header_pairs(response):
    # A list keeps headers that repeat a name.
    header_pairs = []
    for header in response.headers.items():
        header_pair = {'name': header[0], 'value': header[1]}
        header_pairs.append(header_pair)
    return header_pairs


def read_body(response_bytes):
    response_text = response_bytes.decode()

    # Keep a non-JSON reply as plain text.
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return response_text


def read_x_cache(header_pairs):
    if header_pairs is None:
        return 'none'

    for header_pair in header_pairs:
        if header_pair['name'].lower() == 'x-cache':
            return header_pair['value']
    return 'none'


def save_sample(sample_row):
    supabase_url = os.environ['SUPABASE_URL']
    table_url = supabase_url + SAMPLES_TABLE_PATH
    secret_key = os.environ['SUPABASE_SECRET_KEY']

    row_json = json.dumps(sample_row)
    row_bytes = row_json.encode()

    write_headers = {'apikey': secret_key, 'Content-Type': 'application/json'}
    write_request = urllib.request.Request(
        table_url,
        data=row_bytes,
        method='POST',
        headers=write_headers,
    )

    # A failed write fails the run.
    response = urllib.request.urlopen(write_request, timeout=REQUEST_TIMEOUT_SECONDS)
    response.close()


if __name__ == '__main__':
    main()
