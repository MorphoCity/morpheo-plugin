# -*- coding: utf-8 -*-

"""
***************************************************************************
    Way.py
    ---------------------
    Date                 : February 2015
    Copyright            : (C) 2015 Oslandia
    Email                : vincent dot mora at oslandia dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

__author__ = 'Vincent Mora'
__date__ = 'February 2015'
__copyright__ = '(C) 2015, Oslandia'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

from processing.core.ProcessingLog import ProcessingLog
from math import sin, pi
from Terminology import TrCursor
from Indicators import *
import numpy as np

import os, sys, inspect
cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)

def log_info(info):
    "logs and print on console"
    print "info: ", info
    ProcessingLog.addToLog(ProcessingLog.LOG_INFO, info)

def log_error(info):
    "logs and print on console"
    print "error: ", info
    ProcessingLog.addToLog(ProcessingLog.LOG_ERROR, info)

class WayMerger(dict):
    """Fast merging of ways segments"""
    DEBUG = False
    def __init__(self, way_pieces, progress=Progress()):
        """Merge ways"""
        super(WayMerger, self).__init__()
        self.__extremities = {}
        self.__way_id = 0
        for piece_idx, way_piece in enumerate(way_pieces):
            progress.setPercentage(int(100*float(piece_idx)/len(way_pieces)))
            self.__add_way_piece(way_piece)

        log_info("Found "+str(len(self))+" ways from "+
                str(len(way_pieces))+" pieces")

    def __add_way_piece(self, way_piece):
        """High level, just decides, using indexes, if the piece
        joins two ways tohether or lengthen a way or is a ne way in itself"""

        if way_piece[0] in self.__extremities:
            if way_piece[1] in self.__extremities:
                self.__join_ways(way_piece)
            else:
                self.__lengthen_way(self.__extremities[way_piece[0]], way_piece)
        elif way_piece[1] in self.__extremities:
            self.__lengthen_way(self.__extremities[way_piece[1]], way_piece)
        else:
            self.__extremities[way_piece[0]] = self.__way_id
            self.__extremities[way_piece[1]] = self.__way_id
            self[self.__way_id] = list(way_piece)
            self.__way_id += 1

    def __join_ways(self, way_piece):
        """decides wich en matches which, merge ways and update indices
        pre: the indices in way_piece both exist in self.__extremities"""
        idx = [self.__extremities[way_piece[0]],
               self.__extremities[way_piece[1]]]

        if idx[0] == idx[1]: # this way is a loop no need to join
            return

        if self[idx[0]][0] in way_piece:
            if self[idx[1]][0] in way_piece: # begin - begin
                self[idx[0]] = self[idx[0]][::-1] + self[idx[1]]
                self.__extremities[self[idx[1]][-1]] = idx[0]
            else: # begin - end
                assert self[idx[1]][-1] in way_piece
                self[idx[0]] = self[idx[1]] + self[idx[0]]
                self.__extremities[self[idx[1]][0]] = idx[0]
        elif self[idx[0]][-1] in way_piece:
            if self[idx[1]][-1] in way_piece: # end - end
                self[idx[0]] = self[idx[0]] + self[idx[1]][::-1]
                self.__extremities[self[idx[1]][0]] = idx[0]
            else: # end - begin
                assert self[idx[1]][0] in way_piece
                self[idx[0]] = self[idx[0]] + self[idx[1]]
                self.__extremities[self[idx[1]][-1]] = idx[0]

        self.__extremities.pop(way_piece[0])
        self.__extremities.pop(way_piece[1])
        self.pop(idx[1])
        assert self.__extremities[self[idx[0]][0]] == idx[0]
        assert self.__extremities[self[idx[0]][-1]] == idx[0]

    def __lengthen_way(self, way_idx, way_piece):
        """append or prepend the way piece to the way"""

        if self[way_idx][0] == way_piece[0]:
            self[way_idx].insert(0, way_piece[1])
            self.__extremities[way_piece[1]] = way_idx
            self.__extremities.pop(way_piece[0])
        elif self[way_idx][0] == way_piece[1]:
            self[way_idx].insert(0, way_piece[0])
            self.__extremities[way_piece[0]] = way_idx
            self.__extremities.pop(way_piece[1])
        elif self[way_idx][-1] == way_piece[0]:
            self[way_idx].append(way_piece[1])
            self.__extremities[way_piece[1]] = way_idx
            self.__extremities.pop(way_piece[0])
        elif self[way_idx][-1] == way_piece[1]:
            self[way_idx].append(way_piece[0])
            self.__extremities[way_piece[0]] = way_idx
            self.__extremities.pop(way_piece[1])

class Ways(object):
    """Handles table ways that are made of adjacent edges"""

    def __init__(self, graph, output_dir, threshold, progress=Progress(), recompute=True):
        """Create table ways"""

        self.__output_dir = output_dir
        self.__conn = graph.conn

        # we create pieces of growing length until edges are exhausted

        # select the min angle at vertex for unused angles and create
        # a link between edges
        # tag the used angles
        # do that until all angles are used
        cur = TrCursor(self.__conn.cursor())

        cur.execute("SELECT COUNT(1) FROM ways")
        [count] = cur.fetchone()
        if not recompute and count > 0:
            return


        cur.execute("UPDATE $edges SET WAY = NULL")
        cur.execute("DELETE FROM streets_ways")
        cur.execute("DELETE FROM ways_vertices")
        cur.execute("DELETE FROM ways_ways")
        cur.execute("DELETE FROM ways")
        self.__conn.commit()

        progress.setText("Coupling edges with minimum angle below %.0f"%(threshold))
        ways = self.__minimal_angle(threshold, progress)

        way_id = 0
        for way in ways.values():
            way_id += 1
            cur.execute("INSERT INTO ways(OGC_FID, GEOMETRY, NB_EDGES) "
                "SELECT "+str(way_id)+", CastToMulti(LineMerge(Collect(GEOMETRY))),"+str(len(way))+" "
                "FROM $edges "
                "WHERE OGC_FID IN ("+
                ','.join([str(edge_id) for edge_id in way])+")")

            cur.execute("UPDATE $edges SET WAY = "+str(way_id)+" "
                "WHERE OGC_FID IN ("+
                ','.join([str(edge_id) for edge_id in way])+")")

        # add edges that are simple
        simple_ways = []
        cur.execute("SELECT OGC_FID FROM $edges WHERE WAY IS NULL")
        for [ogc_fid] in cur.fetchall():
            way_id += 1
            simple_ways.append((way_id, ogc_fid))

        log_info("Found "+str(len(simple_ways))+" simple ways")
        log_info("Found a total of "+str(way_id)+" ways")

        cur.executemany("""INSERT INTO ways(OGC_FID, GEOMETRY, NB_EDGES)
            SELECT ?, CastToMulti(e.GEOMETRY), 1
            FROM $edges AS e
            WHERE e.OGC_FID = ?""", simple_ways)
        cur.executemany("UPDATE $edges SET WAY = ? "
            "WHERE OGC_FID = ?", simple_ways)

        # update additional info in tables
        progress.setText("Fill ways_vertices")
        cur.execute("""
                INSERT INTO ways_vertices(WAY, VTX)
                SELECT DISTINCT WAY, START_VTX FROM $edges
                UNION
                SELECT DISTINCT WAY, END_VTX FROM $edges
                """)

        progress.setText("Compute connections between ways")
        cur.execute("""INSERT INTO ways_ways(WAY1, WAY2)
                SELECT DISTINCT wv1.WAY, wv2.WAY
                FROM ways_vertices AS wv1, ways_vertices AS wv2
                WHERE wv1.VTX = wv2.VTX
                AND wv1.OGC_FID != wv2.OGC_FID
                """)

        progress.setText("Compute ways degree")
        cur.execute("""UPDATE ways
                SET
                DEGREE = (SELECT COUNT(1)
                        FROM ways_ways
                        WHERE ways.OGC_FID = ways_ways.WAY1),
                LENGTH = GLength(GEOMETRY) """)

        progress.setText("Compute number of intersected edges")
        cur.execute("""UPDATE ways
                SET
                CONNECTIVITY =
                (
                    SELECT COUNT(1)
                    FROM (SELECT $edges.OGC_FID
                          FROM $edges, ways_vertices
                          WHERE ways_vertices.WAY = ways.OGC_FID
                          AND $edges.WAY != ways.OGC_FID
                          AND (ways_vertices.VTX = $edges.START_VTX
                               OR ways_vertices.VTX = $edges.END_VTX))
                )""")



        progress.setText("Compute SPACING and NB_VERTICES")
        cur.execute("""UPDATE ways
                SET SPACING = LENGTH/CONNECTIVITY
                WHERE CONNECTIVITY > 0""")



        # loops first
        cur.execute("""UPDATE ways
                SET NB_VERTICES = ( SELECT COUNT(1)
                    FROM (SELECT DISTINCT VTX FROM ways_vertices
                          WHERE ways_vertices.WAY = ways.OGC_FID)
                )""")

        self.__conn.commit()


    def __minimal_angle(self, threshold, progress=Progress()):
        """Build ways by assembling edges having the min angle
        if angle is below threshold"""
        cur = TrCursor(self.__conn.cursor())
        cur.execute("UPDATE angles SET USED = 0")
        way_pieces = []
        steps = 0
        while True:
            steps += 1
            progress.setText("   Step "+str(steps))
            progress.setText("      select min angles")
            cur.execute(
                "SELECT VTX_ID, EDGE1_ID, EDGE2_ID, MIN(ANGLE) AS ANGLE "
                "FROM angles "
                "WHERE ANGLE < "+str(threshold)+" "
                "AND NOT USED GROUP BY VTX_ID")
            used_ids = []
            for [vtx_id, edge1_id, edge2_id, angle] in cur.fetchall():
                used_ids.append((vtx_id, edge1_id, edge2_id,
                                         edge1_id, edge2_id))
                way_pieces.append((edge1_id, edge2_id))
            progress.setText("      update "+
                    str(len(used_ids))+" used angles")
            cur.executemany("UPDATE angles SET USED = 1 "
                "WHERE VTX_ID = ? "
                "AND (EDGE1_ID IN (?,?) OR EDGE2_ID IN (?,?)) ", used_ids)
            cur.execute("SELECT COUNT(1) FROM angles "
                    "WHERE ANGLE < "+str(threshold)+" AND NOT USED")
            if not cur.fetchone()[0]:
                break

        log_info("Finished in "+str(steps)+" steps")

        cur.execute("UPDATE angles SET USED = 0")
        self.__conn.commit()

        progress.setText("Merging "+str(len(way_pieces))+" way pieces")
        log_info("Merging "+str(len(way_pieces))+" way pieces")
        return  WayMerger(way_pieces, progress)

    def compute_structurality(self, nb_of_classes, progress=Progress()):
        progress.setText("Compute structurality")

        way_way = self.way_way()
        element_length = self.way_length()
        [topo_radius_and_struct, unconnected_ways] = compute_structurality(way_way, element_length, nb_of_classes, self.__output_dir, 'ways_', progress)

        add_attribute(self.__conn, 'ways', 'DEGREE', 'integer')
        add_attribute(self.__conn, 'ways', 'RTOPO', 'real')
        add_attribute(self.__conn, 'ways', 'CLOSENESS', 'real')
        add_attribute(self.__conn, 'ways', 'STRUCT', 'real')

        cur = TrCursor(self.__conn.cursor())
        cur.executemany("DELETE FROM ways WHERE OGC_FID = ?",
                [(ogc_fid,) for ogc_fid in unconnected_ways])
        cur.executemany("UPDATE ways SET DEGREE = ?, RTOPO = ?, CLOSENESS = ?, STRUCT = ? WHERE OGC_FID = ?",
                [(len(way_way[i]), r, c, s, i) for i, (r, c, s) in topo_radius_and_struct.iteritems()])
        self.__conn.commit()

        add_att_div(self.__conn, 'ways', 'SOL', 'STRUCT', 'LENGTH')
        add_att_div(self.__conn, 'ways', 'ROS', 'RTOPO', 'STRUCT')

        add_classification(self.__conn, 'ways', 'STRUCT', nb_of_classes)
        add_classification(self.__conn, 'ways', 'SOL', nb_of_classes)
        add_classification(self.__conn, 'ways', 'ROS', nb_of_classes)

        add_classification(self.__conn, 'ways', 'RTOPO', nb_of_classes)
        add_classification(self.__conn, 'ways', 'LENGTH', nb_of_classes)
        add_classification(self.__conn, 'ways', 'DEGREE', nb_of_classes)

        add_classification(self.__conn, 'ways', 'CLOSENESS', nb_of_classes)

        add_att_dif(self.__conn, 'ways', 'DIFF_CL_STRUCT_RTOPO', 'CL_STRUCT', 'CL_RTOPO')



    def compute_inclusion(self, nb_of_classes, progress=Progress()):
        """Inclusion is the sum of structuralities of connected ways"""
        add_attribute(self.__conn, 'ways', 'STRUCT_POT', 'integer')
        progress.setText("Computing inclusions")
        cur = TrCursor(self.__conn.cursor())
        cur.execute("""UPDATE ways
            SET STRUCT_POT =
            (
                SELECT SUM(STRUCT) FROM ways AS w, ways_ways AS ww
                WHERE w.OGC_FID = ww.WAY2
                AND ww.WAY1 = ways.OGC_FID
            )""")
        self.__conn.commit()

        add_classification(self.__conn, 'ways', 'STRUCT_POT', nb_of_classes)



    def compute_orthogonality(self, nb_of_classes, progress=Progress()):
        """Compute the sum of min sinuses between a way and intersecting edges"""
        progress.setText("Computing orthogonality")

        add_attribute(self.__conn, 'ways', 'ORTHOGONALITY', 'real')
        cur = TrCursor(self.__conn.cursor())

        cur.execute("SELECT COUNT(1) FROM ways")
        [nb_of_ways] = cur.fetchone()

        update_angles = []
        cur.execute("SELECT OGC_FID FROM ways ORDER BY OGC_FID")
        for [way_id] in cur.fetchall():
            progress.setPercentage(int((100.*way_id)/nb_of_ways))

            cur.execute("SELECT VTX FROM ways_vertices WHERE WAY = "+str(way_id))
            way_vertices = [vtx for [vtx] in cur.fetchall()]

            cur.execute("SELECT OGC_FID FROM $edges WHERE WAY = "+str(way_id))
            way_edges = [ogc_fid for [ogc_fid] in cur.fetchall()]

            sum_sinus = 0
            for vtx in way_vertices:
                cur.execute("SELECT ANGLE, EDGE1_ID, EDGE2_ID "
                    "FROM angles WHERE VTX_ID="+str(vtx))
                angle_from = {}
                for [angle, edge1_id, edge2_id] in cur.fetchall():
                    if edge1_id in way_edges and edge2_id not in way_edges:
                        if edge1_id not in angle_from:
                            angle_from[edge1_id] = []
                        angle_from[edge1_id] += [(edge2_id, angle)]
                    elif edge2_id in way_edges and edge1_id not in way_edges:
                        if edge2_id not in angle_from:
                            angle_from[edge2_id] = []
                        angle_from[edge2_id] += [(edge1_id, angle)]

                #assert len(angle_from) <= 2
                # the previous assertion will fail wrongly
                # when there is a loop in a way
                if len(angle_from) >= 1:
                    l = angle_from.values()
                    for a in l:
                        a.sort()
                    # for loops we have a duplicated edge angle, take the min
                    for a in l:
                        for i in reversed(range(1, len(a))):
                            if a[i][0] == a[i-1][0]:
                                a.pop(i)
                    if max([len(a) for a in l]) != min([len(a) for a in l]):
                        raise Exception("Logic error for way:"+str(way_id)+
                                " vtx:"+str(vtx)+" and edge:"+str(angle_from))

                    for i in range(len(l[0])):
                        sum_sinus += sin(min([l[j][i][1] for j in range(len(l))])*pi/180)


            update_angles.append((sum_sinus, way_id))

        cur.executemany("UPDATE ways SET ORTHOGONALITY = ?/CONNECTIVITY WHERE OGC_FID = ?", update_angles)
        self.__conn.commit()

        add_classification(self.__conn, 'ways', 'ORTHOGONALITY', nb_of_classes)


        add_attribute(self.__conn, 'ways', 'ROO', 'real')

        cur.execute("""UPDATE ways SET ROO = RTOPO/ORTHOGONALITY""")
        self.__conn.commit()

        add_classification(self.__conn, 'ways', 'ROO', nb_of_classes)


        # get way vertices and edges

    def way_way(self):
        cur = TrCursor(self.__conn.cursor())
        cur.execute("""SELECT DISTINCT w1.WAY, w2.WAY
                FROM ways_vertices AS w1, ways_vertices AS w2
                WHERE  w1.VTX = w2.VTX """)
        way_way = {}
        for [way1, way2] in cur.fetchall():
            if not way1 in way_way:
                way_way[way1] = set()
            way_way[way1].add(way2)
        return way_way

    def way_length(self):
        cur = TrCursor(self.__conn.cursor())
        cur.execute("SELECT OGC_FID, LENGTH FROM ways")
        way_length = {}
        for [ogc_fid, length] in cur.fetchall():
            way_length[ogc_fid] = length
        return way_length

    def compute_use(self, nb_of_classes, progress=Progress()):
        """Add attribute USE and USE_CLASS to table ways"""
        way_way = self.way_way()
        way_length = self.way_length()
        use = compute_use(way_way, way_length, nb_of_classes, progress)
        add_attribute(self.__conn, 'ways', 'USE', 'integer')
        add_attribute(self.__conn, 'ways', 'USE_MLT', 'integer')
        add_attribute(self.__conn, 'ways', 'USE_MLT_MOY', 'real')
        add_attribute(self.__conn, 'ways', 'USE_LGT', 'integer')
        #calcul de use
        update_use = [(u, um, umm, ul, i) for i, (u, um, umm, ul) in use.iteritems()]
        cur = TrCursor(self.__conn.cursor())
        cur.executemany("UPDATE ways SET USE = ?, USE_MLT = ?, USE_MLT_MOY = ?, USE_LGT = ? WHERE OGC_FID = ?", update_use)
        self.__conn.commit()

        add_classification(self.__conn, 'ways', 'USE', nb_of_classes)
        add_classification(self.__conn, 'ways', 'USE_MLT', nb_of_classes)
        add_classification(self.__conn, 'ways', 'USE_MLT_MOY', nb_of_classes)
        add_classification(self.__conn, 'ways', 'USE_LGT', nb_of_classes)


    def compute_betweenness(self, nb_of_classes, progress=Progress()):
        progress.setText("Compute betweenness")

        #networkx = lib for networks
        try:
            import networkx as nx
        except Exception, e:
            log_error("cannot compute betweenness because networkx is not available")
            return

        #-----------------MATRICES-----------------#

        brut_adjacency = np.loadtxt(path.join(self.__output_dir, "ways_adjacency.txt"), delimiter=',')
        brut_dtopo = np.loadtxt(path.join(self.__output_dir, "ways_dtopo.txt"), delimiter=',')

        #list of rows to remove
        removed = []
        for row in range(len(brut_adjacency)):
            if brut_adjacency[row][0] == -1:
                removed.append(row)

        #removing the lines
        adjacency = np.delete(brut_adjacency,removed,0)
        dtopo = np.delete(brut_dtopo,removed,0)

        #removing the columns
        adjacency = np.delete(adjacency,removed,1)
        dtopo = np.delete(dtopo,removed,1)

        #-----------------GRAPH-----------------#

        gr_adjacency = nx.Graph(adjacency)

        #-----------------CALCULATION-----------------#

        #calculation of betweenness (vector)
        betweenness = nx.betweenness_centrality(gr_adjacency)
        #closeness = nx.closeness_centrality(gr_adjacency)

        #btwstream = open(path.join(self.__output_dir, "ways_betweenness.txt"), 'w')
        #for k,v in betweenness.items():
        #    btwstream.write( ', '.join((str(k), str(v), str(closeness[k]))) + '\n')
        #btwstream.close()

        add_attribute(self.__conn, 'ways', 'BETWEENNESS', 'real')
        update_btw = []
        r = 0
        for row in range(len(brut_adjacency)):
            if brut_adjacency[row][0] == -1:
                update_btw.append(('0.0', row))
            else:
                update_btw.append((betweenness[r], row))
                r = r + 1
        cur = TrCursor(self.__conn.cursor())
        cur.executemany("UPDATE ways SET BETWEENNESS = ? WHERE OGC_FID = ?", update_btw)
        self.__conn.commit()

        add_classification(self.__conn, 'ways', 'BETWEENNESS', nb_of_classes)

        #np.savetxt(path.join(self.__output_dir, "ways_betweenness.txt"), btw, delimiter=',')
