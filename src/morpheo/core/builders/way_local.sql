-- Compute local way attributes


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
-- not part of that way. 

UPDATE ways SET CONNECTIVITY = (SELECT Count(1) FROM (
    SELECT e.OGC_FID FROM place_edges AS e
    WHERE e.START_PL IN (SELECT PLACE FROM way_places WHERE WAY_ID=ways.WAY_ID)
    AND e.WAY<>ways.WAY_ID
    UNION
    SELECT e.OGC_FID FROM place_edges AS e
    WHERE e.END_PL IN (SELECT PLACE FROM way_places WHERE WAY_ID=ways.WAY_ID)
    AND e.WAY<>ways.WAY_ID)
)
;


-- Spacing
UPDATE ways SET SPACING = (SELECT ways.LENGTH/ways.CONNECTIVITY)



