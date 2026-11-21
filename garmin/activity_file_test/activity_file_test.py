"""Save one Garmin activity's detail and file, raw, once."""

import base64
import json
import os
import urllib.parse
import urllib.request

GARMIN_API_URL = 'https://personal.connectapi.garmin.com'
TOKEN_PATH = '/personalapitoken-service/personal-api/personal-api-key/token'
DISCOVERY_TABLE_PATH = '/rest/v1/discovery_garmin_raw_payloads'
ACTIVITY_ID = 25155176957
GARMIN_TIMEOUT_SECONDS = 30
WRITE_TIMEOUT_SECONDS = 20


def main():
    file_endpoint_name = f'Activity file {ACTIVITY_ID}'

    # Stop if an earlier run saved the file.
    if test_already_ran(file_endpoint_name):
        print('The activity file is already in Supabase. No calls made.')
        return

    access_token = get_access_token()

    detail_path = f'/activity-service/activity/{ACTIVITY_ID}'
    detail_bytes = get_garmin_bytes(detail_path, 'application/json', access_token)
    detail_data = json.loads(detail_bytes)
    save_payload(f'Activity detail {ACTIVITY_ID}', detail_data)

    # The file is a ZIP, kept as base64 text.
    file_path = f'/download-service/files/activity/{ACTIVITY_ID}'
    file_bytes = get_garmin_bytes(file_path, 'application/zip', access_token)
    file_text = base64.b64encode(file_bytes).decode()
    file_data = {'zip_base64': file_text}
    save_payload(file_endpoint_name, file_data)

    print('Saved the activity detail and file.')


def test_already_ran(endpoint_name):
    # Look for a saved file row.
    supabase_url = os.environ['SUPABASE_URL']
    secret_key = os.environ['SUPABASE_SECRET_KEY']
    endpoint_filter = urllib.parse.quote(endpoint_name)
    lookup_url = f'{supabase_url}{DISCOVERY_TABLE_PATH}?select=id&endpoint=eq.{endpoint_filter}'
    lookup_headers = {'apikey': secret_key}
    lookup_request = urllib.request.Request(lookup_url, headers=lookup_headers)

    response = urllib.request.urlopen(lookup_request, timeout=WRITE_TIMEOUT_SECONDS)
    matching_rows = json.loads(response.read())
    response.close()

    return len(matching_rows) > 0


def get_access_token():
    # Build the token request from the key.
    garmin_key = os.environ['GARMIN_CONNECT_KEY']
    token_url = GARMIN_API_URL + TOKEN_PATH
    token_headers = {'Authorization': 'ApiKey ' + garmin_key, 'Accept': '*/*'}
    token_request = urllib.request.Request(
        token_url,
        data=b'',
        method='POST',
        headers=token_headers,
    )

    # Send it. A bad key fails the run.
    response = urllib.request.urlopen(token_request, timeout=GARMIN_TIMEOUT_SECONDS)
    response_bytes = response.read()
    response.close()

    # The token is plain text. Never print it.
    response_text = response_bytes.decode()
    access_token = response_text.strip()
    return access_token


def get_garmin_bytes(path, accept_type, access_token):
    # Garmin takes the token as a bearer token.
    garmin_url = GARMIN_API_URL + path
    garmin_headers = {'Authorization': 'Bearer ' + access_token, 'Accept': accept_type}
    garmin_request = urllib.request.Request(garmin_url, headers=garmin_headers)

    # A failed call fails the run.
    response = urllib.request.urlopen(garmin_request, timeout=GARMIN_TIMEOUT_SECONDS)
    response_bytes = response.read()
    response.close()
    return response_bytes


def save_payload(endpoint_name, payload):
    # Build the table address and JSON body.
    supabase_url = os.environ['SUPABASE_URL']
    table_url = supabase_url + DISCOVERY_TABLE_PATH
    secret_key = os.environ['SUPABASE_SECRET_KEY']
    sample_row = {'endpoint': endpoint_name, 'payload': payload}
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
    response = urllib.request.urlopen(write_request, timeout=WRITE_TIMEOUT_SECONDS)
    response.close()


if __name__ == '__main__':
    main()
