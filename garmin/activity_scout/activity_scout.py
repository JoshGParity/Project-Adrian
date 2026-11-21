"""Save 30 days of Garmin activities, raw, to the discovery table."""

import base64
import datetime
import json
import os
import urllib.parse
import urllib.request
import zoneinfo

LOCAL_TIME_ZONE = 'America/Chicago'
GARMIN_API_URL = 'https://personal.connectapi.garmin.com'
TOKEN_PATH = '/personalapitoken-service/personal-api/personal-api-key/token'
DISCOVERY_TABLE_PATH = '/rest/v1/discovery_garmin_raw_payloads'
SEARCH_ENDPOINT_NAME = 'Activity search'
DAYS_TO_SEARCH = 30
MAX_ACTIVITIES = 20
GARMIN_TIMEOUT_SECONDS = 30
WRITE_TIMEOUT_SECONDS = 20


def main():
    # Stop if an earlier run saved the search.
    if test_already_ran():
        print('Activity search is already in Supabase. No calls made.')
        return

    access_token = get_access_token()

    # Search the last 30 days, ending today.
    today = pick_today()
    search_path = build_search_path(today)
    activities = get_garmin_json(search_path, access_token)

    # Save each activity's detail, workouts and file.
    for activity in activities:
        activity_id = activity['activityId']
        save_activity(activity_id, access_token)

    # Today's all-day heart rate, to cut by activity.
    heart_rate_path = f'/wellness-service/wellness/dailyHeartRate?date={today}'
    heart_rate_data = get_garmin_json(heart_rate_path, access_token)
    save_payload(f'Heart rate {today}', heart_rate_data)

    # Saved last, so a failed run can rerun.
    save_payload(SEARCH_ENDPOINT_NAME, activities)

    # Log no ids or counts.
    print('Saved the activity samples.')


def test_already_ran():
    # Look for a saved search row.
    supabase_url = os.environ['SUPABASE_URL']
    secret_key = os.environ['SUPABASE_SECRET_KEY']
    endpoint_filter = urllib.parse.quote(SEARCH_ENDPOINT_NAME)
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


def pick_today():
    chicago_zone = zoneinfo.ZoneInfo(LOCAL_TIME_ZONE)
    now = datetime.datetime.now(chicago_zone)
    today = now.date()
    return today.isoformat()


def build_search_path(today):
    # The start day is 29 days before today.
    today_date = datetime.date.fromisoformat(today)
    days_back = datetime.timedelta(days=DAYS_TO_SEARCH - 1)
    start_date = today_date - days_back
    start_day = start_date.isoformat()

    search_path = (
        '/activitylist-service/activities/search/activities'
        f'?start=0&limit={MAX_ACTIVITIES}&startDate={start_day}&endDate={today}'
    )
    return search_path


def save_activity(activity_id, access_token):
    detail_path = f'/activity-service/activity/{activity_id}'
    detail_data = get_garmin_json(detail_path, access_token)
    save_payload(f'Activity detail {activity_id}', detail_data)

    workouts_path = f'/activity-service/activity/{activity_id}/workouts'
    workouts_data = get_garmin_json(workouts_path, access_token)
    save_payload(f'Activity workouts {activity_id}', workouts_data)

    # The file is a ZIP, kept as base64 text.
    file_path = f'/download-service/files/activity/{activity_id}'
    file_bytes = get_garmin_bytes(file_path, 'application/zip', access_token)
    file_text = base64.b64encode(file_bytes).decode()
    file_data = {'zip_base64': file_text}
    save_payload(f'Activity file {activity_id}', file_data)


def get_garmin_json(path, access_token):
    # An empty answer is saved as null.
    response_bytes = get_garmin_bytes(path, 'application/json', access_token)
    if response_bytes == b'':
        return None

    response_data = json.loads(response_bytes)
    return response_data


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
