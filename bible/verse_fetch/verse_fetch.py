"""Make 56 API.Bible verse calls once and save each to Supabase."""

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
NO_KEY_CALL_NUMBER = 50

KJV = 'de4e12af7f28f599-02'
KJV_TWIN = 'de4e12af7f28f599-01'
WEB = '9879dbb7cfe39e4d-04'
BSB = 'bba9f40183526463-01'
BSB_TWIN = '317e03834065a236-01'
NLT = 'd6e14a625393b4da-01'
NIV11 = '78a9f6124f344018-01'
NKJV = '63097d2a0a2f7db3-01'
ASV = '06125adad2d5898a-01'
F35 = '2f0fd81d7b85b923-01'
MISSING_BIBLE = '0000000000000000-01'

TEXT = 'content-type=text'
PARALLELS = f'content-type=text&parallels={KJV},{WEB}'


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
    endpoints.extend(build_romans_12_calls())
    endpoints.extend(build_romans_6_calls())
    endpoints.extend(build_parallel_calls())
    endpoints.extend(build_john_3_16_calls())
    endpoints.extend(build_edge_calls())
    endpoints.extend(build_repeat_calls())
    return endpoints


def build_romans_12_calls():
    endpoints = []
    endpoints.append(verse_url(KJV, 'ROM.12.2', TEXT))
    endpoints.append(verse_url(KJV, 'ROM.12.2', 'content-type=json'))
    endpoints.append(verse_url(KJV, 'ROM.12.2', ''))
    endpoints.append(verse_url(KJV, 'ROM.12.2', 'content-type=text&include-verse-numbers=false&include-titles=false'))
    endpoints.append(verse_url(WEB, 'ROM.12.2', 'content-type=text&include-notes=true'))
    return endpoints


def build_romans_6_calls():
    endpoints = []
    endpoints.append(passage_url(KJV, 'ROM.6.15-ROM.6.18', TEXT))
    endpoints.append(verse_url(KJV, 'ROM.6.15-ROM.6.18', TEXT))
    endpoints.append(passage_url(KJV, 'ROM.5.21-ROM.6.2', TEXT))
    endpoints.append(passage_url(KJV, 'ROM.6', TEXT))
    endpoints.append(f'{API_BASE_URL}/bibles/{KJV}/chapters/ROM.6?{TEXT}')
    endpoints.append(passage_url(KJV, 'ROM.6.18-ROM.6.15', TEXT))
    endpoints.append(passage_url(KJV, 'GEN.1.1-GEN.10.32', TEXT))
    return endpoints


def build_parallel_calls():
    endpoints = []
    endpoints.append(verse_url(BSB, 'ROM.6.23', PARALLELS))
    endpoints.append(verse_url(BSB, 'ROM.6.15', PARALLELS))
    endpoints.append(verse_url(BSB, 'ROM.6.21', PARALLELS))
    endpoints.append(verse_url(BSB, 'ROM.6.18', PARALLELS))
    return endpoints


def build_john_3_16_calls():
    bible_ids = [KJV, KJV_TWIN, WEB, BSB, BSB_TWIN, NLT, NIV11, NKJV, ASV]

    endpoints = []
    for bible_id in bible_ids:
        endpoints.append(verse_url(bible_id, 'JHN.3.16', TEXT))
    return endpoints


def build_edge_calls():
    endpoints = []
    endpoints.append(f'{API_BASE_URL}/bibles/{KJV}/books')
    endpoints.append(f'{API_BASE_URL}/bibles/{WEB}/books')
    endpoints.append(verse_url(KJV, 'PSA.23.1', TEXT))
    endpoints.append(verse_url(KJV, 'SNG.2.4', TEXT))
    endpoints.append(verse_url(KJV, '1SA.17.47', TEXT))
    endpoints.append(verse_url(KJV, 'PHM.1.6', TEXT))
    endpoints.append(verse_url(KJV, 'JUD.1.24', TEXT))
    endpoints.append(verse_url(KJV, 'JHN.3.99', TEXT))
    endpoints.append(verse_url(KJV, 'JHN.22.1', TEXT))
    endpoints.append(verse_url(KJV, 'XYZ.1.1', TEXT))
    endpoints.append(verse_url(KJV, 'jhn.3.16', TEXT))
    endpoints.append(verse_url(KJV, 'John%203%3A16', TEXT))
    endpoints.append(verse_url(KJV, 'ROM.6.0', TEXT))
    endpoints.append(verse_url(KJV, 'MAT.17.21', TEXT))
    endpoints.append(verse_url(WEB, 'MAT.17.21', TEXT))
    endpoints.append(verse_url(BSB, 'MAT.17.21', TEXT))
    endpoints.append(verse_url(F35, 'GEN.1.1', TEXT))
    endpoints.append(verse_url(MISSING_BIBLE, 'JHN.3.16', TEXT))
    endpoints.append(verse_url(KJV, 'ROM.12.2', 'content-type=xml'))
    endpoints.append(f'{API_BASE_URL}/bibles/{KJV}/chapters/ROM.6/verses')
    endpoints.append(search_url('John%203%3A16'))
    endpoints.append(search_url('Romans%206%3A15-18'))
    endpoints.append(search_url('Song%20of%20Solomon%202%3A4'))
    endpoints.append(search_url('Psalm%2023%3A1'))
    return endpoints


def build_repeat_calls():
    romans_8_28 = verse_url(KJV, 'ROM.8.28', TEXT)

    endpoints = []
    endpoints.append(verse_url(KJV, 'JHN.11.35', TEXT))
    endpoints.append(romans_8_28)
    endpoints.append(romans_8_28)
    endpoints.append(romans_8_28)
    endpoints.append(verse_url(WEB, 'JHN.3.16', TEXT))
    endpoints.append(f'{API_BASE_URL}/bibles/{KJV}/books')
    endpoints.append(romans_8_28)
    return endpoints


def verse_url(bible_id, verse_id, query):
    return add_query(f'{API_BASE_URL}/bibles/{bible_id}/verses/{verse_id}', query)


def passage_url(bible_id, passage_id, query):
    return add_query(f'{API_BASE_URL}/bibles/{bible_id}/passages/{passage_id}', query)


def search_url(encoded_query):
    return f'{API_BASE_URL}/bibles/{KJV}/search?query={encoded_query}'


def add_query(path_url, query):
    if query == '':
        return path_url
    return f'{path_url}?{query}'


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
    send_key = call_number != NO_KEY_CALL_NUMBER

    called_at = datetime.datetime.now(datetime.timezone.utc)
    call_result = send_timed_request(endpoint, send_key)

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


def send_timed_request(endpoint, send_key):
    request_headers = {}

    # The key is never printed.
    if send_key:
        request_headers['api-key'] = os.environ['BIBLE_API_KEY']

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
