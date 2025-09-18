import folium
from folium.plugins import MarkerCluster
import requests
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from branca.colormap import LinearColormap
import pycountry
import time
from dotenv import load_dotenv
import os
load_dotenv()

def get_country_name(country_code):
    try:
        country = pycountry.countries.get(alpha_3=country_code)
        if country:
            return country.name
    except LookupError:
        return None

def get_color(feature, color_scale, map_dict):
    properties = feature['properties']
    country_abb = properties.get('A3')
    country_name = get_country_name(country_abb)
    value = map_dict.get(country_name)
    if value is None:
        return '#000000', 0
    else:
        return color_scale(value), 0.7

def create_choropleth_layer(m, country_visit_counts):
    choropleth_layer = folium.FeatureGroup(name='Linear Color Map')

    max_count = country_visit_counts['count'].max()
    color_scale = LinearColormap(['yellow', 'red'], vmin=country_visit_counts['count'].min(), vmax=max_count)
    map_dict = country_visit_counts.set_index('Country')['count'].to_dict()

    def style_function(feature):
        fillColor, fillOpacity = get_color(feature, color_scale, map_dict)
        return {
            'fillColor': fillColor,
            'fillOpacity': fillOpacity,
            'color': '#D4DADC',
            'weight': 1,
        }

    # Add choropleth layer
    folium.GeoJson(
        data='https://github.com/simonepri/geo-maps/releases/download/v0.6.0/countries-land-10km.geo.json',
        style_function=style_function
    ).add_to(choropleth_layer)

    return choropleth_layer, color_scale, max_count

def create_circle_marker_layer(m, locations, visited_countries):
    maps_api_key = os.getenv('MAPS_API_KEY')
    if not maps_api_key:
        raise ValueError("MAPS_API_KEY not set in environment")
    circle_marker_layer = folium.FeatureGroup(name='Circle Marker')
    marker_cluster = MarkerCluster().add_to(circle_marker_layer)

    for location, country in zip(locations, visited_countries):
        if not location or pd.isnull(location):
            print(f"Skipping invalid location: {location}")
            continue

        search_term = location
        if country and not pd.isnull(country):
            search_term += f', {country}'
        url = f'https://maps.googleapis.com/maps/api/geocode/json?address={search_term}&key={maps_api_key}'
        response = requests.get(url)
        result = response.json()
        if result['status'] == 'OK' and len(result['results']) > 0:
            location = result['results'][0]['geometry']['location']
            lat = location['lat']
            lng = location['lng']
            folium.CircleMarker(
                location=[lat, lng],
                popup=folium.Popup(f'{search_term}', max_width=250),
                radius=5,
                fill=True,
                fill_color='black',
                color='black',
            ).add_to(marker_cluster)
            time.sleep(0.1)  # To respect API rate limits
        else:
            print(f"Geocoding failed for location: {search_term}, status: {result['status']}")
            print(result['error_message'] if 'error_message' in result else '')
    return circle_marker_layer

def create_map():
    # Get data from Google Sheets using pandas
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    gc = gspread.authorize(credentials)
    sheets_id = os.getenv('SHEETS_ID')
    if not sheets_id:
        raise ValueError("SHEETS_ID not set in environment")
    worksheet = gc.open_by_key(sheets_id).worksheet('Sheet1')
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])

    # Create folium m
    m = folium.Map(location=[0, 0], zoom_start=2)

    locations = df['Location']
    visited_countries = df['Country']
    country_visit_counts = visited_countries.value_counts().to_frame().reset_index()

    # Create choropleth layer
    choropleth_layer, color_scale, max_count = create_choropleth_layer(m, country_visit_counts)
    choropleth_layer.add_to(m)

    # Create circle marker layer
    circle_marker_layer = create_circle_marker_layer(m, locations, visited_countries)
    circle_marker_layer.add_to(m)

    # Create legend
    legend_html = '''
        <div style="position: fixed;
                    bottom: 50px; left: 50px; width: 150px; height: {height}px;
                    border: 2px solid grey; z-index: 9999; font-size: 14px;
                    background-color: white;">
            <div style="text-align: center; margin-top: 10px;"><b>Cities Visited</b></div>
            {color_swatches}
        </div>
    '''

    color_swatches = ''
    for value in np.linspace(country_visit_counts['count'].min(), max_count, num=5):
        color = color_scale.rgb_hex_str(value)
        color_swatches += f'<div style="display: flex; flex-direction: row; align-items: center; justify-content: space-between; padding: 0 5px;"><div style="width: 30px; height: 15px; background-color: {color};"></div>{int(value)}</div>'

    legend_html = legend_html.format(height=140, color_swatches=color_swatches)
    m.get_root().html.add_child(folium.Element(legend_html))

    # Light and dark mode
    folium.TileLayer('cartodbdark_matter', overlay=False, name="View in Dark Mode").add_to(m)
    folium.TileLayer('cartodbpositron', overlay=False, name="View in Light Mode").add_to(m)

    folium.LayerControl().add_to(m)
    m.save('index.html')

if __name__ == '__main__':
    create_map()
