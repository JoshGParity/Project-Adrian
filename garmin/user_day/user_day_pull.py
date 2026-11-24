"""Pull Garmin days and activities for each user into Supabase."""

import datetime
import io
import json
import os
import urllib.request
import zipfile
import zoneinfo

import fitdecode

LOCAL_TIME_ZONE = 'America/Chicago'
GARMIN_API_URL = 'https://personal.connectapi.garmin.com'
TOKEN_PATH = '/personalapitoken-service/personal-api/personal-api-key/token'
USER_DAY_TABLE_PATH = '/rest/v1/user_day'
ACTIVITY_TABLE_PATH = '/rest/v1/user_day_activity'
ACTIVITY_HR_TABLE_PATH = '/rest/v1/user_day_activity_hr'
# Garmin's own client sends this list (client.py L303, commit 958ef58).
ACTIVITY_FILE_ACCEPT = 'application/zip, application/x-zip-compressed, application/octet-stream'
ACTIVITY_SEARCH_LIMIT = 100
SECONDS_PER_MINUTE = 60
GARMIN_TIMEOUT_SECONDS = 30
WRITE_TIMEOUT_SECONDS = 20
DEFAULT_LOOKBACK_DAYS = 3

# Each user's Garmin key is its own secret.
USERS = [
    {'first_name': 'Josh', 'key_name': 'GARMIN_CONNECT_KEY'},
    {'first_name': 'Sydney', 'key_name': 'GARMIN_CONNECT_KEY_SYDNEY'},
]


def main():
    pull_days = pick_pull_days()

    # Pull every day for every user.
    for i in range(len(USERS)):
        user = USERS[i]
        pull_user(user, pull_days)


def pick_pull_days():
    # Blank start and end re-pull the last three days.
    start_text = os.environ['START_DAY']
    end_text = os.environ['END_DAY']
    if start_text == '' and end_text == '':
        start_text = find_days_ago(DEFAULT_LOOKBACK_DAYS)
        end_text = find_days_ago(1)

    # Blank start is yesterday. Blank end is start.
    if start_text == '':
        start_text = find_days_ago(1)
    if end_text == '':
        end_text = start_text

    # Bad dates crash here.
    start_date = datetime.date.fromisoformat(start_text)
    end_date = datetime.date.fromisoformat(end_text)

    # List each day from start to end.
    pull_days = []
    one_day = datetime.timedelta(days=1)
    pull_date = start_date
    while pull_date <= end_date:
        pull_day = pull_date.isoformat()
        pull_days.append(pull_day)
        pull_date = pull_date + one_day

    return pull_days


def find_days_ago(days_back):
    chicago_zone = zoneinfo.ZoneInfo(LOCAL_TIME_ZONE)
    now = datetime.datetime.now(chicago_zone)
    today = now.date()
    back = datetime.timedelta(days=days_back)
    past_day = today - back
    return past_day.isoformat()


def pull_user(user, pull_days):
    # A user with no key yet is skipped.
    garmin_key = os.environ[user['key_name']]
    if garmin_key == '':
        print(f'Skipped {user["first_name"]}: no Garmin key.')
        return

    # Trade this user's key for a token.
    access_token = get_access_token(garmin_key)

    # Write each day, then its activities.
    for i in range(len(pull_days)):
        pull_day = pull_days[i]

        user_day_row = build_user_day_row(user, pull_day, access_token)
        write_rows(USER_DAY_TABLE_PATH, [user_day_row])

        garmin_user_id = user_day_row['garmin_user_id']
        activity_rows = build_activity_rows(garmin_user_id, pull_day, access_token)

        # Each activity file adds zone floors and minute rows.
        hr_rows = []
        for j in range(len(activity_rows)):
            activity_row = activity_rows[j]
            activity_id = activity_row['activity_id']
            activity_file = read_activity_file(activity_id, access_token)
            add_zone_floors(activity_row, activity_file['zone_floors'])

            activity_hr_rows = build_activity_hr_rows(activity_id, activity_file['records'])
            for k in range(len(activity_hr_rows)):
                hr_rows.append(activity_hr_rows[k])

        if len(activity_rows) > 0:
            write_rows(ACTIVITY_TABLE_PATH, activity_rows)
        if len(hr_rows) > 0:
            write_rows(ACTIVITY_HR_TABLE_PATH, hr_rows)
        num_hr_minutes = len(hr_rows)

        # Log the day and counts only.
        num_activities = len(activity_rows)
        print(f'Wrote {user["first_name"]} {pull_day}: {num_activities} activities, {num_hr_minutes} heart-rate minutes.')


def get_access_token(garmin_key):
    # Build the token request from the key.
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


def build_user_day_row(user, pull_day, access_token):
    # Read the day's summary and sleep.
    summary_path = f'/usersummary-service/v2/dailysummaries?startDate={pull_day}&endDate={pull_day}'
    summary_data = get_garmin_data(summary_path, access_token)
    day_summary = summary_data.get('data')[0]

    sleep_path = f'/sleep-service/sleep/dailySleep?date={pull_day}'
    sleep = get_garmin_data(sleep_path, access_token)

    # Garmin sends sleep in seconds.
    sleep_total_minutes = seconds_to_minutes(sleep.get('sleepTimeSeconds'))
    sleep_deep_minutes = seconds_to_minutes(sleep.get('deepSleepSeconds'))
    sleep_light_minutes = seconds_to_minutes(sleep.get('lightSleepSeconds'))
    sleep_rem_minutes = seconds_to_minutes(sleep.get('remSleepSeconds'))
    sleep_awake_minutes = seconds_to_minutes(sleep.get('awakeSleepSeconds'))

    user_day_row = {
        'garmin_user_id': day_summary.get('userProfilePk'),
        'first_name': user['first_name'],
        'day': pull_day,
        'sleep_total_minutes': sleep_total_minutes,
        'sleep_deep_minutes': sleep_deep_minutes,
        'sleep_light_minutes': sleep_light_minutes,
        'sleep_rem_minutes': sleep_rem_minutes,
        'sleep_awake_minutes': sleep_awake_minutes,
        'body_battery_high': get_nested(day_summary, ['bodyBattery', 'maxValue']),
        'body_battery_low': get_nested(day_summary, ['bodyBattery', 'minValue']),
        'steps': get_nested(day_summary, ['movement', 'steps', 'value']),
        'calories_total': get_nested(day_summary, ['calories', 'burnedTotal']),
        'calories_active': get_nested(day_summary, ['calories', 'burnedActive']),
    }
    return user_day_row


def seconds_to_minutes(seconds):
    # A night with no sleep stays empty.
    if seconds is None:
        return None

    minutes = seconds // SECONDS_PER_MINUTE
    return minutes


def build_activity_rows(garmin_user_id, pull_day, access_token):
    # Garmin lists the day's activities.
    search_path = f'/activitylist-service/activities/search/activities?start=0&limit={ACTIVITY_SEARCH_LIMIT}&startDate={pull_day}&endDate={pull_day}'
    activities = get_garmin_data(search_path, access_token)

    activity_rows = []
    for i in range(len(activities)):
        activity = activities[i]
        activity_row = build_activity_row(garmin_user_id, activity, access_token)
        activity_rows.append(activity_row)

    return activity_rows


def build_activity_row(garmin_user_id, activity, access_token):
    # Min heart rate is only in the detail.
    activity_id = activity.get('activityId')
    detail_path = f'/activity-service/activity/{activity_id}'
    detail = get_garmin_data(detail_path, access_token)
    min_hr = get_nested(detail, ['summaryDTO', 'minHR'])

    # The day is the local start date.
    start_time_local = activity.get('startTimeLocal')
    start_parts = start_time_local.split(' ')
    activity_day = start_parts[0]

    zone_minutes = get_zone_minutes(activity)

    activity_row = {
        'garmin_user_id': garmin_user_id,
        'activity_id': activity_id,
        'day': activity_day,
        'start_time_local': start_time_local,
        'activity_name': activity.get('activityName'),
        'activity_type': get_nested(activity, ['activityType', 'typeKey']),
        'distance_meters': activity.get('distance'),
        'duration_seconds': activity.get('duration'),
        'calories': activity.get('calories'),
        'avg_hr': activity.get('averageHR'),
        'max_hr': activity.get('maxHR'),
        'min_hr': min_hr,
        'zone1_minutes': zone_minutes[0],
        'zone2_minutes': zone_minutes[1],
        'zone3_minutes': zone_minutes[2],
        'zone4_minutes': zone_minutes[3],
        'zone5_minutes': zone_minutes[4],
    }
    return activity_row


def get_zone_minutes(activity):
    # Garmin sends seconds in each zone.
    zone_minutes = []
    for zone in range(1, 6):
        zone_seconds = activity.get(f'hrTimeInZone_{zone}')
        if zone_seconds is None:
            zone_minutes.append(None)
            continue

        minutes = zone_seconds / SECONDS_PER_MINUTE
        zone_minutes.append(minutes)

    return zone_minutes


def read_activity_file(activity_id, access_token):
    # The file holds one record per second.
    fit_bytes = get_activity_file(activity_id, access_token)
    fit_stream = io.BytesIO(fit_bytes)

    records = []
    zone_floors = [None, None, None, None, None]
    with fitdecode.FitReader(fit_stream) as fit_reader:
        for frame in fit_reader:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue

            if frame.name == 'time_in_zone':
                read_zone_floors(frame, zone_floors)
                continue

            if frame.name != 'record':
                continue

            timestamp = frame.get_value('timestamp', fallback=None)
            if timestamp is None:
                continue

            heart_rate = frame.get_value('heart_rate', fallback=None)
            record = {'timestamp': timestamp, 'heart_rate': heart_rate}
            records.append(record)

    activity_file = {'records': records, 'zone_floors': zone_floors}
    return activity_file


def read_zone_floors(frame, zone_floors):
    # Only the whole-activity zones count, not laps.
    reference = frame.get_value('reference_mesg', fallback=None)
    if reference != 'session':
        return

    # Bounds list zone 1 to 5 floors, then max HR.
    bounds = frame.get_value('hr_zone_high_boundary', fallback=None)
    if bounds is None:
        return

    for i in range(len(zone_floors)):
        zone_floors[i] = bounds[i]


def add_zone_floors(activity_row, zone_floors):
    for i in range(len(zone_floors)):
        zone = i + 1
        activity_row[f'zone{zone}_floor_bpm'] = zone_floors[i]


def build_activity_hr_rows(activity_id, records):
    if len(records) == 0:
        return []

    # Minute 1 is the first 60 seconds.
    first_time = records[0]['timestamp']
    minute_totals = {}
    minute_counts = {}
    for i in range(len(records)):
        record = records[i]
        heart_rate = record['heart_rate']
        if heart_rate is None:
            continue

        elapsed = record['timestamp'] - first_time
        elapsed_seconds = elapsed.total_seconds()
        whole_minutes = elapsed_seconds // SECONDS_PER_MINUTE
        minute = int(whole_minutes) + 1
        if minute not in minute_totals:
            minute_totals[minute] = 0
            minute_counts[minute] = 0
        minute_totals[minute] = minute_totals[minute] + heart_rate
        minute_counts[minute] = minute_counts[minute] + 1

    # Each minute saves its average, to the nearest bpm.
    hr_rows = []
    # Records come in time order, so minutes do too.
    minutes = list(minute_totals)
    for i in range(len(minutes)):
        minute = minutes[i]
        average = minute_totals[minute] / minute_counts[minute]
        heart_rate = int(average + 0.5)
        hr_row = {'activity_id': activity_id, 'minute': minute, 'heart_rate': heart_rate}
        hr_rows.append(hr_row)

    return hr_rows


def get_activity_file(activity_id, access_token):
    # Garmin sends the file inside a zip.
    file_url = f'{GARMIN_API_URL}/download-service/files/activity/{activity_id}'
    file_headers = {'Authorization': 'Bearer ' + access_token, 'Accept': ACTIVITY_FILE_ACCEPT}
    file_request = urllib.request.Request(file_url, headers=file_headers)

    response = urllib.request.urlopen(file_request, timeout=GARMIN_TIMEOUT_SECONDS)
    zip_bytes = response.read()
    response.close()

    # The zip holds one .fit file.
    zip_stream = io.BytesIO(zip_bytes)
    zip_file = zipfile.ZipFile(zip_stream)
    file_names = zip_file.namelist()
    fit_bytes = zip_file.read(file_names[0])
    zip_file.close()
    return fit_bytes


def get_nested(data, keys):
    # Missing fields save empty; the re-pull fills them.
    value = data
    for i in range(len(keys)):
        if value is None:
            return None
        value = value.get(keys[i])

    return value


def get_garmin_data(path, access_token):
    # Garmin takes the token as a bearer token.
    garmin_url = GARMIN_API_URL + path
    garmin_headers = {'Authorization': 'Bearer ' + access_token, 'Accept': 'application/json'}
    garmin_request = urllib.request.Request(garmin_url, headers=garmin_headers)

    # A failed call fails the run.
    response = urllib.request.urlopen(garmin_request, timeout=GARMIN_TIMEOUT_SECONDS)
    response_bytes = response.read()
    response.close()

    garmin_data = json.loads(response_bytes)
    return garmin_data


def write_rows(table_path, rows):
    # Build the table address and JSON body.
    supabase_url = os.environ['SUPABASE_URL']
    table_url = supabase_url + table_path
    secret_key = os.environ['SUPABASE_SECRET_KEY']
    rows_json = json.dumps(rows)
    rows_bytes = rows_json.encode()

    # Merge-duplicates updates a row already there.
    write_headers = {
        'apikey': secret_key,
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates',
    }
    write_request = urllib.request.Request(
        table_url,
        data=rows_bytes,
        method='POST',
        headers=write_headers,
    )

    # A failed write fails the run.
    response = urllib.request.urlopen(write_request, timeout=WRITE_TIMEOUT_SECONDS)
    response.close()


if __name__ == '__main__':
    main()
