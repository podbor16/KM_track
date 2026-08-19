import urllib.request
r = urllib.request.urlopen("https://results.krasmarafon.ru/health", timeout=15)
print(r.read().decode())
