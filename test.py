import requests


url = "https://api.zan.top/node/v1/eth/mainnet/f49b1672f41f49d2b0ba6dfc92a831de"

payload = {
    "id": 1,
    "jsonrpc": "2.0",
    "method": "eth_syncing"
}
headers = {
    "accept": "application/json",
    "content-type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)

print(response.status_code)
