import urllib.request
r = urllib.request.urlopen("https://analytics.krasmarafon.ru/health", timeout=15)
print(r.read().decode())
