import time
import requests
import jwt
import uuid
import numpy as np

# === CONFIG ===
API_KEY = 'your_api_key_here'
API_SECRET = 'your_api_secret_here'  # base64 string from Coinbase Advanced Trade
API_URL = 'https://api.coinbase.com'  # Coinbase Advanced Trade base URL

ORDER_BUDGET_USDC = 5
RSI_PERIOD = 14
SLEEP_INTERVAL = 60 * 5  # 5 minutes between cycles

# === AUTH HEADER GENERATION ===
def get_auth_headers(method, path, body=''):
    timestamp = str(int(time.time()))
    message = timestamp + method + path + body
    secret_bytes = API_SECRET.encode('utf-8')
    # Create JWT token
    token = jwt.encode(
        {
            'iss': API_KEY,
            'iat': int(time.time()),
            'exp': int(time.time()) + 60,
            'jti': str(uuid.uuid4())
        },
        API_SECRET,
        algorithm='HS256'
    )
    return {
        'CB-ACCESS-KEY': API_KEY,
        'CB-ACCESS-SIGN': token,
        'CB-ACCESS-TIMESTAMP': timestamp,
        'Content-Type': 'application/json'
    }

# === API REQUEST FUNCTIONS ===
def api_get(path):
    headers = get_auth_headers('GET', path)
    response = requests.get(API_URL + path, headers=headers)
    response.raise_for_status()
    return response.json()

def api_post(path, data):
    import json
    body = json.dumps(data)
    headers = get_auth_headers('POST', path, body)
    response = requests.post(API_URL + path, headers=headers, data=body)
    response.raise_for_status()
    return response.json()

# === RSI CALCULATION ===
def compute_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    if down == 0:
        return 100.0
    rs = up / down
    rsi = 100. - 100. / (1. + rs)
    return rsi

# === FETCH TRADING PAIRS ===
def get_usdc_pairs():
    data = api_get('/api/v3/brokerage/products')
    pairs = []
    for p in data['products']:
        if p['quote_currency'] == 'USDC' and p['status'] == 'online':
            base = p['base_currency']
            if base not in ['USDC', 'USDT', 'USD', 'DAI']:
                pairs.append(p['symbol'])
    return pairs

# === FETCH HISTORICAL PRICES (candles) ===
def get_candles(symbol):
    path = f'/api/v3/brokerage/products/{symbol}/candles?granularity=300&limit=100'
    data = api_get(path)
    # candles = [ [time, low, high, open, close, volume], ...]
    # We'll extract close prices oldest to newest:
    closes = [c[4] for c in reversed(data['candles'])]
    return closes

# === GET ACCOUNT BALANCES ===
def get_account_balances():
    data = api_get('/api/v3/brokerage/accounts')
    balances = {}
    for acct in data['accounts']:
        balances[acct['currency']] = float(acct['available'])
    return balances

# === PLACE MARKET ORDER ===
def place_order(side, symbol, size):
    data = {
        "product_id": symbol,
        "side": side,
        "size": str(size),
        "type": "market"
    }
    res = api_post('/api/v3/brokerage/orders', data)
    print(f"Placed {side} order for {size} {symbol}: {res}")
    return res

# === MAIN LOOP ===
def main():
    print("Starting Coinbase Advanced Trade bot")
    pairs = get_usdc_pairs()
    print("USDC trading pairs:", pairs)

    while True:
        balances = get_account_balances()
        usdc_balance = balances.get('USDC', 0)
        print(f"USDC balance: {usdc_balance}")

        for symbol in pairs:
            base = symbol.split('-')[0]
            closes = get_candles(symbol)
            if len(closes) < RSI_PERIOD + 1:
                print(f"Not enough data for {symbol}")
                continue
            rsi = compute_rsi(closes, RSI_PERIOD)
            print(f"{symbol} RSI: {rsi:.2f}")

            last_price = closes[-1]
            size = ORDER_BUDGET_USDC / last_price
            base_balance = balances.get(base, 0)

            if rsi < 30 and usdc_balance >= ORDER_BUDGET_USDC:
                print(f"Buying {base} with {ORDER_BUDGET_USDC} USDC")
                place_order('buy', symbol, round(size, 6))
            elif rsi > 70 and base_balance >= size:
                print(f"Selling {base} to USDC")
                place_order('sell', symbol, round(size, 6))
            else:
                print(f"No trade for {symbol}")

            time.sleep(2)  # avoid rate limit

        print(f"Cycle done. Sleeping {SLEEP_INTERVAL} seconds.\n")
        time.sleep(SLEEP_INTERVAL)

if __name__ == "__main__":
    main()
