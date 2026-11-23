"""Write the L7 fitness page's four data files from Supabase."""

import datetime
import decimal
import json
import os
import sys
import urllib.parse
import urllib.request
import zoneinfo

LOCAL_TIME_ZONE = 'America/Chicago'
USER_DAY_TABLE_PATH = '/rest/v1/user_day'
ACTIVITY_TABLE_PATH = '/rest/v1/user_day_activity'
READ_TIMEOUT_SECONDS = 20
WINDOW_DAYS_BACK = 6
JOSH_GARMIN_USER_ID = 152786074
SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
HOURS_PER_HALF_DAY = 12
METERS_PER_KILOMETER = decimal.Decimal('1000')
METERS_PER_MILE = decimal.Decimal('1609.344')
ZONE_FIELDS = ['zone1_minutes', 'zone2_minutes', 'zone3_minutes', 'zone4_minutes', 'zone5_minutes']


def main():
    site_folder = sys.argv[1]

    # The window is today and the 6 days before.
    chicago_zone = zoneinfo.ZoneInfo(LOCAL_TIME_ZONE)
    today = datetime.datetime.now(chicago_zone).date()
    first_day = today - datetime.timedelta(days=WINDOW_DAYS_BACK)

    day_rows = read_rows(USER_DAY_TABLE_PATH, first_day, today, 'day.asc,first_name.asc')
    activity_rows = read_rows(ACTIVITY_TABLE_PATH, first_day, today, 'start_time_local.asc')

    days = build_days(day_rows)
    activities = build_activities(day_rows, activity_rows)
    highlights = build_highlights(day_rows, activity_rows)
    week = build_week(day_rows, activity_rows, first_day, today)

    write_file(site_folder, 'days.json', days)
    write_file(site_folder, 'activities.json', activities)
    write_file(site_folder, 'highlights.json', highlights)
    write_file(site_folder, 'week.json', week)

    # Logs show counts only.
    print(f'{first_day} to {today}: {len(days)} days, {len(activities)} activities.')


def read_rows(table_path, first_day, last_day, order):
    # Filter the table to the window's days.
    supabase_url = os.environ['SUPABASE_URL']
    query = urllib.parse.urlencode([
        ('select', '*'),
        ('day', 'gte.' + first_day.isoformat()),
        ('day', 'lte.' + last_day.isoformat()),
        ('order', order),
    ])
    table_url = supabase_url + table_path + '?' + query

    secret_key = os.environ['SUPABASE_SECRET_KEY']
    read_headers = {'apikey': secret_key, 'Accept': 'application/json'}
    read_request = urllib.request.Request(table_url, headers=read_headers)

    # Decimals keep Postgres numerics exact for rounding.
    response = urllib.request.urlopen(read_request, timeout=READ_TIMEOUT_SECONDS)
    rows = json.loads(response.read(), parse_float=decimal.Decimal)
    response.close()
    return rows


def build_days(day_rows):
    days = []
    for i in range(len(day_rows)):
        day_row = day_rows[i]

        day = {
            'day': day_row['day'],
            'first_name': day_row['first_name'],
            'sleep_total_minutes': day_row['sleep_total_minutes'],
            'sleep_total': format_hours_minutes(day_row['sleep_total_minutes']),
            'sleep_deep_minutes': day_row['sleep_deep_minutes'],
            'sleep_light_minutes': day_row['sleep_light_minutes'],
            'sleep_rem_minutes': day_row['sleep_rem_minutes'],
            'sleep_awake_minutes': day_row['sleep_awake_minutes'],
            'body_battery_high': day_row['body_battery_high'],
            'body_battery_low': day_row['body_battery_low'],
            'steps': day_row['steps'],
            'calories_total': day_row['calories_total'],
            'calories_active': day_row['calories_active'],
            'calories_resting': subtract(day_row['calories_total'], day_row['calories_active']),
        }
        days.append(day)

    return days


def build_activities(day_rows, activity_rows):
    first_names = find_first_names(day_rows)

    # A user with no days this week has no name.
    activities = []
    for i in range(len(activity_rows)):
        activity_row = activity_rows[i]
        start_time = datetime.datetime.fromisoformat(activity_row['start_time_local'])
        duration_seconds = activity_row['duration_seconds']

        activity = {
            'activity_id': str(activity_row['activity_id']),
            'day': activity_row['day'],
            'first_name': first_names.get(activity_row['garmin_user_id']),
            'activity_name': activity_row['activity_name'],
            'activity_type': activity_row['activity_type'],
            'start': format_day_and_time(start_time),
            'distance_km': divide_and_round(activity_row['distance_meters'], METERS_PER_KILOMETER, 2),
            'distance_mi': divide_and_round(activity_row['distance_meters'], METERS_PER_MILE, 2),
            'duration': format_minutes_seconds(duration_seconds),
            'duration_minutes': divide_and_round(duration_seconds, SECONDS_PER_MINUTE, 1),
            'calories': round_to_int(activity_row['calories']),
            'avg_hr': round_to_int(activity_row['avg_hr']),
            'max_hr': round_to_int(activity_row['max_hr']),
            'min_hr': round_to_int(activity_row['min_hr']),
            'below_zone1_minutes': find_below_zone1_minutes(activity_row),
        }
        for j in range(len(ZONE_FIELDS)):
            field = ZONE_FIELDS[j]
            activity[field] = round_to_places(activity_row[field], 1)

        activities.append(activity)

    return activities


def find_first_names(day_rows):
    # Each Garmin user id maps to its first name.
    first_names = {}
    for i in range(len(day_rows)):
        day_row = day_rows[i]
        first_names[day_row['garmin_user_id']] = day_row['first_name']

    return first_names


def find_below_zone1_minutes(activity_row):
    # Time in no zone is duration minus every zone.
    duration_seconds = activity_row['duration_seconds']
    if duration_seconds is None:
        return None

    below_minutes = duration_seconds / SECONDS_PER_MINUTE
    for i in range(len(ZONE_FIELDS)):
        zone_minutes = activity_row[ZONE_FIELDS[i]]
        if zone_minutes is None:
            return None
        below_minutes = below_minutes - zone_minutes

    if below_minutes < 0:
        below_minutes = decimal.Decimal(0)

    return round_to_places(below_minutes, 1)


def build_highlights(day_rows, activity_rows):
    first_names = find_first_names(day_rows)

    # Highlights are listed by first name.
    names = []
    for garmin_user_id in first_names:
        names.append(first_names[garmin_user_id])
    names.sort()

    highlights = []
    for i in range(len(names)):
        name = names[i]
        garmin_user_id = find_garmin_user_id(first_names, name)
        best_night = find_night(day_rows, garmin_user_id, 'best')
        worst_night = find_night(day_rows, garmin_user_id, 'worst')
        top_activity = find_top_heart_rate(activity_rows, garmin_user_id)

        highlight = {
            'first_name': name,
            'best_night_day': None,
            'best_night': None,
            'worst_night_day': None,
            'worst_night': None,
            'hr_max_when': None,
            'hr_max': None,
        }
        if best_night is not None:
            highlight['best_night_day'] = format_day(datetime.date.fromisoformat(best_night['day']))
            highlight['best_night'] = format_hours_minutes(best_night['sleep_total_minutes'])
            highlight['worst_night_day'] = format_day(datetime.date.fromisoformat(worst_night['day']))
            highlight['worst_night'] = format_hours_minutes(worst_night['sleep_total_minutes'])
        if top_activity is not None:
            start_time = datetime.datetime.fromisoformat(top_activity['start_time_local'])
            highlight['hr_max_when'] = format_day_and_time(start_time)
            highlight['hr_max'] = round_to_int(top_activity['max_hr'])

        highlights.append(highlight)

    return highlights


def find_garmin_user_id(first_names, name):
    for garmin_user_id in first_names:
        if first_names[garmin_user_id] == name:
            return garmin_user_id

    return None


def find_night(day_rows, garmin_user_id, which):
    # Rows run oldest first, so ties keep the earliest night.
    chosen_row = None
    for i in range(len(day_rows)):
        day_row = day_rows[i]
        if day_row['garmin_user_id'] != garmin_user_id:
            continue
        if day_row['sleep_total_minutes'] is None:
            continue
        if chosen_row is None:
            chosen_row = day_row
            continue

        sleep_minutes = day_row['sleep_total_minutes']
        chosen_minutes = chosen_row['sleep_total_minutes']
        if which == 'best' and sleep_minutes > chosen_minutes:
            chosen_row = day_row
        if which == 'worst' and sleep_minutes < chosen_minutes:
            chosen_row = day_row

    return chosen_row


def find_top_heart_rate(activity_rows, garmin_user_id):
    # Rows run earliest first, so ties keep the earliest activity.
    top_activity = None
    for i in range(len(activity_rows)):
        activity_row = activity_rows[i]
        if activity_row['garmin_user_id'] != garmin_user_id:
            continue
        if activity_row['max_hr'] is None:
            continue
        if top_activity is None or activity_row['max_hr'] > top_activity['max_hr']:
            top_activity = activity_row

    return top_activity


def build_week(day_rows, activity_rows, first_day, today):
    # The week summary counts Josh only.
    num_days = 0
    num_nights = 0
    sleep_minutes_sum = 0
    num_step_days = 0
    steps_sum = 0
    for i in range(len(day_rows)):
        day_row = day_rows[i]
        if day_row['garmin_user_id'] != JOSH_GARMIN_USER_ID:
            continue

        num_days = num_days + 1
        if day_row['sleep_total_minutes'] is not None:
            num_nights = num_nights + 1
            sleep_minutes_sum = sleep_minutes_sum + day_row['sleep_total_minutes']
        if day_row['steps'] is not None:
            num_step_days = num_step_days + 1
            steps_sum = steps_sum + day_row['steps']

    num_activities = 0
    for i in range(len(activity_rows)):
        if activity_rows[i]['garmin_user_id'] == JOSH_GARMIN_USER_ID:
            num_activities = num_activities + 1

    avg_sleep_minutes = find_average(sleep_minutes_sum, num_nights)
    avg_steps = find_average(steps_sum, num_step_days)
    range_label = format_day(first_day) + ' to ' + format_day(today) + ', ' + str(today.year)

    week = {
        'days': num_days,
        'nights_with_sleep': num_nights,
        'avg_sleep_minutes': avg_sleep_minutes,
        'avg_sleep': format_hours_minutes(avg_sleep_minutes),
        'avg_steps': avg_steps,
        'activities': num_activities,
        'range_label': range_label,
    }
    return [week]


def find_average(total, count):
    if count == 0:
        return None

    average = decimal.Decimal(total) / decimal.Decimal(count)
    return round_to_int(average)


def round_half_up(number, places):
    # Match Postgres round(): halves go away from zero.
    step = decimal.Decimal(1).scaleb(-places)
    return decimal.Decimal(number).quantize(step, rounding=decimal.ROUND_HALF_UP)


def round_to_int(number):
    if number is None:
        return None

    return int(round_half_up(number, 0))


def round_to_places(number, places):
    if number is None:
        return None

    return float(round_half_up(number, places))


def divide_and_round(number, divisor, places):
    if number is None:
        return None

    quotient = decimal.Decimal(number) / decimal.Decimal(divisor)
    return round_to_places(quotient, places)


def subtract(number, taken_away):
    if number is None or taken_away is None:
        return None

    return number - taken_away


def format_hours_minutes(total_minutes):
    if total_minutes is None:
        return None

    # Modulo keeps the minutes left after whole hours.
    hours = total_minutes // MINUTES_PER_HOUR
    minutes = total_minutes % MINUTES_PER_HOUR
    return f'{hours}:{minutes:02d}'


def format_minutes_seconds(duration_seconds):
    if duration_seconds is None:
        return None

    # Modulo keeps the seconds left after whole minutes.
    total_seconds = round_to_int(duration_seconds)
    minutes = total_seconds // SECONDS_PER_MINUTE
    seconds = total_seconds % SECONDS_PER_MINUTE
    return f'{minutes}:{seconds:02d}'


def format_day(day):
    # Reads like 'Sun Nov 22'.
    return day.strftime('%a %b') + ' ' + str(day.day)


def format_day_and_time(start_time):
    # Modulo turns 24-hour time into 12-hour time.
    hour = start_time.hour % HOURS_PER_HALF_DAY
    if hour == 0:
        hour = HOURS_PER_HALF_DAY

    clock = f'{hour}:{start_time.minute:02d} ' + start_time.strftime('%p')
    return format_day(start_time.date()) + ', ' + clock


def write_file(site_folder, file_name, rows):
    file_path = os.path.join(site_folder, file_name)
    with open(file_path, 'w') as data_file:
        json.dump(rows, data_file)


if __name__ == '__main__':
    main()
