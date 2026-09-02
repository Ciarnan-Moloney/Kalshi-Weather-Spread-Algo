import requests

AIRPORT_MAPPING = {
    "Chicago": "KORD",
    "Miami": "KMIA",
    "Phoenix": "KPHX",
    "LAX": "KLAX",
    "Vegas": "KLAS",
    "Austin": "KAUS"
}


def get_live_airport_temperature(city):
    """
    Pulls raw, low-latency airport thermometer data directly from the FAA feed.
    """
    station_id = AIRPORT_MAPPING.get(city)
    if not station_id:
        return None

    url = f"https://aviationweather.gov/api/data/metar?ids={station_id}&format=json&hours=15"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        observations = resp.json()

        recent_temps_f = []
        for obs in observations:
            temp_c = obs.get('temp')
            if temp_c is not None:
                recent_temps_f.append((temp_c * 1.8) + 32)

        if not recent_temps_f:
            return None

        return round(max(recent_temps_f))
    except Exception as e:
        return None
