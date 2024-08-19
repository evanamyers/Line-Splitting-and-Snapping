import arcpy
import os
import sys
from shapely.geometry import Point, LineString
from shapely import STRtree
from shapely.ops import split
from shapely.geometry import MultiPoint

# sys.tracebacklimit = 0

lineLayer = arcpy.GetParameterAsText(0)
pointLayer = arcpy.GetParameterAsText(1)

try:
    lyrworkspace = arcpy.Describe(lineLayer).catalogPath.split('.sde')[0] + '.sde'
    lyrcp = arcpy.Describe(lyrworkspace).connectionProperties
    if lyrcp.version == 'sde.DEFAULT':
        raise ValueError("The input, Line layer, must be set to versioned data.")
except OSError:
    print('line layer is not sde, dont care about versioning')
    pass

# Get the fields for the line feature
loidField = arcpy.Describe(lineLayer).OIDFieldName
lshapeField = arcpy.Describe(lineLayer).ShapeFieldName
lineFields = sorted([f.name for f in arcpy.ListFields(lineLayer) if f.name not in [loidField] and f.type not in ['Geometry', 'GlobalID']])
for each in lineFields:
    if 'shape' and 'length' in each.lower():
        lineFields.remove(each)
# Sort the fields so the OID and SHAPE are in convienent positions:
lineFields.append("SHAPE@")

pointList = []
pointArrayList = []
poidField = arcpy.Describe(pointLayer).OIDFieldName
with arcpy.da.SearchCursor(pointLayer, [poidField, 'SHAPE@XY']) as cursor:
    for row in cursor:
        pointList.append(Point(row[1]))
        pointArrayList.append(row[1])

pointTree = STRtree(pointList)

lineDict = {}
lineArrayDict = {}
with arcpy.da.SearchCursor(lineLayer, [loidField, "SHAPE@"]) as cursor:
    for line in cursor:
        lineCoords = []
        for vert in line[1]:
            for coord in vert:
                lineCoords.append((coord.X, coord.Y))
            lineDict[line[0]] = LineString(lineCoords)

# Create a Dictionary of all new lines that will be made from the splits
splitLineDict = {}
for key, line in lineDict.items():
    newLineList = []
    newLine = line
    splitPoints = [pointList[idx] for idx in pointTree.query(newLine, predicate='contains')]
    intersection = newLine.intersection(splitPoints)
    splitter = MultiPoint(intersection)
    result = split(newLine, splitter)
    for each in result.geoms:
        newLineList.append(each)

    splitLineDict[key] = newLineList


# Create dictionary of all the attributes for the lines, this is used in the insert cursor
lineFieldsDict = {}
with arcpy.da.SearchCursor(lineLayer, [loidField, lineFields]) as cursor:
    for row in cursor:
        lineFieldsDict[row[0]] = row[1:-1]


# Create a dictionary of lines that will replace the old line with the new lines
replaceLine = {}
linesToAdd = {}
for key, newLines in splitLineDict.items():
    # Populate dictionary for replacing existing line, used in the update cursor:
    replaceLine[key] = arcpy.FromWKT(newLines[0].wkt)
    # Populate dictionary for adding the new geometries left over, used in the insert cursor
    linesToAdd[key] = [arcpy.FromWKT(f.wkt) for f in newLines[1:]]


# Modify the linesToAdd dictionary with existing line attributes:
linesWithAtts = []
for key1, newShape in linesToAdd.items():
    for each in newShape:
        if key1 in lineFieldsDict.keys():
            attvalues = list(lineFieldsDict[key1]) + [each]
            linesWithAtts.append(attvalues)


# Perform the edits
lineDesc = arcpy.Describe(lineLayer)
workspace = os.path.dirname(arcpy.Describe(lineLayer).catalogPath)
desc = arcpy.Describe(workspace)
if hasattr(desc, "datasetType") and desc.datasetType == 'FeatureDataset':
    workspace = os.path.dirname(workspace)
with arcpy.da.Editor(workspace, multiuser_mode=lineDesc.isVersioned):
    # Replace the shape of the existing line
    with arcpy.da.UpdateCursor(lineLayer, [loidField, 'SHAPE@']) as cursor:
        for row in cursor:
            if row[0] in replaceLine.keys():
                # Convert the shapely LineString, the replaceLine.value(), to a geometry object
                if row[1] != replaceLine[row[0]]:
                    row[1] = replaceLine[row[0]]
                    print(f'updating line: {row[0]}')
                    arcpy.AddMessage(f'updating line: {row[0]}')
                    cursor.updateRow(row)
    # Add the new lines
    with arcpy.da.InsertCursor(lineLayer, lineFields) as cursor:
        for each in linesWithAtts:
            print('adding new lines')
            arcpy.AddMessage('adding new lines')
            cursor.insertRow(each)

arcpy.management.ApplySymbologyFromLayer(lineLayer, lineLayer, update_symbology="MAINTAIN")

del lineFields, pointTree, lineDict, lineArrayDict, replaceLine, splitLineDict, lineFieldsDict, linesToAdd, linesWithAtts

