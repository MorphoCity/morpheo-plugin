# -*- encoding=utf-8 -*-

import sys
import logging

from .errors import BuilderError
from .sql import SQL

class Sanitizer(object):
    """ Helper for sanitizing geometries to a valid topological
        graph representation
 
        :param conn: spatialite connection
        :param input_table: name of the input raw data
    """

    def __init__(self, conn, input_table):
        self._table  = input_table
        self._conn   = conn

    @property
    def work_table(self):
        """ The name of the table containing 'sanitized' data
        """
        return "sanitized"


    def sanitize(self, snap_distance, min_edge_length, attribute=None):
        """ Sanitize input data

            The method will compute the following:
                
                - Remove unconnected features
                - Snap close geometries
                - Resolve intersection
                - Remove small edges

           :param snap_distance: Snap minimum distance
           :param min_edge_length: Minimum length for small edges
           :param attribute: Attribute to import from original data
        """
        if snap_distance <= 0:
            raise BuilderError("Invalid snap distance {}".format(snap_distance))
             

        logging.info(("Sanitizer: snap_distance={}"
                      ", min_edge_length={}, attribute={}").format(snap_distance,
                                                                    min_edge_length,
                                                                    attribute))

        cur = self._conn.cursor()
        self.delete_unconnected_features(cur)
        self.snap_geometries(cur, snap_distance)
        self.resolve_intersections(cur, min_edge_length, attribute)
        self._conn.commit()

    def delete_unconnected_features(self, cur):
        """ Remove unconnected features from input data
        """
        logging.info("Sanitizer: Deleting unconnected features")
        cur.execute(SQL("""DELETE FROM {input_table}
            WHERE NOT (
                SELECT COUNT(1) FROM {input_table} AS o
                WHERE Intersects( o.GEOMETRY, {input_table}.GEOMETRY )
                AND {input_table}.OGC_FID != o.OGC_FID
                AND
                o.ROWID IN (
                    SELECT ROWID FROM SpatialIndex
                    WHERE f_table_name='{input_table}' AND search_frame={input_table}.GEOMETRY)
                )
                """,input_table=self._table))

    def snap_geometries(self, cur, snap_distance):
        """ Snap close geometries 

            :param snap_distance: minimum snap distance
        """
        logging.info("Sanitizer: Snapping geometries")
        cur.execute(SQL("""UPDATE {input_table}
            SET GEOMETRY = Snap({input_table}.GEOMETRY,
                (
                SELECT Collect(o.GEOMETRY) FROM {input_table} AS o
                WHERE o.ROWID IN (
                      SELECT ROWID FROM SpatialIndex
                      WHERE f_table_name='{input_table}' AND search_frame=Buffer({input_table}.GEOMETRY, {snap_distance}))
                AND o.OGC_FID != {input_table}.OGC_FID
                )
                , {snap_distance})
            """, snap_distance=snap_distance, input_table=self._table))


    def resolve_intersections(self, cur, min_edge_length, attribute):
        """ Resolve intersections

        """
        logging.info("Sanitizer: Resolving intersections")
        self._1_find_overlapping_lines(cur)
        self._2_find_crossing_points(cur)
        self._3_cut_lines_at_nodes(cur)
        self._4_merge_lines(cur)
        self._5_remove_small_edges(cur, min_edge_length)
        self._6_remove_unconnected_elements(cur, attribute)

    def _1_find_overlapping_lines(self, cur):
        """ Find overlapping lines

            The method locates all overlaping lines: i.e parts of 
            geometries from which intersection do not resolve to simple points
        """
        logging.info("Sanitizer: Resolving intersections: find overlapping lines")

        self._create_indexed_table(cur, 'overlaping_lines', 'MULTILINESTRING')
        cur.execute(SQL("""INSERT INTO overlaping_lines(GEOMETRY)
            SELECT CastToMulti(Intersection(w1.GEOMETRY, w2.GEOMETRY))
            FROM {input_table} AS w1, {input_table} AS w2
            WHERE w1.OGC_FID != w2.OGC_FID
            AND Intersects(w1.GEOMETRY, w2.GEOMETRY)
            AND  w1.ROWID IN (
                  SELECT ROWID FROM SpatialIndex
                  WHERE f_table_name='{input_table}' AND search_frame=w2.GEOMETRY)
            AND GeometryType(Intersection(w1.GEOMETRY, w2.GEOMETRY))
                IN ('LINESTRING', 'MULTILINESTRING', 'LINESTRING Z', 'MULTILINESTRING Z')
            """,input_table=self._table))

    def _2_find_crossing_points(self, cur):
        """ Find crossing points between geometries

            The method locates intersections between geometries that resolve
            to points.
        """
        logging.info("Sanitizer: Resolving intersections: find crossing points")

        # add intersections
        # we first locate crossing points
        cur.execute(SQL("""SELECT coord_dimension
                    FROM geometry_columns
                    WHERE f_table_name='{input_table}'""",input_table=self._table))
        [dim] = cur.fetchone()
        self._create_indexed_table(cur, 'crossings', 'MULTIPOINT')

        # Adding crossings, skipping bridge
        cur.execute(SQL("""INSERT INTO crossings(GEOMETRY)
            SELECT CastToMulti(Intersection(w1.GEOMETRY, w2.GEOMETRY))
            FROM {input_table} AS w1, {input_table} AS w2
            WHERE w1.OGC_FID != w2.OGC_FID
            AND Intersects(w1.GEOMETRY, w2.GEOMETRY)
            AND  w1.ROWID IN (
                  SELECT ROWID FROM SpatialIndex
                  WHERE f_table_name='{input_table}' AND search_frame=w2.GEOMETRY)
            AND GeometryType(Intersection(w1.GEOMETRY, w2.GEOMETRY))
                IN ('POINT', 'MULTIPOINT', 'POINT Z', 'MULTIPOINT Z')""" +
           ("""AND ABS(0.5*(Z(StartPoint(w1.GEOMETRY))+Z(EndPoint(w1.GEOMETRY)))
                   -0.5*(Z(StartPoint(w1.GEOMETRY))+Z(EndPoint(w1.GEOMETRY)))) < 3""" if dim == 'XYZ' else ""),
           input_table=self._table))

        # Add overlapping lines end point and lines end points
        cur.execute(SQL("""INSERT INTO crossings(GEOMETRY)
            SELECT DISTINCT CastToMulti(EndPoint(GEOMETRY)) FROM overlaping_lines
            UNION
            SELECT DISTINCT CastToMulti(StartPoint(GEOMETRY)) FROM overlaping_lines
            UNION
            SELECT DISTINCT CastToMulti(EndPoint(GEOMETRY)) FROM {input_table}
            UNION
            SELECT DISTINCT CastToMulti(StartPoint(GEOMETRY)) FROM {input_table}
            """, input_table=self._table))

        # Explode multi points as one point per line
        # The counter is here for indexing points in multi.
        [count_max] = cur.execute(SQL("""SELECT max(NumGeometries(GEOMETRY)) FROM crossings""")).fetchone()
        if not count_max:
            count_max = 1
        cur.execute(SQL("CREATE TABLE counter(VALUE integer)"))
        cur.executemany(SQL("INSERT INTO counter(VALUE) SELECT ?"),[(c,) for c in range(1,count_max+1)] )

        self._create_indexed_table(cur, 'crossing_points', 'POINT')
        cur.execute(SQL("""INSERT INTO crossing_points(GEOMETRY)
            SELECT DISTINCT GeometryN(crossings.GEOMETRY, VALUE)
            FROM crossings, counter
            WHERE counter.VALUE <= NumGeometries(crossings.GEOMETRY)
            """))

        self._create_indexed_table(cur, 'split_lines', 'LINESTRING')
        cur.execute(SQL("ALTER TABLE split_lines ADD COLUMN START_VTX integer REFERENCES crossing_points(OGC_FID)"))
        cur.execute(SQL("ALTER TABLE split_lines ADD COLUMN END_VTX   integer REFERENCES crossing_points(OGC_FID)"))
        cur.execute(SQL("CREATE INDEX split_lines_start_vtx_idx ON split_lines(START_VTX)"))
        cur.execute(SQL("CREATE INDEX split_lines_end_vtx_idx   ON split_lines(END_VTX)"))


    def _3_cut_lines_at_nodes(self, cur):
        """ Cut lines 

        """
        logging.info("Sanitizer: Resolving intersections: cut lines")
        # since LinesCutAtNodes in not available in pyspatialite
        # we have to cut lines one segment at a time
        cur.execute(SQL("SELECT ROWID, OGC_FID FROM {input_table} ORDER BY OGC_FID",input_table=self._table))
        res = cur.fetchall()
        splits = []
        for [rowid, line_id] in res:
            # Get all points on line
            cur.execute(SQL("""
                SELECT Line_Locate_Point(o.GEOMETRY, v.GEOMETRY) AS LOCATION, v.OGC_FID
                FROM {input_table} AS o, crossing_points AS v
                WHERE PtDistWithin(o.GEOMETRY, v.GEOMETRY, 1e-2)
                AND o.OGC_FID = {line_id}
                AND v.ROWID IN (
                      SELECT ROWID FROM SpatialIndex 
                      WHERE f_table_name='crossing_points' AND search_frame=o.GEOMETRY)
                ORDER BY LOCATION;
                """,input_table=self._table,line_id=line_id))
            locations = cur.fetchall()

            # Store segments
            for i in range(1,len(locations)):
                splits.append((locations[i-1][0], locations[i][0], 
                    locations[i-1][1], locations[i][1], line_id))

            # Check if line is a loop and add segment closing loop
            cur.execute(SQL("""SELECT COUNT(1) 
                FROM  {input_table} WHERE OGC_FID = {line_id}
                AND PtDistWithin(EndPoint(GEOMETRY), StartPoint(GEOMETRY), 1e-2)""", 
                input_table=self._table, line_id=line_id))
            [isLoop] = cur.fetchone()
            if isLoop:
                splits.append((locations[-1][0], 1, locations[-1][1], locations[0][1], line_id))

        # Split lines
        cur.executemany(SQL("""
            INSERT INTO split_lines(GEOMETRY, START_VTX, END_VTX)
            SELECT Line_Substring(o.GEOMETRY, ?, ?), ?, ?
            FROM {input_table} AS o
            WHERE o.OGC_FID = ?""",input_table=self._table), splits)

        # remove duplicated lines
        cur.execute(SQL("""SELECT l1.OGC_FID, l2.OGC_FID
            FROM split_lines AS l1, split_lines AS l2
            WHERE Equals(l1.GEOMETRY, l2.GEOMETRY)
            AND l1.OGC_FID < l2.OGC_FID
            AND l1.ROWID IN (
                      SELECT ROWID FROM SpatialIndex 
                      WHERE f_table_name='split_lines' AND search_frame=l2.GEOMETRY)
            ORDER BY l1.OGC_FID
            """))
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
        cur.executemany(SQL("DELETE FROM split_lines WHERE OGC_FID = ?"), deleted_dupes)
        logging.info("Sanitizer: Deleted {} duplicates in split_lines".format(len(deleted_dupes)))

        # Sanity check ?
        cur.execute(SQL("SELECT COUNT(1) FROM split_lines WHERE END_VTX IS NULL OR START_VTX IS NULL"))
        [bug] = cur.fetchone()
        if bug: 
            raise BuilderError("Graph build error: NULL vertices in 'cut_lines_at_nodes'") 

        cur.execute(SQL("ALTER TABLE crossing_points ADD COLUMN DEGREE integer"))
        cur.execute(SQL("""
            UPDATE crossing_points
            SET DEGREE = 
            (
                SELECT COUNT(1) 
                FROM split_lines
                WHERE split_lines.END_VTX = crossing_points.OGC_FID 
                OR split_lines.START_VTX = crossing_points.OGC_FID
            ) """))

        cur.execute(SQL("""
            UPDATE crossing_points
            SET DEGREE = crossing_points.DEGREE + -- add one to the count for each loops
            (
                SELECT COUNT(1) 
                FROM split_lines
                WHERE split_lines.END_VTX = crossing_points.OGC_FID 
                AND split_lines.START_VTX = crossing_points.OGC_FID
            )"""))

    def _collect_lines(self, cur):
        """ join lines that are simply touching 
        """
        logging.info("Sanitizer: Resolving intersections: merge lines")

       


    def _4_merge_lines(self, cur):
        """ join lines that are simply touching 
        
            since several segment can be joined, we need to do that in
            python and not simply SQL
        """
        logging.info("Sanitizer: Resolving intersections: merge lines")

        def collect_lines():
            # Merge all touching segments joined with nodes of DEGREE=2
            from .angles import create_partition, update, resolve
            [max_lines] = cur.execute("SELECT Max(OGC_FID) FROM split_lines").fetchone()      
            if max_lines is None:
                raise BuilderError("No elements in table split_lines: check your input is valid !") 
            part = create_partition(max_lines+1) 
            cur.execute(SQL("SELECT OGC_FID FROM crossing_points WHERE DEGREE = 2"))
            for [pid] in cur.fetchall():
                [[l1],[l2]] = cur.execute(SQL("""
                    SELECT OGC_FID FROM split_lines 
                    WHERE {pid} IN (END_VTX, START_VTX)""",pid=pid)).fetchall()
                resolve(part,l1,l2)

            update(part)

            merges = [[] for i in range(len(part))]
            for i in range(len(part)):
                merges[part[i]].append(i)
            return merges    

        merges = collect_lines()

        # Clean up all crossing points with degree=2
        cur.execute(SQL("DELETE FROM crossing_points WHERE DEGREE = 2"))

        for m in merges:
            if len(m) < 2: continue
            cur.execute(SQL("""
                INSERT INTO split_lines(GEOMETRY)
                SELECT LineMerge(Collect(l.GEOMETRY)) AS geom
                FROM split_lines AS l
                WHERE l.OGC_FID IN ("""+','.join([str(i) for i in m])+")"))
            # If the line segment form a ring, there is no guaranty that
            # the merge endpoint is actually the one belonging to the graph
            # so we have to deal with that case

            cur.execute(SQL("SELECT MAX(OGC_FID), AsText(GEOMETRY) FROM split_lines"))
            [lid, s] = cur.fetchone()
            cur.execute(SQL("""SELECT COUNT(1) 
                FROM split_lines WHERE OGC_FID = """+str(lid)+"""
                AND PtDistWithin(StartPoint(GEOMETRY), EndPoint(GEOMETRY), 1e-2)"""))
            [isLoop] = cur.fetchone()
            if isLoop:
                cur.execute(SQL("""SELECT Line_Locate_Point(l.GEOMETRY, p.GEOMETRY) 
                    FROM split_lines AS l, crossing_points AS p
                    WHERE l.OGC_FID = """+str(lid)+"""
                    AND PtDistWithin(l.GEOMETRY, p.GEOMETRY, 1e-2)
                    """))
                alpha = cur.fetchone()
                if not alpha: # no point found, the loop is unconnected, remove it
                    cur.execute(SQL("DELETE FROM split_lines WHERE OGC_FID = "+str(lid)))
                elif alpha[0] > 0 and alpha[0] < 1:
                    # get the tow segments and invert their order
                    cur.execute(SQL("""
                        SELECT AsText(Line_Substring(GEOMETRY, 0,"""+str(alpha[0])+""")), 
                               AsText(Line_Substring(GEOMETRY,"""+str(alpha[0])+""", 1)),
                               SRID(GEOMETRY)
                        FROM split_lines WHERE OGC_FID = """+str(lid)))
                    [l1, l2, srid] = cur.fetchone()
                    linetype = l1.split('(')[0]
                    l1 = l1.split('(')[1].split(')')[0].split(',')
                    l2 = l2.split('(')[1].split(')')[0].split(',')
                    cur.execute(SQL("""
                        UPDATE split_lines SET GEOMETRY = GeomFromText('"""
                        +linetype+'('+','.join(l2)+','+','.join(l1[1:])+")', "+str(srid)+")"
                        +" WHERE OGC_FID = "+str(lid)))

            # remove joined lines 
            cur.execute(SQL("""
                DELETE FROM split_lines
                WHERE OGC_FID IN ("""+','.join([str(i) for i in m])+")"))

        # Set end vtx for merged lines
        cur.execute(SQL("""
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
            WHERE START_VTX IS NULL OR END_VTX IS NULL"""))

        # Sanity check ?
        cur.execute(SQL("SELECT COUNT(1) FROM split_lines WHERE END_VTX IS NULL OR START_VTX IS NULL"))
        [bug] = cur.fetchone()
        if bug: 
            raise BuilderError("Graph build error: NULL vertices in 'merge_lines'") 

    def _5_remove_small_edges(self, cur, min_edge_length):
        """ Remove small egdes and merge extremities

            All edges below min_edge_length will be removed an connected vertices
            will be merged at the centroid position of the removed geometry.
    
            :param min_edge_length: the minimun length for edges
        """
        # remove small edges and merge extremities at centroid
        logging.info("Sanitizer: Resolving intersections: remove arcs smaller than {}".format(min_edge_length))

        cur.execute(SQL("SELECT MAX(OGC_FID) FROM crossing_points"))
        [max_fid] = cur.fetchone()
        cur.execute(SQL("""SELECT OGC_FID, START_VTX, END_VTX 
            FROM split_lines
            WHERE GLength(GEOMETRY) < """+str(min_edge_length)))

        for [ogc_fid, start_vtx, end_vtx] in cur.fetchall():
            max_fid += 1
            cur.execute(SQL("""INSERT INTO crossing_points(OGC_FID, GEOMETRY)
                SELECT """+str(max_fid)+""", Line_Interpolate_Point(GEOMETRY,0.5)
                FROM split_lines WHERE OGC_FID = """+str(ogc_fid)))

            cur.execute(SQL("""UPDATE split_lines
                SET GEOMETRY = Snap(GEOMETRY, 
                    (SELECT v.GEOMETRY FROM crossing_points AS v 
                    WHERE v.OGC_FID="""+str(max_fid)+"), "+str(1.1*min_edge_length/2)+")"
                "WHERE START_VTX = "+str(start_vtx)+" "
                "OR START_VTX = "+str(end_vtx)+" "
                "OR END_VTX = "+str(start_vtx)+" "
                "OR END_VTX = "+str(end_vtx)))

            cur.execute(SQL("""UPDATE split_lines
                SET START_VTX = """+str(max_fid)+"""
                WHERE START_VTX = """+str(start_vtx)+"""
                OR START_VTX = """+str(end_vtx)))

            cur.execute(SQL("""UPDATE split_lines
                SET END_VTX = """+str(max_fid)+"""
                WHERE END_VTX = """+str(start_vtx)+"""
                OR END_VTX = """+str(end_vtx)))

            cur.execute(SQL("""DELETE FROM crossing_points
                WHERE OGC_FID IN ("""+str(start_vtx)+", "+str(end_vtx)+")"))

            cur.execute(SQL("""DELETE FROM split_lines
                WHERE OGC_FID="""+str(ogc_fid)))

    def _6_remove_unconnected_elements(self, cur, attribute):
        """ Remove unconnected elements

            TODO: Elaborate logic
        """
        logging.info("Sanitizer: Resolving intersections: remove unconnect elements")

        cur.execute(SQL("ALTER TABLE split_lines ADD COLUMN COMPONENT integer"))
        component = 0
        while True:
            component += 1
            cur.execute(SQL("SELECT OGC_FID, START_VTX, END_VTX FROM split_lines "
                "WHERE COMPONENT IS NULL LIMIT 1"))
            res = cur.fetchone()
            if not res:
                break;
            [ogc_fid, start_vtx, end_vtx] = res
            cur.execute(SQL("UPDATE split_lines SET COMPONENT = "+str(component)+" "
                "WHERE OGC_FID = "+str(ogc_fid)))
            boundary = set([start_vtx, end_vtx])
            finished = False

            while len(boundary):
                # get all connected vtx
                cur.execute(SQL("SELECT OGC_FID, START_VTX, END_VTX FROM split_lines "
                    "WHERE COMPONENT IS NULL AND (START_VTX IN ("+','.join([str(v) for v in boundary])+") "
                    "OR END_VTX IN ("+','.join([str(v) for v in boundary])+"))"))
                old_boundary = boundary
                boundary = set()
                fids = []
                for [ogc_fid, start_vtx, end_vtx] in cur.fetchall():
                    fids.append((ogc_fid,))
                    if start_vtx not in old_boundary:
                        boundary.add(start_vtx)
                    if end_vtx not in old_boundary:
                        boundary.add(end_vtx)
                cur.executemany(SQL("UPDATE split_lines SET COMPONENT = "+str(component)+" "
                    "WHERE OGC_FID = ?"), fids)

        cur.execute(SQL("SELECT MAX(CT), COMPONENT FROM (SELECT COUNT(1) AS CT, COMPONENT FROM split_lines GROUP BY COMPONENT)"))
        [count, component] = cur.fetchone()
        cur.execute("DELETE FROM split_lines WHERE COMPONENT != "+str(component))

        if attribute:
            cur.execute(SQL("ALTER TABLE split_lines ADD COLUMN "+attribute))
            cur.execute(SQL("""UPDATE split_lines
                SET """+attribute+""" =
                (
                    SELECT """+attribute+"""
                    FROM {input_table}
                    WHERE Covers({input_table}.GEOMETRY, split_lines.GEOMETRY)
                    AND split_lines.ROWID IN (
                      SELECT ROWID FROM SpatialIndex 
                      WHERE f_table_name='split_lines' AND search_frame={input_table}.GEOMETRY)
                )""",input_table=self._table))

        self._create_indexed_table(cur, self.work_table, 'LINESTRING')
        
        if attribute:
            cur.execute(SQL("ALTER TABLE "+self.work_table+" ADD COLUMN "+attribute))
            cur.execute(SQL("INSERT INTO "+self.work_table+" (GEOMETRY, "+attribute\
                    +") SELECT GEOMETRY, "+attribute+" from split_lines"))
        else:
            cur.execute(SQL("INSERT INTO "+self.work_table+"(GEOMETRY) SELECT Simplify(GEOMETRY,.1) from split_lines"))

        # Do some clean up
        self._drop_indexed_table(cur, "split_lines")
        self._drop_indexed_table(cur, "crossing_points")
        self._drop_indexed_table(cur, "crossings")
        self._drop_indexed_table(cur, "overlaping_lines")
        cur.execute("VACUUM")

    def _drop_indexed_table(self, cur, table):
        """ Drop a table and its index
        """
        cur.execute(SQL("SELECT DisableSpatialIndex('%s', 'GEOMETRY')" % table));
        cur.execute(SQL("SELECT DiscardGeometryColumn('%s', 'GEOMETRY')" % table));
        cur.execute(SQL("DROP TABLE idx_%s_GEOMETRY" % table))
        cur.execute(SQL("DROP TABLE %s" % table))

    def _create_indexed_table(self, cur, table, geomtype):
        """
        """
        cur.execute(SQL("CREATE TABLE {table}(OGC_FID integer PRIMARY KEY)",table=table))
        cur.execute(SQL("""
            SELECT AddGeometryColumn(
                '{table}',
                'GEOMETRY',
                (
                    SELECT CAST(srid AS integer)
                    FROM geometry_columns
                    WHERE f_table_name='{input_table}'
                ),
                '{geomtype}',
                (
                    SELECT coord_dimension
                    FROM geometry_columns
                    WHERE f_table_name='{input_table}'
                )
            )""",input_table=self._table,table=table,geomtype=geomtype))
        cur.execute(SQL("SELECT CreateSpatialIndex('{table}', 'GEOMETRY')",table=table))


def sanitize( conn, table, snap_distance, min_edge_length, attribute=None ):
    """ Wrap sanitizer call
    """
    sanitizer = Sanitizer(conn, table)
    sanitizer.sanitize(snap_distance, min_edge_length, attribute=attribute)
    return sanitizer.work_table

