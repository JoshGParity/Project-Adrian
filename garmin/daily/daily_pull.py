"""Pull Garmin daily totals and write one row per day to Supabase."""

import datetime
import json
import os
import urllib.request
import zoneinfo

LOCAL_TIME_ZONE = 'America/Chicago'
GARMIN_API_URL = 'https://personal.connectapi.garmin.com'
TOKEN_PATH = '/personalapitoken-service/personal-api/personal-api-key/token'
ZONE_SETTINGS_PATH = '/biometric-service/heartRateZones/v2'
ZONE_SETTINGS_SPORT = 'DEFAULT'
DAILY_TABLE_PATH = '/rest/v1/garmin_daily'
GARMIN_TIMEOUT_SECONDS = 30
WRITE_TIMEOUT_SECONDS = 20


def main():
    pull_day = pick_pull_day()

    # Trade the Garmin key for a token.
    access_token = get_access_token()

    # Write the day's row. Log the day only.
    zone_floors = get_zone_floors(access_token)
    daily_row = build_daily_row(pull_day, zone_floors, access_token)
    write_daily_row(daily_row)
    print(f'Wrote {pull_day}.')


def pick_pull_day():
    # A typed day is for backfills. Bad dates crash.
    typed_day = os.environ['PULL_DAY']
    if typed_day != '':
        typed_date = datetime.date.fromisoformat(typed_day)
        return typed_date.isoformat()

    # Otherwise yesterday in Chicago time.
    chicago_zone = zoneinfo.ZoneInfo(LOCAL_TIME_ZONE)
    now = datetime.datetime.now(chicago_zone)
    today = now.date()
    one_day = datetime.timedelta(days=1)
    yesterday = today - one_day
    return yesterday.isoformat()


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


def get_zone_floors(access_token):
    # Garmin keeps one zone set per sport.
    zone_settings = get_garmin_data(ZONE_SETTINGS_PATH, access_token)

    # Use the default set.
    for sport_settings in zone_settings:
        if sport_settings['sport'] == ZONE_SETTINGS_SPORT:
            zone_floors = [
                sport_settings['zone1Floor'],
                sport_settings['zone2Floor'],
                sport_settings['zone3Floor'],
                sport_settings['zone4Floor'],
                sport_settings['zone5Floor'],
            ]
            return zone_floors

    raise RuntimeError('Garmin sent no DEFAULT heart-rate zone settings.')


def build_daily_row(pull_day, zone_floors, access_token):
    # Read each part of the day.
    steps = get_steps(pull_day, access_token)
    sleep_score = get_sleep_score(pull_day, access_token)
    zone_minutes = get_zone_minutes(pull_day, zone_floors, access_token)
    body_battery = get_body_battery(pull_day, access_token)

    # Slot 0 is time below zone 1.
    daily_row = {
        'day': pull_day,
        'steps': steps,
        'sleep_score': sleep_score,
        'below_zone1_minutes': zone_minutes[0],
        'zone1_minutes': zone_minutes[1],
        'zone2_minutes': zone_minutes[2],
        'zone3_minutes': zone_minutes[3],
        'zone4_minutes': zone_minutes[4],
        'zone5_minutes': zone_minutes[5],
        'body_battery_high': body_battery['maxValue'],
        'body_battery_low': body_battery['minValue'],
        'body_battery_end': body_battery['latestValue'],
        'body_battery_charged': body_battery['chargedValue'],
        'body_battery_drained': body_battery['drainedValue'],
    }
    return daily_row


def get_steps(pull_day, access_token):
    # Garmin sends a list with one day.
    steps_path = f'/usersummary-service/stats/steps/daily/{pull_day}/{pull_day}'
    steps_data = get_garmin_data(steps_path, access_token)
    day_entry = steps_data[0]
    steps = day_entry['totalSteps']
    return steps


def get_sleep_score(pull_day, access_token):
    # Take the overall score the app shows.
    sleep_path = f'/sleep-service/sleep/dailySleep?date={pull_day}'
    sleep_data = get_garmin_data(sleep_path, access_token)
    sleep_score = sleep_data['sleepScores']['overall']['value']
    return sleep_score


def get_zone_minutes(pull_day, zone_floors, access_token):
    # Read the day's heart-rate readings.
    heart_rate_path = f'/wellness-service/wellness/dailyHeartRate?date={pull_day}'
    heart_rate_data = get_garmin_data(heart_rate_path, access_token)

    # Find the time and heart-rate slots.
    descriptors = heart_rate_data['heartRateValueDescriptors']
    time_slot = find_slot(descriptors, 'timestamp')
    heart_rate_slot = find_slot(descriptors, 'heartrate')

    # Slot 0 is below zone 1.
    zone_seconds = [0, 0, 0, 0, 0, 0]

    # Each reading lasts until the next one.
    readings = heart_rate_data['heartRateValues']
    for i in range(len(readings) - 1):
        reading = readings[i]
        next_reading = readings[i + 1]
        heart_rate = reading[heart_rate_slot]

        # No heart rate counts toward no zone.
        if heart_rate is None:
            continue

        # Garmin's times are in milliseconds.
        reading_time = reading[time_slot]
        next_time = next_reading[time_slot]
        gap_milliseconds = next_time - reading_time
        gap_seconds = gap_milliseconds // 1000

        zone = pick_zone(heart_rate, zone_floors)
        zone_seconds[zone] = zone_seconds[zone] + gap_seconds

    # Turn seconds into whole minutes.
    zone_minutes = []
    for seconds in zone_seconds:
        minutes = seconds // 60
        zone_minutes.append(minutes)

    return zone_minutes


def find_slot(descriptors, slot_name):
    # Each descriptor names one slot of a reading.
    for descriptor in descriptors:
        if descriptor['key'] == slot_name:
            return descriptor['index']

    raise RuntimeError(f'Garmin sent no {slot_name} slot in its heart-rate readings.')


def pick_zone(heart_rate, zone_floors):
    # Move up each zone whose floor is reached.
    zone = 0
    for i in range(len(zone_floors)):
        if heart_rate >= zone_floors[i]:
            zone = i + 1

    return zone


def get_body_battery(pull_day, access_token):
    # The daily summary holds one day.
    summary_path = f'/usersummary-service/v2/dailysummaries?startDate={pull_day}&endDate={pull_day}'
    summary_data = get_garmin_data(summary_path, access_token)
    day_summary = summary_data['data'][0]
    body_battery = day_summary['bodyBattery']
    return body_battery


def get_garmin_data(path, access_token):
    # Garmin takes the token as a bearer token.
    garmin_url = GARMIN_API_URL + path
    garmin_headers = {'Authorization': 'Bearer ' + access_token, 'Accept': 'application/json'}
    garmin_request = urllib.request.Request(garmin_url, headers=garmin_headers)

    # A failed call fails the run.
    response = urllib.request.urlopen(garmin_request, timeout=GARMIN_TIMEOUT_SECONDS)
    response_bytes = response.read()
    response.close()

    response_data = json.loads(response_bytes)
    return response_data


def write_daily_row(daily_row):
    # Build the table address and JSON body.
    supabase_url = os.environ['SUPABASE_URL']
    table_url = supabase_url + DAILY_TABLE_PATH
    secret_key = os.environ['SUPABASE_SECRET_KEY']
    row_json = json.dumps(daily_row)
    row_bytes = row_json.encode()

    # Merge-duplicates updates a day already there.
    write_headers = {
        'apikey': secret_key,
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates',
    }
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
