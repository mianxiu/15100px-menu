function doesIdExists( id ){// function to check if the id exists
   var res = true;
   var ref = new ActionReference();
   ref.putIdentifier(charIDToTypeID('Lyr '), id);
    try{var desc = executeActionGet(ref)}catch(err){res = false};
    return res;
}

function multiSelectByIDs(ids) {
  if( ids.constructor != Array ) ids = [ ids ];
    var layers = new Array();
    var id54 = charIDToTypeID( "slct" );
    var desc12 = new ActionDescriptor();
    var id55 = charIDToTypeID( "null" );
    var ref9 = new ActionReference();
    for (var i = 0; i < ids.length; i++) {
       if(doesIdExists(ids[i]) == true){// a check to see if the id stil exists
           layers[i] = charIDToTypeID( "Lyr " );
           ref9.putIdentifier(layers[i], ids[i]);
       }
    }
    desc12.putReference( id55, ref9 );
    var id58 = charIDToTypeID( "MkVs" );
    desc12.putBoolean( id58, false );
    executeAction( id54, desc12, DialogModes.NO );
}


multiSelectByIDs ([6])