/**
 * 图层类的构造函数，传入一个图层ID
 * @param id
 * @constructor
 */
function Layer(id) {
    this.id = id;
}

// ------- 实例方法 -------
/**
 * 获取当前实例图层的名称
 * @return {string}
 */
Layer.prototype.name = function() {
    var layerReference = new ActionReference();
        layerReference.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("Nm  "));
        layerReference.putIdentifier(charIDToTypeID("Lyr "), this.id);
    var descriptor = executeActionGet(layerReference);
    return descriptor.getString(charIDToTypeID("Nm  "));
}

/**
 * 获取当前实例图层的层级
 * @return {number}
 */
Layer.prototype.index = function () {
    var layerReference = new ActionReference();
        layerReference.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("ItmI"));
        layerReference.putIdentifier(charIDToTypeID("Lyr "), this.id);
    var descriptor = executeActionGet(layerReference);
    return descriptor.getInteger(charIDToTypeID("ItmI"));
}

/**
 * 获取当前实例图层的类型
 * @return {number}
 */
Layer.prototype.kind = function () {
    var layerReference = new ActionReference();
    layerReference.putProperty(charIDToTypeID("Prpr"), stringIDToTypeID("layerKind"));
    layerReference.putIdentifier(charIDToTypeID("Lyr "), this.id);
    var descriptor = executeActionGet(layerReference);
    return descriptor.getInteger(stringIDToTypeID("layerKind"));
}

/**
 * 获取当前实例图层的尺寸
 * @return {{x: number, width: number, y: number, height: number}}
 */
Layer.prototype.bounds = function () {
    var layerReference = new ActionReference();
        layerReference.putProperty(charIDToTypeID("Prpr"), stringIDToTypeID("bounds"));
        layerReference.putIdentifier(charIDToTypeID("Lyr "), this.id);
    var layerDescriptor = executeActionGet(layerReference);
    var rectangle = layerDescriptor.getObjectValue(stringIDToTypeID("bounds"));
    var left = rectangle.getUnitDoubleValue(charIDToTypeID("Left"));
    var top = rectangle.getUnitDoubleValue(charIDToTypeID("Top "));
    var right = rectangle.getUnitDoubleValue(charIDToTypeID("Rght"));
    var bottom = rectangle.getUnitDoubleValue(charIDToTypeID("Btom"));
    return {x: left, y: top, width: (right - left), height: (bottom - top)};
}

/**
 * 判断当前图层的显示/隐藏
 * @return {boolean}
 */
Layer.prototype.visible = function () {
    var layerReference = new ActionReference();
        layerReference.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("Vsbl"));
        layerReference.putIdentifier(charIDToTypeID("Lyr "), this.id);
    var descriptor = executeActionGet(layerReference);
    if(descriptor.hasKey(charIDToTypeID("Vsbl")) == false) return false;
    return descriptor.getBoolean (charIDToTypeID("Vsbl"));
}



/**
 * 高效遍历图层
 * @param callback
 */
Layer.loopLayers = function (callback) {
    var ref = new ActionReference();
        // 当前文档的图层数量属性key
        ref.putProperty(charIDToTypeID("Prpr"), charIDToTypeID('NmbL'));
        ref.putEnumerated( charIDToTypeID('Dcmn'), charIDToTypeID('Ordn'), charIDToTypeID('Trgt') );
    var desc = executeActionGet(ref);    
    var layerCount = desc.getInteger(charIDToTypeID('NmbL'));
    // 索引起始值，会受是否有背景图层影响，需要做一下处理
    var i = 0;
    try {
        activeDocument.backgroundLayer;
    } catch(e) {
        i = 1;
    }
    // 开始逐级遍历图层index，根据index来获取到图层实例
    for (i; i<layerCount; i++) {
        var ref = new ActionReference();
            ref.putIndex( charIDToTypeID( 'Lyr ' ), i );
        var desc = executeActionGet(ref);
        var id = desc.getInteger(stringIDToTypeID( 'layerID' ));
        var layer = new Layer(id);
        $.writeln(layer.name())
        // 将遍历拿到的图层实例传递给回调函数，回调函数就可以根据自己的需要对图层进行操作了
        callback && callback(layer);
    }
}

// 使用方法
Layer.loopLayers(function (layer) {
    if (layer.kind() === 3) {   // 3是文字图层
        // 打印文字图层的内容
        // ...
    }
    
});