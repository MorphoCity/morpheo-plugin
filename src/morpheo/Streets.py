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


class Streets(object):
    def __init__(self, graph, output_dir, progress=Progress(), recompute=True):
        """Create table streets"""
        self.__output_dir = output_dir
        self.__conn = graph.conn

        cur = TrCursor(self.__conn.cursor())

        cur.execute("SELECT COUNT(1) FROM streets")
        [count] = cur.fetchone()
        if not recompute and count > 0:
            return

        cur.execute("UPDATE $edges SET STREET = NULL")
        cur.execute("DELETE FROM streets_vertices")
        cur.execute("DELETE FROM streets_streets")
        cur.execute("DELETE FROM streets")

        # add streets with no name
        cur.execute("""
            INSERT INTO streets(GEOMETRY, NB_EDGES)
            SELECT CastToMulti(GEOMETRY), 1
            FROM $edges
            WHERE NAME IS NULL""")

        # update edges with no name
        cur.execute("""
            UPDATE $edges
            SET STREET = (SELECT OGC_FID FROM streets
                WHERE NAME IS NULL
                AND Equals(streets.GEOMETRY, $edges.GEOMETRY)
                AND $edges.ROWID IN (
                  SELECT ROWID FROM SpatialIndex
                  WHERE f_table_name='$edges' AND search_frame=streets.GEOMETRY)
            )
            """)

        cur.execute("""
            INSERT INTO streets(GEOMETRY, NB_EDGES, NAME)
            SELECT CastToMulti(LineMerge(Collect(GEOMETRY))), COUNT(1), NAME
            FROM $edges
            WHERE NAME IS NOT NULL
            GROUP BY NAME""")

        # update edges
        cur.execute("""
            UPDATE $edges
            SET STREET = (SELECT OGC_FID FROM streets WHERE streets.NAME = $edges.NAME)
            WHERE STREET IS NULL
            """)

        # compute street length
        cur.execute("""
            UPDATE streets
            SET LENGTH = GLength(GEOMETRY)
            """)

        progress.setText("Fill streets_vertices")
        cur.execute("""
            INSERT INTO streets_vertices(STREET, VTX)
            SELECT DISTINCT STREET, START_VTX FROM $edges
            UNION
            SELECT DISTINCT STREET, END_VTX FROM $edges
            """)

        progress.setText("Compute connections between streets")
        cur.execute("""
            INSERT INTO streets_streets(STREET1, STREET2)
            SELECT DISTINCT sv1.STREET, sv2.STREET
            FROM streets_vertices AS sv1, streets_vertices AS sv2
            WHERE sv1.VTX = sv2.VTX
            AND sv1.OGC_FID != sv2.OGC_FID
            """)

        progress.setText("Compute number of intersected edges")
        cur.execute("""UPDATE streets
                SET
                CONNECTIVITY =
                (
                    SELECT COUNT(1)
                    FROM (SELECT $edges.OGC_FID
                          FROM $edges, streets_vertices
                          WHERE streets_vertices.STREET = streets.OGC_FID
                          AND $edges.STREET != streets.OGC_FID
                          AND (streets_vertices.VTX = $edges.START_VTX
                               OR streets_vertices.VTX = $edges.END_VTX))
                )""")

        progress.setText("Compute SPACING and NB_VERTICES")
        cur.execute("""UPDATE streets
                SET SPACING = CONNECTIVITY/LENGTH
                WHERE LENGTH > 0""")

        cur.execute("""UPDATE streets
                SET NB_VERTICES = ( SELECT COUNT(1)
                    FROM (SELECT DISTINCT VTX FROM streets_vertices
                          WHERE streets_vertices.STREET = streets.OGC_FID)
                )""")

        self.__conn.commit()

    def street_street(self):
        cur = TrCursor(self.__conn.cursor())
        cur.execute("""SELECT DISTINCT s1.STREET, s2.STREET
                FROM streets_vertices AS s1, streets_vertices AS s2
                WHERE  s1.VTX = s2.VTX """)
        street_street = {}
        for [street1, street2] in cur.fetchall():
            if not street1 in street_street:
                street_street[street1] = set()
            street_street[street1].add(street2)
        return street_street

    def street_length(self):
        cur = TrCursor(self.__conn.cursor())
        cur.execute("SELECT OGC_FID, LENGTH FROM streets")
        street_length = {}
        for [ogc_fid, length] in cur.fetchall():
            street_length[ogc_fid] = length
        return street_length

    def compute_structurality(self, nb_of_classes, progress=Progress()):
        progress.setText("Compute structurality")

        street_street = self.street_street()
        element_length = self.street_length()
        [topo_radius_and_struct, unconnected_streets] = compute_structurality(street_street, element_length, nb_of_classes, self.__output_dir, 'streets_', progress)

        add_attribute(self.__conn, 'streets', 'DEGREE', 'integer')
        add_attribute(self.__conn, 'streets', 'RTOPO', 'real')
        add_attribute(self.__conn, 'streets', 'CLOSENESS', 'real')
        add_attribute(self.__conn, 'streets', 'STRUCT', 'real')

        cur = TrCursor(self.__conn.cursor())
        cur.executemany("DELETE FROM streets WHERE OGC_FID = ?",
                [(ogc_fid,) for ogc_fid in unconnected_streets])
        cur.executemany("UPDATE streets SET DEGREE = ?, RTOPO = ?, CLOSENESS = ?, STRUCT = ? WHERE OGC_FID = ?",
                [(len(street_street[i]), r, c, s, i) for i, (r, c, s) in topo_radius_and_struct.iteritems()])
        self.__conn.commit()

        add_att_div(self.__conn, 'streets', 'SOL', 'STRUCT', 'LENGTH')
        add_att_div(self.__conn, 'streets', 'ROS', 'RTOPO', 'STRUCT')

        add_classification(self.__conn, 'streets', 'STRUCT', nb_of_classes)
        add_classification(self.__conn, 'streets', 'SOL', nb_of_classes)
        add_classification(self.__conn, 'streets', 'ROS', nb_of_classes)

        add_classification(self.__conn, 'streets', 'RTOPO', nb_of_classes)
        add_classification(self.__conn, 'streets', 'LENGTH', nb_of_classes)
        add_classification(self.__conn, 'streets', 'DEGREE', nb_of_classes)

        add_classification(self.__conn, 'streets', 'CLOSENESS', nb_of_classes)

        add_att_dif(self.__conn, 'streets', 'DIFF_CL_STRUCT_RTOPO', 'CL_STRUCT', 'CL_RTOPO')


    def compute_inclusion(self, nb_of_classes, progress=Progress()):
        """Inclusion is the sum of structuralities of connected streets"""
        add_attribute(self.__conn, 'streets', 'STRUCT_POT', 'integer')
        if progress:
            progress.setText("Computing inclusions")
        cur = TrCursor(self.__conn.cursor())
        cur.execute("""UPDATE streets
            SET STRUCT_POT =
            (
                SELECT SUM(STRUCT) FROM streets AS w, streets_streets AS ww
                WHERE w.OGC_FID = ww.STREET2
                AND ww.STREET1 = streets.OGC_FID
            )""")
        self.__conn.commit()

    def compute_orthogonality(self, nb_of_classes, progress=Progress()):
        """Compute the sum of min sinuses between a street and intersecting edges"""
        progress.setText("Computing orthogonality")

        add_attribute(self.__conn, 'streets', 'ORTHOGONALITY', 'real')
        cur = TrCursor(self.__conn.cursor())

        cur.execute("SELECT COUNT(1) FROM streets")
        [nb_of_streets] = cur.fetchone()

        update_angles = []
        cur.execute("SELECT OGC_FID FROM streets ORDER BY OGC_FID")
        for [street_id] in cur.fetchall():
            progress.setPercentage(int((100.*street_id)/nb_of_streets))

            cur.execute("SELECT VTX FROM streets_vertices WHERE STREET = "+str(street_id))
            street_vertices = [vtx for [vtx] in cur.fetchall()]

            cur.execute("SELECT OGC_FID FROM $edges WHERE STREET = "+str(street_id))
            street_edges = [ogc_fid for [ogc_fid] in cur.fetchall()]

            sum_sinus = 0
            for vtx in street_vertices:
                cur.execute("SELECT ANGLE, EDGE1_ID, EDGE2_ID "
                    "FROM angles WHERE VTX_ID="+str(vtx))
                angle_from = {}
                for [angle, edge1_id, edge2_id] in cur.fetchall():
                    if edge1_id in street_edges and edge2_id not in street_edges:
                        if edge1_id not in angle_from:
                            angle_from[edge1_id] = []
                        angle_from[edge1_id] += [(edge2_id, angle)]
                    elif edge2_id in street_edges and edge1_id not in street_edges:
                        if edge2_id not in angle_from:
                            angle_from[edge2_id] = []
                        angle_from[edge2_id] += [(edge1_id, angle)]

                #assert len(angle_from) <= 2
                # the previous assertion will fail wrongly
                # when there is a loop in a street
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
                        raise Exception("Logic error for street:"+str(street_id)+
                                " vtx:"+str(vtx)+" and edge:"+str(angle_from))

                    for i in range(len(l[0])):
                        sum_sinus += sin(min([l[j][i][1] for j in range(len(l))])*pi/180)


            update_angles.append((sum_sinus, street_id))

        cur.executemany("UPDATE streets SET ORTHOGONALITY = ?/CONNECTIVITY WHERE OGC_FID = ?", update_angles)
        self.__conn.commit()
        add_classification(self.__conn, 'streets', 'ORTHOGONALITY', nb_of_classes)


    def compute_use(self, nb_of_classes, progress=Progress()):
        """Add attribute USE and USE_CLASS to table streets"""
        street_street = self.street_street()
        street_length = self.street_length()
        use = compute_use(street_street, street_length, nb_of_classes, progress)
        add_attribute(self.__conn, 'streets', 'USE', 'integer')
        add_attribute(self.__conn, 'streets', 'USE_MLT', 'integer')
        add_attribute(self.__conn, 'streets', 'USE_MLT_MOY', 'real')
        add_attribute(self.__conn, 'streets', 'USE_LGT', 'integer')
        #calcul de use
        update_use = [(u, um, umm, ul, i) for i, (u, um, umm, ul) in use.iteritems()]
        cur = TrCursor(self.__conn.cursor())
        cur.executemany("UPDATE streets SET USE = ?, USE_MLT = ?, USE_MLT_MOY = ?, USE_LGT = ? WHERE OGC_FID = ?", update_use)
        self.__conn.commit()

        add_classification(self.__conn, 'streets', 'USE', nb_of_classes)
        add_classification(self.__conn, 'streets', 'USE_MLT', nb_of_classes)
        add_classification(self.__conn, 'streets', 'USE_MLT_MOY', nb_of_classes)
        add_classification(self.__conn, 'streets', 'USE_LGT', nb_of_classes)

