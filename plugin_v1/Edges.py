# -*- coding: utf-8 -*-

"""
***************************************************************************
    Streets.py
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

from math import sin, pi
from Terminology import TrCursor
from Indicators import *

class Edges(object):
    def __init__(self, graph, output_dir, progress=Progress(), recompute=True):
        """Create table edges"""
        self.__output_dir = output_dir
        self.__conn = graph.conn

        cur = TrCursor(self.__conn.cursor())

        cur.execute("SELECT COUNT(1) FROM edges_vertices")
        [count] = cur.fetchone()
        if not recompute and count > 0:
            return

        cur.execute("DELETE FROM edges_vertices")
        cur.execute("DELETE FROM edges_edges")

        progress.setText("Fill edges_vertices")
        cur.execute("""
            INSERT INTO edges_vertices(EDGE, VTX)
            SELECT DISTINCT OGC_FID, START_VTX FROM $edges
            UNION
            SELECT DISTINCT OGC_FID, END_VTX FROM $edges
            """)

        progress.setText("Compute connections between edges")
        cur.execute("""
            INSERT INTO edges_edges(EDGE1, EDGE2)
            SELECT DISTINCT sv1.EDGE, sv2.EDGE
            FROM edges_vertices AS sv1, edges_vertices AS sv2
            WHERE sv1.VTX = sv2.VTX
            AND sv1.OGC_FID != sv2.OGC_FID
            """)

        progress.setText("Compute number of intersected edges")
        cur.execute("""UPDATE $edges
                SET
                CONNECTIVITY =
                (
                    SELECT COUNT(1)
                    FROM (SELECT e.OGC_FID
                          FROM $edges AS e, edges_vertices
                          WHERE edges_vertices.EDGE = $edges.OGC_FID
                          AND $edges.OGC_FID != e.OGC_FID
                          AND (e.WAY IS NULL OR $edges.WAY != e.WAY)
                          AND (edges_vertices.VTX = e.START_VTX
                               OR edges_vertices.VTX = e.END_VTX))
                )""")

        progress.setText("Compute SPACING")
        cur.execute("""UPDATE $edges
                SET SPACING = CONNECTIVITY/LENGTH
                WHERE LENGTH > 0""")

        self.__conn.commit()

    def edge_edge(self):
        cur = TrCursor(self.__conn.cursor())
        cur.execute("""SELECT DISTINCT s1.EDGE, s2.EDGE
                FROM edges_vertices AS s1, edges_vertices AS s2
                WHERE  s1.VTX = s2.VTX """)
        edge_edge = {}
        for [edge1, edge2] in cur.fetchall():
            if not edge1 in edge_edge:
                edge_edge[edge1] = set()
            edge_edge[edge1].add(edge2)
        return edge_edge

    def edge_length(self):
        cur = TrCursor(self.__conn.cursor())
        cur.execute("SELECT OGC_FID, LENGTH FROM $edges")
        edge_length = {}
        for [ogc_fid, length] in cur.fetchall():
            edge_length[ogc_fid] = length
        return edge_length

    def compute_structurality(self, nb_of_classes, progress=Progress()):
        progress.setText("Compute structurality")

        edge_edge = self.edge_edge()
        element_length = self.edge_length()
        [topo_radius_and_struct, unconnected_edges] = compute_structurality(edge_edge, element_length, nb_of_classes, self.__output_dir, 'edges_', progress)

        add_attribute(self.__conn, '$edges', 'DEGREE', 'integer')
        add_attribute(self.__conn, '$edges', 'RTOPO', 'real')
        add_attribute(self.__conn, '$edges', 'CLOSENESS', 'real')
        add_attribute(self.__conn, '$edges', 'STRUCT', 'real')

        cur = TrCursor(self.__conn.cursor())
        cur.executemany("DELETE FROM $edges WHERE OGC_FID = ?",
                [(ogc_fid,) for ogc_fid in unconnected_edges])
        cur.executemany("UPDATE $edges SET DEGREE = ?, RTOPO = ?, CLOSENESS = ?, STRUCT = ? WHERE OGC_FID = ?",
                [(len(edge_edge[i]), r, c, s, i) for i, (r, c, s) in topo_radius_and_struct.iteritems()])
        self.__conn.commit()

        add_att_div(self.__conn, '$edges', 'SOL', 'STRUCT', 'LENGTH')
        add_att_div(self.__conn, '$edges', 'ROS', 'RTOPO', 'STRUCT')

        add_classification(self.__conn, '$edges', 'STRUCT', nb_of_classes)
        add_classification(self.__conn, '$edges', 'SOL', nb_of_classes)
        add_classification(self.__conn, '$edges', 'ROS', nb_of_classes)

        add_classification(self.__conn, '$edges', 'RTOPO', nb_of_classes)
        add_classification(self.__conn, '$edges', 'LENGTH', nb_of_classes)
        add_classification(self.__conn, '$edges', 'DEGREE', nb_of_classes)

        add_classification(self.__conn, '$edges', 'CLOSENESS', nb_of_classes)

        add_att_dif(self.__conn, '$edges', 'DIFF_CL_STRUCT_RTOPO', 'CL_STRUCT', 'CL_RTOPO')


    def compute_inclusion(self, nb_of_classes, progress=Progress()):
        """Inclusion is the sum of structuralities of connected edges"""
        add_attribute(self.__conn, '$edges', 'STRUCT_POT', 'integer')
        if progress:
            progress.setText("Computing structural potential")
        cur = TrCursor(self.__conn.cursor())
        cur.execute("""UPDATE $edges
            SET STRUCT_POT =
            (
                SELECT SUM(STRUCT) FROM $edges AS w, edges_edges AS ww
                WHERE w.OGC_FID = ww.EDGE2
                AND ww.EDGE1 = $edges.OGC_FID
            )""")
        self.__conn.commit()

    def compute_orthogonality(self, nb_of_classes, progress=Progress()):
        """Compute the sum of min sinuses between a edge and intersecting edges"""
        progress.setText("Computing orthogonality")

        add_attribute(self.__conn, '$edges', 'ORTHOGONALITY', 'real')
        cur = TrCursor(self.__conn.cursor())

        cur.execute("SELECT COUNT(1) FROM $edges")
        [nb_of_edges] = cur.fetchone()

        update_angles = []
        cur.execute("SELECT OGC_FID FROM $edges ORDER BY OGC_FID")
        for [edge_id] in cur.fetchall():
            progress.setPercentage(int((100.*edge_id)/nb_of_edges))

            cur.execute("SELECT VTX FROM edges_vertices WHERE EDGE = "+str(edge_id))
            edge_vertices = [vtx for [vtx] in cur.fetchall()]

            cur.execute("SELECT OGC_FID FROM $edges WHERE OGC_FID = "+str(edge_id))
            edge_edges = [ogc_fid for [ogc_fid] in cur.fetchall()]

            sum_sinus = 0
            for vtx in edge_vertices:
                cur.execute("SELECT ANGLE, EDGE1_ID, EDGE2_ID "
                    "FROM angles WHERE VTX_ID="+str(vtx))
                angle_from = {}
                for [angle, edge1_id, edge2_id] in cur.fetchall():
                    if edge1_id in edge_edges and edge2_id not in edge_edges:
                        if edge1_id not in angle_from:
                            angle_from[edge1_id] = []
                        angle_from[edge1_id] += [(edge2_id, angle)]
                    elif edge2_id in edge_edges and edge1_id not in edge_edges:
                        if edge2_id not in angle_from:
                            angle_from[edge2_id] = []
                        angle_from[edge2_id] += [(edge1_id, angle)]

                #assert len(angle_from) <= 2
                # the previous assertion will fail wrongly
                # when there is a loop in a edge
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
                        raise Exception("Logic error for edge:"+str(edge_id)+
                                " vtx:"+str(vtx)+" and edge:"+str(angle_from))

                    for i in range(len(l[0])):
                        sum_sinus += sin(min([l[j][i][1] for j in range(len(l))])*pi/180)


            update_angles.append((sum_sinus, edge_id))

        cur.executemany("UPDATE $edges SET ORTHOGONALITY = ?/CONNECTIVITY WHERE OGC_FID = ?", update_angles)
        self.__conn.commit()
        add_classification(self.__conn, '$edges', 'ORTHOGONALITY', nb_of_classes)


    def compute_use(self, nb_of_classes, progress=Progress()):
        """Add attribute USE and USE_CLASS to table edges"""
        edge_edge = self.edge_edge()
        edge_length = self.edge_length()
        use = compute_use(edge_edge, edge_length, nb_of_classes, progress)
        add_attribute(self.__conn, '$edges', 'USE', 'integer')
        add_attribute(self.__conn, '$edges', 'USE_MLT', 'integer')
        add_attribute(self.__conn, '$edges', 'USE_MLT_MOY', 'real')
        add_attribute(self.__conn, '$edges', 'USE_LGT', 'integer')
        #calcul de use
        update_use = [(u, um, umm, ul, i) for i, (u, um, umm, ul) in use.iteritems()]
        cur = TrCursor(self.__conn.cursor())
        cur.executemany("UPDATE $edges SET USE = ?, USE_MLT = ?, USE_MLT_MOY = ?, USE_LGT = ? WHERE OGC_FID = ?", update_use)
        self.__conn.commit()

        add_classification(self.__conn, '$edges', 'USE', nb_of_classes)
        add_classification(self.__conn, '$edges', 'USE_MLT', nb_of_classes)
        add_classification(self.__conn, '$edges', 'USE_MLT_MOY', nb_of_classes)
        add_classification(self.__conn, '$edges', 'USE_LGT', nb_of_classes)

