-- Build edges between places

DELETE FROM place_vtx;
DELETE FROM place_edges;

-- Create an association table between places and graph vertices
-- This is much faster than using subqueries/join with edge table

-- Do not clusterize cul-de-sac vertices (ie DEGREE=1)
-- This will prevent artificially connecting dead-end with other edges

INSERT INTO place_vtx(VERTEX, PLACE)
SELECT v.OGC_FID, p.OGC_FID
FROM vertices AS v, places AS p
WHERE ST_Within( v.GEOMETRY, p.GEOMETRY ) 
AND v.OGC_FID NOT IN (SELECT OGC_FID FROM left_vertices)
AND v.ROWID IN (
    SELECT ROWID FROM Spatialindex
    WHERE f_table_name='vertices' AND search_frame=p.GEOMETRY)
;


-- Add 'places' for all left vertices
INSERT INTO places(GEOMETRY,END_VTX)
SELECT ST_Buffer(v.GEOMETRY, 1), v.OGC_FID
FROM vertices AS v, left_vertices as l WHERE v.OGC_FID=l.OGC_FID
;

-- Udpate vertex-place table association

INSERT INTO place_vtx(VERTEX, PLACE) 
SELECT END_VTX, OGC_FID FROM places WHERE END_VTX IS NOT NULL
;

-- Update places with the number of vertices

-- Create temporary table
CREATE TABLE IF NOT EXISTS nb_vtx(ID integer, VALUE integer);
CREATE INDEX IF NOT EXISTS nb_vtx_idx ON nb_vtx(ID);

DELETE FROM nb_vtx;

INSERT INTO nb_vtx(ID,VALUE) SELECT pl.OGC_FID, Count(pl.OGC_FID) FROM place_vtx AS p, places AS pl WHERE pl.OGC_FID=p.PLACE
        GROUP BY pl.OGC_FID
;

-- Update table
UPDATE places SET NB_VTX = (SELECT VALUE FROM nb_vtx WHERE ID=places.OGC_FID)
;

-- Clean up
DROP INDEX nb_vtx_idx;
DROP TABLE nb_vtx;

-- Fill up place edge table

INSERT INTO place_edges(OGC_FID, GEOMETRY, START_VTX, END_VTX)
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

-- Create temporary table
CREATE TABLE IF NOT EXISTS place_degree(ID integer, VALUE integer);
CREATE INDEX IF NOT EXISTS place_degree_idx ON place_degree(ID);

DELETE FROM place_degree;

INSERT INTO place_degree(ID,VALUE) 
    SELECT pl.OGC_FID, Count(pl.OGC_FID) FROM place_edges AS pe, places AS pl 
        WHERE pl.OGC_FID=pe.START_PL OR pl.OGC_FID=pe.END_PL
        GROUP BY pl.OGC_FID
;

UPDATE places SET DEGREE = (SELECT VALUE FROM place_degree WHERE place_degree.ID=places.OGC_FID)
WHERE OGC_FID IN (SELECT ID FROM place_degree)
;

-- Add one for each loop
DELETE FROM place_degree;

INSERT INTO place_degree(ID,VALUE) 
    SELECT pl.OGC_FID, Count(pl.OGC_FID) FROM place_edges AS pe, places AS pl 
        WHERE pl.OGC_FID=pe.START_PL AND pl.OGC_FID=pe.END_PL
        GROUP BY pl.OGC_FID;
 
UPDATE places SET DEGREE = 
    places.DEGREE + (SELECT VALUE FROM place_degree WHERE place_degree.ID=places.OGC_FID) 
WHERE OGC_FID IN (SELECT ID FROM place_degree)
;


-- Clean up
DROP INDEX place_degree_idx;
DROP TABLE place_degree;

-- Remove all places with DEGREE=0 

DELETE FROM places WHERE DEGREE=0
;

-- Mark invalid geometries
-- Invalid geometries are geometries that crosses start or end places
-- multiple times - this may happends with places wich are not convex 
-- such as digitalized places

UPDATE place_edges SET
STATUS = (
    SELECT Min(t.status) FROM (
        SELECT ST_NumGeometries(ST_Difference(place_edges.GEOMETRY, p.GEOMETRY))=1
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
    SELECT CASE WHEN p.DEGREE>1 THEN ST_Difference(place_edges.GEOMETRY, p.GEOMETRY)
           ELSE place_edges.GEOMETRY
           END
    FROM places AS p 
    WHERE p.OGC_FID=place_edges.START_PL
    AND place_edges.ROWID IN (
        SELECT ROWID FROM Spatialindex
        WHERE f_table_name='place_edges' AND search_frame=p.GEOMETRY)
) WHERE STATUS=1
;

-- Cut geometry at end
-- Exclude loop because they have already been handled in the previous statement

UPDATE place_edges SET
GEOMETRY = 
(
    SELECT CASE WHEN (p.DEGREE>1 AND place_edges.END_PL<>place_edges.START_PL)
         THEN ST_Difference(place_edges.GEOMETRY, p.GEOMETRY)
         ELSE place_edges.GEOMETRY
         END
  FROM places AS p 
  WHERE p.OGC_FID=place_edges.END_PL
  AND place_edges.ROWID IN (
      SELECT ROWID FROM Spatialindex
      WHERE f_table_name='place_edges' AND search_frame=p.GEOMETRY)
) WHERE STATUS=1
;

-- Handle invalid geometries

UPDATE place_edges SET
GEOMETRY = (
  SELECT CASE WHEN ST_NumGeometries(geom)>1 THEN  ST_GeometryN(geom, ST_NumGeometries(geom))
         ELSE geom
         END
  FROM (
    SELECT CASE WHEN p.DEGREE>1 THEN ST_Difference(place_edges.GEOMETRY, p.GEOMETRY)
           ELSE place_edges.GEOMETRY
           END
    AS geom
    FROM places AS p
    WHERE p.OGC_FID=place_edges.START_PL
    AND place_edges.ROWID IN (
          SELECT ROWID FROM Spatialindex
          WHERE f_table_name='place_edges' AND search_frame=p.GEOMETRY)
  )
) WHERE STATUS=0
;

UPDATE place_edges SET
GEOMETRY = (
  SELECT CASE WHEN ST_NumGeometries(geom)>1 THEN ST_GeometryN(geom, 1)
         ELSE geom
         END
  FROM (
    SELECT CASE WHEN p.DEGREE>1 THEN ST_Difference(place_edges.GEOMETRY, p.GEOMETRY)
           ELSE place_edges.GEOMETRY
           END
    AS geom
    FROM places AS p
    WHERE p.OGC_FID=place_edges.END_PL
    AND place_edges.ROWID IN (
        SELECT ROWID FROM Spatialindex
        WHERE f_table_name='place_edges' AND search_frame=p.GEOMETRY)
  )
) WHERE STATUS=0
;

-- In some cases, convex hull overlaps non-connected places
-- This leads in situation where place edges geometries are null when 
-- computed from differences from places geometries
-- In those case restore the original edge geometry
-- We mark those edges with a special status code  

UPDATE place_edges SET
GEOMETRY = (SELECT e.GEOMETRY FROM edges AS e WHERE place_edges.OGC_FID=e.OGC_FID),
STATUS   = 2
WHERE GEOMETRY IS NULL
;

-- Update place_edges degree

UPDATE place_edges
SET DEGREE =
        (SELECT DEGREE FROM places WHERE places.OGC_FID = place_edges.START_PL)
       +(SELECT DEGREE FROM places WHERE places.OGC_FID = place_edges.END_PL)
       - 2
    WHERE place_edges.START_PL != place_edges.END_PL
;

UPDATE place_edges
SET DEGREE =
        (SELECT DEGREE FROM places WHERE places.OGC_FID = place_edges.START_PL)
       - 2
    WHERE place_edges.START_VTX == place_edges.END_VTX
;

-- Update place_edges length

UPDATE place_edges SET LENGTH = (SELECT ST_Length(place_edges.GEOMETRY))
;


-- Clean up
VACUUM
;


