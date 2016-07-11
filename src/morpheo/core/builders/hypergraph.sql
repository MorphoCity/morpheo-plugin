-- Build hypergraph 

DELETE FROM place_vtx;
DELETE FROM place_edges;
DELETE FROM angles;

-- Create an association table between places and graph vertices
-- This is much faster than using subqueries/join with edge table

INSERT INTO place_vtx(VERTEX, PLACE)
SELECT v.OGC_FID, p.OGC_FID
FROM vertices AS v, places AS p
WHERE ST_Within( v.GEOMETRY, p.GEOMETRY )
AND v.ROWID IN (
    SELECT ROWID FROM Spatialindex
    WHERE f_table_name='vertices' AND search_frame=p.GEOMETRY)
;

-- Fill up place edge table

INSERT INTO place_edges(EDGE, GEOMETRY, START_VTX, END_VTX)
SELECT e.OGC_FID, e.GEOMETRY, e.START_VTX, e.END_VTX
FROM edges AS e
;

-- Update places 

UPDATE place_edges SET
START_PL =
(
    SELECT v.PLACE
    FROM place_vtx AS v
    WHERE v.VERTEX=place_edges.START_VTX
),
END_PL =
(
   SELECT v.PLACE
   FROM place_vtx AS v
   WHERE v.VERTEX=place_edges.END_VTX
)
;

-- Filter all edges whose geometry is totally contained in places

DELETE FROM place_edges
WHERE OGC_FID IN (SELECT e.OGC_FID
    FROM places AS p, place_edges AS e
    WHERE e.START_PL=p.OGC_FID AND e.END_PL=p.OGC_FID AND ST_Within(e.GEOMETRY, p.GEOMETRY)
    AND e.ROWID IN (
        SELECT ROWID FROM Spatialindex
        WHERE f_table_name='edges' AND search_frame=p.GEOMETRY))
;

-- Update geometries

-- Cut geometry at start 

UPDATE place_edges SET
GEOMETRY = 
(
    SELECT ST_LineMerge(ST_Difference(place_edges.GEOMETRY, p.GEOMETRY))
    FROM places as p 
        WHERE p.OGC_FID=place_edges.START_PL
        AND place_edges.ROWID IN (
        SELECT ROWID FROM Spatialindex
        WHERE f_table_name='place_edges' AND search_frame=p.GEOMETRY)
);

-- Cut geometry at end

UPDATE place_edges SET
GEOMETRY = 
(
    SELECT ST_LineMerge(ST_Difference(place_edges.GEOMETRY, p.GEOMETRY)) 
    FROM places as p 
    WHERE p.OGC_FID=place_edges.END_PL
    AND place_edges.ROWID IN (
        SELECT ROWID FROM Spatialindex
        WHERE f_table_name='place_edges' AND search_frame=p.GEOMETRY)
);


