"""Store S&P 500 closes from Massive and save three bounce picks."""

import datetime
import json
import os
import urllib.request

import pandas

MEMBER_LIST_URL = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
USER_AGENT = 'ProjectAdrianStocks/1.0 (github.com/JoshGParity/Project-Adrian)'
MASSIVE_API_URL = 'https://api.massive.com'
NUM_PICKS = 3
REQUEST_TIMEOUT_SECONDS = 60


def main():
    trade_date = pick_trade_date()

    # Replace the member list with Wikipedia's.
    member_rows = get_member_rows()
    send_to_supabase('DELETE', '/rest/v1/stocks_sp500_members?ticker=not.is.null')
    send_to_supabase('POST', '/rest/v1/stocks_sp500_members', member_rows)

    # Store the day's member closes.
    price_rows = get_price_rows(trade_date, member_rows)
    send_to_supabase('POST', '/rest/v1/stocks_daily_prices', price_rows)

    # Keep only the latest 30 trading days.
    delete_old_prices()

    # Save the day's top three picks.
    pick_rows = get_pick_rows(trade_date)
    send_to_supabase('POST', '/rest/v1/stocks_bounce_picks', pick_rows)

    num_closes = len(price_rows)
    num_picks = len(pick_rows)
    print(f'{trade_date}: {num_closes} closes, {num_picks} picks.')


def pick_trade_date():
    # A typed date wins. Bad dates crash here.
    typed_date = os.environ['TRADE_DATE']
    if typed_date != '':
        trade_day = datetime.date.fromisoformat(typed_date)
        return trade_day.isoformat()

    # Otherwise the last weekday before today, UTC.
    today = datetime.date.today()
    one_day = datetime.timedelta(days=1)
    trade_day = today - one_day
    while trade_day.weekday() >= 5:
        trade_day = trade_day - one_day
    return trade_day.isoformat()


def get_member_rows():
    # Wikipedia refuses requests without a named client.
    page_headers = {'User-Agent': USER_AGENT}
    page_tables = pandas.read_html(MEMBER_LIST_URL, storage_options=page_headers)
    member_table = page_tables[0]

    member_rows = []
    for i in range(len(member_table)):
        member_row = {
            'ticker': member_table['Symbol'][i],
            'name': member_table['Security'][i],
            'sector': member_table['GICS Sector'][i],
        }
        member_rows.append(member_row)
    return member_rows


def get_price_rows(trade_date, member_rows):
    # One Massive call returns every US stock.
    grouped_path = f'/v2/aggs/grouped/locale/us/market/stocks/{trade_date}'
    massive_url = MASSIVE_API_URL + grouped_path
    massive_key = os.environ['MASSIVE_API_KEY']
    massive_headers = {'Authorization': 'Bearer ' + massive_key}
    massive_request = urllib.request.Request(massive_url, headers=massive_headers)
    response = urllib.request.urlopen(massive_request, timeout=REQUEST_TIMEOUT_SECONDS)
    response_bytes = response.read()
    response.close()
    massive_data = json.loads(response_bytes)

    member_tickers = set()
    for member_row in member_rows:
        member_tickers.add(member_row['ticker'])

    # Keep members only. T is the ticker, c the close.
    price_rows = []
    for result in massive_data['results']:
        if result['T'] in member_tickers:
            price_row = {'ticker': result['T'], 'trade_date': trade_date, 'close': result['c']}
            price_rows.append(price_row)
    return price_rows


def delete_old_prices():
    # Find the 30th latest trading day.
    oldest_path = '/rest/v1/stocks_price_averages?select=trade_date&days_back=eq.30&limit=1'
    oldest_rows = send_to_supabase('GET', oldest_path)
    if len(oldest_rows) == 0:
        return

    oldest_date = oldest_rows[0]['trade_date']
    send_to_supabase('DELETE', f'/rest/v1/stocks_daily_prices?trade_date=lt.{oldest_date}')


def get_pick_rows(trade_date):
    # Bounce candidates, deepest under the 30-day first.
    candidates_path = (
        '/rest/v1/stocks_price_averages'
        f'?trade_date=eq.{trade_date}&is_bounce=is.true&order=pct_30.desc&limit={NUM_PICKS}'
    )
    candidates = send_to_supabase('GET', candidates_path)

    pick_rows = []
    for i in range(len(candidates)):
        candidate = candidates[i]
        pick_row = {
            'pick_date': trade_date,
            'rank': i + 1,
            'ticker': candidate['ticker'],
            'close': candidate['close'],
            'sma_5': candidate['sma_5'],
            'sma_10': candidate['sma_10'],
            'sma_30': candidate['sma_30'],
            'pct_5': candidate['pct_5'],
            'pct_10': candidate['pct_10'],
            'pct_30': candidate['pct_30'],
        }
        pick_rows.append(pick_row)
    return pick_rows


def send_to_supabase(method, path, rows=None):
    # Posts upsert, so a rerun replaces rows.
    supabase_url = os.environ['SUPABASE_URL']
    secret_key = os.environ['SUPABASE_SECRET_KEY']
    supabase_headers = {
        'apikey': secret_key,
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates',
    }

    rows_bytes = None
    if rows is not None:
        rows_json = json.dumps(rows)
        rows_bytes = rows_json.encode()

    request_url = supabase_url + path
    supabase_request = urllib.request.Request(
        request_url,
        data=rows_bytes,
        method=method,
        headers=supabase_headers,
    )

    # A failed call crashes, so the run goes red.
    response = urllib.request.urlopen(supabase_request, timeout=REQUEST_TIMEOUT_SECONDS)
    response_bytes = response.read()
    response.close()
    if response_bytes == b'':
        return []
    return json.loads(response_bytes)


if __name__ == '__main__':
    main()
