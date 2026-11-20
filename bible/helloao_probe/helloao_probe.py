"""Fetch the helloao translation list once and save it."""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TRANSLATIONS_URL = 'https://bible.helloao.org/api/available_translations.json'
SAMPLES_TABLE_PATH = '/rest/v1/versuz_helloao_samples'
REQUEST_TIMEOUT_SECONDS = 60


def main():
    # Stop if an earlier run already saved the call.
    if test_already_ran():
        print('A row for this URL is already in Supabase. No call made.')
        return

    # One try. No retries.
    call_result = send_timed_request()

    http_status = call_result['http_status']
    latency_ms = call_result['latency_ms']
    print(f'{TRANSLATIONS_URL}: status {http_status}, {latency_ms} ms.')

    sample_row = {
        'url': TRANSLATIONS_URL,
        'http_status': http_status,
        'response_headers': call_result['response_headers'],
        'response_body': call_result['response_body'],
        'latency_ms': latency_ms,
    }
    saved_id = save_sample(sample_row)
    print(f'Saved as versuz_helloao_samples id {saved_id}.')

    # A failed call turns the run red.
    if http_status != 200:
        sys.exit(1)


def test_already_ran():
    supabase_url = os.environ['SUPABASE_URL']
    secret_key = os.environ['SUPABASE_SECRET_KEY']

    # Encode the URL so it fits in a filter.
    url_filter = urllib.parse.quote(TRANSLATIONS_URL, safe='')
    lookup_url = f'{supabase_url}{SAMPLES_TABLE_PATH}?select=id&url=eq.{url_filter}'

    lookup_headers = {'apikey': secret_key}
    lookup_request = urllib.request.Request(lookup_url, headers=lookup_headers)
    response = urllib.request.urlopen(lookup_request, timeout=REQUEST_TIMEOUT_SECONDS)
    matching_rows = json.loads(response.read())
    response.close()

    return len(matching_rows) > 0


def send_timed_request():
    # No key or auth header. The API is open.
    helloao_request = urllib.request.Request(TRANSLATIONS_URL)

    start_seconds = time.perf_counter()
    try:
        response = urllib.request.urlopen(helloao_request, timeout=REQUEST_TIMEOUT_SECONDS)
        response_bytes = response.read()
    except urllib.error.HTTPError as http_error:
        response = http_error
        response_bytes = http_error.read()
    except Exception as call_error:
        latency_ms = measure_latency_ms(start_seconds)
        return {
            'http_status': None,
            'response_headers': None,
            'response_body': repr(call_error),
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

    # Keep a non-JSON reply as a JSON string.
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return response_text


def save_sample(sample_row):
    supabase_url = os.environ['SUPABASE_URL']
    table_url = supabase_url + SAMPLES_TABLE_PATH
    secret_key = os.environ['SUPABASE_SECRET_KEY']

    row_json = json.dumps(sample_row)
    row_bytes = row_json.encode()

    # Ask Supabase to send back the new id.
    write_headers = {
        'apikey': secret_key,
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }
    write_request = urllib.request.Request(
        table_url + '?select=id',
        data=row_bytes,
        method='POST',
        headers=write_headers,
    )
    response = urllib.request.urlopen(write_request, timeout=REQUEST_TIMEOUT_SECONDS)
    saved_rows = json.loads(response.read())
    response.close()

    return saved_rows[0]['id']


if __name__ == '__main__':
    main()
