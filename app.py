#Import packages from library
import streamlit as st
from streamlit_folium import st_folium
from routing import shaded_route, get_coordinates

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
  if start_lat is None or end_lat is None:
    st.error("One or both addresses could not be found. Please try again.")
  else:
    st.session_state["map"] = shaded_route(start_lat, start_lon, end_lat, end_lon, datetime_str)

if "map" in st.session_state:
  st_folium(st.session_state["map"], width = 700, height = 500, returned_objects = [])
  
