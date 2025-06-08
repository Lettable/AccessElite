import hmac
import json
import hashlib
import requests

def signature(secret, data):
    return hmac.new(
        key=secret.encode(),
        msg=data.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()

def invoice(api, secret, data):
    url = 'https://ff.io/api/v2/create'
    
    params = {
        "type": "float",
        "fromCcy": "USDTTRC",
        "toCcy": "LTC",
        "direction": "to",
        "amount": data['plans']['amount'],
        "toAddress": data['ltc_address']
    }
    
    data = json.dumps(params)
    
    headers = {
        'Accept': 'application/json',
        'X-API-KEY': api,
        'X-API-SIGN': signature(secret, data),
        'Content-Type': 'application/json; charset=UTF-8'
    }
    
    response = requests.post(url, data=data, headers=headers)
    
    return response.json()
