import arcpy
from shapely.geometry import Point, LineString
from shapely import STRtree, snap

sys.tracebacklimit = 1000

# Feature Layers
lineLayer = arcpy.GetParameterAsText(0)
pointLayer = arcpy.GetParameterAsText(1)
tolerance = arcpy.GetParameter(2)


def findWorkspace(fc):
    desc = arcpy.Describe(fc)
    fullPath = desc.catalogPath

    if '.sde' in fullPath:
        return fullPath.rsplit('.sde', 1)[0] + '.sde'
    elif '.gdb' in fullPath:
        return fullPath.rsplit('.gdb', 1)[0] + '.gdb'
    elif fullPath.lower().startswith("http"):
        # Hosted feature service or REST URL
        return fullPath  # or return None if you just want to skip these
    else:
        # Default fallback
        return arcpy.env.workspace


pointList = []
with arcpy.da.SearchCursor(pointLayer, ['OID@', 'SHAPE@XY']) as cursor:
    for row in cursor:
        pointList.append(Point(row[1]))

pointTree = STRtree(pointList)

lineDict = {}
with arcpy.da.SearchCursor(lineLayer, ["OID@", "SHAPE@"]) as cursor:
    for line in cursor:
        lineCoords = []
        for vert in line[1]:
            for coord in vert:
                lineCoords.append((coord.X, coord.Y))
            lineDict[line[0]] = LineString(lineCoords)

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

count = 0
try:

    workspace_fc = findWorkspace(lineLayer)
    TableDesc = arcpy.Describe(lineLayer)

    # with arcpy.da.Editor(workspace, multiuser_mode=lineDesc.isVersioned):
    with arcpy.da.Editor(workspace_fc, multiuser_mode=TableDesc.isVersioned):
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

    del pointList, pointTree, lineDict, snapPointDict

except SystemError:
    print('Edits need to be saved before running tool.')
    raise SystemError('Edits need to be saved before running tool.') from None


