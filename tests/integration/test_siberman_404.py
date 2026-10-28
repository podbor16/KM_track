"""Несуществующие страницы live.siberman515.com → 404 Тильды; API, «Спортсмен не найден» и другие домены — как были."""
SIB = {"host": "siberman.localhost"}
TILDA_404 = "https://siberman515.com/page"


def test_unknown_siberman_pages_redirect_to_tilda_404(client):
    for path in ("/hall/nope", "/draw/2028/overlay/nope", "/entries/1999", "/nope"):
        r = client.get(path, headers=SIB, follow_redirects=False)
        assert (r.status_code, r.headers.get("location")) == (302, TILDA_404), path


def test_api_and_other_domains_keep_json_404(client):
    r = client.get("/api/siberman/nope", headers=SIB)
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
    r = client.get("/draw/2028/overlay/nope", follow_redirects=False)            # не Siberman
    assert r.status_code == 404 and "location" not in r.headers
    r = client.get("/nope", follow_redirects=False)
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}


def test_unknown_athlete_keeps_own_page(client):
    r = client.get("/athlete/r999999999", headers=SIB, follow_redirects=False)
    assert r.status_code in (404, 200) and "location" not in r.headers
