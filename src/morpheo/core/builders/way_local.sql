-- Compute local way attributes
-- TODO CHECK:
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
 
UPDATE ways SET CONNECTIVITY = (SELECT Count(1) FROM (
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
UPDATE ways SET SPACING = (SELECT ways.LENGTH/ways.CONNECTIVITY WHERE ways.CONNECTIVITY>0)



