from flask import Flask
app = Flask(__name__)


from flask import Flask, render_template, request, jsonify, make_response,Response
from requests.auth import HTTPBasicAuth
import requests
import xml.etree.ElementTree as ET
from flask import g

from random import *
import configparser


import urllib.request
import pdfkit

from collections import OrderedDict

import sqlite3
import pandas as pd

import time

from concorde_optimize import concordeOptimize, get_distance, get_time
from werkzeug.contrib.cache import SimpleCache

cache = SimpleCache()
app = Flask(__name__)

#Read the api value
config = configparser.ConfigParser()
config.read("./.properties")
api = config['SECTION_HEADER']['api']
DATABASE = 'EParkLocations.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def getData():
    #get cash balance from CALE
    response = requests.get(
        'https://webservice.mdc.dmz.caleaccess.com/cwo2exportservice/LiveDataExport/1/LiveDataExportService.svc/terminalbalances',
        auth=HTTPBasicAuth('e_Edmonton2_2835', 'Chemistry149@'))
    root = ET.fromstring(response.content)
    df_terminalBalance = pd.DataFrame(columns=['TerminalID', 'TerminalLocation', 'CoinBalance'])
    for child in root:
        df_terminalBalance = df_terminalBalance.append(pd.DataFrame(
            [[child.attrib['TerminalID'], child.attrib['TerminalLocation'].replace(",", ""),float(child.attrib['CoinBalance'])]],
            columns=['TerminalID', 'TerminalLocation', 'CoinBalance']))

    response = requests.get(
        'https://webservice.mdc.dmz.caleaccess.com/cwo2exportservice/LiveDataExport/1/LiveDataExportService.svc/uncollectedterminals',
        auth=HTTPBasicAuth('e_Edmonton2_2835', 'Chemistry149@'))
    root = ET.fromstring(response.content)

    df_Days = pd.DataFrame(columns=['TerminalID', 'CollectionDateLocal', 'NumberOfDays', 'Balance'])
    for child in root:
        if child.attrib['TerminalStatus'] == 'Active':
            df_Days = df_Days.append(pd.DataFrame([[child.attrib['TerminalID'], child.attrib['CollectionDateLocal'],
                                          child.attrib['NumberOfDays'], child.attrib['Balance']]],
                                        columns=['TerminalID', 'CollectionDateLocal', 'NumberOfDays', 'Balance']))

    df_Days['CollectionDateLocal'] = pd.to_datetime(df_Days['CollectionDateLocal'], format='%Y-%m-%dT%H:%M:%S.%f')
    df_Days['Balance'] = df_Days['Balance'].apply(lambda x: float(x))
    df_Days['NumberOfDays'] = df_Days['NumberOfDays'].apply(lambda x: float(x))

    df_Days.drop_duplicates(subset=['TerminalID'], keep='last', inplace=True)

    df_terminalBalance = df_terminalBalance.merge(df_Days[['TerminalID', 'NumberOfDays']], on='TerminalID', how='left')

    df_terminalBalance = df_terminalBalance.sort_values('CoinBalance', ascending=False)

    #get terminal locations from db
    # Create a SQL connection to our SQLite database
    con = get_db()

    # the result of a "cursor.execute" can be iterated over by row
    df_Locations = pd.read_sql('Select * FROM EParkLocations;', con)
    con.close()

    df = df_terminalBalance.merge(df_Locations, on='TerminalID', how='left')

    df.sort_values('CoinBalance', ascending=False, inplace=True)

    df.set_index('TerminalID', inplace=True)

    id_latlon = OrderedDict()

    for index, row in df.iterrows():
        id_latlon[index] = {'CoinBalance': row['CoinBalance'], 'lat_lon': str(row['lat'])+","+str(row['lon']), 'Days Since last Collected':
                            row['NumberOfDays']}

    # for TM in df.index:
    #     id_latlon[str(TM) + ",  " + str(df['CoinBalance'].loc[str(TM)])] = str(df.lat.loc[str(TM)]) + ", " + str(df.lon.loc[str(TM)])

    return id_latlon

# This function will receive the distance or time matrix
@app.route("/optimize")
def optimize_my_route():
    matrix = request.args.get('matrix').replace('"', '')
    #cache the stopover submitted previously
    stopover = cache.get('stopover')
    coords = cache.get('coords')
    print(stopover)
    print(coords)
    print('main: ', stopover)
    #rv = cache.get('optimized_route')
    #url = cache.get('url')
    #if old_stopover is None or old_stopover != stopover:
    rv, url = concordeOptimize(matrix, stopover, coords)
    #cache.set('stopover', stopover, timeout=30 * 60)
    cache.set('optimized_route', rv[1:-1], timeout=30 * 60)
    #cache.set('url', url, timeout=30 * 60)
    return jsonify(result=rv[1:-1], url=url)
    #else:
    #    return jsonify(result=rv, url=url)

@app.route("/")
@app.route("/optimap/")
def optimap():
    id_latlon = getData()
    return render_template('directions.html', id_latlon=id_latlon)

@app.route("/show_tables/")
def show_tables():
    import datetime
    d = datetime.datetime.today().strftime('%Y-%m-%d')

    optimized_route = cache.get('optimized_route')

    if optimized_route is not None:
        cur = get_db().execute(
            'SELECT TerminalID, TerminalLocation FROM EParkLocations WHERE TerminalID in {0}'.format(str(optimized_route).
                                                                                         replace("[", "(").replace(']',
                                                                                                                   ')')))
        rv = cur.fetchall()
        cur.close()
        location_dict = dict((x, y) for x, y in rv)
        optimized_route = [str(i + ": " + location_dict[i]) for i in optimized_route]
        while len(optimized_route) < 25:
            optimized_route.append("")
    else:
        optimized_route = ['']*25
    rendered = render_template('stopOrederTable.html', optimal_route=optimized_route, date=d)
    pdf = pdfkit.from_string(rendered, False)

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=output.pdf'

    return response

@app.route('/page')
def get_page():
    return render_template('progress.html')


#This function will construct the distance matrix and pass it back to flask to pass forward to optimize function.
@app.route('/progress')
def progress():
    # Read the MachineID selected on the web page
    stops = request.args.get('stopover').split(",")
    #print('stops = ', stops)
    
    # cache the stopover submitted previously
    cache.set('stopover', stops, timeout=30*60)
    
    #print('cache = ', cache.get('stopover'))

    #read the lat-lon from the db
    con = sqlite3.connect(DATABASE)

    df_Locations = pd.read_sql('Select * FROM EParkLocations;', con)
    df_Locations = df_Locations[df_Locations.TerminalID.isin(stops)]

    # get the stopver coords
    coords = []
    for index, row in df_Locations.iterrows():
        coords.append([row['lat'], row['lon']])

    # add a start and end
    coords.append([53.5892396, -113.42835785])
    coords.append([53.568889, -113.502966])

    cache.set('coords', coords, timeout=30 * 60)

    distances = [[0 for i in range(len(coords))] for j in range(len(coords))]
    times = [[0 for i in range(len(coords))] for j in range(len(coords))]

    def generate():
        for i in range(len(coords)):
            for j in range(len(coords)):
                time.sleep(1)
                if i == j:
                    pass
                else:
                    # url = """https://maps.googleapis.com/maps/api/directions/json?origin={0},{1}&destination={2},{3}&key={4}""".format(
                    #     coords[i][0], coords[i][1],
                    #     coords[j][0], coords[j][1],
                    # api)
                    # f = urllib.request.urlopen(url)
                    # text = f.read()
                    # distances[i][j] = get_distance(text)
                    # times[i][j] = get_time(text)
                    distances[i][j] = randint(1,1000)
                    times[i][j] = randint(100,500)
            yield "data:" + str(int(i * 100 / len(coords))) + "\n\n"

        yield "data:" + str(100) + "\n\n"

        #set the distance and time between start and stop to 0
        distances[len(coords) - 2][len(coords) - 1] = 0
        distances[len(coords) - 1][len(coords) - 2] = 0

        times[len(coords) - 2][len(coords) - 1] = 0
        times[len(coords) - 1][len(coords) - 2] = 0

        yield "data:"+ str(times) + "\n\n"

    return Response(generate(), mimetype='text/event-stream')

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True, port=80, threaded=True)