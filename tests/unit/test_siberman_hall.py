from src.siberman.medals import medal_for


def test_medals_by_finish_number():
    assert [medal_for(n)["key"] for n in range(1, 8)] == [
        "silver", "black", "gold", "copper", "chameleon", "hex_black", "hex_silver_red"]
    assert medal_for(12)["key"] == "hex_silver_red"
    assert medal_for(0) is None and medal_for(None) is None
    assert medal_for(None, relay=True)["key"] == "relay_silver"
    assert set(medal_for(3)) == {"key", "name", "color"}
