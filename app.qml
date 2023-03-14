import QtQuick 6.2
import QtQuick.Window 6.2

Window {
    width: mainScreen.width
    height: mainScreen.height

    visible: true
    color: "#00000000"
    visibility: Window.Windowed
    flags: Qt.ToolTip | Qt.FramelessWindowHint | Qt.WA_TranslucentBackground
    modality: Qt.WindowModal
    title: "151500-QT"


    Screen01 {
        id: mainScreen
        opacity: 1
        color: "#00ffffff"
    }

}

