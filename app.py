#Import packages from library
import osmnx as ox
import pvlib
import folium
import pandas as pd
import math
import networkx as nx
import streamlit as st
from streamlit_folium import st_folium
from shapely.geometry import Point, Polygon
from shapely import affinity
from shapely.ops import unary_union

#Function to recieve coordinates from user
def get_coordinates(address):
  coords = ox.geocode(address)
  return coords

#Function to calculate shadow polygon
def shadow_calculation(geometry, height, altitude, azimuth):
  #Convert altitude to radians
  altitude_in_radians = math.radians(altitude)
  #Calculate shadow length
  shadow_length = height / math.tan(altitude_in_radians)
  #Calculate shadow direction
  shadow_direction = (azimuth + 180) % 360
  #Convert to radians
  shadow_direction_in_radians = math.radians(shadow_direction)
  #x and y (east-west and north-south) component of shadow direction
  dx = shadow_length * math.sin(shadow_direction_in_radians)
  dy = shadow_length * math.cos(shadow_direction_in_radians)
  #Convert to degrees
  dx_degrees = dx / 111000
  dy_degrees = dy / 111000
  #Create shifted polygon
  shifted_polygon = affinity.translate(geometry, dx_degrees, dy_degrees)
  #Return the union of the two shadows
  return geometry.union(shifted_polygon)

#Function to return a value between 0 and 1, 0 being a segment fully in the sun and 1 being fully in the shade
def shade_fraction(geometry, all_shadows):
  shaded_length = geometry.intersection(all_shadows).length
  if geometry.length > 0:
    return shaded_length / geometry.length
  else: return 0

#Function to calculate shaded route
def shaded_route(start_lat, start_lon, end_lat, end_lon, datetime_str, timezone = "Europe/London"):
  #Calculate the centre point between start and end
  centre_lat = (start_lat + end_lat) / 2
  centre_lon = (start_lon + end_lon) / 2
  #Calculate radius large enough to cover route, plus 20% buffer
  route_distance = ox.distance.great_circle(start_lat, start_lon, end_lat, end_lon)
  radius = (route_distance / 2) * 1.2
  #Calculate building heights
  building_heights = ox.features.features_from_point((centre_lat, centre_lon), {"building" : True}, radius)
  building_heights["calculated_heights"] = pd.to_numeric(building_heights["height"], errors='coerce').fillna(pd.to_numeric(building_heights["building:levels"], errors = 'coerce') * 3.5)
  #Calculate solar position
  Area = pvlib.location.Location(centre_lat, centre_lon, timezone) #Location object
  timestamp = pd.Timestamp(datetime_str, tz = timezone) #Timezone object
  solar_position = Area.get_solarposition(timestamp)
  #Extract altitude and azimuth
  altitude = solar_position["elevation"].iloc[0]
  azimuth = solar_position["azimuth"].iloc[0]
  #Apply shadow calculation to all valid buildings
  building_heights["shadow"] = building_heights.apply(lambda row: shadow_calculation(row["geometry"], row["calculated_heights"], altitude, azimuth) if pd.notnull(row["calculated_heights"]) and row.geometry.geom_type in ["Polygon", "MultiPolygon"] else None, axis = 1)
  #Create all_shadows from unary_union
  all_shadows = unary_union(building_heights["shadow"].dropna())
  #Fetch street network
  G = ox.graph_from_point((centre_lat, centre_lon), radius, network_type = "walk")
  #Convert to GDF (GeoDataFrames)
  nodes, edges = ox.graph_to_gdfs(G)
  #Score edges with shade_fraction
  edges["shade_fraction"] = edges["geometry"].apply(lambda geom: shade_fraction(geom, all_shadows))
  #Apply shaded weights to graph
  for (u, v, k), row in edges.iterrows():
    if pd.notnull(row["shade_fraction"]):
      G[u][v][k]["shade_weight"] = row["length"] * (1 - row["shade_fraction"] * 0.9)
  # Obtain origin and destination node
  orig = ox.nearest_nodes(G, start_lon, start_lat)
  dest = ox.nearest_nodes(G, end_lon, end_lat)
  #Calculate and return shaded and fastest route on created map
  m = folium.Map(location = [centre_lat, centre_lon], zoom_start = 16)
  for idx, row in building_heights.iterrows():
    if row["shadow"] is not None:
      folium.GeoJson(row["shadow"], style_function = lambda x: {"fillColor": "#333333", "color": "#333333", "fillOpacity": 0.4}).add_to(m)
  get_shaded_route = nx.shortest_path(G, orig, dest, weight = "shade_weight")
  get_fastest_route = nx.shortest_path(G, orig, dest, weight = "length")
  shaded_coords = [(nodes.loc[node, "y"], nodes.loc[node, "x"]) for node in get_shaded_route]
  fastest_coords = [(nodes.loc[node, "y"], nodes.loc[node, "x"]) for node in get_fastest_route]
  folium.PolyLine(shaded_coords, color = "blue", weight = 5, opacity = 0.8).add_to(m)
  folium.PolyLine(fastest_coords, color = "red", weight = 5, opacity = 0.8).add_to(m)
  return m

#Streamlit interface
st.title("Shade-Aware Routing Algorithm")
st.write("Finds a walking route to keep users in a variable quantity of shade")

start_address = st.text_input("Start address", "Cambridge Circus, London")
end_address = st.text_input("End address", "Oxford Circus, London")
datetime_str = st.text_input("Date and time (YYYY-MM-DD HH:MM)", "2025-07-14 14:00")

if st.button("Find Shaded Route"):
  st.write("Calculating...")
  start_lat, start_lon = get_coordinates(start_address)
  end_lat, end_lon = get_coordinates(end_address)
  m = shaded_route(start_lat, start_lon, end_lat, end_lon, datetime_str)
  st.session_state["map"] = shaded_route(start_lat, start_lon, end_lat, end_lon, datetime_str)

if "map" in st.session_state:
  st_folium(st.session_state["map"], width = 700, height = 500)
  
