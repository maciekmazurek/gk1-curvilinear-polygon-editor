from PySide6.QtWidgets import QApplication, QMainWindow, QGraphicsScene
from ui.MainWindow import Ui_MainWindow
from polygon_renderer import PolygonRenderer

import sys

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        # Setting up scene
        self.scene = QGraphicsScene(self)
        self.graphicsView.setScene(self.scene)
        rect = self.graphicsView.rect()
        self.scene.setSceneRect(0, 0, rect.width(), rect.height())

        # Rendering predefined polygon
        self.renderer = PolygonRenderer(self.scene)
        self.renderer.render()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
