"""Pull one day of Garmin data and print its field names, never its values."""

import datetime
import json
import os
import urllib.error
import urllib.request

GARMIN_API_URL = 'https://personal.connectapi.garmin.com'
TOKEN_PATH = '/personalapitoken-service/personal-api/personal-api-key/token'
REQUEST_TIMEOUT_SECONDS = 30
PAYLOAD_TABLE_PATH = '/rest/v1/discovery_garmin_raw_payloads'


def main():
    # Pick the day to scout.
    scout_day = pick_scout_day()
    print(f'Scouting {scout_day}.')

    # Trade the Garmin key for an access token.
    access_token = get_access_token()

    # Pull each daily endpoint and print the field names it returns.
    endpoints = build_endpoints(scout_day)
    for endpoint in endpoints:
        scout_endpoint(endpoint, access_token)


def pick_scout_day():
    # Use the day typed into the run form when there is one. A day that isn't YYYY-MM-DD crashes here, before it reaches a Garmin address.
    typed_day = os.environ['SCOUT_DAY']
    if typed_day != '':
        scout_date = datetime.date.fromisoformat(typed_day)
        return scout_date.isoformat()

    # Otherwise use yesterday by the runner's clock, which is UTC.
    today = datetime.date.today()
    one_day = datetime.timedelta(days=1)
    yesterday = today - one_day
    return yesterday.isoformat()


def get_access_token():
    # Read the Garmin key from the run's secrets.
    garmin_key = os.environ['GARMIN_CONNECT_KEY']

    # Build the token request. Garmin takes the key in the Authorization header and needs no body.
    token_url = GARMIN_API_URL + TOKEN_PATH
    token_headers = {'Authorization': 'ApiKey ' + garmin_key, 'Accept': '*/*'}
    token_request = urllib.request.Request(
        token_url,
        data=b'',
        method='POST',
        headers=token_headers,
    )

    # Send it. A wrong or expired key crashes here, so the run goes red.
    response = urllib.request.urlopen(token_request, timeout=REQUEST_TIMEOUT_SECONDS)
    response_bytes = response.read()
    response.close()

    # The answer is the token as plain text, with a trailing newline trimmed. It is never printed.
    response_text = response_bytes.decode()
    access_token = response_text.strip()
    return access_token


def build_endpoints(scout_day):
    # Build each endpoint's path for the day. The paths come from Garmin's own Python client.
    summary_path = f'/usersummary-service/v2/dailysummaries?startDate={scout_day}&endDate={scout_day}'
    steps_path = f'/usersummary-service/stats/steps/daily/{scout_day}/{scout_day}'
    sleep_path = f'/sleep-service/sleep/dailySleep?date={scout_day}'
    heart_rate_path = f'/wellness-service/wellness/dailyHeartRate?date={scout_day}'
    zone_settings_path = '/biometric-service/heartRateZones/v2'
    workouts_path = f'/activitylist-service/activities/search/activities?start=0&limit=1&startDate={scout_day}&endDate={scout_day}'

    # Pair each path with a short name for the log.
    endpoints = [
        {'name': 'Daily summary', 'path': summary_path},
        {'name': 'Daily steps', 'path': steps_path},
        {'name': 'Sleep', 'path': sleep_path},
        {'name': 'Heart rate', 'path': heart_rate_path},
        {'name': 'Heart-rate zone settings', 'path': zone_settings_path},
        {'name': 'Workouts', 'path': workouts_path},
    ]
    return endpoints


def scout_endpoint(endpoint, access_token):
    # Print a heading for this endpoint in the log.
    endpoint_name = endpoint['name']
    print('')
    print(f'== {endpoint_name} ==')

    # Build the request. Garmin takes the access token as a bearer token.
    endpoint_url = GARMIN_API_URL + endpoint['path']
    endpoint_headers = {'Authorization': 'Bearer ' + access_token, 'Accept': 'application/json'}
    endpoint_request = urllib.request.Request(endpoint_url, headers=endpoint_headers)

    # Send it. A failed endpoint prints its status, and the scout moves on to the next one.
    try:
        response = urllib.request.urlopen(endpoint_request, timeout=REQUEST_TIMEOUT_SECONDS)
        response_bytes = response.read()
        response.close()
    except urllib.error.HTTPError as http_error:
        status_code = http_error.code
        print(f'Failed with status {status_code}.')
        return

    # An empty answer means Garmin has nothing for that day.
    if response_bytes == b'':
        print('No data.')
        return

    # Print every field name and its type, never the value.
    response_data = json.loads(response_bytes)
    print_fields('response', response_data)

    # Save the raw answer to the locked discovery table.
    save_payload(endpoint_name, response_data)


def save_payload(endpoint_name, response_data):
    # Build the row and its table address.
    supabase_url = os.environ['SUPABASE_URL']
    table_url = supabase_url + PAYLOAD_TABLE_PATH
    secret_key = os.environ['SUPABASE_SECRET_KEY']
    payload_row = {'endpoint': endpoint_name, 'payload': response_data}
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
    response.close()


def print_fields(field_path, value):
    # A dict prints nothing itself. Each of its keys is walked as a field of its own.
    if isinstance(value, dict):
        for key in value:
            # A key that starts with a digit is a time or a reading, not a field name, so it prints as <number>.
            key_name = key
            if key[0].isdigit():
                key_name = '<number>'

            child_path = field_path + '.' + key_name
            print_fields(child_path, value[key])
        return

    # A list prints without its length, since a length could show how long a night or a workout was.
    if isinstance(value, list):
        print(f'{field_path}: list')

        # The first item shows the shape of every item, so only it is walked.
        if len(value) > 0:
            item_path = field_path + '[]'
            print_fields(item_path, value[0])
        return

    # Anything else is a plain value, so print its type name only. A null prints as NoneType.
    type_name = type(value).__name__
    print(f'{field_path}: {type_name}')


if __name__ == '__main__':
    main()
