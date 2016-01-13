import string

TERMS = {
    'vertices':{
        'fr':('noeuds', "Table des noeuds du graphe (intersections et impasse"), 
        'en':('vertices', "Table of graph's vertices"),
        },
    'edges':{
        'fr':('arcs', "Table des arcs du graphe"),
        'en':('edges', "Table of the graph's edges")
        }
}

LANGUAGE='en'

def tr(sql, additional_terms = None):
    term_map = {}
    if additional_terms:
        term_map = additional_terms
    for term, value in TERMS.iteritems():
        term_map[term] = value[LANGUAGE][0]
    return string.Template(sql).substitute(term_map)

class TrCursor(object):
    """decorator to translate sql templated statements"""
    def __init__(self, cursor, additional_terms = None, debug=False):
        self.__cursor = cursor
        self.__add_term = additional_terms
        self.__debug = debug
    def execute(self, sql):
        if self.__debug:
            print tr(sql, self.__add_term)
        return self.__cursor.execute(tr(sql, self.__add_term))
    def executemany(self, sql, tuples):
        if self.__debug:
            print tr(sql, self.__add_term)
        return self.__cursor.executemany(tr(sql, self.__add_term), tuples)
    def fetchone(self):
        return self.__cursor.fetchone()
    def fetchall(self):
        return self.__cursor.fetchall()
    def rowcount(self):
        return self.rowcount
    def set_debug(self, debug):
        self.__debug = debug

    
