# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""HoloViews plus Datashader inputs for a workspace snapshot.

Aegir's lineup draws ``hv.Chord`` through Panel and Bokeh, and rasters
dense layers with Datashader. This module builds the node and edge tables
for that chord. It does not import HoloViews, so the AMP install stays
free of the viz stack. The ``viz`` extra provides holoviews, datashader,
bokeh, panel, and pandas.
"""

from optagent.snapshot import Snapshot


def chord_tables(snapshot: Snapshot) -> dict:
    nodes = [{"index": name, "name": name} for name in snapshot.projects]
    edges = []
    names = snapshot.projects
    for i, source in enumerate(names):
        for target in names[i + 1 :]:
            edges.append({"source": source, "target": target, "value": 1})
    return {
        "library": "holoviews",
        "element": "Chord",
        "raster": "datashader",
        "nodes": nodes,
        "edges": edges,
    }
