"""Save raw Massive stock responses to a discovery table."""

import datetime
import json
import os
import urllib.request

MASSIVE_API_URL = 'https://api.massive.com'
TICKER = 'AAPL'
PAYLOAD_TABLE_PATH = '/rest/v1/discovery_stocks_raw_payloads'
REQUEST_TIMEOUT_SECONDS = 60


def main():
    # Find the last weekday and thirty days before it.
    last_day = find_last_weekday()
    thirty_days = datetime.timedelta(days=30)
    first_day = last_day - thirty_days

    # One call for all stocks on that day.
    grouped_path = f'/v2/aggs/grouped/locale/us/market/stocks/{last_day}'
    save_endpoint(grouped_path)

    # One call for thirty days of one ticker.
    ticker_path = f'/v2/aggs/ticker/{TICKER}/range/1/day/{first_day}/{last_day}'
    save_endpoint(ticker_path)


def find_last_weekday():
    # Start at yesterday by the runner's UTC clock.
    today = datetime.date.today()
    one_day = datetime.timedelta(days=1)
    last_day = today - one_day

    # Step back past Saturday and Sunday.
    while last_day.weekday() >= 5:
        last_day = last_day - one_day
    return last_day


def save_endpoint(endpoint_path):
    # Call Massive with the key in a header.
    massive_key = os.environ['MASSIVE_API_KEY']
    massive_url = MASSIVE_API_URL + endpoint_path
    massive_headers = {'Authorization': 'Bearer ' + massive_key}
    massive_request = urllib.request.Request(massive_url, headers=massive_headers)
    response = urllib.request.urlopen(massive_request, timeout=REQUEST_TIMEOUT_SECONDS)
    print(f'Massive status {response.status}.')
    response_bytes = response.read()
    response.close()

    # Build the row and its table address.
    supabase_url = os.environ['SUPABASE_URL']
    table_url = supabase_url + PAYLOAD_TABLE_PATH
    secret_key = os.environ['SUPABASE_SECRET_KEY']
    response_data = json.loads(response_bytes)
    payload_row = {'endpoint': endpoint_path, 'payload': response_data}
    row_json = json.dumps(payload_row)
    row_bytes = row_json.encode()

    # A failed write fails the run.
    save_headers = {'apikey': secret_key, 'Content-Type': 'application/json'}
    save_request = urllib.request.Request(
        table_url,
        data=row_bytes,
        method='POST',
        headers=save_headers,
    )
    response = urllib.request.urlopen(save_request, timeout=REQUEST_TIMEOUT_SECONDS)
    print(f'Supabase status {response.status}.')
    response.close()


if __name__ == '__main__':
    main()
