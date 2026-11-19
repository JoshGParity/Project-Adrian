"""Make one API.Bible call and print status, headers and Bibles."""

import json
import os
import sys
import urllib.error
import urllib.request

BIBLES_URL = 'https://rest.api.bible/v1/bibles'
REQUEST_TIMEOUT_SECONDS = 30


def main():
    # Send the one call. No retries.
    response = send_bibles_request()

    status_code = response.status
    print(f'HTTP status: {status_code}')

    print_headers(response)

    response_bytes = response.read()
    response.close()

    # A failed call prints its reply and goes red.
    if status_code != 200:
        print('')
        print(response_bytes.decode())
        sys.exit(1)

    response_data = json.loads(response_bytes)
    print_bibles(response_data['data'])


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


def print_headers(response):
    print('')
    print('== Response headers ==')

    for header in response.headers.items():
        header_name = header[0]
        header_value = header[1]
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
