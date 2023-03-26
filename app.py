import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QTimer, QObject, Signal

class Backend(QObject):
    update = Signal(str,arguments=['time'])

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("1500px-menu")

          
app = QApplication(sys.argv)
engine = QQmlApplicationEngine()
engine.quit.connect(app.quit)
engine.load('app.qml')
# window = MainWindow()
# window.show()
app.exec()
