"""Read the saved activity file and save its records, once."""

import base64
import datetime
import io
import json
import os
import urllib.parse
import urllib.request
import zipfile

import fitdecode

DISCOVERY_TABLE_PATH = '/rest/v1/discovery_garmin_raw_payloads'
ACTIVITY_ID = 25155176957
WRITE_TIMEOUT_SECONDS = 20


def main():
    records_endpoint_name = f'Activity records {ACTIVITY_ID}'

    # Stop if an earlier run saved the records.
    if len(read_rows(records_endpoint_name)) > 0:
        print('The activity records are already in Supabase.')
        return

    # Unzip the file the first test saved.
    file_rows = read_rows(f'Activity file {ACTIVITY_ID}')
    zip_text = file_rows[0]['payload']['zip_base64']
    zip_bytes = base64.b64decode(zip_text)
    zip_file = zipfile.ZipFile(io.BytesIO(zip_bytes))

    # Walk every message in every file inside.
    file_names = zip_file.namelist()
    message_counts = {}
    records = []
    for file_name in file_names:
        fit_bytes = zip_file.read(file_name)
        read_fit_file(fit_bytes, message_counts, records)

    file_summary = {'file_names': file_names, 'message_counts': message_counts}
    save_payload(f'Activity file messages {ACTIVITY_ID}', file_summary)
    save_payload(records_endpoint_name, records)
    print('Saved the activity records.')


def read_fit_file(fit_bytes, message_counts, records):
    with fitdecode.FitReader(io.BytesIO(fit_bytes)) as fit_reader:
        for frame in fit_reader:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue

            # Count every message type by name.
            if frame.name not in message_counts:
                message_counts[frame.name] = 0
            message_counts[frame.name] = message_counts[frame.name] + 1

            # Keep every field of each record.
            if frame.name == 'record':
                record = {}
                for field in frame.fields:
                    record[field.name] = make_json_value(field.value)
                records.append(record)


def make_json_value(value):
    # Times become text. Bytes become text too.
    if isinstance(value, datetime.datetime):
        return value.isoformat()

    if isinstance(value, bytes):
        return value.hex()

    return value


def read_rows(endpoint_name):
    supabase_url = os.environ['SUPABASE_URL']
    secret_key = os.environ['SUPABASE_SECRET_KEY']
    endpoint_filter = urllib.parse.quote(endpoint_name)
    lookup_url = f'{supabase_url}{DISCOVERY_TABLE_PATH}?select=payload&endpoint=eq.{endpoint_filter}'
    lookup_headers = {'apikey': secret_key}
    lookup_request = urllib.request.Request(lookup_url, headers=lookup_headers)

    response = urllib.request.urlopen(lookup_request, timeout=WRITE_TIMEOUT_SECONDS)
    rows = json.loads(response.read())
    response.close()
    return rows


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
