from PySide6.QtWidgets import QApplication, QMainWindow, QGraphicsScene
from ui.MainWindow import Ui_MainWindow
from polygon_renderer import PolygonRenderer
from model import LineDrawingMode

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
        self.polygon_item = self.renderer.render()

        # Connecting radio buttons
        self.radioButton_Bresenham.toggled.connect(lambda checked: self._on_radio_toggled(checked, LineDrawingMode.BRESENHAM))
        self.radioButton_QGraphics.toggled.connect(lambda checked: self._on_radio_toggled(checked, LineDrawingMode.QGRAPHICS))
        # By default we draw with QGraphics library algorithm
        self.radioButton_QGraphics.setChecked(True)

    def _on_radio_toggled(self, checked: bool, mode: LineDrawingMode):
        if checked and self.polygon_item:
            self.polygon_item.redraw_with_new_mode(mode)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
