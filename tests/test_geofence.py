from server.walk.geofence import distance_m, nearest_unseen, poi_key


def test_distance_one_millidegree_lat():
    d = distance_m(18.0, 73.0, 18.001, 73.0)
    assert 105 < d < 118  # ~111 m


def test_nearest_unseen_skips_narrated_and_factless():
    near = {"name": "A", "lat": 18.0001, "lon": 73.0, "facts": "x"}
    factless = {"name": "B", "lat": 18.00005, "lon": 73.0, "facts": ""}
    far = {"name": "C", "lat": 18.01, "lon": 73.0, "facts": "y"}
    assert nearest_unseen([near, factless, far], 18.0, 73.0, set(), 40)["name"] == "A"
    assert nearest_unseen([near, factless, far], 18.0, 73.0, {poi_key(near)}, 40) is None
