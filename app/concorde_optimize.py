import sqlite3
import pandas as pd

from flask import Response, Flask, send_file

import json
import urllib.request

import os
import subprocess

import itertools

app = Flask(__name__)

def shift(l,n):
    return itertools.islice(itertools.cycle(l),n,n+len(l))

def get_distance(direction_data):
    """
    get distance from google directions api response,
    the unit for this field is meter
    """
    return json.loads(direction_data)['routes'][0]['legs'][0]['distance']['value']

def get_time(direction_data):
    """
    get time from google directions api response,
    the unit for this field is seconds
    """
    return json.loads(direction_data)['routes'][0]['legs'][0]['duration']['value']


# after running the Concorde executable, parse the output file
def parse_solution(filename):
    solution = []
    f = open(filename, 'r')
    for line in f.readlines():
        tokens = line.split()
        solution += [int(c) for c in tokens]
    f.close()
    solution = solution[1:]  # first number is just the dimension
    return solution

def concordeOptimize(matrix, stopovers, coords):
    print(stopovers)
    matrix = eval(matrix)

    matrix = [[str(j) for j in i] for i in matrix]

    i = 0
    id_order_match = {}
    for s in stopovers:
        id_order_match[i] = s
        i += 1
    id_order_match[len(stopovers)] = 'start'
    id_order_match[len(stopovers) + 1] = 'end'

    # create input file for Concorde TSP solver
    # we are minimizing total time
    sc_id = 0
    output = ''
    for sc_name in matrix:
        output += '{0}\n'.format(" ".join(sc_name))
        sc_id += 1

    header = """NAME: ParkingMeters
TYPE: TSP
COMMENT: driving time (seconds)
DIMENSION:  %d
EDGE_WEIGHT_TYPE: EXPLICIT
EDGE_WEIGHT_FORMAT: FULL_MATRIX
EDGE_WEIGHT_SECTION
""" % sc_id

    with open('/usr/src/sc.tsp', 'w') as output_file:
        output_file.write(header)
        output_file.write(output)

    tsp_path = '/usr/src/sc.tsp'
    bdir = os.path.dirname(tsp_path)
    os.chdir(bdir)

    CONCORDE = os.environ.get('concorde', '/usr/src/concorde/TSP/concorde')
    try:
        output = subprocess.check_output([CONCORDE, tsp_path], shell=False)
    except OSError as exc:
        if "No such file or directory" in str(exc):
            raise "{0} is not found on your path or is not executable".format(CONCORDE)

    solf = os.path.join(
        bdir, os.path.splitext(os.path.basename(tsp_path))[0] + ".sol")

    solution = parse_solution(solf)

    coords_path = []
    optimal_path = []
    for solution_id in solution:
        optimal_path.append(id_order_match[solution_id])
        coords_path.append("(" + str(coords[solution_id][0]) + "," + str(coords[solution_id][1]) + ")")

    # check if start or end occurs first in the optimal_path
    start = [index for index in range(len(optimal_path)) if optimal_path[index] == 'start'][0]
    end = [index for index in range(len(optimal_path)) if optimal_path[index] == 'end'][0]
    if start > end:
        optimal_path = list(shift(optimal_path, start))
        coords_path = list(shift(coords_path, start))
    else:
        optimal_path = list(shift(optimal_path, start+1))[::-1]
        coords_path = list(shift(coords_path, start+1))[::-1]

    url = 'https://www.google.ca/maps/dir/' + "/".join(coords_path)


    return optimal_path, url

if __name__ == '__main__':
    pass
    #print(conconrdeOptimize(['1048']))