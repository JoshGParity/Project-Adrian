"""Make one API.Bible call, save the sample, print what came back."""

import json
import os
import sys
import urllib.error
import urllib.request

BIBLES_URL = 'https://rest.api.bible/v1/bibles'
SAMPLES_TABLE_PATH = '/rest/v1/versuz_bible_api_samples'
REQUEST_TIMEOUT_SECONDS = 30


def main():
    # Send the one call. No retries.
    response = send_bibles_request()

    status_code = response.status
    header_pairs = read_header_pairs(response)
    response_bytes = response.read()
    response.close()

    response_body = read_body(response_bytes)

    print(f'HTTP status: {status_code}')
    print_headers(header_pairs)

    # Save before the Bible list, so the sample lands.
    save_sample(status_code, header_pairs, response_body)

    # A failed call prints its reply and goes red.
    if status_code != 200:
        print('')
        print(response_bytes.decode())
        sys.exit(1)

    print_bibles(response_body['data'])


def send_bibles_request():
    # The key is never printed.
    bible_api_key = os.environ['BIBLE_API_KEY']

    request_headers = {'api-key': bible_api_key, 'Accept': 'application/json'}
    bibles_request = urllib.request.Request(BIBLES_URL, headers=request_headers)

    # An error reply still carries a status and headers.
    try:
        return urllib.request.urlopen(bibles_request, timeout=REQUEST_TIMEOUT_SECONDS)
    except urllib.error.HTTPError as http_error:
        return http_error


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


def save_sample(status_code, header_pairs, response_body):
    supabase_url = os.environ['SUPABASE_URL']
    table_url = supabase_url + SAMPLES_TABLE_PATH
    secret_key = os.environ['SUPABASE_SECRET_KEY']

    sample_row = {
        'endpoint': BIBLES_URL,
        'http_status': status_code,
        'response_headers': header_pairs,
        'response_body': response_body,
    }
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
    print('Saved the sample to Supabase.')


def print_headers(header_pairs):
    print('')
    print('== Response headers ==')

    for header_pair in header_pairs:
        header_name = header_pair['name']
        header_value = header_pair['value']
        print(f'{header_name}: {header_value}')


def print_bibles(bibles):
    num_bibles = len(bibles)
    print('')
    print(f'== Bibles ({num_bibles}) ==')
    print('id | abbreviation | name | language')

    for bible in bibles:
        bible_id = bible['id']
        abbreviation = bible['abbreviation']
        name = bible['name']
        language_name = bible['language']['name']
        print(f'{bible_id} | {abbreviation} | {name} | {language_name}')


if __name__ == '__main__':
    main()
