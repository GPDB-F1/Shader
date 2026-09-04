#Shaded Routing Algorithm

#Install geographic libraries
#!pip install osmnx pvlib folium shapely
#Import packages from library
import osmnx as ox
import pvlib
import folium
import pandas as pd
import math
import networkx as nx
import numpy as np
from shapely.geometry import Point, Polygon
from shapely import affinity
from shapely.ops import unary_union

OVERPASS_MIRRORS = [
  "https://overpass.kumi.systems/api/interpreter",
  "https://overpass.private.coffee/api/interpreter",
  "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
  "https://overpass.openstreetmap.ru/api/interpreter"
]

def set_overpass_mirror(index = 0):
  ox.settings.timeout = 30
  ox.settings.overpass_url = OVERPASS_MIRRORS[index]
set_overpass_mirror(0)

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
  radius = max(300, min((route_distance / 2) * 1.2, 1500))
  #Calculate building heights
  for i, mirror in enumerate(OVERPASS_MIRRORS):
    try:
      set_overpass_mirror(i)
      building_heights = ox.features.features_from_point((centre_lat, centre_lon), {"building" : True}, radius)
      break
    except Exception:
      if i == len(OVERPASS_MIRRORS) - 1:
        raise
      continue
  building_heights["calculated_heights"] = pd.to_numeric(building_heights["height"], errors='coerce').fillna(pd.to_numeric(building_heights["building:levels"], errors = 'coerce') * 3.5)
  #Calculate solar position
  Area = pvlib.location.Location(centre_lat, centre_lon, timezone) #Location object
  timestamp = pd.Timestamp(datetime_str, tz = timezone) #Timezone object
  solar_position = Area.get_solarposition(timestamp)
  #Extract altitude and azimuth
  altitude = solar_position["elevation"].iloc[0]
  azimuth = solar_position["azimuth"].iloc[0]
  #Check if altitude is below 5°, if so skip calculation
  if altitude < 5:
    print("Altitude too low for calculation, returning fastest route")
    m = folium.Map(location = [centre_lat, centre_lon], zoom_start = 16)
    for i, mirror in enumerate(OVERPASS_MIRRORS):
      try:
        set_overpass_mirror(i)
        G = ox.graph_from_point((centre_lat, centre_lon), radius, network_type = "walk")
        break
      except Exception:
        if i == len(OVERPASS_MIRRORS) - 1:
          raise
        continue
    nodes, edges = ox.graph_to_gdfs(G)
    orig = ox.nearest_nodes(G, start_lon, start_lat)
    dest = ox.nearest_nodes(G, end_lon, end_lat)
    try:
      get_fastest_route = nx.shortest_path(G, orig, dest, weight = "length")
      fastest_coords = [(nodes.loc[node, "y"], nodes.loc[node, "x"]) for node in get_fastest_route]
      folium.PolyLine(fastest_coords, color = "red", weight = 5, opacity = 0.8).add_to(m)
    except Exception as e:
      print(f"Error: {e}")
      print("No valid route found")
    return m, G, [], []
  #Apply shadow calculation to all valid buildings
  building_heights["shadow"] = building_heights.apply(lambda row: shadow_calculation(row["geometry"], row["calculated_heights"], altitude, azimuth) if pd.notnull(row["calculated_heights"]) and row.geometry.geom_type in ["Polygon", "MultiPolygon"] else None, axis = 1)
  #Create all_shadows from unary_union
  all_shadows = unary_union(building_heights["shadow"].dropna())
  #Fetch street network
  for i, mirror in enumerate(OVERPASS_MIRRORS):
    try:
      set_overpass_mirror(i)
      G = ox.graph_from_point((centre_lat, centre_lon), radius, network_type = "walk")
      break
    except Exception:
      if i == len(OVERPASS_MIRRORS) - 1:
        raise
      continue
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
  get_shaded_route = []
  get_fastest_route = []
  try:
    get_shaded_route = nx.shortest_path(G, orig, dest, weight = "shade_weight")
    get_fastest_route = nx.shortest_path(G, orig, dest, weight = "length")
    shaded_coords = [(nodes.loc[node, "y"], nodes.loc[node, "x"]) for node in get_shaded_route]
    fastest_coords = [(nodes.loc[node, "y"], nodes.loc[node, "x"]) for node in get_fastest_route]
    folium.PolyLine(shaded_coords, color = "blue", weight = 5, opacity = 0.8).add_to(m)
    folium.PolyLine(fastest_coords, color = "red", weight = 5, opacity = 0.8).add_to(m)
  except Exception as e:
    print(f"Error: {e}")
    print("No valid route found")
  return m, G, get_shaded_route, get_fastest_route

def get_coordinates(address):
  try:
    coords = ox.geocode(address)
    return coords
  except Exception as e:
    print(f"Address not found: {address}")
    return None

#ETA Calculations using Monte Carlo Simulations
def monte_carlo_eta(G, route, datetime_str, n_simulations = 500):
  #Calculate total distance
  total_distance = 0
  for i in range(len(route) - 1):
    total_distance = total_distance + G[route[i]][route[i+1]][0]["length"]
    #This loop sums each consecutive node ID (i.e. a singlular distance)

  #Calculate busyness multiplier
  hour = pd.Timestamp(datetime_str).hour
  #Busyness increased between 7-9am and 4-7pm
  if (hour >= 7 and hour <= 9) or (hour >= 16 and hour <= 19):
    busyness = 1.3
  else:
    busyness = 1

  #Simulation loop
  times = []
  for i in range(n_simulations):
    #Store sampled walking speed with mean of 1.4m/s and standard deviation of 0.2m/s
    walking_speed = max(0.5, np.random.normal(1.4, 0.2))
    #Count an average of one crossing every 5 nodes
    n_crossings = len(route) // 5
    #Calculate total journey time
    time = (total_distance / walking_speed) * busyness
    #Factor in crossing delay
    for j in range(n_crossings):
      #Crossing is between 0 and 90 seconds
      delay = np.random.uniform(0,90)
      time = time + delay
    #Append final time to times
    times.append(time)
  mean = np.mean(times)
  p10 = np.percentile(times, 10)
  p90 = np.percentile(times, 90)
  return {"mean": mean, "p10": p10, "p90": p90}

#App address: https://shader-xv35.onrender.com/
