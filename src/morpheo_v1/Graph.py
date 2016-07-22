# -*- coding: utf-8 -*-

"""
***************************************************************************
    Graph.py
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
import string
import os
from Terminology import tr, TrCursor

def log_info(info):
    "logs and print on console"
    print "info: ", info
    ProcessingLog.addToLog(ProcessingLog.LOG_INFO, info)

class Graph(object):
    """Handles the graph construction"""

    DEBUG = False

    def __init__(self, conn, brutArcsTablename=None,
            name_field=None, progress=None, minArcLength=1, cleanupRadius=0):

        self.conn = conn

        if not brutArcsTablename:
            return

        self.brutArcsTablename = brutArcsTablename.lower()
        if cleanupRadius:
            self.cleanup(cleanupRadius, minArcLength, name_field, progress) 

        self.conn.commit()

        with open(os.path.join(os.path.dirname(__file__),
            'create_graph.sql'), "r") as sqlfile:

            cur = TrCursor(self.conn.cursor(), {'origin_table':self.brutArcsTablename})
            statements = sqlfile.read().split(';')
            for i, statement in enumerate(statements):
                progress.setPercentage(int(100*float(i)/len(statements)))
                if statement:
                    if self.DEBUG:
                        print statement
                    cur.execute(statement)
                    rec = cur.fetchone()
                    if rec and len(rec) == 2 and type(rec[0]) is unicode \
                            and type(rec[1]) is unicode:
                        log_info(rec[0]+" "+rec[1])

            if name_field:
                cur.execute("UPDATE $edges "
                        "SET NAME = (SELECT "+name_field+" "
                                "FROM "+self.brutArcsTablename+" AS b "
                                "WHERE $edges.OGC_FID = b.OGC_FID)")
                #cur.execute("INSERT INTO STREETS")

            self.conn.commit()

    def cleanup(self, epsilon, minArcLength, name_field='', progress=None):
        cur = TrCursor(self.conn.cursor(), {
                'origin_table':self.brutArcsTablename, 
                'epsilon':epsilon})

        # remove unconnected features
        cur.execute("""DELETE FROM $origin_table
            WHERE NOT (
                SELECT COUNT(1) FROM $origin_table AS o
                WHERE Intersects( o.GEOMETRY, $origin_table.GEOMETRY )
                AND $origin_table.OGC_FID != o.OGC_FID
                AND 
                o.ROWID IN (
                    SELECT ROWID FROM SpatialIndex 
                    WHERE f_table_name='$origin_table' AND search_frame=$origin_table.GEOMETRY)
                )
                """)

        # snap geometries to neighbors
        cur.execute("""UPDATE $origin_table
            SET GEOMETRY = Snap($origin_table.GEOMETRY, 
                (
                SELECT Collect(o.GEOMETRY) FROM $origin_table AS o 
                WHERE o.ROWID IN (
                      SELECT ROWID FROM SpatialIndex 
                      WHERE f_table_name='$origin_table' AND search_frame=Buffer($origin_table.GEOMETRY, $epsilon))
                AND o.OGC_FID != $origin_table.OGC_FID
                )
                , $epsilon)
            """)

        # find overlapping lines
        self.create_indexed_line_table('overlaping_lines', 'MULTI')
        cur.execute("""INSERT INTO overlaping_lines(GEOMETRY)
            SELECT CastToMulti(Intersection(w1.GEOMETRY, w2.GEOMETRY))
            FROM $origin_table AS w1, $origin_table AS w2
            WHERE w1.OGC_FID != w2.OGC_FID
            AND Intersects(w1.GEOMETRY, w2.GEOMETRY)
            AND  w1.ROWID IN (
                  SELECT ROWID FROM SpatialIndex 
                  WHERE f_table_name='$origin_table' AND search_frame=w2.GEOMETRY)
            AND GeometryType(Intersection(w1.GEOMETRY, w2.GEOMETRY)) 
                IN ('LINESTRING', 'MULTILINESTRING', 'LINESTRING Z', 'MULTILINESTRING Z')
            """)


        # add intersections
        # we first locate crossing points
        cur.execute("""SELECT coord_dimension
                    FROM geometry_columns
                    WHERE f_table_name='$origin_table'""")
        [dim] = cur.fetchone()
        self.create_indexed_point_table('crossings', 'MULTI')
        print "Adding crossings, skipping bridge"
        cur.execute("""INSERT INTO crossings(GEOMETRY)
            SELECT CastToMulti(Intersection(w1.GEOMETRY, w2.GEOMETRY))
            FROM $origin_table AS w1, $origin_table AS w2
            WHERE w1.OGC_FID != w2.OGC_FID
            AND Intersects(w1.GEOMETRY, w2.GEOMETRY)
            AND  w1.ROWID IN (
                  SELECT ROWID FROM SpatialIndex 
                  WHERE f_table_name='$origin_table' AND search_frame=w2.GEOMETRY)
            AND GeometryType(Intersection(w1.GEOMETRY, w2.GEOMETRY))
                IN ('POINT', 'MULTIPOINT', 'POINT Z', 'MULTIPOINT Z')""" +  
           ("""AND ABS(0.5*(Z(StartPoint(w1.GEOMETRY))+Z(EndPoint(w1.GEOMETRY)))
                   -0.5*(Z(StartPoint(w1.GEOMETRY))+Z(EndPoint(w1.GEOMETRY)))) < 3""" if dim == 'XYZ' else ""))

        # add overlapping lines end point and lines end points
        cur.execute("""INSERT INTO crossings(GEOMETRY)
            SELECT DISTINCT CastToMulti(EndPoint(GEOMETRY)) FROM overlaping_lines
            UNION
            SELECT DISTINCT CastToMulti(StartPoint(GEOMETRY)) FROM overlaping_lines
            UNION
            SELECT DISTINCT CastToMulti(EndPoint(GEOMETRY)) FROM $origin_table
            UNION
            SELECT DISTINCT CastToMulti(StartPoint(GEOMETRY)) FROM $origin_table
            """)

        cur.execute("""SELECT max(NumGeometries(GEOMETRY)) FROM crossings""")
        [count_max] = cur.fetchone()
        if not count_max:
            count_max = 1
        cur.execute("CREATE TABLE counter(VALUE integer)")
        cur.executemany("INSERT INTO counter(VALUE) SELECT ?",[(c+1,) for c in range(count_max)] )

        self.create_indexed_point_table('crossing_points')
        cur.execute("""INSERT INTO crossing_points(GEOMETRY)
            SELECT DISTINCT GeometryN(crossings.GEOMETRY, VALUE)
            FROM crossings, counter
            WHERE counter.VALUE <= NumGeometries(crossings.GEOMETRY)
            """)

        self.create_indexed_line_table('split_lines')
        cur.execute("ALTER TABLE split_lines ADD COLUMN START_VTX integer REFERENCES crossing_points(OGC_FID)")
        cur.execute("ALTER TABLE split_lines ADD COLUMN END_VTX integer REFERENCES crossing_points(OGC_FID)")
        cur.execute("CREATE INDEX split_lines_start_vtx_idx ON split_lines(START_VTX)")
        cur.execute("CREATE INDEX split_lines_end_vtx_idx ON split_lines(END_VTX)")
        
        # since LinesCutAtNodes in not available in pyspatialite
        # we have to cut lines one segment at a time
        cur.execute("SELECT ROWID, OGC_FID FROM $origin_table ORDER BY OGC_FID")
        res = cur.fetchall()
        splits = []
        for [rowid, line_id] in res:
            if progress:
                progress.setPercentage(int(100*float(rowid)/len(res)))
            # get all points on line
            cur.execute("""
                SELECT Line_Locate_Point(o.GEOMETRY, v.GEOMETRY) AS LOCATION, v.OGC_FID
                FROM $origin_table AS o, crossing_points AS v
                WHERE PtDistWithin(o.GEOMETRY, v.GEOMETRY, 1e-2)
                AND o.OGC_FID = """+str(line_id)+"""
                AND v.ROWID IN (
                      SELECT ROWID FROM SpatialIndex 
                      WHERE f_table_name='crossing_points' AND search_frame=o.GEOMETRY)
                ORDER BY LOCATION;
                """)
            locations = cur.fetchall()

            for i in range(1,len(locations)):
                splits.append((locations[i-1][0], locations[i][0], 
                    locations[i-1][1], locations[i][1], line_id))

            # add segment to loop
            cur.execute("""SELECT COUNT(1) 
                FROM  $origin_table WHERE OGC_FID = """+str(line_id)+"""
                AND PtDistWithin(EndPoint(GEOMETRY), StartPoint(GEOMETRY), 1e-2)""")
            [isLoop] = cur.fetchone()
            if isLoop:
                splits.append((locations[-1][0], 1, locations[-1][1], locations[0][1], line_id))

        cur.executemany("""
            INSERT INTO split_lines(GEOMETRY, START_VTX, END_VTX)
            SELECT Line_Substring(o.GEOMETRY, ?, ?), ?, ?
            FROM $origin_table AS o
            WHERE o.OGC_FID = ?""", splits)

        # remove duplicated lines
        cur.execute("""SELECT l1.OGC_FID, l2.OGC_FID
            FROM split_lines AS l1, split_lines AS l2
            WHERE Equals(l1.GEOMETRY, l2.GEOMETRY)
            AND l1.OGC_FID < l2.OGC_FID
            AND l1.ROWID IN (
                      SELECT ROWID FROM SpatialIndex 
                      WHERE f_table_name='split_lines' AND search_frame=l2.GEOMETRY)
            ORDER BY l1.OGC_FID
            """)
        equivalent = []
        for [l1_id, l2_id] in cur.fetchall():
            found = False
            for eq in equivalent:
                if l1_id in eq:
                    eq.add(l2_id)
                    found = True
                if l2_id in eq:
                    eq.add(l1_id)
                    found = True
            if not found:
                equivalent.append(set([l1_id, l2_id]))
        # merge equivalent
        for i in range(len(equivalent)):
            for j in range(len(equivalent), i+1):
                if equivalent[i].intersection(equivalent[j]):
                    equivalent[i] = equivalent[i].union(equivalent[j])
                    equivalent[j] = set()

        deleted_dupes = []
        for eq in equivalent:
            if len(eq):
                for id_ in list(eq)[1:]:
                    deleted_dupes.append((id_,))
        cur.executemany("DELETE FROM split_lines WHERE OGC_FID = ?", deleted_dupes)
        print "Deleted ", len(deleted_dupes), " duplicates in split_lines"

        cur.execute("ALTER TABLE crossing_points ADD COLUMN DEGREE integer")
        cur.execute("""
            UPDATE crossing_points
            SET DEGREE = 
            (
                SELECT COUNT(1) 
                FROM split_lines
                WHERE split_lines.END_VTX = crossing_points.OGC_FID 
                OR split_lines.START_VTX = crossing_points.OGC_FID
            ) """)

        cur.execute("""
            UPDATE crossing_points
            SET DEGREE = crossing_points.DEGREE + -- add one to the count for each loops
            (
                SELECT COUNT(1) 
                FROM split_lines
                WHERE split_lines.END_VTX = crossing_points.OGC_FID 
                AND split_lines.START_VTX = crossing_points.OGC_FID
            )""")


        cur.execute("SELECT COUNT(1) FROM split_lines WHERE END_VTX IS NULL OR START_VTX IS NULL")
        [bug] = cur.fetchone()
        assert not bug

        # join lines that are simply touching 
        # since several segment can be joined, we need to do that in
        # python and not simply SQL
        merges = []
        cur.execute("SELECT OGC_FID FROM crossing_points WHERE DEGREE = 2")
        for [pid] in cur.fetchall():
            cur.execute("SELECT OGC_FID FROM split_lines WHERE "+str(pid)+\
                    " IN (END_VTX, START_VTX)")
            to_merge = [lid for [lid] in cur.fetchall()]
            assert len(to_merge) == 2
            for m in merges:
                if to_merge[0] in m or to_merge[1] in m: 
                    m.add(to_merge[0])
                    m.add(to_merge[1])
                    to_merge = []
                    break
            if len(to_merge):
                merges.append(set(to_merge))
        for i in range(len(merges)):
            for j in range(i+1, len(merges)):
                if merges[i].intersection(merges[j]):
                    merges[i] = merges[i].union(merges[j])
                    merges[j] = set()

        cur.execute("DELETE FROM crossing_points WHERE DEGREE = 2")
        
        for m in merges:
            if not m: continue
            cur.execute("""
                INSERT INTO split_lines(GEOMETRY)
                SELECT LineMerge(Collect(l.GEOMETRY))
                FROM split_lines AS l
                WHERE l.OGC_FID IN ("""+','.join([str(i) for i in m])+")")
            # if the line segment form a ring, there is no guaranty that
            # the merge endpoint is actually the one belonging to the graph
            # so we have to deal with that case
            cur.execute("SELECT MAX(OGC_FID), AsText(GEOMETRY) FROM split_lines")
            [lid, s] = cur.fetchone()
            cur.execute("""SELECT COUNT(1) 
                FROM split_lines WHERE OGC_FID = """+str(lid)+"""
                AND PtDistWithin(StartPoint(GEOMETRY), EndPoint(GEOMETRY), 1e-2)""")
            [isLoop] = cur.fetchone()
            if isLoop:
                cur.execute("""SELECT Line_Locate_Point(l.GEOMETRY, p.GEOMETRY) 
                    FROM split_lines AS l, crossing_points AS p
                    WHERE l.OGC_FID = """+str(lid)+"""
                    AND PtDistWithin(l.GEOMETRY, p.GEOMETRY, 1e-2)
                    """)
                alpha = cur.fetchone()
                print "alpha ", alpha
                if not alpha: # no point found, the loop is unconnected, remove it
                    cur.execute("DELETE FROM split_lines WHERE OGC_FID = "+str(lid))
                elif alpha[0] > 0 and alpha[0] < 1:
                    # get the tow segments and invert their order
                    cur.execute("""
                        SELECT AsText(Line_Substring(GEOMETRY, 0,"""+str(alpha[0])+""")), 
                               AsText(Line_Substring(GEOMETRY,"""+str(alpha[0])+""", 1)),
                               SRID(GEOMETRY)
                        FROM split_lines WHERE OGC_FID = """+str(lid))
                    [l1, l2, srid] = cur.fetchone()
                    linetype = l1.split('(')[0]
                    l1 = l1.split('(')[1].split(')')[0].split(',')
                    l2 = l2.split('(')[1].split(')')[0].split(',')
                    cur.execute("""
                        UPDATE split_lines SET GEOMETRY = GeomFromText('"""
                        +linetype+'('+','.join(l2)+','+','.join(l1[1:])+")', "+str(srid)+")"
                        +" WHERE OGC_FID = "+str(lid))


            # remove joined lines 
            cur.execute("""
                DELETE FROM split_lines
                WHERE OGC_FID IN ("""+','.join([str(i) for i in m])+")")


        # set end vtx for merged lines
        cur.execute("""
            UPDATE split_lines
            SET START_VTX =
            (
                SELECT v.OGC_FID FROM crossing_points AS v, split_lines AS l
                WHERE PtDistWithin(StartPoint(l.GEOMETRY), v.GEOMETRY, 1e-2)
                AND l.OGC_FID = split_lines.OGC_FID
                AND v.ROWID IN (
                      SELECT ROWID FROM SpatialIndex 
                      WHERE f_table_name='crossing_points' AND search_frame=l.GEOMETRY)
            ),
            END_VTX = 
            (
                SELECT v.OGC_FID FROM crossing_points AS v, split_lines AS l
                WHERE PtDistWithin(EndPoint(l.GEOMETRY), v.GEOMETRY, 1e-2)
                AND l.OGC_FID = split_lines.OGC_FID
                AND v.ROWID IN (
                      SELECT ROWID FROM SpatialIndex 
                      WHERE f_table_name='crossing_points' AND search_frame=l.GEOMETRY)
            )
            WHERE START_VTX IS NULL OR END_VTX IS NULL""")

        cur.execute("SELECT COUNT(1) FROM split_lines WHERE END_VTX IS NULL OR START_VTX IS NULL")
        [bug] = cur.fetchone()
        assert not bug

        # remove small edges and merge extremities at centroid
        cur.execute("SELECT MAX(OGC_FID) FROM crossing_points")
        [max_fid] = cur.fetchone()
        cur.execute("""SELECT OGC_FID, START_VTX, END_VTX 
            FROM split_lines
            WHERE GLength(GEOMETRY) < """+str(minArcLength))
        print "Removing arcs smaller than ", minArcLength
        for [ogc_fid, start_vtx, end_vtx] in cur.fetchall():
            max_fid += 1
            cur.execute("""INSERT INTO crossing_points(OGC_FID, GEOMETRY)
                SELECT """+str(max_fid)+""", Line_Interpolate_Point(GEOMETRY,0.5)
                FROM split_lines WHERE OGC_FID = """+str(ogc_fid))

            cur.execute("""UPDATE split_lines
                SET GEOMETRY = Snap(GEOMETRY, 
                    (SELECT v.GEOMETRY FROM crossing_points AS v 
                    WHERE v.OGC_FID="""+str(max_fid)+"), "+str(1.1*minArcLength/2)+")"
                "WHERE START_VTX = "+str(start_vtx)+" "
                "OR START_VTX = "+str(end_vtx)+" "
                "OR END_VTX = "+str(start_vtx)+" "
                "OR END_VTX = "+str(end_vtx))

            cur.execute("""UPDATE split_lines
                SET START_VTX = """+str(max_fid)+"""
                WHERE START_VTX = """+str(start_vtx)+"""
                OR START_VTX = """+str(end_vtx))

            cur.execute("""UPDATE split_lines
                SET END_VTX = """+str(max_fid)+"""
                WHERE END_VTX = """+str(start_vtx)+"""
                OR END_VTX = """+str(end_vtx))

            cur.execute("""DELETE FROM crossing_points
                WHERE OGC_FID IN ("""+str(start_vtx)+", "+str(end_vtx)+")")
            cur.execute("""DELETE FROM split_lines
                WHERE OGC_FID="""+str(ogc_fid))

        # remove unconnected elements
        cur.execute("ALTER TABLE split_lines ADD COLUMN COMPONENT integer")
        component = 0
        while True:
            component += 1
            cur.execute("SELECT OGC_FID, START_VTX, END_VTX FROM split_lines "
                "WHERE COMPONENT IS NULL LIMIT 1")
            res = cur.fetchone()
            if not res:
                break;
            [ogc_fid, start_vtx, end_vtx] = res
            cur.execute("UPDATE split_lines SET COMPONENT = "+str(component)+" "
                "WHERE OGC_FID = "+str(ogc_fid))
            boundary = set([start_vtx, end_vtx])
            finished = False
            while len(boundary):
                # get all connected vtx
                cur.execute("SELECT OGC_FID, START_VTX, END_VTX FROM split_lines "
                    "WHERE COMPONENT IS NULL AND (START_VTX IN ("+','.join([str(v) for v in boundary])+") "
                    "OR END_VTX IN ("+','.join([str(v) for v in boundary])+"))")
                old_boundary = boundary
                boundary = set()
                fids = []
                for [ogc_fid, start_vtx, end_vtx] in cur.fetchall():
                    fids.append((ogc_fid,))
                    if start_vtx not in old_boundary:
                        boundary.add(start_vtx)
                    if end_vtx not in old_boundary:
                        boundary.add(end_vtx)
                cur.executemany("UPDATE split_lines SET COMPONENT = "+str(component)+" "
                    "WHERE OGC_FID = ?", fids)
        cur.execute("SELECT MAX(CT), COMPONENT FROM (SELECT COUNT(1) AS CT, COMPONENT FROM split_lines GROUP BY COMPONENT)")
        [count, component] = cur.fetchone()
        cur.execute("DELETE FROM split_lines WHERE COMPONENT != "+str(component))

        if name_field:
            cur.execute("ALTER TABLE split_lines ADD COLUMN "+name_field)
            cur.execute("""UPDATE split_lines
                SET """+name_field+""" =
                (
                    SELECT """+name_field+"""
                    FROM $origin_table
                    WHERE Covers($origin_table.GEOMETRY, split_lines.GEOMETRY)
                    AND split_lines.ROWID IN (
                      SELECT ROWID FROM SpatialIndex 
                      WHERE f_table_name='split_lines' AND search_frame=$origin_table.GEOMETRY)
                )""")

        cur.execute("DROP TABLE $origin_table")
        self.create_indexed_line_table('$origin_table')
        if name_field:
            cur.execute("ALTER TABLE $origin_table ADD COLUMN "+name_field)
            cur.execute("INSERT INTO $origin_table(GEOMETRY, "+name_field\
                    +") SELECT GEOMETRY, "+name_field+" from split_lines")
        else:
            cur.execute("INSERT INTO $origin_table(GEOMETRY) SELECT Simplify(GEOMETRY,.1) from split_lines")

        self.conn.commit()
        
    def create_indexed_line_table(self, table, multi=''):
        cur = TrCursor(self.conn.cursor(), {'origin_table':self.brutArcsTablename})
        cur.execute("""
            CREATE TABLE """+table+"""(
                OGC_FID integer PRIMARY KEY
                )""")
        cur.execute("""
            SELECT AddGeometryColumn(
                '"""+table+"""', 
                'GEOMETRY', 
                (
                    SELECT CAST(srid AS integer) 
                    FROM geometry_columns 
                    WHERE f_table_name='$origin_table'
                ), 
                '"""+multi+"""LINESTRING', 
                (
                    SELECT coord_dimension
                    FROM geometry_columns
                    WHERE f_table_name='$origin_table'
                )
            )""")
        cur.execute("SELECT CreateSpatialIndex('"+table+"', 'GEOMETRY')")

    def create_indexed_point_table(self, table, multi=''):
        cur = TrCursor(self.conn.cursor(), {'origin_table':self.brutArcsTablename})
        cur.execute("""
            CREATE TABLE """+table+"""(
                OGC_FID integer PRIMARY KEY
                )""")
        cur.execute("""
            SELECT AddGeometryColumn(
                '"""+table+"""', 
                'GEOMETRY', 
                (
                    SELECT CAST(srid AS integer) 
                    FROM geometry_columns 
                    WHERE f_table_name='$origin_table'
                ), 
                '"""+multi+"""POINT', 
                (
                    SELECT coord_dimension
                    FROM geometry_columns
                    WHERE f_table_name='$origin_table'
                )
            )""")
        cur.execute("SELECT CreateSpatialIndex('"+table+"', 'GEOMETRY')")




