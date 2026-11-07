"""Pull daily steps, sleep score and minutes per heart-rate zone from Garmin, and write one row per day to Supabase."""

import datetime
import json
import os
import urllib.request

GARMIN_API_URL = 'https://personal.connectapi.garmin.com'
TOKEN_PATH = '/personalapitoken-service/personal-api/personal-api-key/token'
ZONE_SETTINGS_PATH = '/biometric-service/heartRateZones/v2'
ZONE_SETTINGS_SPORT = 'DEFAULT'
DAILY_TABLE_PATH = '/rest/v1/garmin_daily'
DAYS_TO_PULL = 3
GARMIN_TIMEOUT_SECONDS = 30
INSERT_TIMEOUT_SECONDS = 20


def main():
    # Pick the days to pull.
    pull_days = pick_pull_days()

    # Trade the Garmin key for an access token.
    access_token = get_access_token()

    # Read your heart-rate zone floors once for the whole run.
    zone_floors = get_zone_floors(access_token)

    # Build one row per day and write it to the daily table. Only the day goes in the log, never its numbers.
    for pull_day in pull_days:
        daily_row = build_daily_row(pull_day, zone_floors, access_token)
        write_daily_row(daily_row)
        print(f'Wrote {pull_day}.')


def pick_pull_days():
    # Use the day typed into the run form when there is one. A day that isn't YYYY-MM-DD crashes here, before it reaches a Garmin address.
    typed_day = os.environ['PULL_DAY']
    if typed_day != '':
        pull_date = datetime.date.fromisoformat(typed_day)
        return [pull_date.isoformat()]

    # Otherwise pull the last few days before today by the runner's clock, which is UTC, so late watch syncs fill in.
    today = datetime.date.today()
    pull_days = []
    for days_back in range(1, DAYS_TO_PULL + 1):
        time_back = datetime.timedelta(days=days_back)
        pull_date = today - time_back
        pull_days.append(pull_date.isoformat())

    return pull_days


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
    response = urllib.request.urlopen(token_request, timeout=GARMIN_TIMEOUT_SECONDS)
    response_bytes = response.read()
    response.close()

    # The answer is the token as plain text, with a trailing newline trimmed. It is never printed.
    response_text = response_bytes.decode()
    access_token = response_text.strip()
    return access_token


def get_zone_floors(access_token):
    # Ask Garmin for your heart-rate zone settings. There is one set per sport.
    zone_settings = get_garmin_data(ZONE_SETTINGS_PATH, access_token)

    # Use the default set, the one Garmin applies when no sport is picked.
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

    # With no default set the zones can't be worked out, so the run stops here.
    raise RuntimeError('Garmin sent no DEFAULT heart-rate zone settings.')


def build_daily_row(pull_day, zone_floors, access_token):
    # Read each part of the day from Garmin.
    steps = get_steps(pull_day, access_token)
    sleep_score = get_sleep_score(pull_day, access_token)
    zone_minutes = get_zone_minutes(pull_day, zone_floors, access_token)

    # Put the day together as one row. Slot 0 of the zone minutes is time below zone 1.
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
    }
    return daily_row


def get_steps(pull_day, access_token):
    # Ask Garmin for the day's step total. It comes back as a list with one entry for the day.
    steps_path = f'/usersummary-service/stats/steps/daily/{pull_day}/{pull_day}'
    steps_data = get_garmin_data(steps_path, access_token)

    # Take the total from the day's entry.
    day_entry = steps_data[0]
    steps = day_entry['totalSteps']
    return steps


def get_sleep_score(pull_day, access_token):
    # Ask Garmin for the night's sleep.
    sleep_path = f'/sleep-service/sleep/dailySleep?date={pull_day}'
    sleep_data = get_garmin_data(sleep_path, access_token)

    # Take the overall score, the one the Garmin app shows.
    sleep_score = sleep_data['sleepScores']['overall']['value']
    return sleep_score


def get_zone_minutes(pull_day, zone_floors, access_token):
    # Ask Garmin for the day's heart-rate readings.
    heart_rate_path = f'/wellness-service/wellness/dailyHeartRate?date={pull_day}'
    heart_rate_data = get_garmin_data(heart_rate_path, access_token)

    # Find which slot of each reading holds the time and which holds the heart rate.
    descriptors = heart_rate_data['heartRateValueDescriptors']
    time_slot = find_slot(descriptors, 'timestamp')
    heart_rate_slot = find_slot(descriptors, 'heartrate')

    # Start every zone at zero seconds. Slot 0 is time below zone 1, slots 1 to 5 are zones 1 to 5.
    zone_seconds = [0, 0, 0, 0, 0, 0]

    # Give each reading the time until the next reading, in the zone its heart rate falls in.
    readings = heart_rate_data['heartRateValues']
    for i in range(len(readings) - 1):
        reading = readings[i]
        next_reading = readings[i + 1]
        heart_rate = reading[heart_rate_slot]

        # A reading with no heart rate counts toward no zone.
        if heart_rate is None:
            continue

        # Work out the seconds until the next reading. Garmin's times are in milliseconds.
        reading_time = reading[time_slot]
        next_time = next_reading[time_slot]
        gap_milliseconds = next_time - reading_time
        gap_seconds = gap_milliseconds // 1000

        # Add those seconds to the reading's zone.
        zone = pick_zone(heart_rate, zone_floors)
        zone_seconds[zone] = zone_seconds[zone] + gap_seconds

    # Turn each zone's seconds into whole minutes.
    zone_minutes = []
    for seconds in zone_seconds:
        minutes = seconds // 60
        zone_minutes.append(minutes)

    return zone_minutes


def find_slot(descriptors, slot_name):
    # Each descriptor names one slot of a reading, such as the time or the heart rate.
    for descriptor in descriptors:
        if descriptor['key'] == slot_name:
            return descriptor['index']

    # A missing name means Garmin changed the reading format, so the run stops here.
    raise RuntimeError(f'Garmin sent no {slot_name} slot in its heart-rate readings.')


def pick_zone(heart_rate, zone_floors):
    # Start below zone 1, then move up through each zone whose floor the heart rate reaches.
    zone = 0
    for i in range(len(zone_floors)):
        if heart_rate >= zone_floors[i]:
            zone = i + 1

    return zone


def get_garmin_data(path, access_token):
    # Build the request. Garmin takes the access token as a bearer token.
    garmin_url = GARMIN_API_URL + path
    garmin_headers = {'Authorization': 'Bearer ' + access_token, 'Accept': 'application/json'}
    garmin_request = urllib.request.Request(garmin_url, headers=garmin_headers)

    # Send it. A failed call crashes here, so the run goes red.
    response = urllib.request.urlopen(garmin_request, timeout=GARMIN_TIMEOUT_SECONDS)
    response_bytes = response.read()
    response.close()

    # Read the answer as data.
    response_data = json.loads(response_bytes)
    return response_data


def write_daily_row(daily_row):
    # Build the table address in Project Adrian.
    supabase_url = os.environ['SUPABASE_URL']
    table_url = supabase_url + DAILY_TABLE_PATH

    # Read Project Adrian's secret key.
    secret_key = os.environ['SUPABASE_SECRET_KEY']

    # Put the row in a JSON body.
    row_json = json.dumps(daily_row)
    row_bytes = row_json.encode()

    # Build the write request. Merge-duplicates makes a day that is already there get updated instead of failing.
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

    # Send the write. A failed write crashes here, so the run goes red.
    response = urllib.request.urlopen(write_request, timeout=INSERT_TIMEOUT_SECONDS)
    response.close()


if __name__ == '__main__':
    main()
