"""Make 38 API.Bible flag and error calls once and save each."""

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

NO_KEY_CALL_NUMBER = 27
EMPTY_KEY_CALL_NUMBER = 28
MADE_UP_KEY_CALL_NUMBER = 29
MADE_UP_KEY = 'not-a-real-key'

NIV = '78a9f6124f344018-01'
NLT = 'd6e14a625393b4da-01'
NKJV = '63097d2a0a2f7db3-01'

TEXT = 'content-type=text'
FLAG_QUERIES = [
    'content-type=json',
    'content-type=html',
    'content-type=text&include-notes=true',
    'content-type=text&include-titles=false',
    'content-type=text&include-chapter-numbers=true',
    'content-type=text&include-verse-numbers=false',
    'content-type=text&include-verse-spans=true',
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
    endpoints.extend(build_book_list_calls())
    endpoints.extend(build_flag_calls())
    endpoints.extend(build_title_calls())
    endpoints.extend(build_error_calls())
    return endpoints


def build_book_list_calls():
    endpoints = []
    endpoints.append(f'{API_BASE_URL}/bibles/{NIV}/books')
    endpoints.append(f'{API_BASE_URL}/bibles/{NLT}/books')
    endpoints.append(f'{API_BASE_URL}/bibles/{NKJV}/books')
    return endpoints


def build_flag_calls():
    bible_ids = [NIV, NLT, NKJV]

    endpoints = []
    for bible_id in bible_ids:
        for flag_query in FLAG_QUERIES:
            endpoints.append(verse_url(bible_id, 'JHN.3.16', flag_query))
    return endpoints


def build_title_calls():
    endpoints = []
    endpoints.append(verse_url(NIV, 'PSA.23.1', TEXT))
    endpoints.append(verse_url(NIV, 'PSA.23.1', 'content-type=text&include-titles=false'))
    return endpoints


def build_error_calls():
    john_3_16 = verse_url(NIV, 'JHN.3.16', TEXT)

    endpoints = []
    endpoints.append(john_3_16)
    endpoints.append(john_3_16)
    endpoints.append(john_3_16)
    endpoints.append(verse_url(NIV, 'JHN.3.99', TEXT))
    endpoints.append(verse_url(NIV, 'XYZ.1.1', TEXT))
    endpoints.append(verse_url(NIV, 'John%203%3A16', TEXT))
    endpoints.append(verse_url(NIV, 'JHN.3.16', 'content-type=xml'))
    endpoints.append(verse_url(NIV, 'ROM.6.15-ROM.6.18', TEXT))
    endpoints.append(f'{API_BASE_URL}/bibles/{NIV}/passages/ROM.6.18-ROM.6.15?{TEXT}')
    endpoints.append(verse_url(NIV, 'MAT.17.21', TEXT))
    endpoints.append(verse_url(NLT, 'MAT.17.21', TEXT))
    endpoints.append(verse_url(NKJV, 'MAT.17.21', TEXT))
    return endpoints


def verse_url(bible_id, verse_id, query):
    return f'{API_BASE_URL}/bibles/{bible_id}/verses/{verse_id}?{query}'


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
    request_headers = build_request_headers(call_number)

    called_at = datetime.datetime.now(datetime.timezone.utc)
    call_result = send_timed_request(endpoint, request_headers)

    http_status = call_result['http_status']
    latency_ms = call_result['latency_ms']
    print(f'#{call_number} {endpoint}: status {http_status}, {latency_ms} ms.')

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


def build_request_headers(call_number):
    if call_number == NO_KEY_CALL_NUMBER:
        return {}

    if call_number == EMPTY_KEY_CALL_NUMBER:
        return {'api-key': ''}

    if call_number == MADE_UP_KEY_CALL_NUMBER:
        return {'api-key': MADE_UP_KEY}

    # The real key is never printed.
    return {'api-key': os.environ['BIBLE_API_KEY']}


def send_timed_request(endpoint, request_headers):
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
