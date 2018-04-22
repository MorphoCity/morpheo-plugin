# -*- encoding=utf-8 -*-
""" Utilities for computing classes
"""
import logging

from .sql import SQL

def compute_classes( cur, table, fid, attribut, classes): 
    """  Compute classes of equal lengths for attribute 'attr'

        :param cur: Database cursor
        :param fid: Feature id
        :param table: Destination table
        :param attribut: Attribut name
        :param classes: Number of classes

        :return: A generator for iterating through pair of fid,classe
    """

    maxlen = cur.execute(SQL('SELECT Sum(LENGTH) FROM {table}',fid=fid,table=table)).fetchone()[0]
    rows   = cur.execute(SQL('SELECT {fid},LENGTH FROM {table} ORDER BY {attr}',
                        fid=fid, attr=attribut, table=table)).fetchall()

    buckl = maxlen/float(classes)
    limit = buckl
    klass = 0
    ltot  = 0
    for fid,l in rows:
        yield fid, klass
        ltot = ltot+l
        if ltot >= limit:
            limit = limit+buckl
            klass = klass+1

     
