import requests

# Official FAA/ICAO Airport codes where Kalshi weather contracts settle
AIRPORT_MAPPING = {
    "Chicago": "KORD",    # O'Hare International Airport
    "Miami": "KMIA",      # Miami International Airport
    "Phoenix": "KPHX",    # Phoenix Sky Harbor International Airport
    "LAX": "KLAX",        # Los Angeles International Airport
    "Vegas": "KLAS",      # Harry Reid International Airport (Las Vegas)
    "Austin": "KAUS"      # Austin-Bergstrom International Airport
}


def get_market_probability(city):
    """
    Hard to get high frequency data, orgionally went on meteo stat for updates, however found that once market makes were allowed on the markets data wasn't
    accurate enough. Here is the problem that led to shutting it down. Tried to use predictive modeling using last 15 hours, but again wasnt accurate enough.
    Here is what I consider the weakest part of the project.
    """
    station_id = AIRPORT_MAPPING.get(city)
    if not station_id:
        print(f"⚠️ Unknown city mapping for: {city}")
        return None

    # Pulling the last 15 hours of raw airport METAR sensor data in JSON format
    url = f"https://aviationweather.gov/api/data/metar?ids={station_id}&format=json&hours=15"

    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        observations = resp.json()

        if not observations or not isinstance(observations, list):
            print(
                f"Empty response or invalid format from FAA for {station_id}")
            return None

        recent_temps_f = []
        for obs in observations:
            temp_c = obs.get('temp')
            if temp_c is not None:
                # Convert to Farenheit
                temp_f = (temp_c * 1.8) + 32
                recent_temps_f.append(temp_f)

        if not recent_temps_f:
            print(
                f"No temperature readings found in recent data for {station_id}")
            return None

        live_high_recorded = max(recent_temps_f)
        forecast_max = round(live_high_recorded)
        return {
            "probability": 0.65,
            "forecast_max": forecast_max
        }

    except Exception as e:
        print(
            f"❌ Aviation API Connection Failure for {city} ({station_id}): {e}")
        return None
