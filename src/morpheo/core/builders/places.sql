-- Build edges between places


DELETE FROM place_vtx;
DELETE FROM place_edges;
DELETE FROM angles;

-- Create an association table between places and graph vertices
-- This is much faster than using subqueries/join with edge table

-- Do not clusterize cul-de-sac vertices (ie DEGREE=1)
-- This will prevent artificially connecting dead-end with other edges

INSERT INTO place_vtx(VERTEX, PLACE)
SELECT v.OGC_FID, p.OGC_FID
FROM vertices AS v, places AS p
WHERE ST_Within( v.GEOMETRY, p.GEOMETRY ) AND v.DEGREE > 1
AND v.ROWID IN (
    SELECT ROWID FROM Spatialindex
    WHERE f_table_name='vertices' AND search_frame=p.GEOMETRY)
;

-- Add 'places' for all vertices with DEGREE=1
INSERT INTO places(GEOMETRY, CUL_DE_SAC)
SELECT ST_Buffer(v.GEOMETRY, 1), v.OGC_FID 
FROM vertices AS v WHERE v.DEGREE=1
;

-- Udpate vertex-place table association

INSERT INTO place_vtx(VERTEX, PLACE) 
SELECT CUL_DE_SAC, OGC_FID FROM places WHERE CUL_DE_SAC IS NOT NULL
;

-- Update places with the number of vertices

UPDATE places
SET NB_VTX = (SELECT Count(*) FROM place_vtx AS p WHERE places.OGC_FID=p.PLACE)
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
-- Note: we are OR'ing start/end place because of a side effect from using single place from
-- cul-de-sac: places can contain cul-de-sac connected to another point in the same place
-- but place fid are different for at each end. 
DELETE FROM place_edges
WHERE OGC_FID IN (SELECT e.OGC_FID
    FROM places AS p, place_edges AS e
    WHERE (e.START_PL=p.OGC_FID OR e.END_PL=p.OGC_FID) AND ST_Within(e.GEOMETRY, p.GEOMETRY)
    AND e.ROWID IN (
        SELECT ROWID FROM Spatialindex
        WHERE f_table_name='place_edges' AND search_frame=p.GEOMETRY))
;

-- Compute place's degree

UPDATE places 
SET DEGREE = 
(
    SELECT COUNT(1) FROM place_edges
    WHERE place_edges.START_PL=places.OGC_FID 
    OR place_edges.END_PL=places.OGC_FID
)
;

-- Add one for each loop
UPDATE places 
SET DEGREE = places.DEGREE + 
(
    SELECT COUNT(1) FROM place_edges
    WHERE place_edges.START_PL=places.OGC_FID 
    AND place_edges.END_PL=places.OGC_FID
)
;

-- Remove all places with DEGREE=0 

DELETE FROM places WHERE DEGREE=0
;


-- Mark invalid geometries
-- Invalid geometries are geometries that crosses start or end places
-- multiple times 

UPDATE place_edges SET
STATUS = (
    SELECT Min(t.status) FROM (
        SELECT CASE WHEN p.NB_VTX>1 THEN  ST_NumGeometries(ST_Difference(place_edges.GEOMETRY, p.GEOMETRY))=1
        ELSE 1
        END
        AS status
        FROM places as p
        WHERE (p.OGC_FID=place_edges.START_PL OR p.OGC_FID=place_edges.END_PL)
            AND place_edges.ROWID IN (
            SELECT ROWID FROM Spatialindex
            WHERE f_table_name='place_edges' AND search_frame=p.GEOMETRY)
) AS t);

-- Update geometries

-- Cut geometry at start 

UPDATE place_edges SET
GEOMETRY = 
(
    SELECT CASE WHEN p.NB_VTX>1 THEN ST_Difference(place_edges.GEOMETRY, p.GEOMETRY)
           ELSE place_edges.GEOMETRY
           END
    FROM places as p 
        WHERE p.OGC_FID=place_edges.START_PL
        AND place_edges.ROWID IN (
        SELECT ROWID FROM Spatialindex
        WHERE f_table_name='place_edges' AND search_frame=p.GEOMETRY)
) WHERE STATUS=1
;

-- Cut geometry at end

UPDATE place_edges SET
GEOMETRY = 
(
  SELECT CASE WHEN p.NB_VTX>1 THEN ST_Difference(place_edges.GEOMETRY, p.GEOMETRY)
         ELSE place_edges.GEOMETRY
         END
  FROM places as p 
  WHERE p.OGC_FID=place_edges.END_PL
  AND place_edges.ROWID IN (
      SELECT ROWID FROM Spatialindex
      WHERE f_table_name='place_edges' AND search_frame=p.GEOMETRY)
) WHERE STATUS=1
;


--Compute azimuth
--XXX SQLite does not come with ST_Azimuth by default
--UPDATE place_edges SET
--START_AZ = (SELECT ST_Azimuth( ST_StartPoint(GEOMETRY), ST_PointN(GEOMETRY,2))),
--END_AZ   = (SELECT ST_Azimuth( ST_EndPoint(GEOMETRY), ST_PointN(GEOMETRY, ST_NumPoint(GEOMETRY)-1)))
--;



