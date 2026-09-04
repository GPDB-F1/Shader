#Import packages from library
import streamlit as st
from streamlit_folium import st_folium
from routing import shaded_route, get_coordinates, monte_carlo_eta

#Streamlit interface
st.title("Shade-Aware Routing Algorithm")
st.write("Finds a walking route to keep users in a variable quantity of shade")

start_address = st.text_input("Start address", "Cambridge Circus, London")
end_address = st.text_input("End address", "Oxford Circus, London")
datetime_str = st.text_input("Date and time (YYYY-MM-DD HH:MM)", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))

if st.button("Find Shaded Route"):
  start_lat, start_lon = get_coordinates(start_address)
  end_lat, end_lon = get_coordinates(end_address)
  if start_lat is None or end_lat is None:
    st.error("One or both addresses could not be found. Please try again.")
  else:
    with st.spinner("Calculating..."):
      m, G, shaded_path, fastest_path = shaded_route(start_lat, start_lon, end_lat, end_lon, datetime_str)
      if shaded_path and fastest_path:
        shaded_eta = monte_carlo_eta(G, shaded_path, datetime_str)
        fastest_eta = monte_carlo_eta(G, fastest_path, datetime_str)
        st.session_state["map"] = m
        st.session_state["shaded_eta"] = shaded_eta
        st.session_state["fastest_eta"] = fastest_eta
      else:
        st.session_state["map"] = m

if "map" in st.session_state:
  if "shaded_eta" in st.session_state:
    shaded = st.session_state["shaded_eta"]
    fastest = st.session_state["fastest_eta"]
    st.write(f"Shaded route: ~{shaded['mean']/60:.0f} min (range: {shaded['p10']/60:.0f}-{shaded['p90']/60:.0f} min)")
    st.write(f"Fastest route: ~{fastest['mean']/60:.0f} min (range: {fastest['p10']/60:.0f}-{fastest['p90']/60:.0f} min)")
  st_folium(st.session_state["map"], width = 700, height = 500, returned_objects = [])
  
