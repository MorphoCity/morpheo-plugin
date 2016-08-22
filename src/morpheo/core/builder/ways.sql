-- Build ways as geometric objects
-- TESTS TODO
-- Check that there two places and only two for way on table way_partition
-- Check that there is no missing START_PL/END_PL on table ways

DELETE FROM ways;
DELETE FROM way_places;

-- Update place edges with way index

UPDATE place_edges SET 
WAY = (SELECT WAY FROM way_partition WHERE way_partition.EDGE=place_edges.OGC_FID)
;

-- Cleanup ways attributes on edges

UPDATE edges SET RTOPO = NULL, ACCES = NULL, WAY_ID = NULL;

-- Compute Way geometry (as MULTILINESTRING)

INSERT INTO ways(GEOMETRY,WAY_ID)
SELECT ST_Multi(ST_LineMerge(ST_Collect(e.GEOMETRY))), e.WAY
FROM place_edges as e 
GROUP BY e.WAY
;


-- Build way/places association

INSERT INTO way_places(WAY_ID,PLACE)
SELECT way, pl
FROM (
    SELECT WAY as way, START_PL AS pl FROM place_edges
    UNION
    SELECT WAY as way, END_PL AS pl FROM place_edges
)
;

-- Update edge with ways id

UPDATE edges SET WAY_ID = 
    (SELECT WAY FROM place_edges WHERE place_edges.OGC_FID=edges.OGC_FID)
;

-- Compute basic way attributes

-- Tests TODO:
-- DEGREE > 0
-- CONNECTIVITY > 0


-- Length
UPDATE ways SET LENGTH = (
    SELECT ST_Length(ways.GEOMETRY) + Sum(p.DIST) FROM way_partition AS p WHERE p.WAY=ways.WAY_ID
)
;

-- Degree
-- Number of other intersecting ways
UPDATE ways SET DEGREE = (
    SELECT Count(DISTINCT WAY_ID) FROM way_places 
    WHERE PLACE IN (SELECT PLACE FROM way_places WHERE WAY_ID=ways.WAY_ID) 
    AND WAY_ID<>ways.WAY_ID 
)
;

-- Connectivity
-- Number of arcs in the viary graph intersected by a way wich are
-- not part of that way (sum by place)
 
UPDATE ways SET CONN = (SELECT Count(1) FROM (
    SELECT OGC_FID, START_PL FROM place_edges
    WHERE START_PL IN (SELECT PLACE FROM way_places WHERE WAY_ID=ways.WAY_ID)
    AND WAY<>ways.WAY_ID
    UNION
    SELECT OGC_FID, END_PL FROM place_edges
    WHERE END_PL IN (SELECT PLACE FROM way_places WHERE WAY_ID=ways.WAY_ID)
    AND WAY<>ways.WAY_ID)
)
;

-- Spacing

UPDATE ways SET SPACING = (SELECT ways.LENGTH/ways.CONN)
WHERE CONN>0
;

-- Clean up
VACUUM
;


