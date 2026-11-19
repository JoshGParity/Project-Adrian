"""Fetch 19 API.Bible Bible records once and save each to Supabase."""

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE_URL = 'https://rest.api.bible/v1'
SAMPLES_TABLE_PATH = '/rest/v1/versuz_bible_api_samples'
REQUEST_TIMEOUT_SECONDS = 30
BIBLE_IDS = [
    '78a9f6124f344018-01',
    '63097d2a0a2f7db3-01',
    'd6e14a625393b4da-01',
    'b907c8622b59a1f7-01',
    '43e315b442a7c862-01',
    '66c22495370cdfc0-01',
    '32339cf2f720ff8e-01',
    'c89622d31b60c444-02',
    '2f0fd81d7b85b923-01',
    '317e03834065a236-01',
    '7142879509583d59-04',
    '72f4e6dc683324df-02',
    '32664dc3288a28df-02',
    'de4e12af7f28f599-02',
    '06125adad2d5898a-01',
    '65bfdebd704a8324-01',
    '6bab4d6c61b31b80-01',
    'bf8f1c7f3f9045a5-01',
    'ec290b5045ff54a5-01',
]


def main():
    endpoints = build_endpoints()
    print(f'{len(endpoints)} calls planned.')

    # Stop if an earlier run already saved call 1.
    if test_already_ran(endpoints[0]):
        print('Call 1 is already in Supabase. No calls made.')
        return

    # One try per call. No retries.
    all_rows_saved = True
    for call_index in range(len(endpoints)):
        call_number = call_index + 1
        row_saved = time_and_save_call(call_number, endpoints[call_index])
        if not row_saved:
            all_rows_saved = False

    # A failed save turns the run red.
    if not all_rows_saved:
        sys.exit(1)


def build_endpoints():
    endpoints = []
    for bible_id in BIBLE_IDS:
        endpoints.append(f'{API_BASE_URL}/bibles/{bible_id}')
    return endpoints


def test_already_ran(first_endpoint):
    supabase_url = os.environ['SUPABASE_URL']
    secret_key = os.environ['SUPABASE_SECRET_KEY']

    # Encode the URL so it fits in a filter.
    endpoint_filter = urllib.parse.quote(first_endpoint, safe='')
    lookup_url = f'{supabase_url}{SAMPLES_TABLE_PATH}?select=id&endpoint=eq.{endpoint_filter}'

    lookup_headers = {'apikey': secret_key}
    lookup_request = urllib.request.Request(lookup_url, headers=lookup_headers)
    response = urllib.request.urlopen(lookup_request, timeout=REQUEST_TIMEOUT_SECONDS)
    matching_rows = json.loads(response.read())
    response.close()

    return len(matching_rows) > 0


def time_and_save_call(call_number, endpoint):
    called_at = datetime.datetime.now(datetime.timezone.utc)
    call_result = send_timed_request(endpoint)

    http_status = call_result['http_status']
    latency_ms = call_result['latency_ms']
    x_cache = read_x_cache(call_result['response_headers'])
    print(f'#{call_number} {endpoint}: status {http_status}, {latency_ms} ms, X-Cache {x_cache}.')

    sample_row = {
        'called_at': called_at.isoformat(),
        'endpoint': endpoint,
        'http_status': http_status,
        'response_headers': call_result['response_headers'],
        'response_body': call_result['response_body'],
        'latency_ms': latency_ms,
    }

    # Keep calling even if one save fails.
    try:
        save_sample(sample_row)
    except Exception as save_error:
        print(f'#{call_number} save failed: {save_error!r}')
        return False
    return True


def send_timed_request(endpoint):
    # The key is never printed.
    request_headers = {'api-key': os.environ['BIBLE_API_KEY']}
    bible_request = urllib.request.Request(endpoint, headers=request_headers)

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
    response_text = response_bytes.decode(errors='replace')

    # Keep a non-JSON reply under a raw key.
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return {'raw': response_text}


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
    response = urllib.request.urlopen(write_request, timeout=REQUEST_TIMEOUT_SECONDS)
    response.close()


if __name__ == '__main__':
    main()
