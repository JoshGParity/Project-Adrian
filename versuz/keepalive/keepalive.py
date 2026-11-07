"""Ping the Versuz API so Render stays awake, then record the ping in Supabase."""

import json
import os
import time
import urllib.error
import urllib.request

PING_TIMEOUT_SECONDS = 90
INSERT_TIMEOUT_SECONDS = 20
PING_TABLE_PATH = '/rest/v1/versuz_keepalive_pings'


def main():
    # Ping Versuz once and time the call.
    ping_row = ping_versuz()

    # Show the status and latency in the run log.
    status_code = ping_row['status_code']
    latency_ms = ping_row['latency_ms']
    print(f'Ping status {status_code}, {latency_ms} ms.')

    # Write the ping row to the table in Project Adrian.
    write_ping_row(ping_row)


def ping_versuz():
    # Build the ping address from the API address and the ping route.
    api_base_url = os.environ['VERSUZ_API_BASE_URL']
    ping_path = os.environ['VERSUZ_PING_PATH']
    ping_url = api_base_url + ping_path

    # Start the clock just before the call.
    start_time = time.monotonic()

    # Send the ping with no login. An awake API answers 401, and every outcome still gets a row.
    try:
        response = urllib.request.urlopen(ping_url, timeout=PING_TIMEOUT_SECONDS)
        status_code = response.status
        response.close()
    except urllib.error.HTTPError as http_error:
        # A 4xx or 5xx answer is still an answer, so keep its status.
        status_code = http_error.code
    except OSError:
        # No answer at all (asleep past the timeout, or no connection) has no status.
        status_code = None

    # Work out how long the call took, in milliseconds.
    elapsed_seconds = time.monotonic() - start_time
    latency_ms = int(elapsed_seconds * 1000)

    return {'status_code': status_code, 'latency_ms': latency_ms}


def write_ping_row(ping_row):
    # Build the table address in Project Adrian.
    supabase_url = os.environ['SUPABASE_URL']
    table_url = supabase_url + PING_TABLE_PATH

    # Read Project Adrian's secret key.
    secret_key = os.environ['SUPABASE_SECRET_KEY']

    # Put the ping row in a JSON body. The table fills in the time.
    row_json = json.dumps(ping_row)
    row_bytes = row_json.encode()

    # Build the insert request. Supabase takes the secret key in the apikey header.
    insert_headers = {'apikey': secret_key, 'Content-Type': 'application/json'}
    insert_request = urllib.request.Request(
        table_url,
        data=row_bytes,
        method='POST',
        headers=insert_headers,
    )

    # Send the insert. A failed insert crashes here, so the run goes red.
    response = urllib.request.urlopen(insert_request, timeout=INSERT_TIMEOUT_SECONDS)
    response.close()


if __name__ == '__main__':
    main()
