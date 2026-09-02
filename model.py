import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
import pickle

# 1. Define the 6-City Matrix
CITIES = {
    "Chicago": {"station": "72530", "lat": 41.87, "lon": -87.62, "tz": "America/Chicago"},
    "Phoenix": {"station": "72278", "lat": 33.44, "lon": -112.07, "tz": "America/Phoenix"},
    "Miami":   {"station": "72202", "lat": 25.76, "lon": -80.19, "tz": "America/New_York"},
    "LAX":     {"station": "72295", "lat": 33.94, "lon": -118.40, "tz": "America/Los_Angeles"},
    "Austin":  {"station": "72254", "lat": 30.26, "lon": -97.74, "tz": "America/Chicago"},
    "Vegas":   {"station": "72386", "lat": 36.16, "lon": -115.14, "tz": "America/Los_Angeles"}
}

trained_models = {}

for city, info in CITIES.items():
    print(f"Training model for {city}...")

    # A. Fetch Actuals (Meteostat)
    actual_url = f"https://bulk.meteostat.net/v2/hourly/{info['station']}.csv.gz"
    df_actuals = pd.read_csv(actual_url, compression='gzip', names=[
                             'date', 'hour', 'temp', 'dwpt', 'rhum', 'prcp', 'snow', 'wdir', 'wspd', 'wpgt', 'pres', 'tsun', 'coco'])

    # Convert Meteostat Celsius to Fahrenheit BEFORE resampling
    df_actuals['temp'] = (df_actuals['temp'] * 1.8) + 32

    df_actuals['time'] = pd.to_datetime(
        df_actuals['date'] + ' ' + df_actuals['hour'].astype(str) + ':00:00')
    df_actuals.set_index('time', inplace=True)

    daily_actuals = df_actuals.resample('D').agg(
        {'temp': 'max', 'pres': 'mean', 'rhum': 'mean'})
    daily_actuals.columns = ['actual_max', 'avg_pres', 'avg_rhum']

    # B. Fetch Historical Forecasts (Open-Meteo Archive)
    archive_url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": info['lat'], "longitude": info['lon'],
        "start_date": "2024-01-01", "end_date": "2026-03-15",
        "daily": "temperature_2m_max", "timezone": info['tz'],
        "temperature_unit": "fahrenheit"  # ⚠️ FORCED NATIVE FAHRENHEIT
    }
    f_data = requests.get(archive_url, params=params).json()['daily']
    df_forecast = pd.DataFrame(f_data).rename(
        columns={'time': 'time', 'temperature_2m_max': 'forecast_max'})
    df_forecast['time'] = pd.to_datetime(df_forecast['time'])
    df_forecast.set_index('time', inplace=True)

    # C. Merge and Train
    data = daily_actuals.join(df_forecast).dropna()

    # ⚠️ TIGHTENED TARGET: Now checks if actual is within +/- 2 degrees FAHRENHEIT
    data['target_hit'] = (
        (data['actual_max'] - data['forecast_max']).abs() <= 2).astype(int)

    X = data[['forecast_max', 'avg_pres', 'avg_rhum']]
    y = data['target_hit']

    model = LogisticRegression()
    model.fit(X, y)

    trained_models[city] = model
    print(
        f"✅ {city} Model Trained. Strict 4°F Bracket Accuracy: {model.score(X, y):.2%}")

print("\n--- ALL MODELS SYNCED TO HEDGE FUND ---")

# Export Models
for city in CITIES.keys():
    filename = f"{city.lower()}_model.pkl"
    with open(filename, 'wb') as file:
        pickle.dump(trained_models[city], file)
    print(f"✅ Saved {filename}")
