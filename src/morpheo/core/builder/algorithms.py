# -*- encoding=utf-8 -*-
""" Graph algorithms
"""

import random
from networkx.algorithms.centrality.betweenness import (_single_source_shortest_path_basic,
                                                        _single_source_dijkstra_path_basic,
                                                        _rescale)

def stress_centrality( G, k=None, normalized=True, weight=None, endpoints=False, seed=None ):
    """ Compute stress centrality 

        We use the same BSF algorithm as for beteweeness centrality 
        used in networkx, but we change the accumulating phase
        in order to get only the number of shortests path

        see algorithm 12 in http://algo.uni-konstanz.de/publications/b-vspbc-08.pdf
    """
    stress = dict.fromkeys(G, 0.0)  # b[v]=0 for v in G
    if k is None:
        nodes = G
    else:
        random.seed(seed)
        nodes = random.sample(G.nodes(), k)
    for s in nodes:
        # single source shortest paths
        if weight is None:  # use BFS
            S, P, sigma = _single_source_shortest_path_basic(G, s)
        else:  # use Dijkstra's algorithm
            S, P, sigma = _single_source_dijkstra_path_basic(G, s, weight)
        # accumulation
        if endpoints:
            stress = _accumulate_stress_endpoints(stress, S, P, sigma, s)
        else:
            stress = _accumulate_stress_basic(stress, S, P, sigma, s)
    # rescaling
    stress = _rescale(stress, len(G),
                      normalized=normalized,
                      directed=G.is_directed(),
                      k=k)
    return stress


# Helpers for stress centrality

def _accumulate_stress_basic(stress, S, P, sigma, s):
    delta = dict.fromkeys(S, 0)
    while S:
        w = S.pop()
        for v in P[w]:
            delta[v] += (1.0+delta[w])
        if w != s:
            stress[w] += sigma[w]*delta[w]
    return stress


def _accumulate_stress_endpoints(stress, S, P, sigma, s):
    stress[s] += len(S) - 1
    delta = dict.fromkeys(S, 0)
    while S:
        w = S.pop()
        for v in P[w]:
            delta[v] += (1.0+delta[w])
        if w != s:
            stress[w] += sigma[w]*delta[w] + 1
    return stress



def multiple_sources_shortest_path_length( G, sources, cutoff=None ):
    """ Compute shortest path length from a set of sources

        The algorithm is the same as the BFS algorithme used in
        networkx.single_source_shortest_path_length except that it takes 
        a several set of source as starting point.

        :param G: Networkx Graph
        :param sources: list of starting nodes
        :param cutoff: optional. Only path of length >= cutoff are
                       returned

        :return: lengths : Dictionary of shorterts path lengths keyed by target
    """
    seen={}                  # level (number of hops) when seen in BFS
    level=0                  # the current level
    nextlevel=dict.fromkeys(sources,1)  # dict of nodes to check at next level
    while nextlevel:
        thislevel=nextlevel  # advance to next level
        nextlevel={}         # and start a new list (fringe)
        for v in thislevel:
            if v not in seen:
                seen[v]=level # set the level of vertex v
                nextlevel.update(G[v]) # add neighbors of v
        if (cutoff is not None and cutoff <= level):  break
        level=level+1
    return seen  # return all path lengths as dictionary



def unweighted_shortest_path( G, source, stop_predicat, cutoff=None ): 
    """ Compute shortest path between source
        and a the set of nodes in targets reachable.

        This as variant of Networkx BFS algorithm implemented in single source shortesst path

        Propagation stop when predicat is met 
   
        :param G: NetworkX graph
        :param source : Node label, Starting node for path

        :return: list of nodes in shortest path

        Notes
        -----
        The shortest path is not necessarily unique. So there can be multiple
    """
    level=0                  # the current level
    nextlevel={source:1}     # list of nodes to check at next level
    paths={source:[source]}  # paths dictionary  (paths to key from source)
    if cutoff==0 or stop_predicat(G,source):
        return paths
    while nextlevel:
        thislevel=nextlevel
        nextlevel={}
        for v in thislevel:
            for w in G[v]:
                if w not in paths:
                    paths[w]=paths[v]+[w]
                    nextlevel[w]=1
                    if stop_predicat(G,w):
                        return paths[w]
        if (cutoff is not None and cutoff <= level):  break
        level=level+1
    raise nx.NetworkxNoPath("No path found from %s" % source)


def dijkstra_path( G, source, stop_predicat, weight='weight'):
    """ Compute shortest path between source
        and a the set of nodes in targets reachable.

        This as variant of Networkx  algorithm implemented in single source shortesst path

        Propagation stop when predicat is met 
   
        :param G: NetworkX graph
        :param source : Node label, Starting node for path

        :return: list of nodes in shortest path

    """
    (length, path) = single_source_dijkstra(G, source, stop_predicat,                                                                                     weight=weight)
    try:
        return path[target]
    except KeyError:
        raise nx.NetworkXNoPath("No reachable nodes from %s" % source)


def single_source_dijkstra_path( G, source, stop_predicat, weight='weight' ):
    """ Compute shortest path between source
        and a the set of nodes in targets reachable.

        This as variant of Networkx  algorithm implemented in single source shortesst path

        Propagation stop when predicat is met 
   
        :param G: NetworkX graph
        :param source : Node label, Starting node for path

        :return: dictionaries
               Returns a tuple of two dictionaries keyed by node.
               The first dictionary stores distance from the source.
               The second stores the path from the source to that node.
    """
    if stop_predicat(G,source):
        return ({source: 0}, {source: [source]})
    push = heappush
    pop = heappop
    dist = {}  # dictionary of final distances
    paths = {source: [source]}  # dictionary of paths
    seen = {source: 0}
    c = count()
    fringe = []  # use heapq with (distance,label) tuples
    push(fringe, (0, next(c), source))
    while fringe:
        (d, _, v) = pop(fringe)
        if v in dist:
            continue  # already searched this node.
        dist[v] = d
        #if v == target:
        #    break
        if stop_predicat(G,v):
            break
       # for ignore,w,edgedata in G.edges_iter(v,data=True):
        # is about 30% slower than the following
        if G.is_multigraph():
            edata = []
            for w, keydata in G[v].items():
                minweight = min((dd.get(weight, 1)
                                 for k, dd in keydata.items()))
                edata.append((w, {weight: minweight}))
        else:
            edata = iter(G[v].items())

        for w, edgedata in edata:
            vw_dist = dist[v] + edgedata.get(weight, 1)
            if cutoff is not None:
                if vw_dist > cutoff:
                    continue
            if w in dist:
                if vw_dist < dist[w]:
                    raise ValueError('Contradictory paths found:',
                                     'negative weights?')
            elif w not in seen or vw_dist < seen[w]:
                seen[w] = vw_dist
                push(fringe, (vw_dist, next(c), w))
                paths[w] = paths[v] + [w]
    return (dist, paths)

