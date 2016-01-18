# -*- coding: utf-8 -*-

"""
***************************************************************************
    Way.py
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

from os import path
from sys import stdout
from time import time, sleep

from Terminology import TrCursor

class Progress(object):
    """To avoid testing if progress is there or not (progress bar and log in qgis)
    this class logs progress in the terminal"""
    def __init__(self, silent=False):
        """Set silent to false if no progress needed"""
        self.__silent = silent
        self.__start = time()
        self.__in_progress = False

    def setPercentage(self, percent):
        """Print percentage, no newline"""
        self.__in_progress = True
        if percent == 0:
            self.__start = time()
        elif percent >= 100:
            stdout.write("\r    100%% (%.2f sec)\n"%(time()-self.__start))
            self.__in_progress = False
            return
        stdout.write("\r    % 3d%%" % (int(percent)))
        stdout.flush()

    def setText(self, text):
        if self.__in_progress:
            stdout.write("\n")
            self.__in_progress = False
        print text

def classify_with_equal_length(tuples, nb_of_classes):
    """Given a list of tuples (ogc_fid, length)
    return a list of nb_of_classes of list of
    ogc_fid that makes classes of ~equal total length according to value.
    Note that no sorting is performed, to classify an attribute the input tuple list
    should be sorted by attribute value."""
    assert nb_of_classes
    if nb_of_classes == 1:
        return [v[0] for v in tuples]
    total_length = sum([v[1] for v in tuples])
    class_length = total_length / nb_of_classes
    result = [[]]
    accum_length = 0
    for e in range(len(tuples)):
        if accum_length >= class_length and len(result) != nb_of_classes:
            accum_length = 0
            result.append([])
        accum_length += tuples[e][1]
        result[-1].append( tuples[e][0] )
    return result

def add_attribute(conn, table, attribute, attribute_type):
    """Add an attribute column if it does not exist, NULL's it if it exists"""
    cur = TrCursor(conn.cursor())
    cur.execute("pragma table_info("+table+")")
    column_names = [name for [cid,name,typ,notnull,dflt_value,pk] in cur.fetchall()]
    if attribute not in column_names:
        cur.execute("ALTER TABLE "+table+" "
            "ADD COLUMN "+attribute+" "+attribute_type)
    else:
        cur.execute("UPDATE "+table+" SET "+attribute+" = NULL")

def add_classification(conn, table, attribute, nb_of_classes, order='ASC'):
    """Add a classification column and fills it, classes of
    approx equal total length."""
    cur = TrCursor(conn.cursor())

    cur.execute("pragma table_info("+table+")")
    column_names = [name for [cid,name,typ,notnull,dflt_value,pk] in cur.fetchall()]
    if "CL_"+attribute not in column_names:
        cur.execute("ALTER TABLE "+table+" "
            "ADD COLUMN CL_"+attribute+" integer")
    else:
        cur.execute("UPDATE "+table+" SET CL_"+attribute+" = NULL")

    cur.execute("SELECT OGC_FID, LENGTH FROM "+table+" ORDER BY "+attribute+" "+order)
    for c, ogc_fid_list in enumerate(\
            classify_with_equal_length(cur.fetchall(), nb_of_classes)):
        cur.execute("UPDATE "+table+" SET CL_"+attribute+" = "+str(c+1)+" "
                "WHERE OGC_FID IN ("+str(ogc_fid_list)[1:-1]+")")
    conn.commit()

def add_att_div(conn, table, attribute, att_prod, att_div):
    """Add a division column and fills it."""
    cur = TrCursor(conn.cursor())

    cur.execute("pragma table_info("+table+")")
    column_names = [name for [cid,name,typ,notnull,dflt_value,pk] in cur.fetchall()]
    if attribute not in column_names:
        cur.execute("ALTER TABLE "+table+" "
            "ADD COLUMN "+attribute+" real")
    else:
        cur.execute("UPDATE "+table+" SET "+attribute+" = NULL")

    cur.execute("UPDATE "+table+" SET "+attribute+" = "+att_prod+" / "+att_div+"")
    conn.commit()

def add_att_dif(conn, table, attribute, att1, att2):
    """Add a difference column and fills it."""
    cur = TrCursor(conn.cursor())

    cur.execute("pragma table_info("+table+")")
    column_names = [name for [cid,name,typ,notnull,dflt_value,pk] in cur.fetchall()]
    if attribute not in column_names:
        cur.execute("ALTER TABLE "+table+" "
            "ADD COLUMN "+attribute+" real")
    else:
        cur.execute("UPDATE "+table+" SET "+attribute+" = NULL")

    cur.execute("UPDATE "+table+" SET "+attribute+" = "+att1+" - "+att2+"")
    conn.commit()


# Testing if module is run as main
if __name__ == "__main__":
    # test Progress
    progress = Progress()
    progress.setText("Testing counter")
    for i in range(101):
        sleep(.001)
        if i == 50:
            progress.setText("Alfway there")
        progress.setPercentage(i)
    progress.setText("Done")

    # test classify_with_equal_length
    test = [(0, 1), (2,3), (1, 2), (3, 4), (4, 5)]
    res = classify_with_equal_length(test, 3)
    ref = [[0, 2, 1],[3, 4],[]]
    for i in range(len(res)):
        assert res[i] == ref[i]


def compute_use(element_connections, element_length, nb_of_classes, progress=Progress()):
    """Given a dict of set that describe connections between
    elements (ways, streets, edges) returns a dict of use indexed
    by elements. A dict of length for each element is also requiered.
    WARNING: the algorithm uses arrays instead of maps, sor the maximum id of
    element is important for memory use. Also note that if all ways don't need to be
    in element_connections (removed unconnected ways) they all need to be in element_length.
    """

    [max_wayid, nb_of_ways] = [max(element_length.keys()), len(element_length)]

    #creation du tableau compteur unique
    voie_use = [0]*(max_wayid + 1)
    #creation du tableau compteur multiple
    voie_useMLT = [0]*(max_wayid + 1)
    #creation du tableau compteur distance
    voie_useLGT = [0]*(max_wayid + 1)
    #compteur des chemin
    nb_chemin = 0;
    #creation du tableau donnant la longueur de chaque voie
    length_voie = [-1]*(max_wayid + 1)
    for key, value in element_length.iteritems():
        length_voie[key] = value

    # si length_voie[v] = -1 ici ça veut dire que la voie n'était pas connexe
    # et a été retirée

    idv1 = 1
    while idv1 < max_wayid + 1:
        progress.setPercentage((100.*idv1)/max_wayid)

        if length_voie[idv1] != -1:
            # la voie idv1 existe dans la table voie, elle est connexe au reste

            #creation / maj du tableau de parent pour compteur unique
            voie_parente = [-1]*(max_wayid + 1)
            idv_fille = None
            idv_parent = None
            voie_parente[idv1] = 0

            #creation / maj du tableau de parent pour compteur multiple
            voie_parenteMLT = [-1]*(max_wayid + 1)
            idv_filleMLT = None
            idv_parentMLT = None
            voie_parenteMLT[idv1] = 0

            #creation / maj du tableau de parent pour compteur avec prise en
            #compte de la longueur
            voie_parenteLGT = [-1]*(max_wayid + 1)
            idv_filleLGT = None
            idv_parentLGT = None
            voie_parenteLGT[idv1] = 0

            dtopo = 0
            nb_voiestraitees = 0
            nb_voiestraitees_test = 0

            #creation / maj du tableau donnant les distances topologiques de
            #toutes les voies par rapport à la voie i
            dtopo_voies = [-1]*(max_wayid + 1)

            #creation / maj du tableau donnant les longueurs d'accès de toutes les
            #voies par rapport à la voie i
            lacces_voies = [0]*(max_wayid + 1)

            #traitement de la voie principale en cours (voie i)
            dtopo_voies[idv1] = dtopo
            nb_voiestraitees = 1

            while nb_voiestraitees != nb_of_ways:
                nb_voiestraitees_test = nb_voiestraitees
                #------------------------------------------voie j
                idv2 = 1
                while idv2 < max_wayid + 1:
                    if length_voie[idv2] != -1:
                        #la voie idv2 existe dans la table voie, elle est connexe au reste

                        #on cherche toutes les voies de l'ordre auquel on se trouve
                        if dtopo_voies[idv2] == dtopo:
                            for idv3 in element_connections[idv2]:
                                if length_voie[idv3] != -1:
                                    #la voie idv3 existe dans la table voie, elle est connexe au reste

                                    #si on est dans le cas d'un premier chemin le plus cout ou d'un
                                    # même chemin double
                                    if dtopo_voies[idv3] == -1 \
                                            or dtopo_voies[idv3] == dtopo_voies[idv2] + 1:

                                        # on stocke le parent (cas multiple)
                                        voie_parenteMLT[idv3] = idv2

                                        # on fait les comptes (cas multiple)
                                        idv_filleMLT = idv3
                                        idv_parentMLT =  voie_parenteMLT[idv_filleMLT]
                                        if idv_parentMLT != idv2:
                                            raise Exception("Probleme de voie parente !")

                                        while voie_parenteMLT[idv_filleMLT] != 0:
                                            voie_useMLT[idv_parentMLT] += 1
                                            idv_filleMLT = idv_parentMLT
                                            idv_parentMLT = voie_parenteMLT[idv_filleMLT]

                                            if idv_parentMLT == -1:
                                                raise Exception("Probleme de voie parente non remplie ! (idv_parentMLT = %d)"%(idv_parentMLT))

                                        #on est dans le cas où on a trouvé un nouveau chemin, on incrémente le compteur
                                        nb_chemin += 1

                                    # = si la voie a deja ete traitee
                                    if dtopo_voies[idv3] != -1:

                                        #on compare les longueurs d'accès
                                        if lacces_voies[idv3] > length_voie[idv2] + lacces_voies[idv2]:
                                            #on a trouvé un chemin plus court en distance !
                                            #(même si équivalent plus grand en distance topologique)
                                            idv_filleLGT = idv3
                                            idv_parentLGT = voie_parenteLGT[idv_filleLGT]

                                            #si ce n'est pas la première fois
                                            if idv_parentLGT != -1:
                                                #il faut enlever l'info dans use ajoutee a tord
                                                #remise a niveau du use
                                                while idv_parentLGT != 0:
                                                    voie_useLGT[idv_parentLGT] -= 1
                                                    idv_filleLGT = idv_parentLGT
                                                    idv_parentLGT = voie_parente[idv_filleLGT]

                                                    if idv_parentLGT == -1:
                                                        raise Exception("REMISE A NIVEAU DU USE : Probleme de voie parente non remplie ! (idv_parentLGT = %d)"%(idv_parentLGT))

                                                #il faut supprimer l'ancien chemin ajoute a tord
                                                #remontee jusqua l'ancetre commun

                                            #il faut stocker le nouveau

                                            # on stocke le parent (cas distance min)
                                            voie_parenteLGT[idv3] = idv2

                                            # on fait les comptes (cas distance min)
                                            idv_filleLGT = idv3
                                            idv_parentLGT =  voie_parenteLGT[idv_filleLGT]

                                            while idv_parentLGT != 0:
                                                voie_useLGT[idv_parentLGT] += 1
                                                idv_filleLGT = idv_parentLGT
                                                idv_parentLGT = voie_parente[idv_filleLGT]

                                                if idv_parentLGT == -1:
                                                    raise Exception("Probleme de voie parente non remplie ! (idv_parentLGT = %d)"%(idv_parentLGT))


                                        #end if nouveau chemin plus court en distance

                                    #end if déjà traitée

                                    # = si la voie n'a pas deja ete traitee
                                    if dtopo_voies[idv3] == -1:
                                        dtopo_voies[idv3] = dtopo +1
                                        lacces_voies[idv3] = length_voie[idv2] + lacces_voies[idv2]
                                        nb_voiestraitees += 1


                                        # on stocke le parent unique
                                        voie_parente[idv3] = idv2

                                        # on fait les comptes unique
                                        idv_fille = idv3
                                        idv_parent =  voie_parente[idv_fille]
                                        if idv_parent != idv2:
                                            raise Exception("Probleme de voie parente !")

                                        while voie_parente[idv_fille] != 0:
                                            voie_use[idv_parent] += 1
                                            idv_fille = idv_parent
                                            idv_parent = voie_parente[idv_fille]

                                            if idv_parent == -1:
                                                raise Exception("Probleme de voie parente non remplie ! (idv_parent = %d)"%(idv_parent))


                                    #end if (voie non traitee)
                                 #end if
                            #end for idv3
                        #end if (on trouve les voies de l'ordre souhaite)
                    #end if
                    idv2 += 1
                #end for idv2 : voie j

                if nb_voiestraitees == nb_voiestraitees_test and nb_voiestraitees != nb_of_ways:
                    raise Exception("Seulement %d voies traitees sur %d pour idv %d"%(nb_voiestraitees, nb_of_ways, idv1))

                dtopo += 1

            #end while (voies a traitees)

        #end if

        idv1 += 1
    #end for idv1

    if not nb_chemin:
        raise Exception("Aucun chemin trouve : Pas de voies !!!!")

    use = {}
    for idv in range(1, max_wayid + 1):
        use_v = voie_use[idv]
        useMLT_v = voie_useMLT[idv]
        useMLT_moy = useMLT_v / (1.0*nb_chemin)
        useLGT_v = voie_useLGT[idv] if voie_useLGT[idv] else voie_use[idv]
        use[idv] = (use_v, useMLT_v, useMLT_moy, useLGT_v)
    return use;

def compute_structurality(element_connections, element_length,
        nb_of_classes, folder=None, prefix='', progress=Progress()):
    """return (topo_radius, struct) pairs in a dict indexed by element id along
    with unconnected elements """
    progress.setText("Compute structurality")

    nb_of_ways = len(element_length)

    adjacencystream = None
    dtopostream = None
    if folder:
        adjacencystream = open(path.join(folder, prefix+'adjacency.txt'), 'w')
        dtopostream = open(path.join(folder, prefix+'dtopo.txt'), 'w')

    deleted_ways = set()
    topo_radius_and_struct = {}

    nb_voies_supprimees = 0
    idv1 = 1
    while idv1 < nb_of_ways+1:
        progress.setPercentage(int((100.*idv1)/nb_of_ways))
        dtopo = 0
        nb_voiestraitees_test = 0
        dtopo_voies = [-1]*(nb_of_ways + 1)
        dtopo_voies[idv1] = dtopo
        nb_voiestraitees = 1
        V_ordreNombre = [1]
        V_ordreLength = [element_length[idv1]]

        while nb_voiestraitees != nb_of_ways:
            nb_voiestraitees_test = nb_voiestraitees
            #TRAITEMENT DE LA LIGrE ORDRE+1 DANS LES VECTEURS
            V_ordreNombre.append(0)
            V_ordreLength.append(0)

            idv2 = 1
            while idv2 < nb_of_ways+1:
                if dtopo_voies[idv2] == dtopo and idv2 in element_connections:
                    for idv3 in element_connections[idv2]:
                        if dtopo_voies[idv3] == -1:
                            dtopo_voies[idv3] = dtopo + 1
                            nb_voiestraitees += 1
                            V_ordreNombre[dtopo+1] += 1
                            V_ordreLength[dtopo+1] += element_length[idv3]
                idv2 +=1

            if nb_voiestraitees == nb_voiestraitees_test:
                nbvoies_connexe = 0
                k = 1
                while k<nb_of_ways+1:
                    if dtopo_voies[k]!=-1:
                        nbvoies_connexe += 1
                    else:
                        nb_voiestraitees += 1
                    k += 1

                #SUPPRESSION DES VOIES NON CONNEXES AU GRAPHE PRINCIPAL
                if nbvoies_connexe < nb_of_ways/4:
                    deleted_ways.add(idv1)
                    nb_voies_supprimees +=1

                break
            if nb_voiestraitees == nb_voiestraitees_test:
                raise Exception("Only "+str(nb_voiestraitees)+"/"+str(nb_of_ways)+" processed way")
            dtopo += 1

        #CALCUL DE L'ACCESSIBILITE
        structuralite_v = sum([l*v for l,v in enumerate(V_ordreLength)])

        #CALCUL DU RAYON TOPO
        rayonTopologique_v = sum([l*v for l,v in enumerate(V_ordreNombre)])

        #CALCUL DE LA CLOSENESS
        closeness_v = 1.0/rayonTopologique_v if rayonTopologique_v else 1.0

        topo_radius_and_struct[idv1] = (rayonTopologique_v, closeness_v, structuralite_v)

        if dtopostream:
            dtopostream.write( ', '.join([str(v) for v in dtopo_voies[1:]]) + '\n')

        if adjacencystream:
            adjacencystream.write( ', '.join([str(v if v <= 1 else 0) for v in dtopo_voies[1:]]) + '\n')

        idv1 += 1

    return [topo_radius_and_struct, deleted_ways]


