-- todo sanitize the input so that intersections actually touch
-- sale bruxelles osm   

-- Vertices

SELECT 'start', time();

SELECT 'create vertices, ways, edges and angles tables', time();

CREATE TABLE vertices(
    OGC_FID integer PRIMARY KEY,
    DEGREE integer DEFAULT 0
);

SELECT AddGeometryColumn(
    'vertices', 
    'GEOMETRY', 
    (
        SELECT CAST(srid AS integer) 
        FROM geometry_columns 
        WHERE f_table_name='$input_table'
    ), 
    'POINT', 
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    )
);

SELECT CreateSpatialIndex('vertices', 'GEOMETRY');

-- Ways

CREATE TABLE ways( 
    OGC_FID integer PRIMARY KEY,
    LENGTH real,
    NB_EDGES integer,
    NB_VERTICES integer, -- nb of edges plus
    DEGREE integer, -- nb of intersecting ways
    CONNECTIVITY integer,
    SPACING real -- CONNECTIVITY / LENGTH
);

SELECT AddGeometryColumn(
    'ways', 
    'GEOMETRY', 
    (
        SELECT CAST(srid AS integer) 
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    ), 
    'MULTILINESTRING',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    )
);

SELECT CreateSpatialIndex('ways', 'GEOMETRY');

-- Way - Vertex

CREATE TABLE ways_vertices(
    OGC_FID integer PRIMARY KEY,
    WAY integer REFERENCES ways(OGC_FID),
    VTX integer REFERENCES vertices(OGC_FID)
);

CREATE INDEX ways_vertices_way_idx ON ways_vertices(WAY);
CREATE INDEX ways_vertices_vtx_idx ON ways_vertices(VTX);

-- Way - Way

CREATE TABLE ways_ways(
    OGC_FID integer PRIMARY KEY,
    WAY1 integer REFERENCES ways(OGC_FID),
    WAY2 integer REFERENCES ways(OGC_FID)
);

CREATE INDEX ways_ways_way1_idx ON ways_ways(WAY1);
CREATE INDEX ways_ways_way2_idx ON ways_ways(WAY2);

-- Streets

CREATE TABLE streets(
    OGC_FID integer PRIMARY KEY,
    LENGTH real,
    NB_EDGES integer,
    NB_VERTICES integer,
    NAME text
    DEGREE integer, -- nb of intersecting streets
    CONNECTIVITY integer,
    SPACING real -- CONNECTIVITY / LENGTH
);

SELECT AddGeometryColumn( -- to ease update, because joins are not allowed
    'streets', 
    'GEOMETRY', 
    (
        SELECT CAST(srid AS integer) 
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    ), 
    'MULTILINESTRING',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    )
);

SELECT CreateSpatialIndex('streets', 'GEOMETRY');

-- Street - Vertex

CREATE TABLE streets_vertices(
    OGC_FID integer PRIMARY KEY,
    STREET integer REFERENCES streets(OGC_FID),
    VTX integer REFERENCES vertices(OGC_FID)
);

CREATE INDEX streets_vertices_street_idx ON streets_vertices(STREET);
CREATE INDEX streets_vertices_vtx_idx ON streets_vertices(VTX);

-- Street - Street

CREATE TABLE streets_streets(
    OGC_FID integer PRIMARY KEY,
    STREET1 integer REFERENCES streets(OGC_FID),
    STREET2 integer REFERENCES streets(OGC_FID)
);

CREATE INDEX streets_streets_street1_idx ON streets_streets(STREET1);
CREATE INDEX streets_streets_street2_idx ON streets_streets(STREET2);

-- Street - Way

CREATE TABLE streets_ways(
    OGC_FID integer PRIMARY KEY,
    STREET integer REFERENCES streets(OGC_FID),
    WAY integer REFERENCES ways(OGC_FID)
);

CREATE INDEX streets_ways_street_idx ON streets_ways(STREET);
CREATE INDEX streets_ways_way_idx ON streets_ways(WAY);


-- Edges

CREATE TABLE edges(
    OGC_FID integer PRIMARY KEY REFERENCES $input_table(OGC_FID),
    START_VTX integer REFERENCES vertices(OGC_FID),
    END_VTX integer REFERENCES vertices(OGC_FID),
    WAY integer REFERENCES ways(OGC_FID),
    STREET integer REFERENCES streets(OGC_FID),
    START_AZIMUTH real,
    END_AZIMUTH real,
    CONNECTIVITY integer,
    LENGTH real,
    SPACING real,
    DEGREE integer,
    NAME text DEFAULT NULL
);

SELECT AddGeometryColumn( -- to ease update, because joins are not allowed
    'edges', 
    'GEOMETRY', 
    (
        SELECT CAST(srid AS integer) 
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    ), 
    'LINESTRING',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    )
);

SELECT CreateSpatialIndex('edges', 'GEOMETRY');
CREATE INDEX edges_start_vtx_idx ON edges(START_VTX);
CREATE INDEX edges_end_vtx_idx ON edges(END_VTX);
CREATE INDEX edges_way_idx ON edges(WAY);
CREATE INDEX edges_name_idx ON edges(NAME);

-- Edges - Vertex

CREATE TABLE edges_vertices(
    OGC_FID integer PRIMARY KEY,
    EDGE integer REFERENCES edges(OGC_FID),
    VTX integer REFERENCES vertices(OGC_FID)
);

CREATE INDEX edges_vertices_edge_idx ON edges_vertices(EDGE);
CREATE INDEX edges_vertices_vtx_idx ON edges_vertices(VTX);

-- Edges - Edges

CREATE TABLE edges_edges(
    OGC_FID integer PRIMARY KEY,
    EDGE1 integer REFERENCES edges(OGC_FID),
    EDGE2 integer REFERENCES edges(OGC_FID)
);

CREATE INDEX edges_edges_edge1_idx ON edges_edges(EDGE1);
CREATE INDEX edges_edges_edge2_idx ON edges_edges(EDGE2);

-- Angles

CREATE TABLE angles(
    OGC_FID integer PRIMARY KEY,
    VTX_ID integer REFERENCES vertices(OGC_FID),
    EDGE1_ID integer REFERENCES edges(OGC_FID),
    EDGE2_ID integer REFERENCES edges(OGC_FID),
    ANGLE double,
    USED boolean DEFAULT 0 -- remove after algo
);

CREATE INDEX angles_vtx_id_idx ON angles(VTX_ID);
CREATE INDEX angles_edge1_id_idx ON angles(EDGE1_ID);
CREATE INDEX angles_edge2_id_idx ON angles(EDGE2_ID);


-- Copy edges from origin table

SELECT 'Initialze edges table by copying $input_table', time();

INSERT INTO edges(GEOMETRY, LENGTH, START_AZIMUTH, END_AZIMUTH)
SELECT GEOMETRY, GLength(GEOMETRY),
    -- Azimuth computation TODO replace Azimuth computatio by macro
    (case
        when X(StartPoint(GEOMETRY)) == X(PointN(GEOMETRY,2)) then case
            when Y(StartPoint(GEOMETRY)) < Y(PointN(GEOMETRY,2)) then 0.0
            when Y(StartPoint(GEOMETRY)) > Y(PointN(GEOMETRY,2)) then 3.141592653589793
            else 0
            end
        when Y(StartPoint(GEOMETRY)) == Y(PointN(GEOMETRY,2)) then case 
            when X(StartPoint(GEOMETRY)) < X(PointN(GEOMETRY,2)) then 3.141592653589793/2
            when X(StartPoint(GEOMETRY)) > X(PointN(GEOMETRY,2)) then 3.141592653589793 + 3.141592653589793/2
            else 0
            end
        when X(StartPoint(GEOMETRY)) < X(PointN(GEOMETRY,2)) then case
            when Y(StartPoint(GEOMETRY)) < Y(PointN(GEOMETRY,2)) then atan( abs(X(StartPoint(GEOMETRY)) - X(PointN(GEOMETRY,2))) / abs(Y(StartPoint(GEOMETRY)) - Y(PointN(GEOMETRY,2))) )
            else atan( abs(Y(StartPoint(GEOMETRY)) - Y(PointN(GEOMETRY,2))) / abs(X(StartPoint(GEOMETRY)) - X(PointN(GEOMETRY,2))) ) + 3.141592653589793/2
            end
        else case
            when Y(StartPoint(GEOMETRY)) > Y(PointN(GEOMETRY,2)) then atan( abs(X(StartPoint(GEOMETRY)) - X(PointN(GEOMETRY,2))) / abs(Y(StartPoint(GEOMETRY)) - Y(PointN(GEOMETRY,2))) ) + 3.141592653589793
            else atan( abs(Y(StartPoint(GEOMETRY)) - Y(PointN(GEOMETRY,2))) / abs(X(StartPoint(GEOMETRY)) - X(PointN(GEOMETRY,2))) ) + 3.141592653589793 + 3.141592653589793/2
            end
        end)
,
    (case
        when X(EndPoint(GEOMETRY)) == X(PointN(GEOMETRY,NumPoints(GEOMETRY)-1)) then case
            when Y(EndPoint(GEOMETRY)) < Y(PointN(GEOMETRY,NumPoints(GEOMETRY)-1)) then 0.0
            when Y(EndPoint(GEOMETRY)) > Y(PointN(GEOMETRY,NumPoints(GEOMETRY)-1)) then 3.141592653589793
            else 0
            end
        when Y(EndPoint(GEOMETRY)) == Y(PointN(GEOMETRY,NumPoints(GEOMETRY)-1)) then case 
            when X(EndPoint(GEOMETRY)) < X(PointN(GEOMETRY,NumPoints(GEOMETRY)-1)) then 3.141592653589793/2
            when X(EndPoint(GEOMETRY)) > X(PointN(GEOMETRY,NumPoints(GEOMETRY)-1)) then 3.141592653589793 + 3.141592653589793/2
            else 0
            end
        when X(EndPoint(GEOMETRY)) < X(PointN(GEOMETRY,NumPoints(GEOMETRY)-1)) then case
            when Y(EndPoint(GEOMETRY)) < Y(PointN(GEOMETRY,NumPoints(GEOMETRY)-1)) then atan( abs(X(EndPoint(GEOMETRY)) - X(PointN(GEOMETRY,NumPoints(GEOMETRY)-1))) / abs(Y(EndPoint(GEOMETRY)) - Y(PointN(GEOMETRY,NumPoints(GEOMETRY)-1))) )
            else atan( abs(Y(EndPoint(GEOMETRY)) - Y(PointN(GEOMETRY,NumPoints(GEOMETRY)-1))) / abs(X(EndPoint(GEOMETRY)) - X(PointN(GEOMETRY,NumPoints(GEOMETRY)-1))) ) + 3.141592653589793/2
            end
        else case
            when Y(EndPoint(GEOMETRY)) > Y(PointN(GEOMETRY,NumPoints(GEOMETRY)-1)) then atan( abs(X(EndPoint(GEOMETRY)) - X(PointN(GEOMETRY,NumPoints(GEOMETRY)-1))) / abs(Y(EndPoint(GEOMETRY)) - Y(PointN(GEOMETRY,NumPoints(GEOMETRY)-1))) ) + 3.141592653589793
            else atan( abs(Y(EndPoint(GEOMETRY)) - Y(PointN(GEOMETRY,NumPoints(GEOMETRY)-1))) / abs(X(EndPoint(GEOMETRY)) - X(PointN(GEOMETRY,NumPoints(GEOMETRY)-1))) ) + 3.141592653589793 + 3.141592653589793/2
            end
        end)
FROM $input_table
;

-- Create the vertices of the graph

SELECT 'Fill up vertices table', time();

INSERT INTO vertices(GEOMETRY)
SELECT StartPoint( GEOMETRY ) AS GEOMETRY FROM edges
UNION
SELECT EndPoint( GEOMETRY ) AS GEOMETRY FROM edges
;

-- Edges connectivity

SELECT 'Set edges connectivity', time();

UPDATE edges 
SET END_VTX = 
(
    SELECT v.OGC_FID 
    FROM vertices AS v
    WHERE Intersects( v.GEOMETRY, EndPoint( edges.GEOMETRY ) )
    AND
    v.ROWID IN (
      SELECT ROWID FROM SpatialIndex 
      WHERE f_table_name='vertices' AND search_frame=edges.GEOMETRY)
),
START_VTX = 
(
    SELECT v.OGC_FID 
    FROM vertices AS v
    WHERE Intersects( v.GEOMETRY, StartPoint( edges.GEOMETRY ) )
    AND
    v.ROWID IN (
      SELECT ROWID FROM SpatialIndex 
      WHERE f_table_name='vertices' AND search_frame=edges.GEOMETRY)
)
;

-- Update vertices degree

SELECT 'Set vertices degree', time();

UPDATE vertices 
SET DEGREE = 
(
    SELECT COUNT(1) 
    FROM edges 
    WHERE edges.END_VTX = vertices.OGC_FID 
    OR edges.START_VTX = vertices.OGC_FID
)
;

UPDATE vertices 
SET DEGREE = vertices.DEGREE + -- add one to the count for each loops touching the vertex
(
    SELECT COUNT(1) 
    FROM edges 
    WHERE edges.END_VTX = vertices.OGC_FID 
    AND edges.START_VTX = vertices.OGC_FID
)
;

-- Update edges degree

SELECT 'Set edges degree', time();

UPDATE edges 
SET DEGREE = 
        (SELECT DEGREE FROM vertices WHERE $vertices.OGC_FID = edges.START_VTX)
       +(SELECT DEGREE FROM vertices WHERE $vertices.OGC_FID = edges.END_VTX)
       - 2
    WHERE edges.START_VTX != edges.END_VTX
;

UPDATE edges 
SET DEGREE = 
        (SELECT DEGREE FROM vertices WHERE $vertices.OGC_FID = edges.START_VTX)
       - 2
    WHERE edges.START_VTX == edges.END_VTX
;


-- Set angles

SELECT 'Compute angles', time();

-- union is a lot faster than a general connectivity condition plus a CASE
INSERT INTO angles(VTX_ID, EDGE1_ID, EDGE2_ID, ANGLE)
SELECT v.OGC_FID, e1.OGC_FID, e2.OGC_FID, (e1.START_AZIMUTH - e2.START_AZIMUTH)
FROM vertices AS v, edges AS e1, edges AS e2
WHERE e1.OGC_FID < e2.OGC_FID -- avoid both sides angles
AND v.OGC_FID = e1.START_VTX AND v.OGC_FID = e2.START_VTX
UNION ALL
SELECT v.OGC_FID, e1.OGC_FID, e2.OGC_FID, (e1.END_AZIMUTH - e2.START_AZIMUTH)
FROM vertices AS v, edges AS e1, edges AS e2
WHERE e1.OGC_FID < e2.OGC_FID -- avoid both sides angles
AND v.OGC_FID = e1.END_VTX AND v.OGC_FID = e2.START_VTX
UNION ALL
SELECT v.OGC_FID, e1.OGC_FID, e2.OGC_FID, (e1.START_AZIMUTH - e2.END_AZIMUTH) 
FROM vertices AS v, edges AS e1, edges AS e2
WHERE e1.OGC_FID < e2.OGC_FID -- avoid both sides angles
AND v.OGC_FID = e1.START_VTX AND v.OGC_FID = e2.END_VTX
UNION ALL
SELECT v.OGC_FID, e1.OGC_FID, e2.OGC_FID, (e1.END_AZIMUTH - e2.END_AZIMUTH) 
FROM vertices AS v, edges AS e1, edges AS e2
WHERE e1.OGC_FID < e2.OGC_FID -- avoid both sides angles
AND v.OGC_FID = e1.END_VTX AND v.OGC_FID = e2.END_VTX
;

-- add loops
INSERT INTO angles(VTX_ID, EDGE1_ID, EDGE2_ID, ANGLE)
SELECT v.OGC_FID, e.OGC_FID, e.OGC_FID, (e.START_AZIMUTH - e.END_AZIMUTH)
FROM vertices AS v, edges AS e
WHERE v.OGC_FID = e.START_VTX AND v.OGC_FID = e.END_VTX
;

-- alignment angle
UPDATE angles SET
ANGLE = 
CASE WHEN ABS( ANGLE*180/3.1416 ) > 180. THEN ABS( 180. - ABS( ANGLE*180/3.1416 ) )
ELSE ABS( ABS( ANGLE*180/3.1416 ) - 180. )
END
;

