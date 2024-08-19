import arcpy
import os, sys
import numpy as np
from shapely.geometry import Point, LineString
from shapely import STRtree, snap
import datetime

sys.tracebacklimit = 1000

# Feature Layers
lineLayer = arcpy.GetParameterAsText(0)
pointLayer = arcpy.GetParameterAsText(1)
tolerance = arcpy.GetParameter(2)


# startTime = datetime.datetime.now().replace(microsecond=0)
# arcpy.AddMessage(f'Operation started on {startTime}')
# print(f'Operation started on {startTime}')


pointList = []
pointArrayList = []
with arcpy.da.SearchCursor(pointLayer, ['OID@', 'SHAPE@XY']) as cursor:
    for row in cursor:
        pointList.append(Point(row[1]))
        pointArrayList.append(row[1])

pointTree = STRtree(pointList)
pointArray = np.array(pointArrayList)

lineDict = {}
lineArrayDict = {}
with arcpy.da.SearchCursor(lineLayer, ["OID@", "SHAPE@"]) as cursor:
    for line in cursor:
        lineCoords = []
        for vert in line[1]:
            for coord in vert:
                lineCoords.append((coord.X, coord.Y))
            lineDict[line[0]] = LineString(lineCoords)
            lineArrayDict[line[0]] = np.array(lineCoords)

snapPointDict = {}
for key, line in lineDict.items():
    snapPoints = [pointList[idx] for idx in pointTree.query(line.buffer(tolerance), distance=None)]
    print(snapPoints)
    if snapPoints:
        newLine = line
        for point in snapPoints:
            result = snap(newLine, point, tolerance=tolerance)
            if result != newLine:
                newLine = result
        new_geom = arcpy.FromWKB(newLine.wkb)
        snapPointDict[key] = new_geom


lineDesc = arcpy.Describe(lineLayer)
workspace = os.path.dirname(arcpy.Describe(lineLayer).catalogPath)
desc = arcpy.Describe(workspace)
if hasattr(desc, "datasetType") and desc.datasetType == 'FeatureDataset':
    workspace = os.path.dirname(workspace)
count = 0
try:
    with arcpy.da.Editor(workspace, multiuser_mode=lineDesc.isVersioned):
        with arcpy.da.UpdateCursor(lineLayer, ["OID@", "SHAPE@"]) as cursor:
            for row in cursor:
                if row[0] in snapPointDict:
                    lineCoords = [(pnt.X, pnt.Y) for part in row[1].getPart() for pnt in part]
                    newLineCoords = [(pnt.X, pnt.Y) for part in snapPointDict[row[0]].getPart() for pnt in part]
                    if lineCoords != newLineCoords:
                        arcpy.AddMessage(f'Fixing line: {row[0]}')
                        count += 1
                        cursor.updateRow((row[0], snapPointDict[row[0]]))

    arcpy.management.ApplySymbologyFromLayer(lineLayer, lineLayer, update_symbology="MAINTAIN")
except SystemError:
    print('Edits need to be saved before running tool.')
    raise SystemError('Edits need to be saved before running tool.') from None


# endTime = datetime.datetime.now().replace(microsecond=0)
# dur = endTime - startTime
# dur = str(dur)
# arcpy.AddMessage(f'Fixed {count} lines.')
# arcpy.AddMessage(f'Duration: {dur}')
# print(f'Duration: {dur}')

