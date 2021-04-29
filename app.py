import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State
from dash import callback_context
from dash.exceptions import PreventUpdate
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
#IMPORTING LIBRARY
import requests
import json
import numpy as np
#import webbrowser
#from threading import Timer
import os.path

port = os.environ.get('dash_port')
debug = os.environ.get('dash_debug')=="True"
icao24_name=''

# def open_browser():
#     webbrowser.open_new("http://localhost:{}".format(port))

token = open(".mapbox_token").read()

ac_database = 'aircraftDatabase.csv'
ac_database_pkl = os.path.basename(ac_database).split('.')[0]+'.pkl'
if os.path.isfile(ac_database_pkl):
    ac_df = pd.read_pickle(ac_database_pkl)
else:
    ac_df = pd.read_csv(ac_database)
    ac_df = ac_df[['icao24','manufacturername','model','typecode', 'operator', 'owner','built','registered']]
    ac_df = ac_df.fillna('N/A')
    ac_df.to_pickle(ac_database_pkl)
ac_df['built'].fillna(ac_df['registered'], inplace=True)
ac_df['built_year'] = ac_df['built'].replace('N/A','0-0-0').apply(lambda x: int(x.split('-')[0]))
ac_df['manufacturername'] = ac_df['manufacturername'].apply(lambda x: x.split(' ')[0].strip())
max_year=ac_df['built_year'].max()

def airplane_traking (lon_min,lon_max,lat_min,lat_max):
    #REST API QUERY
    user_name='siksdad'
    password='b737b787'
    url_data='https://'+user_name+':'+password+'@opensky-network.org/api/states/all?'+'lamin='+str(lat_min)+'&lomin='+str(lon_min)+'&lamax='+str(lat_max)+'&lomax='+str(lon_max)
    response=requests.get(url_data).json()

    #LOAD TO PANDAS DATAFRAME
    col_name=['icao24','callsign','origin_country','time_position','last_contact','long','lat','baro_altitude','on_ground','velocity',       
    'true_track','vertical_rate','sensors','geo_altitude','squawk','spi','position_source']
    flight_df=pd.DataFrame(response['states'],columns=col_name)
    flight_df=flight_df.fillna('No Data') #replace NAN with No Data

    #FUNCTION TO CONVERT GCS WGS84 TO WEB MERCATOR
    #POINT
    def wgs84_web_mercator_point(lon,lat):
        k = 6378137
        x= lon * (k * np.pi/180.0)
        y= np.log(np.tan((90 + lat) * np.pi/360.0)) * k
        return x,y

    #DATA FRAME
    def wgs84_to_web_mercator(df, lon="long", lat="lat"):
        k = 6378137
        df["x"] = df[lon] * (k * np.pi/180.0)
        df["y"] = np.log(np.tan((90 + df[lat]) * np.pi/360.0)) * k
        return df

    #COORDINATE CONVERSION
    xy_min=wgs84_web_mercator_point(lon_min,lat_min)
    xy_max=wgs84_web_mercator_point(lon_max,lat_max)
    wgs84_to_web_mercator(flight_df)
    flight_df['rot_angle']=flight_df['true_track'] #Rotation angle
    icon_url='https://opensky-network.org/aircraft-profile?icao24='+ flight_df['icao24']#Icon url
    flight_df['url']=icon_url
    flight_df = pd.merge(flight_df, ac_df, how='inner', on='icao24')
    flight_df = flight_df[flight_df['on_ground']==False]

    return flight_df

lon_min,lat_min=-179.9,-89
lon_max,lat_max=179.9,89
flight_df = airplane_traking(lon_min,lon_max,lat_min,lat_max)
range_dict = {i: '{}'.format(i) for i in range(1960, 2050, 30)}
#range_dict[max_year] = str(max_year)[-2:]

app = dash.Dash(__name__)
app.title = 'WhatsUpFlight'
app.layout = html.Div(className="app-container",

    children=[
    html.Div( className="app-header", 
        children=[
        html.Div(className="title",children=[html.H1("WhatsUpFlight")]),
        html.Br(),
        html.P('ICAO Number:'),
        dcc.Input(id='link_address',value="link_address"),
        html.A(html.Button('Check'), id='link', target='_blank'),
        html.P("Map Style:"),
        dcc.RadioItems(
            id='map_style', 
            className="radio",
            options=[{'value': x, 'label': x} for x in ['Point','Direction']],
            value='Point',
            labelStyle={'display': 'inline-block'}
        ),
        html.P("Manufacturer:"),
        dcc.RadioItems(
            id='ac', 
            className="radio",
            options=[{'value': x, 'label': x} for x in ['Boeing','Airbus','Others','All']],
            value='All',
            labelStyle={'display': 'inline-block'}
        ),
        html.P("Year Built:"),
        dcc.RangeSlider(
            id='yearb',
            className="slider",
            min=1960,
            max=2050,
            value=[1960, 2050],
            step=30,
            dots=True,
            marks=range_dict,
            updatemode='drag'
        ),
        html.Br(),
        html.Label(id="nplane", children="nplane")  
    ]),
    html.Div(className="app-body", 
        children=[
        dcc.Graph(id="map"),
        dcc.Interval(
                id='interval-component',
                interval=20*1000, # in milliseconds
                n_intervals=0
        )
    ])
])
@app.callback(
    [Output("link", "href"),
    Output("link_address","value")],
    [Input("map", "hoverData")])
def display_hover_data(hoverData):
    if hoverData:
        target = hoverData['points'][0]['customdata'][0]
        icao24_name = target.split("=")[-1]
        return target, icao24_name
    else:
        return '', ''

@app.callback(
    [Output("map", "figure"),
     Output("nplane","children")
     ], 
    [Input('interval-component', 'n_intervals'),
     Input("map","relayoutData"),
     Input("map_style","value"),
     Input("ac", "value"),
     Input("yearb", "value")],
     [State("map_style","value"),
     State("ac", "value")])
def display_map(n,r,m,a,yb,psm,psa):
    global flight_df
    trigger = callback_context.triggered[0]
    #print (trigger)

    lon_min,lat_min=-179.9,-89
    lon_max,lat_max=179.9,89

    try:
        latInitial = (r['mapbox.center']['lat'])
        lonInitial = (r['mapbox.center']['lon'])
        zoom = (r['mapbox.zoom'])
    except:
        zoom = 5
        latInitial = 47
        lonInitial = -122

    #print (m,psm,'--',a, psa) 
    if trigger['prop_id'] == 'ac.value' or trigger['prop_id'] == 'map_style.value' or trigger['prop_id'] == 'yearb.value' or trigger['prop_id'] == '.' :
        pass
    else:
        flight_df = airplane_traking(lon_min,lon_max,lat_min,lat_max)
        # print('updated', trigger['prop_id'])
        # print('-----------------------------')
   # fig = go.Figure(data=go.Scattergeo(lat=flight_df["lat"],lon=flight_df["long"]))
    # if trigger['prop_id'] == '.':
    #     flight_df1 = flight_df[((flight_df.built_year>=yb[0])&(flight_df.built_year<=yb[1]))|(flight_df.built_year==0)]
    #     no_planes = "{} All Planes.".format(len(flight_df1))
    #     srange = [flight_df1["built_year"].min(), flight_df1["built_year"].max()]
    # else:
    if a=='Boeing':
        flight_df1 = flight_df[((flight_df.manufacturername=='Boeing')&(flight_df.built_year>=yb[0])
            &(flight_df.built_year<=yb[1]))|((flight_df.manufacturername=='Boeing')&(flight_df.built_year==0))]
        no_planes = "{} Boeing Planes.".format(len(flight_df1))
        srange = [flight_df1["built_year"].min(), flight_df1["built_year"].max()]
    elif a=='Airbus':
        flight_df1 = flight_df[((flight_df.manufacturername=='Airbus')&(flight_df.built_year>=yb[0])
            &(flight_df.built_year<=yb[1]))|((flight_df.manufacturername=='Airbus')&(flight_df.built_year==0))]
        no_planes = "{} Airbus Planes.".format(len(flight_df1))
        srange = [flight_df1["built_year"].min(), flight_df1["built_year"].max()]
    elif a=='Others':
        flight_df1 = flight_df[((flight_df.manufacturername!='Airbus')&(flight_df.manufacturername!='Boeing')
            &(flight_df.built_year>=yb[0])&(flight_df.built_year<=yb[1]))|((flight_df.manufacturername!='Airbus')&(flight_df.manufacturername!='Boeing')&(flight_df.built_year==0))]
        no_planes = "{} Other Planes.".format(len(flight_df1))
        srange = [flight_df1["built_year"].min(), flight_df1["built_year"].max()]
    else:
        flight_df1 = flight_df[((flight_df.built_year>=yb[0])&(flight_df.built_year<=yb[1]))|(flight_df.built_year==0)]
        no_planes = "{} All Planes.".format(len(flight_df1))
        srange = [flight_df1["built_year"].min(), flight_df1["built_year"].max()]

    if len(flight_df1)==0:
        flight_df1 = pd.DataFrame(columns=["lat","long","url"])
        fig = px.scatter_mapbox(flight_df1, lat=[-89.9], lon=[0.0], 
                            color_discrete_sequence=["fuchsia"], center={'lat':latInitial, 'lon':lonInitial}, zoom=zoom, 
                            height=700, ) 
        fig.update_traces(hoverinfo='skip')
    else:
        fig = px.scatter_mapbox(flight_df1, lat="lat", lon="long", hover_name="callsign", hover_data=["icao24", "baro_altitude", "velocity", "rot_angle", 
                            "manufacturername", "model", "typecode", "owner", "built","origin_country"],
                            color_discrete_sequence=["fuchsia"], center={'lat':latInitial, 'lon':lonInitial}, zoom=zoom, 
                            height=700, custom_data=["url"], text="model")
    if m == 'Direction':
        fig.update_layout(mapbox=dict(accesstoken=token))
        try:
            fig.update_traces(marker=go.scattermapbox.Marker(angle=list(flight_df1["rot_angle"]), symbol='airport', size=9, color="fuchsia"), textposition="top right")
        except:
            fig.update_traces(marker=go.scattermapbox.Marker(symbol='airport', size=9, color="fuchsia"), textposition="top right")
    else:
        fig.update_layout(mapbox=dict(accesstoken=token), mapbox_style="open-street-map")
        fig.update_traces(marker=go.scattermapbox.Marker( symbol='circle', size=8, color="fuchsia"))
        
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})

    fig['layout']['uirevision'] = 'some-constant'

    # def do_click(trace, points, state):
    #     ind = points.point_inds[0]
    #     url = flight_df.icon_url.iloc[ind]
    #     webbrowser.open_new_tab(url)

    # fig.on_click(do_click)
    #print(no_planes)

    return fig, no_planes

if __name__ =="__main__":
    # Timer(1,open_browser).start()
    app.run_server(debug=debug, host='0.0.0.0', port=3000)