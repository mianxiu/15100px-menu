#target photoshop

var oldPrefs = app.preferences.rulerUnits
app.preferences.rulerUnits = Units.POINTS
var doc = activeDocument;
var curLay = doc.activeLayer;
var curLayName = curLay.name
var res = doc.resolution;
var len54 = 54*(72/res);

var path1 = doc.pathItems.getByName(curLay.name + ' Shape Path');
var p1 = path1.subPathItems[0]
var pt1 = p1.pathPoints[0].anchor
var pt2 = p1.pathPoints[1].anchor

alert(p1)

var totalPath = new Array();
var newPath = new Array();

newPath[0] = new PathPointInfo
newPath[0].kind = PointKind.CORNERPOINT;    

newPath[0].anchor = Array(pt1[0],pt1[1]+len54);
newPath[0].rightDirection = Array(pt1[0],pt1[1]+len54);
newPath[0].leftDirection = Array(pt1[0],pt1[1]+len54);

newPath[1] = new PathPointInfo
newPath[1].kind = PointKind.CORNERPOINT;    

newPath[1].anchor = Array(pt1[0],pt1[1]);
newPath[1].rightDirection = Array(pt1[0],pt1[1]);
newPath[1].leftDirection = Array(pt1[0],pt1[1]);

newPath[2] = new PathPointInfo
newPath[2].kind = PointKind.CORNERPOINT;    

newPath[2].anchor = Array(pt2[0],pt2[1]);
newPath[2].rightDirection = Array(pt2[0],pt2[1]);
newPath[2].leftDirection = Array(pt2[0],pt2[1]);

newPath[3] = new PathPointInfo
newPath[3].kind = PointKind.CORNERPOINT;    

newPath[3].anchor = Array(pt2[0],pt2[1]+len54);
newPath[3].rightDirection = Array(pt2[0],pt2[1]+len54);
newPath[3].leftDirection = Array(pt2[0],pt2[1]+len54);

totalPath[0]= new SubPathInfo();
totalPath[0].closed = false;
totalPath[0].operation = ShapeOperation.SHAPEADD


totalPath[0].entireSubPath = newPath;
   
var thePath = doc.pathItems.add('My Path ',totalPath);

convertPathtoShape();
setStroke ();
doc.activeLayer.name = curLayName;
curLay.remove();
thePath.remove();


app.preferences.rulerUnits = oldPrefs

function convertPathtoShape() {
	var d = new ActionDescriptor();
	var d2 = new ActionDescriptor();
	var d3 = new ActionDescriptor();
	var d4 = new ActionDescriptor();
	var r = new ActionReference();
	r.putClass( stringIDToTypeID( "contentLayer" ));
	d.putReference( charIDToTypeID( "null" ), r );
	d4.putDouble( charIDToTypeID( "Rd  " ), 255);
	d4.putDouble( charIDToTypeID( "Grn " ), 255);
	d4.putDouble( charIDToTypeID( "Bl  " ), 255);
	d3.putObject( charIDToTypeID( "Clr " ), charIDToTypeID( "RGBC" ), d4 );
	d2.putObject( charIDToTypeID( "Type" ), stringIDToTypeID( "solidColorLayer" ), d3 );
	d.putObject( charIDToTypeID( "Usng" ), stringIDToTypeID( "contentLayer" ), d2 );
	executeAction( charIDToTypeID( "Mk  " ), d, DialogModes.NO );
}

function setStroke(){
    var idsetd = charIDToTypeID( "setd" );
        var desc3 = new ActionDescriptor();
        var idnull = charIDToTypeID( "null" );
            var ref1 = new ActionReference();
            var idcontentLayer = stringIDToTypeID( "contentLayer" );
            var idOrdn = charIDToTypeID( "Ordn" );
            var idTrgt = charIDToTypeID( "Trgt" );
            ref1.putEnumerated( idcontentLayer, idOrdn, idTrgt );
        desc3.putReference( idnull, ref1 );
        var idT = charIDToTypeID( "T   " );
            var desc4 = new ActionDescriptor();
            var idstrokeStyle = stringIDToTypeID( "strokeStyle" );
                var desc5 = new ActionDescriptor();
                var idstrokeStyleContent = stringIDToTypeID( "strokeStyleContent" );
                    var desc6 = new ActionDescriptor();
                    var idClr = charIDToTypeID( "Clr " );
                        var desc7 = new ActionDescriptor();
                        var idCyn = charIDToTypeID( "Cyn " );
                        desc7.putDouble( idCyn, 74.970000 );
                        var idMgnt = charIDToTypeID( "Mgnt" );
                        desc7.putDouble( idMgnt, 67.920000 );
                        var idYlw = charIDToTypeID( "Ylw " );
                        desc7.putDouble( idYlw, 67.050000 );
                        var idBlck = charIDToTypeID( "Blck" );
                        desc7.putDouble( idBlck, 90.150000 );
                    var idCMYC = charIDToTypeID( "CMYC" );
                    desc6.putObject( idClr, idCMYC, desc7 );
                var idsolidColorLayer = stringIDToTypeID( "solidColorLayer" );
                desc5.putObject( idstrokeStyleContent, idsolidColorLayer, desc6 );
                var idstrokeStyleVersion = stringIDToTypeID( "strokeStyleVersion" );
                desc5.putInteger( idstrokeStyleVersion, 2 );
                var idstrokeEnabled = stringIDToTypeID( "strokeEnabled" );
                desc5.putBoolean( idstrokeEnabled, true );
                var idfillEnabled = stringIDToTypeID( "fillEnabled" );
                desc5.putBoolean( idfillEnabled, false );
            var idstrokeStyle = stringIDToTypeID( "strokeStyle" );
            desc4.putObject( idstrokeStyle, idstrokeStyle, desc5 );
        var idshapeStyle = stringIDToTypeID( "shapeStyle" );
        desc3.putObject( idT, idshapeStyle, desc4 );
    executeAction( idsetd, desc3, DialogModes.NO );

    var idsetd = charIDToTypeID( "setd" );
        var desc9 = new ActionDescriptor();
        var idnull = charIDToTypeID( "null" );
            var ref2 = new ActionReference();
            var idcontentLayer = stringIDToTypeID( "contentLayer" );
            var idOrdn = charIDToTypeID( "Ordn" );
            var idTrgt = charIDToTypeID( "Trgt" );
            ref2.putEnumerated( idcontentLayer, idOrdn, idTrgt );
        desc9.putReference( idnull, ref2 );
        var idT = charIDToTypeID( "T   " );
            var desc10 = new ActionDescriptor();
            var idstrokeStyle = stringIDToTypeID( "strokeStyle" );
                var desc11 = new ActionDescriptor();
                var idstrokeStyleLineWidth = stringIDToTypeID( "strokeStyleLineWidth" );
                var idPxl = charIDToTypeID( "#Pxl" );
                desc11.putUnitDouble( idstrokeStyleLineWidth, idPxl, 7.000000 );
                var idstrokeStyleVersion = stringIDToTypeID( "strokeStyleVersion" );
                desc11.putInteger( idstrokeStyleVersion, 2 );
                var idstrokeEnabled = stringIDToTypeID( "strokeEnabled" );
                desc11.putBoolean( idstrokeEnabled, true );
            var idstrokeStyle = stringIDToTypeID( "strokeStyle" );
            desc10.putObject( idstrokeStyle, idstrokeStyle, desc11 );
        var idshapeStyle = stringIDToTypeID( "shapeStyle" );
        desc9.putObject( idT, idshapeStyle, desc10 );
    executeAction( idsetd, desc9, DialogModes.NO );
}