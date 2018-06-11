# Morpheo: python package and plugin QGIS for the characterization of spatial graphs.


## References:

* Claire Lagesse's PhD thesis: https://halshs.archives-ouvertes.fr/tel-01245898

# Requirements:

* QGIS 3.0 minimum
* GDAL/OGR tools
* spatialite 4.2 (Use mod\_spatialite)

# Install as command line:

```bash
python setup.py 
```

From this, Morpheo will be available as command line, i.e:

```bash
morpheo --help
```

# Install as QGIS plugin

Copy or extract the morpheo python package (found in src/) in the .qgis/python/plugins folder of your
home directory. This will add a Extension/Morpheo menu.

Note that if you are using the latest version from gitlab or github, you can add a symbolic link to the src/morpheo folder in your
.qgis/python/plugins folder (on OSX and Linux)


## What's computed

* Viary geometries as topological graph (arcs and vertices)
* Places 
* Ways
* Orhogonality, topological radius, centrality indicators on edges and ways
* Horizon from mesh structures
* Shortest/simplest path
* Shortest/simplest path with topological shortcuts from mesh structures.
* Way simplest path (simplest path in way line graph)
* Structural differences


## Outputs

By default, Morpheo creates a spatialite database and a folder name morpheo_<name_of_the_datasource> where all produced shapefiles and other moprpheo data are stored.
 

## Graph indicators

Indicators computed on ways and arcs:

    CONN             real, -- connectivity
    CLOSEN           real, -- closeness
    SPACING          real, -- spacing
    ORTHOG           real, -- orthogonality
    BETWEE           real, -- betweeness
    USE              real, -- stress centrality
    RTOPO            real, -- topological radius
    ACCES            real, -- accessibility


## Geographic features computed

These are the tables computed in the working database of morpheo: these table
can be accessed in qgis for debug purpose.

* **edges**: edges of the topological graph computed from initial data
* **vertices**: vertices of the topological graph command from initial data
* **places**: places buffers computed, including external places definitions. These
          or vertices of edges in  'place_edges'
* **place_zedges**: edges beteween places. All indicators and path are computed using these edges.
* **ways**: computed ways from place_edges
* **shortest**: last shortest computed path 
* **simplest**: last shortest computed path
* **azimuth**: last azimuthal path
* **mesh_shortest**: last computed shortest path using structural mesh as topological shortcut
* **mesh_simplest**: last computed simplest path using structucal mesh as topological shortcut
* **way_simplest**: last computed path on ways using the simplest path in the way's line graph. 
* **paired_edges**: Computed invariants edges between two graphs (structural diff)
 






